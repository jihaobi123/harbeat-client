# Flow Wear Validation and Alpha Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用可重复脚本和明确证据完成桌面稳定性、佩戴测试、续航、隐私日志、安装与回滚，并产出可交给现场人员的 Alpha 发布包。

**Architecture:** 自动测试负责产生机器可读 JSON，人工现场测试只补充主观项目和设备信息；报告由脚本汇总，不能手填成功数字。版本、合同版本、固件 SHA 和 Gateway 包 SHA 必须在设备状态与发布清单中一致。

**Tech Stack:** Python 3.12、pytest、journalctl、systemd、esptool.py、SHA-256、GitHub Actions/Releases

---

### Task 1: 稳定性测试事件生成器

**Files:**
- Create: `tools/stability/run_gateway_stability.py`
- Create: `tools/stability/analyze_events.py`
- Test: `tests/tools/test_stability_analyzer.py`

- [ ] **Step 1: 写分析器失败测试**

输入合成 JSONL，验证能识别：重复 engine 执行、Command 无终态、accepted 超过 500 ms、完成超过 20 秒、session/revision 倒退、Gateway/Engine 重启、日志中出现 MAC/密钥模式。

- [ ] **Step 2: 实现固定 2 小时场景**

脚本默认 2 小时，每 90 秒发送一条合法 Command，能量与风格交替；每 10 条插入一次重复 command_id；第 20/40/60 条分别重启 Gateway、Engine、关闭再开启蓝牙。仅测试管理员可运行，默认只连接 Fake Wrist/Test API，不绕过正式授权。

输出固定为：

```text
artifacts/stability/<UTC>/events.jsonl
artifacts/stability/<UTC>/summary.json
artifacts/stability/<UTC>/journal-gateway.log
artifacts/stability/<UTC>/journal-engine.log
```

- [ ] **Step 3: 冻结通过条件**

零进程崩溃、零 watchdog、零重复执行、零无终态；accepted p95 ≤500 ms 且 max ≤750 ms；成功命令 10–20 秒完成，`no_candidate` 等预期拒绝不计成功；重启后 30 秒内恢复 ready。

### Task 2: 续航记录与计算

**Files:**
- Create: `tools/power/analyze_battery_log.py`
- Create: `docs/test-protocols/BATTERY-4H.md`
- Test: `tests/tools/test_battery_analyzer.py`

- [ ] **Step 1: 写计算测试**

验证乱序、重复时间、缺失样本、百分比回升、测试中充电会使结果失败。只接受 UTC 时间、每 30–90 秒一个样本。

- [ ] **Step 2: 定义真实使用负载**

满充后拔线，屏幕默认灭；每 5 分钟唤醒并浏览 Energy/Style，每 10 分钟提交一次 Command；BLE 全程连接；手势关闭。持续至少 4 小时，期间不充电、不复位。

- [ ] **Step 3: 冻结通过条件**

4 小时末设备仍可唤醒、连接和提交，剩余电量 ≥5%，零 brownout/重启。报告同时给出起止电压、百分比和估算平均每小时下降，不用线性外推代替真实 4 小时。

### Task 3: 30 分钟佩戴/舞动测试

**Files:**
- Create: `docs/test-protocols/WEAR-DANCE-30M.md`
- Create: `docs/test-results/GATE-4-STABILITY.md`

- [ ] **Step 1: 固定动作序列**

5 分钟自然走动、10 分钟中强度舞动、5 分钟快速手臂动作、5 分钟出汗后触控、5 分钟站立操作。每 2 分钟唤醒一次，Energy/Style 交替操作；合计至少 15 个成功 Command。

- [ ] **Step 2: 固定记录项**

记录误唤醒、误提交、漏触、错误页面、断连、皮肤不适、表带松脱、屏幕可读性。V0.1 手势关闭，因此身体动作绝不能直接更改能量/风格。

- [ ] **Step 3: 通过条件**

零误提交、零崩溃、零不可恢复卡页；15 条命令每条只有一次 engine 执行；断连若发生须 30 秒内自动恢复；连续三次触控失败或任何硬件松脱均判失败。

### Task 4: 7 天日志留存与隐私检查

**Files:**
- Create: `hub-gateway/packaging/systemd/journald-flow-wear.conf`
- Create: `tools/privacy/audit_logs.py`
- Test: `tests/tools/test_log_privacy.py`

- [ ] **Step 1: 写敏感字段测试**

拒绝日志中的完整 BLE MAC、Bluetooth key、邮箱、手机号、access token、歌曲文件路径和歌曲名。允许：设备资产 ID、session/request/command ID、能量、风格、BPM、phase、错误码、耗时和资源水位。

- [ ] **Step 2: 配置留存**

