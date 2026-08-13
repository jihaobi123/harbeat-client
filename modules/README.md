# HarBeat 功能模块

本目录保存从当前 HarBeat 生产代码中提取的 13 个功能模块。它们按产品职责拆分，目的是让开发人员能够单独理解、测试和演进每个模块，再通过适配器逐步接回手机、Jetson 和 RK3588。

## 版本定位

| 版本 | Git 标签 | 用途 | 生产状态 |
|---|---|---|---|
| 基础第一版 | `functional-modules/v0.1.0` | 冻结已验证行为，作为回归和回滚基线 | 未替换生产 |
| 干净边界版 | `functional-modules/v0.2.0` | 分离领域核心与设备、网络、数据库或 UI 适配器 | 未替换生产 |
| 生产最终版 | `functional-modules/v1.0.0` | 通过影子接入和真实三端验收后发布 | 尚未发布 |

统一分支：

- `delivery/functional-module-extraction-20260813`：`v0.1.0` 基础版。
- `delivery/functional-modules-clean-v0.2`：`v0.2.0` 干净边界版。

单模块分支和标签：

- 分支：`module/<module-name>-clean-v0.2`
- 标签：`module/<module-name>/v0.2.0`
- 回滚标签：`module/<module-name>/v0.1.0`

`v0.2.0` 共执行 13 条模块测试命令，146 项测试通过。该结论只表示模块核心与契约测试通过，不表示手机 App、Jetson 服务、RK systemd 已经切换到这些模块。

## 13 个模块

| 模块 | 对应产品功能 | 运行位置 | v0.2 测试 |
|---|---|---|---:|
| `observability-e2e` | 三端日志、调用链追踪和自动验收 | 开发/QA | 9 |
| `device-runtime` | 手机连接 RK、设备身份、重连和播放状态 | 手机 + RK | 22 |
| `library-catalog` | 曲库、歌单、歌曲 ID 和资源清单 | Jetson + 手机 | 12 |
| `audio-preprocess` | 节拍、段落、能量和候选切点离线分析 | Jetson | 10 |
| `stem-separation` | Demucs 人声、鼓、贝斯、其他四轨分离 | Jetson | 9 |
| `sequence-planner` | 自动排歌和整套能量走势 | Jetson | 7 |
| `transition-planner` | 自动接歌、快切、能量/风格切歌的选点和对齐 | Jetson | 7 |
| `transition-renderer` | 生成两首歌之间实际播放的衔接 WAV/meta | Jetson | 6 |
| `asset-sync` | 下载、校验并缓存歌曲和混音包 | RK | 9 |
| `transition-orchestrator` | 串联同步、准备、定时执行和任务状态 | RK | 7 |
| `audio-runtime` | RK 播放、双 deck、到点切换和续播 | RK | 25 |
| `mobile-dj-control` | 快切、能量/风格预览确认及任务恢复 | 手机 | 11 |
| `physical-input` | 实体按键、音效、暂停和音量输入 | RK | 12 |

## 开发入口

1. 阅读 `modules/REGISTRY.md`，确认模块版本、提交和生产接入状态。
2. 阅读模块自己的 `MODULE.yaml`，确认输入、输出、依赖和部署边界。
3. 阅读模块自己的 `README.md`，按其 health check 单独测试。
4. 修改前后均运行统一测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_functional_modules.ps1
```

详细交接说明：

- `docs/functional_modules_v0_2_clean_delivery_20260813.md`
- `docs/functional_modules_v0_1_developer_handover_20260813.md`
- `docs/functional_modules_clean_final_execution_plan_20260813.md`

机器可读清单：

- `modules/BASELINE-v0.1.0.json`
- `modules/BASELINE-v0.2.0.json`

## 获取代码

获取完整 `v0.2.0`：

```powershell
git clone https://github.com/jihaobi123/harbeat-client.git
cd harbeat-client
git checkout functional-modules/v0.2.0
powershell -ExecutionPolicy Bypass -File scripts/test_functional_modules.ps1
```

只开发一个模块，以分轨为例：

```powershell
git clone --branch module/stem-separation-clean-v0.2 `
  https://github.com/jihaobi123/harbeat-client.git harbeat-stem-separation
cd harbeat-stem-separation
git checkout module/stem-separation/v0.2.0
python -m unittest discover modules/stem-separation/tests
```

单模块分支仍属于同一个 monorepo。它提供独立的代码、契约和核心测试，但不是已经封装好的生产微服务镜像。真实 Demucs、数据库、Flutter、HTTP、声卡和 systemd 等外部能力由适配器接入，并需单独验收。

## 强制规则

- 不提交歌曲、stem、渲染 WAV、数据库、模型权重、凭据、设备备份和生产缓存。
- 不因 `modules/` 已有等价实现就删除当前生产文件。
- 不允许缺少版本化契约时静默 fallback。
- 规划、渲染、同步、编排和真实播放必须保持职责分离。
- 每个 clean 模块必须先与 `v0.1.0` 做行为对比，再以 adapter/影子模式接入生产。
- 只有真实手机、Jetson、RK 三端验收及回滚演练通过后，才能声明 `v1.0.0` 可交付。
