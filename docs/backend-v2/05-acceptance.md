# 05｜怎么验证后端真的做完了

[返回手册](README.md)。分开记录“本轮已经检查”与“后端开发后必须通过”。不能把文档、单元测试或界面 Mock 当成实际链路验收。

## 一、本轮交付了什么，没交付什么

- 已核对当前仓库分区、Jetson release 指针、旧 API 位置、NAS 索引及数据库表结构；没有迁库、重新部署或跑模型。
- 已实看用户 Android 手机的新 APK 主要页面，包指纹匹配；准备终页明确标注 Mock。没有测试实际播放、配对、Live、手机网络请求。
- 新增只读 `reference/read_delivery.py` 及离线 pytest，能枚举同一版本的基础+人声完整资源。没有新增线上 `/api/v2` 服务。
- 真实 EDM 检查得到8首、112文件、2,826,072,608 bytes；JSON hash/schema/绑定和音频存在/大小通过。本轮真实音频全量 hash 未重算，必须在正式目录启用前补验。
- 质量状态仍是基础 degraded、人声 ready；这是产物状态，不是准确率或播放效果验收。

## 二、开发者今天怎样运行参考程序

在本仓库独立虚拟环境中安装 `jsonschema` 和 `pytest`；不要修改 Jetson GPU 环境。输入根目录要包含 published，不是直接指到 published 自身。

```bash
python docs/backend-v2/reference/read_delivery.py --help
python docs/backend-v2/reference/read_delivery.py --root /mnt/nas/harbeat/preprocess --verify-audio
python -m pytest -q tests/test_backend_handoff_reference.py
```

普通电脑没有 NAS 挂载时，使用经授权的完整离线包解压根目录。旧 EDM ZIP 若没有人声报告，需要人声增补，否则应报错而不是默认人声为空。

当前 Jetson 模型环境的 jsonschema 在 release/vendor；不要看到 ImportError 就升级 torch。确需在现有环境运行只读 reader 时，通过已核对的 vendor 与附加依赖路径设置 PYTHONPATH；开发后端本身使用独立环境和锁文件。

测试样本是临时目录中的合成音频字节，只验证读取逻辑，不评测模型质量。本轮测试包括：14文件完整性、不写输入、固定index不跟随latest、两种音频hash模式、manifest损坏、人声关联错误、缺音轨、路径穿越和越界软链接、文档导航。

本轮结果：新增参考程序测试17项 + 既有仓库整理/模块/引擎位置测试129项，合计 **146 passed**。执行命令如下；这不是全项目或手机联网测试：

```bash
python -m pytest -q tests/test_backend_handoff_reference.py tests/test_reference_catalog.py tests/test_current_modules.py tests/test_repository_layout.py tests/test_analysis_engine_layout.py
```

## 三、后端实现后逐项验收

