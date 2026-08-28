# HarBeat 手机前端负责人开工与协作说明

版本：`v1.1-draft`
收件人：Flutter 手机 App 产品与前端负责人
协作分支：`integration/harbeat-contract-first-v1`

## 1. 你的任务结果

你负责 HarBeat 手机 App。App 是用户业务客户端、RK 配对与控制器、准备同步界面，但不是中央业务真相、音频中转站或现场执行器。

最终 App 必须做到：

- 未连接 RK 时可登录、浏览、搜索、整理个人曲库/歌单、上传、查看分析和播放 Preview；
- 未连接并验证 RK 时不能完整播放、同步设备资源或使用现场控制；
- 同时、清晰地维护中央连接状态和 RK 局域网状态；
- 连接 RK 后根据 capability 动态展示 Pad、固定控制和可用功能；
- 手机只发 Manifest/SyncJob/Operation，不中转歌曲、Stem 和 Render；
- 现场按钮只有收到 RK 权威状态/事件后才显示已执行；
- App、中央或 RK 断线和重启后可恢复，不重复上传、同步或现场操作。

## 2. 你必须理解的两条连接

```text
连接 A：App → 阿里云 HTTPS → Jetson FastAPI
用途：登录、曲库、上传、分析、设备权限、准备、Manifest、会话

连接 B：App ↔ 手机热点内 RK edge-agent
用途：发现、配对、能力、状态、同步进度、现场 Operation、WebSocket
```

中央在线不等于 RK 可控；RK 在线不等于中央在线；RK 连接成功不等于资源 ready；下载 100% 不等于 hash 校验完成。

前端至少维护：

```text
central: online | degraded | offline
rk_lan: disconnected | discovered | pairing | connected | unauthorized
rk_readiness: unknown | not_ready | syncing | cache_ready | live
```

## 3. 当前代码状态

| 路径 | 当前内容 | 判断 |
|---|---|---|
| `mobile/lib/src/api_client.dart` | 中央 API 客户端 | PARTIAL，目标改为 OpenAPI 生成 + adapter |
| `mobile/lib/src/models.dart` | 当前手写 DTO | PARTIAL，需避免与生成模型双真相 |
| `mobile/lib/src/home_page.dart` | 首页骨架 | CURRENT/PARTIAL |
| `mobile/lib/src/library/` | 曲目详情等 | CURRENT/PARTIAL，需接 Track/UserLibrary DTO |
| `mobile/lib/src/import/` | 导入/上传页面 | PARTIAL，需接 UploadSubmission/AnalysisRun |
| `mobile/lib/src/edge_agent_client.dart` | RK edge 客户端 | PARTIAL，需按 rk-control-v1 收敛 |
| `mobile/lib/src/sync_worker_client.dart` | 旧直接 sync-worker 客户端 | CONFLICT，手机目标不能访问 `:9100` |
| `mobile/lib/src/dj_control_page.dart`, `live_deck_page.dart` | 控制/现场页面 | PARTIAL，需基于 Operation/State/Capability |
| `modules/mobile-dj-control` | 抽取模块和测试 | 参考，不是最终协议真相 |

现有页面和交互骨架可以复用，但接口模型、状态恢复和 RK 路由不能根据旧实现继续复制。

## 4. 已冻结的产品规则

1. 手机开启热点，RK 加入热点并通过热点访问互联网。
2. 手机不代理歌曲、Stem、Render 和 Pad 音效下载。
3. 一台 RK 一个 Owner，可临时授权 controller/viewer；一个用户可有多台 RK。
4. Pad 页面当前可展示 8 个槽，但槽位和功能必须由 capability 动态驱动。
5. 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo 是固定控制，不占 Pad。
6. 复杂 EQ、Stem Solo、Filter 和专业 DJ 参数不进入普通 P0 UI。
7. 用户移除个人歌曲时使用“从我的曲库移除”，不能写成“删除音乐文件”。
8. 手机完整歌曲播放不在 P0；手机只允许 Preview，完整音频由 RK 输出。
9. 算法 `needs_review/provisional` 不得显示为确定风格；当前 Style 只允许“可能/相近”。

## 5. 功能可用矩阵

