# 07 前端页面与 API 字段映射

状态：`v1.0-draft`
主负责人：前端
必须评审：后端、产品

## 1. 前端必须维护的三种连接状态

App 不能只用“有网/没网”判断功能。运行时至少组合以下状态：

```text
central: online | degraded | offline
rk_lan: disconnected | discovered | pairing | connected | unauthorized
rk_readiness: unknown | not_ready | syncing | cache_ready | live
```

用户是否能点击现场功能由服务端权限、RK 局域网连接和 RK 实际 capability 共同决定。阿里云/Jetson online 不代表手机连接了 RK；Jetson 的 `device.online` 也只是最近心跳镜像，不能替代局域网探测。

## 2. 功能可用矩阵

| 功能 | 中央在线、RK 未连接 | 中央离线、RK 未连接 | RK 已连接但中央离线 | RK 已连接且中央在线 |
|---|---:|---:|---:|---:|
| 登录/刷新登录 | ✅ | ❌，可保留已登录只读壳 | 不影响已建立局域网控制，但不能新登录 | ✅ |
| 浏览公开曲库 | ✅ | 已缓存只读 | 已缓存只读 | ✅ |
| 整理个人曲库/歌单 | ✅ | P0 不提交修改；可只读缓存 | P0 不提交中央修改 | ✅ |
| 上传音乐 | ✅ | ❌ | ❌ | ✅ |
| 查看分析进度 | ✅ | 最后缓存状态 | 最后缓存状态 | ✅ |
| 手机播放完整歌曲 | ❌ | ❌ | ❌ | ❌ |
| 手机试听 Preview | ✅ | 仅已缓存且未过策略的 preview；P0 可直接禁用 | 同左 | ✅ |
| 创建/编辑准备草稿 | ✅ | 可本地草稿为 P1；P0 只读 | 可编辑 RK 当前临时态但不自动冒充中央草稿 | ✅ |
| 同步资源到 RK | ❌ | ❌ | 只能使用 RK 已缓存资产 | ✅ |
| 现场控制 | ❌ | ❌ | ✅，使用 RK 本地现有资源和有效授权缓存 | ✅ |
| 完整歌曲输出 | ❌ | ❌ | ✅，由 RK 音频输出 | ✅，由 RK 音频输出 |

“手机完整播放”不在 P0。手机未连接 RK 时只允许受控试听，不返回原曲 URL。现场完整播放始终是 App 发控制意图、RK 执行。

## 3. 页面/API/字段映射

### 3.1 启动、登录与个人资料

| 页面/动作 | 中央 API | 读取字段 | 写入字段/规则 |
|---|---|---|---|
| 启动恢复会话 | `POST /auth/refresh`、`GET /me` | `expires_in,user,status,version` | Refresh token 每次轮换；新 token 落安全存储后再丢旧 token |
| 注册 | `POST /auth/register` | `AuthTokens` | email/password/display_name/client_id |
| 登录 | `POST /auth/login` | `AuthTokens` | 不记录密码；401 与 429 区分提示 |
| 退出 | `POST /auth/logout` | 204 | 无论网络结果都清本机 access；若中央离线需标记待撤销/提示 |
| 我的资料 | `GET/PATCH /me` | avatar_url/display_name/email/version | PATCH 必带 `If-Match`; 409 拉新值再让用户确认 |

客户端 Token 规则：access token 只放内存，refresh token 放 Keychain/Keystore；收到 refresh 重放/401 时清会话，不无限循环刷新。

### 3.2 首页、发现、搜索与曲目详情

| UI 元素 | API/字段 | 展示规则 |
|---|---|---|
| 首页推荐卡 | `GET /recommendations` → `impression_id,track,reason_codes` | 记录曝光；reason code 本地化，不显示内部分数 |
| 最新/公开曲库 | `GET /catalog/tracks?sort=newest` | 只会返回 published；cursor 分页，不用页码猜测 |
| 搜索 | `GET /catalog/tracks?q=` | 输入 debounce 300–500ms；新搜索取消旧请求 |
| 曲名/艺人/封面 | `TrackSummary.title,artist_name,cover_url` | null 有占位图/未知艺人文案 |
| BPM/Key/Energy | `track.analysis.*` | pending/running 显示分析中；低质量/空值不显示伪默认值 |
| 风格 | `style_labels[].certainty` | `possible` 显示“可能：…”；不能当确定标签 |
| 加入曲库 | `PUT /me/library/{track_id}` | 使用 Idempotency-Key；响应更新 `in_my_library` |
| 删除个人曲库 | `DELETE /me/library/{track_id}` | 文案“从我的曲库移除”；不能写“删除音乐文件” |
| 试听 | `POST /catalog/tracks/{id}/preview` | URL 短期有效；到期重新获取；绝不拼接 storage path |

