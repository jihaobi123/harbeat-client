#!/usr/bin/env bash
# 2026-05 hotfix:
#   1) input-daemon: 数字 6/7/8/9 不再触发 SFX（仅 1-5 触发）
#   2) audio-engine: SAMPLE_FILES 改为 5 个 DJ 加花文件，并生成对应 wav
#
# 在 RK3588 上手动运行：
#   cd ~/code/harbeat-client/cypher-integration/rk3588-edge/deploy
#   bash hotfix-2026-05.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
EDGE_ROOT="$REPO_ROOT/cypher-integration/rk3588-edge"

echo "[1/4] 生成 5 个加花 wav（scratch / air_horn / spinback / siren / whoosh）"
python3 "$EDGE_ROOT/audio-engine/scripts/gen_dj_sfx.py"

echo "[2/4] 备份旧的 06_hat_loop 等无用 sample（若存在）"
SAMPLES_DIR="$HOME/cypher/samples"
mkdir -p "$SAMPLES_DIR/_archive_2026-05"
for f in 01_ha.wav 02_scratch.wav 03_horn.wav 04_drum_loop.wav 05_bass_loop.wav 06_hat_loop.wav; do
    if [[ -f "$SAMPLES_DIR/$f" ]]; then
        mv -v "$SAMPLES_DIR/$f" "$SAMPLES_DIR/_archive_2026-05/"
    fi
done

echo "[3/4] 同步代码（已修改）"
# 假设代码已通过 git pull / scp 同步到这里
ls "$EDGE_ROOT/input-daemon/main.py" "$EDGE_ROOT/audio-engine/engine.py" >/dev/null

echo "[4/4] 重启相关 systemd 服务"
for svc in cypher-audio-engine cypher-input-daemon; do
    if systemctl is-active --quiet "$svc.service"; then
        echo "  restarting $svc.service ..."
        sudo systemctl restart "$svc.service"
    else
        echo "  $svc.service 未启用，跳过"
    fi
done

echo
echo "完成。验证："
echo "  - 按 1-5  → 听到搓碟/气笛/倒带/警报/嗖声"
echo "  - 按 6-9  → 仅 edge-agent 收到 key_event，不应有 SFX 声"
echo "  - journalctl -u cypher-input-daemon -f  实时看输入日志"