| 功能 | 中央在线、RK未连 | 中央离线、RK未连 | RK已连、中央离线 | RK已连、中央在线 |
|---|---:|---:|---:|---:|
| 登录/刷新 | 是 | 否 | 不影响已建立且有效的短期现场授权 | 是 |
| 浏览公共曲库 | 是 | 缓存只读 | 缓存只读 | 是 |
| 整理曲库/歌单 | 是 | P0 不提交 | P0 不提交中央修改 | 是 |
| 上传 | 是 | 否 | 否 | 是 |
| 查看分析 | 是 | 最后缓存 | 最后缓存 | 是 |
| Preview | 是 | P0 可禁用 | P0 可禁用 | 是 |
| 手机完整播放 | 否 | 否 | 否 | 否 |
| 新资源同步 | 否 | 否 | 只能使用已缓存资源 | 是 |
| 现场控制 | 否 | 否 | 授权和资源有效时是 | 是 |
| 完整音频输出 | 否 | 否 | RK 输出 | RK 输出 |

页面 gating 必须由权限、连接、capability、session 和 cache readiness 共同决定，不能只检查一个 `isConnected`。

## 6. 你的责任与禁止事项

你负责：Flutter 页面、ViewState、中央 API/RK 客户端、token 安全存储、缓存、用户反馈、Mock/fixture 测试和重启恢复。

你不得：

- 直接解析算法完整 artifact 或模型 evidence；
- 手工复制一份与 OpenAPI 不同的中央 DTO；
- 用 API message 文案判断业务错误，必须按稳定 error code；
- 在按钮点击后直接把 UI 改成 executed；
- 让手机访问 RK `sync-worker:9100` 或 audio-engine；
- 把 `track_id/library_item_id/playlist_item_id/asset_id` 混用；
- 把 8 Pad 或实体 keycode 写成长期协议；
- 在日志中记录 access/refresh/RK session token、配对码或签名 URL。

## 7. 推荐前端分层

```text
Generated Central API Models
  → CentralApiClient
  → Auth/Catalog/Library/Upload/Device Repositories
  → Feature Controllers / State
  → Page ViewState

RK Protocol Models
  → DeviceDiscovery/RkApi/RkWebSocket
  → DeviceRepository
  → Prepare/Sync/Live Controllers
  → Page ViewState

Secure/Cache Storage
  → refresh token、账户缓存、恢复上下文、operation/sync IDs
```

生成代码不手工修改；兼容和页面语义在 Repository/Mapper 层处理。中央状态与 RK 状态必须分开存储和展示。

## 8. P0 任务拆解

### MOB-00 工程和合同基线

- 固定 Flutter/Dart/Android/iOS 构建版本；
- 从中央 OpenAPI 生成客户端并锁定 generator 版本；
- 对共享 mobile-api fixtures 做解析测试；
- 配置开发/测试/生产中央 base URL；
- RK 地址由发现结果产生，不硬编码生产 IP；
- build 页面或诊断信息显示 App git SHA、API/RK/Manifest 版本。

### MOB-01 Auth 和账户恢复

- access token 只放内存；refresh token 放 Keychain/Keystore；
- refresh 单飞，同一时间只允许一个请求；
- 401 最多自动 refresh 一次；
- rotation 成功先安全保存新 token，再废弃旧 token；
- logout 清理账户私有缓存和 RK session；
- 403/撤销/账号切换不能继续显示上一用户设备和曲库。

### MOB-02 Catalog、个人曲库、歌单和 Preview

- 公共列表/搜索/详情只使用 Track DTO；
- 个人曲库条目同时保存 `library_item_id + track_id`；
- 删除文案和行为只移除关联；
- 列表支持 loading/empty/error/offline/cached/pagination；
- Preview 使用受控短期 URL或媒体接口，不缓存为完整歌曲；
- `pending_review/rejected/blocked` 仅上传者可见并有正确文案。

### MOB-03 Upload 和 AnalysisRun

- 创建 submission、上传、complete 和分析状态轮询/推送；
- 上传恢复持久化 `submission_id`，重试使用相同幂等语义；
- 分析页面分离 processing、partial、failed 和 publication 状态；
- Core/Stem/Feature/Style 进度只展示后端 DTO，不自行估算成功；
- 低置信 BPM/Key/Style 使用 null/possible/needs_review 文案。

### MOB-04 RK 发现、身份、配对和授权

- mDNS `_harbeat-rk._tcp.local`，二维码/地址作为兜底；
- 发现到 IP 后仍验证 hardware_id 和公钥指纹；
- 完整支持中央 claim/finalize 与 RK local proof；
- 配对码、nonce、proof 不持久化到普通日志；
- Owner/controller/viewer 权限决定页面和操作；
- 设备撤销或 session 过期时安全退出控制。