点击推荐卡、试听、加入或跳过后，用 `impression_id` 调 `POST /recommendation-feedback`。失败可有限重试，不能阻塞主界面。

### 3.3 我的曲库和上传

| 页面状态 | API 字段 | UI 行为 |
|---|---|---|
| 曲库正常条目 | `LibraryItem.track` | 公开曲和本人待审曲都可出现 |
| 本人上传处理中 | `publication_status=processing` 或 analysis pending/running | 展示阶段与进度；禁用设备同步 |
| 待审核 | `pending_review` | 本人可见“等待公开审核”；其他用户不可见 |
| 被拒绝 | `rejected + rejection` | 展示安全理由和后续动作；不能展示内部 traceback |
| 被封禁 | `blocked` | 停止 preview/同步；按错误码提示 |
| 上传 | `POST /uploads` → `PUT content` → `POST complete` | 三步各自持久化 submission_id；中断可查询状态 |
| 分析详情 | `GET /analysis-runs/{id}` | 2 秒起轮询，最大 10 秒；终态停止 |

上传 UI 必须展示：文件名、大小、上传进度、服务端校验、各分析阶段、审核状态。上传进度是 HTTP 字节进度；算法进度是 AnalysisRun，不能混成同一个百分比。

### 3.4 歌单

| 动作 | API | 并发规则 |
|---|---|---|
| 列表/详情 | `GET /playlists`、`GET /playlists/{id}` | 缓存 ETag/version |
| 创建 | `POST /playlists` | Idempotency-Key |
| 改名/描述 | `PATCH /playlists/{id}` | `If-Match: "version"` |
| 加曲 | `POST /playlists/{id}/items` | 发送 `track_id,after_item_id`，不自己算 position |
| 移曲 | `DELETE /playlists/{id}/items/{item_id}` | 只删除歌单项，不删除个人/公共曲目 |
| 删除歌单 | `DELETE /playlists/{id}` | 二次确认；曲目不受影响 |

出现 409 version conflict 时：保留用户尚未提交的意图，拉取服务端最新 PlaylistDetail，能自动重放的简单 add/remove 可生成新 Idempotency-Key 重放；排序冲突让用户确认。

### 3.5 设备列表、发现和配对

中央与局域网分别读取：

- `GET /devices`：账号拥有/获授权的设备；
- 局域网 mDNS/发现：当前手机真正可连接的 RK；
- `GET http://<rk>:9000/api/v1/capabilities`：当前 RK 能力；
- `GET/WS http://<rk>:9000/...`：RK 当前状态。

页面合并键是中央 `device_id`；未配对设备先用 `device_hardware_id` 显示“发现的新设备”。不能用 IP 当设备 ID。

配对流程：

1. 发现 RK，TLS/局域网签名校验其 `hardware_id + nonce`；
2. 用户读取 RK 显示的配对码；
3. App 调中央 `POST /device-pairings/claim`；
4. App 在局域网要求 RK 确认，获得一次性 `device_proof`；
5. App 调中央 `POST /device-pairings/{claim_id}/finalize`；
6. App 再向 RK 下发中央确认结果并获取局域网 session token；
7. 失败/超时清除一次性 secret，不能复用配对码。

### 3.6 PadPreset

前端从 `capabilities.pad.slot_count` 动态生成槽位；现有产品稿的 8 个 Pad 可以作为当前视觉默认，但不能写进 API 模型或数组长度常量。

| UI | 字段 | 校验 |
|---|---|---|
| Pad 卡片 | `slot_id,label,color,position` | slot_id 稳定，拖动只改 position |
| 音效 | `sound_asset_id` | 必须是用户有权引用的 ready pad_sound asset |
| 模式 | `mode` | 必须在 RK `supported_modes` 中 |
| 音量 | `gain_db` | 同时满足合同范围和 RK 能力 |
| 量化 | `quantize_mode` | 不支持则 UI 禁用而不是静默忽略 |
| 固定控制 | `fixed_controls` | 播放/下一首/Talk/Undo 等单独渲染，不占 Pad slot |

发布预设产生不可变 version。编辑已发布预设应复制成新草稿版本。

### 3.7 准备、Manifest 和同步

1. App 用 `/prepare-drafts` 保存中央草稿；
2. 用户选择当前局域网 RK 后，读取 capability；
3. `POST /prepare-drafts/{id}/freeze` 生成不可变快照/Manifest；
4. `POST /devices/{id}/sync-jobs` 创建中央镜像；
5. App 调 RK `POST /api/v1/sync-jobs` 下发 `sync_job_id + manifest_id/URL + token`；
6. App 用 RK WebSocket 监听实际进度；中央 `GET /sync-jobs/{id}` 只用于跨端/恢复镜像；
7. 只有 RK 声明 `cache_ready` 且 required assets 无缺失，App 才启用“开始现场”。

