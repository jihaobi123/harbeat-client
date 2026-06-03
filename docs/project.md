# HarBeat 项目交接与真实部署手册

版本日期：2026-06-04  
适用对象：后续开发者、部署运维人员、接手项目的 AI Agent  
覆盖范围：FastAPI 后端、Flutter 手机 App、Jetson 后端部署、RK3588 播放端、DJ Control、风格/能量切歌、现场同步与排障。

> 安全说明：本文档不写入明文密码。SSH、App 登录账号等凭据请从项目交接渠道或负责人处获取。不要把密码、Token、`.env`、`cypher.env` 提交到 Git。

---

## 1. 项目一句话说明

HarBeat 是一个面向街舞练习、cypher、battle warm-up、小型 party 的自动控乐系统。它把“曲库分析、选歌、排序、接歌、预取、混音、现场切歌和舞种解释”拆成三端协作：

```text
手机 App
  - 用户登录、DJ Control UI、选择舞种/能量、确认切歌
  - 直接请求 Jetson 公网 API
  - 直接请求 RK3588 局域网 edge-agent

Jetson / 后端
  - FastAPI API、认证、曲库、音频分析、舞种/能量策略、DJ 计划生成
  - 对外通过 nginx 暴露 http://8.136.120.255

RK3588 / 现场播放盒子
  - edge-agent 接收 App 控制
  - audio-engine 执行播放、xfade、FX
  - sync-worker 从 Jetson 拉取并缓存音频
  - input-daemon 接 USB 九键控制器
```

重要原则：手机正式使用时不依赖电脑转发。电脑只用于开发、安装 APK、ADB 日志和临时测试。

---

## 2. 当前真实部署状态

### 2.1 Jetson / 后端 API

当前运行入口：

```text
公网 API: http://8.136.120.255
Tailscale: jetson / 100.87.142.21
SSH: root@100.87.142.21
systemd: harbeat-api.service
真实运行目录: /home/mark/harbeat
Python venv: /home/mark/venvs/harbeat
```

注意：`/home/mark/harbeat-client` 也存在，但当前 `harbeat-api.service` 的 `WorkingDirectory` 是 `/home/mark/harbeat`。修改后端代码必须部署到 `/home/mark/harbeat` 才会生效。

服务命令：

```bash
ssh root@100.87.142.21
systemctl status harbeat-api --no-pager
journalctl -u harbeat-api -n 120 --no-pager
systemctl restart harbeat-api
```

当前服务形态：

```text
User=mark
WorkingDirectory=/home/mark/harbeat
ExecStart=/home/mark/venvs/harbeat/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
nginx: :80 -> uvicorn :8000
PUBLIC_ASSET_BASE_URL=http://8.136.120.255
```

快速健康检查：

```bash
curl -i http://127.0.0.1:8000/api/health
curl -i http://8.136.120.255/api/auth/me
```

`/api/auth/me` 未登录时返回 `401` 是正常的，说明公网 API 可达。

### 2.2 RK3588 / 现场播放端

当前运行入口：

```text
局域网 IP: 192.168.43.7
hostname: lubancat
SSH: cat@192.168.43.7
运行目录: /home/cat/cypher
Python venv: /home/cat/venvs/edge
edge-agent REST: http://192.168.43.7:9000
sync-worker REST: http://192.168.43.7:9100
```

连接和检查：

```bash
ssh cat@192.168.43.7
hostname -I
systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9100/status
```

常用日志：

```bash
journalctl -u cypher-edge-agent -n 120 --no-pager
journalctl -u cypher-audio-engine -n 120 --no-pager
journalctl -u cypher-sync-worker -n 120 --no-pager
journalctl -u cypher-input-daemon -n 120 --no-pager
```

重启：

```bash
sudo systemctl restart cypher-edge-agent
sudo systemctl restart cypher-audio-engine
sudo systemctl restart cypher-sync-worker
sudo systemctl restart cypher-input-daemon
```

当前 systemd 形态：

