# 在线混音：现有代码与执行边界

“在线”需要区分网页提交任务、计划生成和真正的音频时钟执行。当前 V3 与 Hip-Hop 试听页播放的是预先渲染的文件；打开网页不会实时运行 V3。

| 层 | 现有源码 | 责任 |
| --- | --- | --- |
| 接歌准备 API | `analysis_platform/dj_routes.py` | 从两份报告生成并保存不可变计划 |
| 会话控制 | `app/modules/session/coordinator.py`、`queue_manager.py`、`state_machine.py` | 当前歌曲、队列、切歌指令和会话状态 |
| 转场策略 | `app/modules/playlists/transition_planner.py`、`stem_automix.py` | 选择转场、分轨策略和自动化曲线 |
| 音频执行 | `cypher-integration/rk3588-edge/audio-engine/` | 双 deck、混音计划、DSP、音频输出和 socket 控制 |
| 设备接入 | `cypher-integration/rk3588-edge/edge-agent/` | 把外部请求传给执行端 |

启动音频执行端参见 [audio-engine README](../cypher-integration/rk3588-edge/audio-engine/README.md)。这是硬件服务，有声卡、缓存、系统依赖。不得在分析服务的 Python 环境里直接安装所有播放依赖。

## 本次保存了什么

保留上述现有源码，以及工作区里的会话自动化构建辅助函数。代码存在不代表这条路径已经接入所有按钮：本次没有把 `_build_transition_command` 或 V3 替换接入所有在线调用点，也没有验证 RK 设备当前部署版本与本仓库一致。

V3 原始渲染函数已冻结在 `mixing/vendor/colleague_demo_v1`。把它迁移到在线播放时，仍需要独立实现并验收前奏变速/正文恢复、滤波与增益曲线、预加载、采样时钟调度和计划/实际偏差记录，不能直接把 FFmpeg 离线命令当成实时播放器。

## 共用合同

预处理只发布带来源的分析。计划负责选点和自动化。执行端只执行已冻结计划，并记录计划 ID、音频哈希、计划时间、执行时间及错误。报告保留每层依据；没有人声数据不能写成无人声，未确认的段落不能写成已校准。

本次是源码整理与验证，没有改线上服务、音频引擎或既有 V3 的声音。