### MOB-05 Capability 和页面动态能力

- 保存 capability `report_version`；
- Pad 根据 `slot_ids/slot_count` 动态生成；
- 固定控制根据 supported operations 显示/禁用；
- codec/Stem/Render/缓存能力影响准备和同步；
- capability 更新时重新校验当前页面，不继续发送失效操作；
- 未知 capability 字段忽略，未知必需协议版本进入“不兼容”状态。

### MOB-06 Prepare、Manifest 和 Sync

- 编辑 PrepareDraft/歌单/PadPreset；
- freeze 后获得不可变 snapshot/Manifest；
- 只向 RK 下发 Manifest/SyncJob 引用和短期授权；
- 展示 queued/downloading/verifying/cache_ready/failed/canceled；
- 100% 下载后仍等待 RK hash/格式校验；
- App 关闭或断开不能取消已接受任务，除非用户明确发送 cancel operation；
- App 重启用原 `sync_job_id` 向 RK 查询恢复。

### MOB-07 LiveSession 和现场控制

- 开始前同时检查 RK 授权、capability、cache_ready、音频输出和 session；
- 现场操作使用 UUID `operation_id`；
- timeout 后显示“状态未知/正在确认”，使用相同 operation_id 查询/重试；
- 收到 accepted/scheduled 不等于 executed；
- WebSocket state snapshot 使用 sequence 去重，断线重连后先拉完整 snapshot；
- UI 不按跨设备时间戳排序现场事实；
- 实体键操作也从 RK Event/State 反映到页面。

### MOB-08 离线、错误和可观测性

- 中央/RK 两条连接分别重试和展示；
- 401/403/404/409/422/429/5xx/timeout 分状态处理；
- 按 error code 分支，不解析 message；
- 保存 request_id/operation_id/sync_job_id 供用户诊断，但不显示 secret；
- 账号切换、App kill、网络切换、热点重建、WebSocket 重连有测试。

## 9. 你主维护和评审的合同

你主维护：页面/API/字段映射、页面状态文案、App 本地恢复模型。

你必须评审：

- 后端中央 OpenAPI 是否覆盖页面全部状态；
- RK Capability/State/Operation/Event 是否可生成稳定客户端；
- Manifest/Sync 是否能完整显示进度和错误；
- 算法 AnalysisSummary 是否正确隐藏低置信/内部字段。

你不能要求后端或 RK 为单个页面临时新增无版本字段。发现缺字段时走合同变更流程。

## 10. 你需要从其他负责人取得的输入

后端：冻结 OpenAPI、Mock server、错误码、分页/ETag/If-Match、token 生命周期、Preview、设备权限和 build version。

算法：AnalysisSummary 可展示字段、null/degraded/possible/confirmed 条件和阶段进度语义。不要直接索取完整 model evidence 给普通页面。

RK：mDNS/identity、配对、capability、operation/state/event、WebSocket 重连、sync 状态、错误码和 simulator。

## 11. 第一批提交顺序

1. OpenAPI 生成客户端和共享 fixture 测试；
2. 双连接状态模型和 Auth；
3. Catalog/Library/Upload/Analysis 页面；
4. RK discovery/pairing/capability；
5. Prepare/Manifest/Sync；
6. LiveSession/Operation/WS 恢复；
7. 真机网络切换、断网和重启验收。

可以在后端/RK实现完成前用共享 Mock/simulator 开发，但禁止维护私有 Mock 字段。

## 12. 完成标准

- 中央客户端从冻结 OpenAPI 可重复生成；
- 页面不依赖原始 JSON和 message 文案；
- 双连接、权限、capability、资源状态 gating 正确；
- 未连接 RK 不进入完整播放/同步/现场功能；
- 操作不乐观伪造 executed，超时可恢复查询；
- App 重启、账号切换、token rotation、热点/WS 重连不会重复操作或泄露账户数据；
- 所有 loading/empty/error/offline/partial/needs_review 状态有测试；
- 与后端 Mock、RK simulator、真实 RK 和 Jetson 完成验收。

## 13. 开工回执

请首先回复：当前页面清单、仍在直接调用的旧 RK 路径、中央 API 字段缺口、你计划采用的状态管理和 OpenAPI generator，以及第一批需要后端/RK提供的 fixtures。