```text
cypher-edge-agent:
  WorkingDirectory=/home/cat/cypher/edge-agent
  ExecStart=/home/cat/venvs/edge/bin/python /home/cat/cypher/edge-agent/run.py
  Port=9000

cypher-sync-worker:
  WorkingDirectory=/home/cat/cypher/sync-worker
  ExecStart=/home/cat/venvs/edge/bin/uvicorn main:app --host 0.0.0.0 --port 9100
```

换网络时只要 RK IP 变化，手机 App 里的 RK 地址需要改为新的 `http://<RK_LAN_IP>:9000`。Jetson 公网 API 不需要跟着局域网变化。

### 2.3 手机 / Flutter App

当前开发机工具路径：

```powershell
Flutter: D:\flutter_install\flutter
ADB: C:\Android\platform-tools\adb.exe
```

检查 USB 设备：

```powershell
C:\Android\platform-tools\adb.exe devices
```

构建并安装 debug APK：

```powershell
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat build apk --debug
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

看日志：

```powershell
C:\Android\platform-tools\adb.exe logcat
C:\Android\platform-tools\adb.exe logcat | Select-String -Pattern "flutter|HarBeat|Dio|http|edge|sync"
```

当前 App 默认地址在 `mobile/lib/src/app.dart`：

```text
API URL: http://8.136.120.255
RK URL: http://192.168.43.7:9000
```

如果后续不用电脑调试，不要使用 `adb reverse` 作为正式方案。手机必须能直接访问：

```text
http://8.136.120.255
http://192.168.43.7:9000
```

---

## 3. 本地代码地图

### 3.1 后端 FastAPI

```text
app/main.py                         FastAPI app 入口
app/modules/router.py               汇总模块路由
app/shared/config.py                配置
app/shared/database.py              数据库连接
app/modules/auth/*                  登录、鉴权、JWT
app/modules/library/*               曲库、上传、音频分析、metadata
app/modules/manifest/*              asset manifest
app/modules/assets/*                音频资源访问
app/modules/dj_set/*                DJ set 生成、段落、排序、质量门
app/modules/dj_control/*            DJ Control 实时控制核心
app/tests/*                         后端测试
```

DJ Control 关键文件：

```text
app/modules/dj_control/router.py
  - /api/dj/styles
  - /api/dj/styles/pick
  - /api/dj/live/pool/prepare
  - /api/dj/cut/plan
  - /api/dj/transitions/plan

app/modules/dj_control/schemas.py
  - 请求/响应 schema
  - CutPlanRequest
  - target_dance_style 相关字段

app/modules/dj_control/cut_strategy.py
  - prepare_live_pool(...)
  - plan_target_energy_cut(...)
  - plan_target_style_cut(...)
  - 风格/能量切歌候选、打分、兜底

app/modules/dj_control/dance_style.py
app/modules/dj_control/style_taxonomy.py
app/modules/dj_control/style_reference_profiles.py
  - 舞种识别、标准舞种、参考特征

app/modules/dj_control/transition_strategy.py
app/modules/dj_control/mixer_rules.py
app/modules/dj_control/sequencer.py
  - 转场规划、混音规则、队列排序

app/modules/dj_control/energy_hiphop.py
  - Hip-hop 能量模型
```

### 3.2 Flutter 手机端

```text
mobile/lib/src/app.dart                  App 初始化、默认 API/RK 地址
mobile/lib/src/home_page.dart            首页、登录后入口
mobile/lib/src/api_client.dart           Jetson API client
mobile/lib/src/dj_control_page.dart      DJ Control 主界面和交互
mobile/lib/src/edge_agent_client.dart    RK edge-agent client
mobile/lib/src/sync_worker_client.dart   RK sync-worker client
mobile/lib/src/models.dart               App 数据模型
```

DJ Control 关键移动端逻辑：

```text
mobile/lib/src/api_client.dart
  - djPrepareLivePool(...)
  - djPlanTargetEnergyCut(...)
  - djPlanTargetStyleCut(...)

mobile/lib/src/dj_control_page.dart
  - _prepareLivePoolForOrdered(...)
  - _warmActiveQueueAndReservePool(...)
  - _syncRemainingTracksInBackground(...)
  - _previewTargetStyle(...)
  - _confirmTargetStyleCut(...)
  - _previewTargetEnergy(...)
  - _confirmTargetEnergyCut(...)
  - _backgroundSyncInProgress
```

### 3.3 RK3588 集成代码

```text
cypher-integration/rk3588-edge/edge-agent/*
  - App 控制入口
  - 播放、暂停、切歌、状态、Web/API

cypher-integration/rk3588-edge/audio-engine/*
  - 实际播放、crossfade、transition planner、策略选择

cypher-integration/rk3588-edge/sync-worker/main.py
  - 从 Jetson 下载/缓存音频
  - manifest 和 track sync

cypher-integration/rk3588-edge/input-daemon/main.py
  - USB 九键控制器输入

cypher-integration/rk3588-edge/deploy/*.service
  - RK systemd 服务定义
```

---

## 4. “要改什么就看哪里”速查

| 需求 | 优先修改位置 | 说明 |
|---|---|---|
| 登录、Token、用户态异常 | `app/modules/auth/*`, `mobile/lib/src/api_client.dart` | 先看后端 401/403，再看 App token 保存和请求头 |
| 曲库导入、音频分析 | `app/modules/library/*` | 包括 BPM、能量、舞种 evidence、metadata 适配器 |
| 舞种列表和舞种标准化 | `app/modules/dj_control/style_taxonomy.py`, `dance_style.py` | 增加/重命名舞种要同步后端与 UI |
| 舞种选歌 | `app/modules/dj_control/router.py`, `cut_strategy.py`, `style_reference_profiles.py` | `/api/dj/styles/pick` 和实时风格切歌都依赖舞种分数 |
| 实时风格切歌 | `app/modules/dj_control/cut_strategy.py`, `schemas.py`, `router.py`, `mobile/lib/src/api_client.dart`, `dj_control_page.dart` | intent/strategy 为 `target_dance_style` |
| 实时能量切歌 | `app/modules/dj_control/cut_strategy.py`, `energy_hiphop.py`, `mobile/lib/src/dj_control_page.dart` | 关注 `dance_energy_score` 和候选池 |
| 预加载/备用池/RK 同步 | `prepare_live_pool(...)`, `mobile/lib/src/sync_worker_client.dart`, `cypher-integration/rk3588-edge/sync-worker/main.py` | 关注 `style_reserve_pool`、`sync_priority`、缓存状态 |
| DJ Control UI | `mobile/lib/src/dj_control_page.dart` | 按钮禁用、预览卡片、确认切歌、背景同步提示 |
| RK 播放控制 | `cypher-integration/rk3588-edge/edge-agent/*` | App 到 RK 的控制协议 |
| RK 混音/xfade | `cypher-integration/rk3588-edge/audio-engine/*` | 播放行为、转场、音量包络 |
| APK 地址配置 | `mobile/lib/src/app.dart` | 公网 API 和 RK LAN 地址 |
| 服务部署配置 | Jetson systemd、RK `deploy/*.service` | 改服务启动参数后要重启服务 |

---

## 5. 实时舞种风格切歌链路

目标：DJ Control 播放中，用户点击 Popping / Locking / House 等目标舞种，系统推荐下一首更适合该舞种的歌，用户确认后插入下一首，并让 RK 预取/播放。

当前实现链路：

```text
Flutter DJ Control
  -> api_client.djPlanTargetStyleCut(...)
  -> POST /api/dj/cut/plan
  -> router.py 判断 intent == target_dance_style
  -> cut_strategy.plan_target_style_cut(...)
  -> 返回推荐歌曲、理由、置信度、同步建议
  -> App 用户确认
  -> App 更新队列并通知 RK
```

关键后端代码：

```text
app/modules/dj_control/router.py
  - intent == "target_dance_style"
  - 校验 target_style
  - 调用 plan_target_style_cut(...)

app/modules/dj_control/cut_strategy.py
  - prepare_live_pool(...) 生成 style_reserve_pool/style_pool_status/sync_priority
  - plan_target_style_cut(...) 从主队列、风格备用池、曲库兜底里找候选

app/modules/dj_control/schemas.py
  - CutPlanRequest.strategy 允许 target_dance_style
  - target_style / target_dance_style 字段
```

关键移动端代码：

```text
mobile/lib/src/api_client.dart
  - djPlanTargetStyleCut(...)
  - payload 包含 strategy: target_dance_style 和 intent: target_dance_style

mobile/lib/src/dj_control_page.dart
  - _previewTargetStyle(...)
  - _confirmTargetStyleCut(...)
  - _targetStyleCard(...)
  - _backgroundSyncInProgress 控制首批同步完成前不允许切歌
```

测试文件：

```text
app/tests/test_target_style_cut_strategy.py
app/tests/test_live_pool_prepare.py
```

---

## 6. 部署流程

### 6.1 后端部署到 Jetson

本地修改后先测试：

```powershell
cd D:\work\harbeat-client
python -m pytest app/tests/test_target_style_cut_strategy.py
python -m pytest app/tests/test_target_energy_cut_strategy.py
```

部署到 Jetson 的核心要求：代码必须进入 `/home/mark/harbeat`。

常用思路：

```powershell
# 示例：用 scp/rsync/IDE 同步修改过的 app 文件到 Jetson 的 /home/mark/harbeat
# 同步完成后在 Jetson 上执行：
ssh root@100.87.142.21
cd /home/mark/harbeat
systemctl restart harbeat-api
journalctl -u harbeat-api -n 80 --no-pager
```

如果接口行为没有变化，优先确认：

```bash
systemctl cat harbeat-api
pwd
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
```

### 6.2 RK3588 部署

部署目标目录：`/home/cat/cypher`。

```powershell
# 示例：同步 cypher-integration/rk3588-edge 下改动到 RK 的 /home/cat/cypher
ssh cat@192.168.43.7
cd /home/cat/cypher
sudo systemctl restart cypher-edge-agent
sudo systemctl restart cypher-audio-engine
sudo systemctl restart cypher-sync-worker
sudo systemctl restart cypher-input-daemon
systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
```

只改 sync-worker 时通常只需重启：

```bash
sudo systemctl restart cypher-sync-worker
```

只改播放/xfade 时通常重启：

```bash
sudo systemctl restart cypher-audio-engine cypher-edge-agent
```

### 6.3 手机 App 重新安装

```powershell
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat clean
D:\flutter_install\flutter\bin\flutter.bat pub get
D:\flutter_install\flutter\bin\flutter.bat build apk --debug
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

安装后如仍旧是旧行为：

```powershell
C:\Android\platform-tools\adb.exe shell pm clear com.example.harbeat_mobile
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

包名以实际 Android manifest 为准；如果命令失败，用 `adb shell pm list packages | Select-String harbeat` 查实际包名。

---

## 7. 联调和排障

### 7.1 App 显示“网络请求失败”

先从手机真实网络可达性查，不要先上 `adb reverse`：

```powershell
C:\Android\platform-tools\adb.exe shell curl -i http://8.136.120.255/api/auth/me
C:\Android\platform-tools\adb.exe shell curl -i http://192.168.43.7:9000/health
```

判断：

```text
Jetson /api/auth/me 返回 401：正常，说明 API 可达但未登录。
Jetson 无响应：查公网、nginx、harbeat-api。
RK health 无响应：查手机和 RK 是否同一局域网/热点，RK IP 是否变了，edge-agent 是否 active。
```

再看 App 日志：

```powershell
C:\Android\platform-tools\adb.exe logcat | Select-String -Pattern "flutter|Dio|SocketException|Handshake|401|403|500|edge|sync"
```

### 7.2 换网络后怎么处理

Jetson API 使用公网 `http://8.136.120.255`，一般不用改。

RK 使用局域网 IP，换 WiFi/热点后可能变化：

```bash
ssh cat@192.168.43.7
hostname -I
```

如果 RK IP 变化，需要把手机 App 的 RK URL 改成：

```text
http://<新的 RK IP>:9000
```

如果 App 已经把地址写死在 `mobile/lib/src/app.dart`，需要重新构建安装 APK。后续建议做成 App 设置项或配置页，避免每次换网都重新打包。

### 7.3 风格切歌没有候选

先确认 live pool 是否准备成功：

```text
POST /api/dj/live/pool/prepare
```

重点看响应：

```text
style_reserve_pool
style_pool_status
sync_priority
```

后端排查：

```bash
journalctl -u harbeat-api -n 160 --no-pager
```

代码排查点：

```text
app/modules/dj_control/cut_strategy.py
  - plan_target_style_cut(...)
  - prepare_live_pool(...)
  - 候选是否从主队列、风格备用池、曲库兜底进入

app/modules/library/models.py
  - dance_styles
  - dance_style_scores
  - genre_profile.style_evidence_v1
```

### 7.4 能量切歌没有候选

重点看歌曲是否有可用 `dance_energy_score`、`energy`、`energy_curve`，以及 App 展示逻辑是否只看本地队列而没有把备用池算进去。

代码排查点：

```text
app/modules/dj_control/cut_strategy.py
app/modules/dj_control/energy_hiphop.py
mobile/lib/src/dj_control_page.dart
```

### 7.5 RK 报缺少 original / 409 / 缓存失败

这通常是 RK 本地还没有同步对应音频，或 manifest 的 asset URL 不可达。

检查：

```bash
ssh cat@192.168.43.7
curl http://127.0.0.1:9100/status
journalctl -u cypher-sync-worker -n 160 --no-pager
```

再确认 Jetson asset URL：

```bash
curl -I http://8.136.120.255/api/assets/<asset_id-or-path>
```

代码排查点：

```text
app/modules/manifest/router.py
app/modules/assets/router.py
mobile/lib/src/sync_worker_client.dart
cypher-integration/rk3588-edge/sync-worker/main.py
```

### 7.6 播放、xfade 或现场控制异常

先确认 RK 服务：

```bash
systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
journalctl -u cypher-edge-agent -n 120 --no-pager
journalctl -u cypher-audio-engine -n 120 --no-pager
```

代码排查点：

```text
cypher-integration/rk3588-edge/edge-agent/*
cypher-integration/rk3588-edge/audio-engine/*
mobile/lib/src/edge_agent_client.dart
```

---

## 8. 常用测试命令

后端单测：

```powershell
cd D:\work\harbeat-client
python -m pytest app/tests/test_target_style_cut_strategy.py
python -m pytest app/tests/test_target_energy_cut_strategy.py
python -m pytest app/tests/test_live_pool_prepare.py
```

Flutter 静态检查：

```powershell
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat analyze
```

RK 测试：

```powershell
cd D:\work\harbeat-client
python -m pytest cypher-integration/rk3588-edge/tests
```

真实手机联调最小闭环：

```text
1. 手机能访问 http://8.136.120.255
2. 手机能访问 http://192.168.43.7:9000
3. App 登录成功
4. 进入 DJ Control
5. 准备 live pool
6. 等首批 active queue / reserve pool 同步完成
7. 点击目标舞种预览
8. 确认切歌
9. RK 正常预取和播放
```

---

## 9. 接手时的优先阅读顺序

如果你只有半小时，按这个顺序看：

```text
1. 本文档第 1-5 节，先理解三端职责和 DJ Control 链路
2. mobile/lib/src/dj_control_page.dart，理解用户实际操作
3. mobile/lib/src/api_client.dart，理解 App 发给后端的 payload
4. app/modules/dj_control/router.py，理解 API 分发
5. app/modules/dj_control/cut_strategy.py，理解候选池、打分、兜底
6. mobile/lib/src/sync_worker_client.dart 和 cypher-integration/rk3588-edge/sync-worker/main.py，理解 RK 预取
7. cypher-integration/rk3588-edge/edge-agent 和 audio-engine，理解现场播放
```

如果要继续完善项目，优先建议：

```text
1. 把 RK URL 做成 App 内可编辑配置，避免换网重打包
2. 把 live pool / sync 状态做成更清晰的 UI 状态机
3. 给 target_dance_style 和 target_energy 补更多端到端集成测试
4. 在 Jetson 部署流程中加入自动同步和自动重启脚本，减少手动复制风险
5. 给 RK sync-worker 增加更明确的错误码和 App 侧提示
```