| 编号 | 做什么 | 必须看到什么 |
|---|---|---|
| D01 | 对EDM运行全量hash校验后导入新测试库，再导入一次 | 8首、80音频和32元数据文件完整；不产生重复run/assets |
| D02 | 在测试包复制件中删一条kick | 导入失败/invalid，不能can_prepare；不改真实NAS |
| D03 | 在复制件改manifest一个字节、替错人声版本 | 指纹/绑定校验失败，不能继续发布目录 |
| D04 | 任务创建后切换测试latest到新run | 原任务仍指原run和原文件hash；新任务可选择新版本 |
| A01 | 无Token、错误Token、手机Token调用设备接口 | 401/403，不返回文件或私密路径 |
| A02 | 用户甲查询乙的设备/任务/文件 | 拒绝且不泄露乙数据；收藏歌曲不自动赋权 |
| A03 | 撤销设备或用户歌曲权限，重试旧文件URL | 后续请求拒绝；旧长效链接不能绕过权限 |
| A04 | 请求绝对路径、../、编码穿越、NAS外软链接 | 拒绝，响应不含/etc或其他文件内容 |
| P01 | 相同Idempotency-Key并发提交20次同一选歌 | 只有1个任务，响应指同一ID |
| P02 | 相同key换歌曲；提交不存在/重复/异风格歌曲 | 409或422；整单拒绝，不悄悄丢曲 |
| P03 | 对当前degraded结果提交accept_degraded=false | 提示质量审核；不清空quality_flags绕过 |
| P04 | 两个领取进程并发claim、同request_id重发 | 同任务单租约，重发返回原领取结果 |
| P05 | 断网超过租期，再报旧lease进度 | 拒绝旧lease；新领取仍固定原资源 |
| P06 | seq重发、倒序、同seq不同内容 | 同内容幂等；冲突/旧序号409；进度不重复累计 |
| P07 | 只报100%或少一个文件就complete | 拒绝prepared；后端按每文件verified计算 |
| P08 | 取消任务后再领取/下载；重启API/Worker | 取消不复活；状态持久化，不依赖内存字典 |
| F01 | GET完整文件、HEAD、首段/后段/尾部Range | 正确200/206/416、Content-Length/Range、ETag、无HEAD正文 |
| F02 | If-Range不匹配、多个Range、下载中断再续传 | 行为符合第02章；最终文件大小与SHA256相同 |
| F03 | 下载最大音轨，监控Jetson和阿里云内存 | 不能按文件大小增长到全量缓冲；手机接口仍可响应 |
| F04 | RK先缓存一首，再提交相同资源 | 真实校验后复用缓存，不重复下载、不重复计字节 |
| F05 | 测试环境模拟NAS不可达/磁盘满 | 明确NAS_UNAVAILABLE/DISK_FULL，不显示prepared |
| W01 | 分析Worker在基础完成、人声前退出再恢复 | 验证已有run并补人声，不盲目重跑全部模型 |
| W02 | 任务取消/超时 | 模型子进程组退出、GPU槽释放、尝试日志保留 |
| W03 | 同输入同配置重复提交、改变模型配置 | 同意图去重；配置变化不覆盖旧run，遵守publisher缓存边界 |

不要在生产NAS上删除/篡改文件演练。用测试复制件和测试数据库，服务撤权等测试也只针对专用测试账号。

## 四、与新手机/RK的联合验收

1. 前端提供有INTERNET权限的新构建，能识别当前服务环境，生产构建关闭Mock回退。
2. 手机显示真实EDM曲目和BPM；个人库、歌单是用户关系，不是NAS全局曲库的另一份文件。
3. 试听至少两首不同歌曲，核对歌名、音频和时间位置一致；播放目标明确是手机还是RK。
4. PREP01选择→返回仍保留草稿；未提交时数据库不产生下载任务。
5. PREP03按服务端检查展示：未知不显示通过；提交时重新验证；质量提示能看见具体标记。
6. RK经手机热点主动连接阿里云，领取指定任务并下载完整资源；不要依赖同一局域网或手机手工转文件。
7. 真实网络断开/重连，任务可恢复；手机进度来自校验回执，不能固定计时变100%。
8. 准备完成只是prepared；开始使用/播放需要RK确认。没有RK回执显示等待/失败，不显示已执行。
9. Pad若纳入，要另验配置版本、文件hash、设备已应用版本；若未纳入，页面明确未支持，不能Mock绿勾。
10. 现场换歌/能量调整不修改个人长期偏好；仅经明确个人设置操作更新preferences。

## 五、交付给项目负责人时必须带的证据

每个编号记录：pass/fail/not_run、Git SHA、手机构建hash、服务release、测试设备、测试时间、输入run/hash、request_id/preparation_id、实际输出和脱敏日志。附成功与失败操作录屏，但不把Token/账号个人信息上传公共仓库。

最小上线前交付：OpenAPI文件、数据库迁移与恢复记录、依赖锁文件、环境变量说明、独立部署/回滚步骤、EDM全量hash结果、热点下载实测、所有阻塞失败已关闭的验收表。

必须先确认的决定：账号/设备授权方式、degraded允许策略、Pad与手机上传范围、歌曲数量限制、Live命令合同、新库与公网路由切换。文档的建议不能代替这些批准；未决不影响只读目录和模拟RK开发，但不能发布无鉴权接口凑通路。