同步 UI 至少区分 `downloading`、`verifying`、`ready`、`failed`；不能在下载到 100% 时提前显示 ready。

### 3.8 现场控制

现场页的数据和命令全部走 RK 08 协议：

- 初始状态：连接 WebSocket 后先收 `state.snapshot`；
- 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo、Pad：发送 operation；
- UI 先显示“已发送/等待确认”，收到 `operation.accepted` 后才显示排程，收到 `operation.executed` 才显示已执行；
- 若请求超时，显示“状态未知，正在同步”，拉快照；不得自动重复可能已执行的操作；
- 实体键事件也通过同一状态流回传，App 无需知道 Linux keycode；
- 中央不可达时，只要 RK 授权缓存仍有效、资源 ready，现场功能继续。

## 4. 前端领域 DTO

前端不直接让页面依赖 OpenAPI 原始 JSON。建议分三层：

```text
Generated API Models -> Repository/Mapper -> Page ViewState
RK Protocol Models   -> DeviceRepository  -> Live ViewState
Local Cache Models   -> Repository        -> Offline Read-only ViewState
```

重要字段不得混用：

- `track.id`、`library_item.id`、`playlist_item.id` 是三个不同 ID；
- `device.online`（中央最近心跳）与 `rk_lan=connected` 不同；
- `analysis.status` 与 `publication_status` 不同；分析成功不代表已公开；
- `sync_job.status` 中央镜像与 RK 当前 `rk_sequence` 不同时，以局域网 RK 新序列为准；
- `operation_id` 是一次控制意图的全链路 ID；按钮连点不能复用不同 payload。

## 5. 加载、空、错和降级状态

每个页面在联调前必须有以下设计，不允许只画成功态：

| 状态 | 必需行为 |
|---|---|
| 首次加载 | 骨架/进度，可取消请求 |
| 空数据 | 区分“没有内容”和“筛选无结果” |
| 401 | 单次 refresh；失败回登录 |
| 403 | 功能/对象级权限提示，不循环请求 |
| 404 | 对象删除或权限隐藏，退回列表 |
| 409 | 版本/幂等冲突，按 10 恢复 |
| 422 | 字段级错误映射；未知字段错误展示通用提示 + request_id |
| 429/503 | 根据 Retry-After 退避，保留当前界面 |
| 中央断网 | 展示缓存时间；禁用会写中央的动作 |
| RK 断开 | 立即禁用现场动作，保留最后状态并明确“非实时” |
| WS 断开 | 指数退避重连；重连后先 GET/收 snapshot，再处理增量 |

## 6. 缓存和隐私

- App 本地只缓存曲目摘要、歌单/草稿可恢复副本和 preview 策略允许的数据；P0 不缓存完整歌曲、Stem 或 Render；
- 不把 access/refresh token、配对码、device proof 写普通数据库/日志/崩溃上报；
- 图片/试听 URL 过期后通过 asset/preview grant 刷新，不永久缓存带签名 URL；
- 用户退出后删除账户私有缓存和 RK session token；公共摘要可按产品策略保留；
- 请求日志只记录 request_id/operation_id，不记录 Authorization 和完整媒体 URL query。

## 7. 前后端字段冻结流程

每个后端接口进入开发前需完成：

1. 产品确认页面状态与用户文案；
2. 后端在 06 补齐 schema、枚举、错误码、示例；
3. 前端确认每个页面字段是否齐全，并提交“页面 → 字段”映射；
4. 前后端共同生成/更新客户端和 Mock；
5. 算法评审所有面向用户的分析字段，明确 validated/provisional 展示；
6. RK 评审所有设备/同步/现场字段，提供 capability 和事件 fixture；
7. 合同测试通过后才允许一方单独实现，后续破坏性变更升级版本。

## 8. 前端交付物

- 由 06 生成的 API client，生成代码不手工改；
- CentralRepository、DeviceRepository 与 token refresh 单飞机制；
- 页面/API/字段自动或人工覆盖矩阵；
- 成功、空、加载、错误、中央离线、RK 断开、低 capability 的 UI 截图/测试；
- OpenAPI Mock 场景和 RK WebSocket fixture 回放；
- `operation_id/Idempotency-Key` 生成、持久和恢复测试；
- 安全存储、退出清理和日志脱敏测试；
- 与 12 中验收用例对应的端到端自动化结果。

## 9. 当前代码接入提醒

当前 `mobile/` 已有部分直接请求 RK `:9100` 和 `/live/intent`、`/live/override` 的实现，但 RK edge-agent 当前路由并不完整一致。目标是只访问 edge-agent `:9000`（HTTP）和 `:9001`（WS），由 edge-agent 内部访问 loopback sync-worker。前端不应为了兼容当前 mock 同时维护两套长期协议。