Gateway 与 Engine 使用独立 syslog identifier；journald 最大 100 MiB、最长 7 天。导出脚本默认再次脱敏。`/var/lib/bluetooth` 永远不进入报告包。

- [ ] **Step 3: 验证**

```bash
python3 tools/privacy/audit_logs.py artifacts/stability/<UTC>
journalctl --disk-usage
```

### Task 5: 可复现发布包

**Files:**
- Create: `tools/release/build_alpha.sh`
- Create: `tools/release/verify_manifest.py`
- Create: `release/manifest.schema.json`
- Test: `tests/tools/test_release_manifest.py`

- [ ] **Step 1: 写 manifest 测试**

manifest 必须含：`release_id`、`created_at`、wear/client 40 位 SHA、ESP-IDF/LVGL/BSP/Gateway 版本、BLE/Engine 合同版本、每个文件的 SHA-256、最低硬件型号。任何 dirty worktree 或占位符使构建失败。

- [ ] **Step 2: 构建 artifacts**

```text
dist/flow-wear-v0.1.0-alpha.1/
  wrist/bootloader.bin
  wrist/partition-table.bin
  wrist/flow-wrist.bin
  wrist/flash_args.json
  gateway/flow_wear_gateway-0.1.0a1-py3-none-any.whl
  gateway/systemd/
  contracts/
  manifest.json
  SHA256SUMS
  INSTALL.md
  ROLLBACK.md
```

脚本从 clean checkout 构建，不复制本地旧 build 目录。固件用 `idf.py merge-bin` 额外生成 `flow-wrist-full.bin` 供简单恢复烧录。

- [ ] **Step 3: 双重校验**

在 Mac 验证 manifest/SHA；把目录复制到 RK3588 后再验证一次。验证失败不得安装。

### Task 6: 安装、升级和回滚演练

**Files:**
- Create: `docs/runbooks/INSTALL-ALPHA.md`
- Create: `docs/runbooks/ROLLBACK-ALPHA.md`
- Create: `docs/test-results/GATE-5-ALPHA.md`

- [ ] **Step 1: Gateway 原子安装**

wheel 安装到版本目录 `/opt/flow-wear/releases/gateway-v0.1.0-alpha.1/venv`；`/opt/flow-wear/current` 是 symlink。先停止 Gateway、切换 symlink、daemon-reload、启动并运行 `flow-wearctl health`。不要覆盖旧版本目录。

- [ ] **Step 2: Wrist USB 安装**

记录唯一串口和芯片 MAC 的哈希后 8 位作为设备 ID，先读取 flash SHA，再按 `flash_args.json` 烧录。烧录后确认屏幕版本、BLE device ID、主页、Energy/Style 二级页。

- [ ] **Step 3: 回滚演练**

Gateway symlink 切回上一版本并重启；Wrist 使用上一版 `flow-wrist-full.bin` USB 烧录。回滚后完成一次 Fake/real state 查询，不要求向前版本的未完成 Command 自动续传。

- [ ] **Step 4: 发布前 Smoke Test**

依次验证：Wrist 重启、Hub 重启、主页可离线浏览、Finding Hub 可返回、连接后 state 对账、能量切换、风格切换、busy 阻止第二条、completed 解锁、旧 RK 客户端正常。

### Task 7: CI、Tag 和 Alpha 放行

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/release-alpha.yml`
- Create: `docs/release-notes/v0.1.0-alpha.1.md`

- [ ] **Step 1: CI Matrix**

PR 必跑合同、Gateway Python、Wrist host、两套 ESP-IDF build、release manifest tests。audio-engine 位于另一仓库，其指定 SHA 的 CI 链接必须写入 Gate 5 报告。

- [ ] **Step 2: 放行检查**

只有 Gate 0–5 报告齐全且不存在 `FAIL`/占位符时才允许 tag。发布工作流只打包已有 commit，不自动修改版本文件。

- [ ] **Step 3: 创建签名 tag 与 Release**

```bash
git tag -s wrist-v0.1.0-alpha.1 -m "Flow Wrist v0.1.0 alpha.1"
git tag -s gateway-v0.1.0-alpha.1 -m "Flow Wear Gateway v0.1.0 alpha.1"
git push origin main --follow-tags
```

若本机没有可用签名 key，不降级为无签名 tag；记录阻塞并先保留已验证的 `dist/`。

- [ ] **Step 4: 最终完成定义**

必须同时满足：2 小时桌面、30 分钟佩戴、4 小时续航通过；7 天隐私策略已配置并通过样例审计；安装与回滚各演练一次；两种真实切换均完成；无重复执行、崩溃和误提交。任何一项失败都保留为 Alpha 候选，不对现场放行。
