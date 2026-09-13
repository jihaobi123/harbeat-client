# HarBeat 第二版后端负责人交接与实施顺序

日期：2026-09-13。状态：**已有代码盘点 + 新连接层实施草案**，不是已经运行的 V2 OpenAPI。
下文新表、新接口和状态机是待实现建议；本文不会自动增加路由或迁移线上数据库。

## 1. 你负责什么

负责 Jetson 上的业务后端、数据库、预处理任务管理，以及手机选歌后供 RK 下载资源的服务端接口。
复用现有分析算法；不重写 BPM、SongFormer、Demucs、MDX23C、Silero。
手机前端由前端同事负责。RK 客户端下载器、实时混音/播放、戒指/手环由用户负责。
你提供模拟 RK 客户端验证服务，不接管硬件实现。

新 APK 是前端单独交付的产物，不在仓库是正常现状；不需要兼容旧手机 API。
仓库里的旧 `mobile/` 只能参考，不作为新前端页面或字段的事实来源。

系统第二版包括整个系统。现有预处理与部分数据库已经是可复用基础，而非“只有手机升级”。
先克隆 [第二版入口](../../HARBEAT_V2_START_HERE.md) 指定分支，再读 [数据消费合同](preprocess-consumer.md)。

## 2. 已有部分与真正缺口

| 部分 | 已有代码 | 当前结论 |
|---|---|---|
| 单曲/曲库分析 | `scripts/run_same_style_preprocess.py`、`import_same_style_library.py`、`deploy/jetson/` | 已有统一 NAS 发布；直接复用 |
| 五类重点结果 | `analysis.py`、`stem_analysis.py`、`music_analysis/drum_analysis/`、`vocal_activity.py` | 已部署产生数据，精度/降级限制仍需保留 |
| 用户、曲库、歌单 | `app/modules/auth/`、`library/models.py`、`playlists/` | 已有，不是空白；先对账再迁移 |
| 原业务分析调度 | `app/modules/library/background_tasks.py` | 旧进程内工作链；不能当作持久任务队列 |
| 原 Manifest / assets | `app/modules/manifest/`、`assets/` | 旧 DB 输出，未完成新 NAS 的权限/版本适配 |
| 网关 | `deploy/cloud_gateway/app/main.py` | 有代理样例，但缓冲完整响应；大音轨流式/Range/HEAD 尚须验收 |
| 手机选歌 → 指定 RK 资源同步 | 尚无本文完整闭环 | 需要目录映射、设备权限、版本冻结、任务与进度接口 |

不用把所有算法移到新目录后才开始开发。建议新增独立业务模块处理连接层，依赖现有发布合同而不是算法内部数组。

## 3. 数据存储和职责

- NAS `/mnt/nas/harbeat/preprocess`：音频、不可变基础 run、Manifest、成功标记、人声报告；Worker 可写，下载服务只读。
- 数据库：用户/歌单/设备关系、曲库目录投影、选歌准备任务、重试/租约/进度、审计。
- Jetson：业务真相库及 Worker；阿里云：HTTPS 公网入口/受控转发，不建立另一个独立曲库真相库。
- RK：主动通过手机热点连接公网入口领取任务；不能设计成 Jetson 主动访问热点内部 RK IP。
- 手机：提交选择及查看进度；App 不承担音轨下载转发。

文件已发布与数据库投影成功不是一回事：允许重复扫描索引修复投影，不能因数据库失败覆盖已发布 run。
不要把 NAS 账号、SSH 私钥、模型权重或整个根目录暴露给手机/RK。

## 4. 数据库：在已有基础上增加映射（拟议）

先导出当前 schema、备份并在测试库恢复，核对已有用户/歌单/歌曲主键和外键。
已有 `LibrarySong.id` 与 NAS 的 `track_id` 不能直接视为同一 ID，更不能用歌名匹配。
下面是逻辑实体，落库前确认现有表能否复用，避免建第二套同义表。

| 实体 | 最少字段 / 约束 |
|---|---|
| track_catalog | `track_id`、源 SHA256、标题、风格标签；源标识去重，不以标题唯一 |
| track_publications | `track_id`、`analysis_run_id`、manifest key/hash、状态、质量标记；版本联合唯一、不可变 |
| vocal_publications | 基础 run/hash、report key/hash、status；只关联完全匹配版本 |
| library_track_links | 已有用户曲库行 ID → track_id；显式授权归属，保留旧关系 |
| devices / user_device_links | 不透明 device_id、设备凭据摘要、归属/授权、撤销时间、last_seen |
| preparation_jobs | job_id、user_id、device_id、幂等键、请求内容 hash、状态、创建/更新时间 |
| preparation_job_items | 固定曲目顺序、track_id、run_id、manifest hash、人声 report hash、资产集合 |
| transfer_progress | job/item/asset、RK 回报字节数、校验状态、错误、递增事件序号 |
| preprocessing_jobs | 输入引用、阶段、attempt、lease_until、worker_id、错误；持久化而非仅线程内状态 |

迁移使用可审查的版本脚本：新增表/可空列 → 幂等回填 → 对账 → 切换读路径。
本轮不要删旧表列、批量重写 LibrarySong 或用 `create_all` 代替迁移。

## 5. 接口草案：先交付 OpenAPI 和 Mock，再实现

下面 `/api/v2` 是新业务接口建议命名，不代表现有服务器已有这些路由，也不改变 NAS schema 版本。
新 API 统一 UTF-8 JSON、UTC 时间戳、音频时间整数毫秒、资源大小字节、ID 字符串。

| 请求 | 调用方 | 目的 |
|---|---|---|
| `GET /api/v2/tracks?style=EDM&cursor=...` | 手机 | 分页曲库，只返回用户有权看见的歌曲及可用性 |
| `GET /api/v2/tracks/{track_id}` | 手机 | 显示分析阶段/质量、可用版本；不返回 NAS 密码或绝对路径 |
| `GET /api/v2/devices` | 手机 | 返回此用户可控制设备，不暴露全部设备 |
| `POST /api/v2/preparations` | 手机 | 提交有序 track_ids + device_id，创建准备任务 |
| `GET /api/v2/preparations/{job_id}` | 手机 | 查看真实准备/下载/校验状态 |
| `GET /api/v2/device/jobs?after=...` | RK | 用设备身份主动领取本设备任务，可先短轮询 |
| `GET /api/v2/device/jobs/{job_id}/resources` | RK | 固定版本下载清单、hash、大小、获准的短期 URL |
| `POST /api/v2/device/jobs/{job_id}/progress` | RK | 上报下载/校验状态与事件序号 |
| `GET /api/v2/assets/{asset_id}` 和 `HEAD` | RK | 经授权流式传输指定对象，支持单 Range |

选歌请求示例（示例 ID，不可直接调用）：

```json
{"device_id":"rk_demo","track_ids":["track_a","track_b"]}
```

请求附 `Idempotency-Key`。同一用户、同键、同请求返回同任务；同键不同请求返回 409。
设备不归该用户或曲目无权限必须拒绝；缺少必要资源返回明确原因，不自动对整库重跑模型。
响应建议 `202 {"job_id":"job_demo","status":"queued"}`。

下载清单外壳示例（节选，待双方冻结）：

```json
{
  "schema_name":"harbeat_transfer_manifest",
  "schema_version":"1.0.0",
  "job_id":"job_demo",
  "device_id":"rk_demo",
  "items":[{
    "track_id":"track_a",
    "analysis_run_id":"run_a",
    "manifest_sha256":"<64个十六进制字符>",
    "resources":[{
      "asset_id":"asset_demo",
      "role":"stems.vocals",
      "sha256":"<64个十六进制字符>",
      "size_bytes":123456,
      "content_type":"audio/wav",
      "download_url":"https://gateway.example/api/v2/assets/asset_demo",
      "expires_at":"2026-09-13T12:00:00Z"
    }]
  }]
}
```

实际清单必须包含基础 Manifest、成功标记、master、四轨、五个鼓轨、匹配的人声报告及成功标记。
允许缺失哪些资产由 RK 的消费能力合同决定；在尚未协商前，本次完整资源测试缺任何必要资产就不标为就绪。
role 区分基础 JSON 与音频。内部保留 storage_key→asset_id 映射；客户端不得提交任意路径。
临时 URL 过期只刷新 URL，不修改固定版本、hash 和资产集合。

错误统一建议 `{"error":{"code":"...","message":"...","request_id":"..."}}`。
至少定义：未登录 401、无权限 403、不可见/不存在 404、幂等冲突/版本冲突 409、参数错误 422、资源未齐的业务错误码。
不要把文件读失败返回 200 或伪造空分析结果。

## 6. 状态与版本：最容易出错的地方

建议服务器任务状态：`queued → preparing → available → transferring → verified`；另有 `failed/cancelled`。
`available` 只表示服务端准备好；`verified` 由 RK 完成资产校验后上报。
可播放与播放中是 RK 引擎状态，另存字段，不能从下载 100% 推算。

- 创建任务固定每首 track/run/Manifest SHA 和人声绑定；中途不再次解析 latest。
- 下载进度是 RK 报告值；同一事件序号幂等处理、旧序号忽略，终态不能被迟到事件倒退。
- 校验失败重新取该资产，网络中断保留任务与已验证缓存；恢复不是创建重复任务。
- 凭据撤销/设备解绑立即停止后续授权，已发临时 URL 的有效期应短并明示风险。
- 按 job/device/object 同时鉴权，不能只校验“持有任意 token”。

## 7. Worker 与部署建议

第一版连接层建议复用已有 PostgreSQL，新增持久任务表 + 独立 systemd Worker，避免同时引入多种队列框架。
领取任务用事务/行锁与租约；Worker 周期续约、限制重试、记录失败阶段；进程重启后只回收过期租约。
GPU 重任务初期串行；Silero 使用现有独立并发配置。具体限额用 Jetson 实测决定。
Web 进程只提交任务/查状态，不把几分钟的 GPU 推理挂在 HTTP 请求或普通 BackgroundTasks 中。

部署分离：API、预处理 Worker、索引投影任务；API/下载进程 NAS 只读，Worker 使用限定写权限。
保持 NVIDIA torch 环境，不因装普通依赖覆盖 Jetson CUDA 版本。
先在测试环境验收阿里云→Jetson 的流式下载，再放行真实资产：

- 大文件不整块读入网关内存；透传 Range / Content-Range / Content-Length / Content-Type。
- GET 完整 200；有效单范围 206；无效范围 416；HEAD 不返回文件体。
- 不透明转码，hash 对原发布字节；客户端断线关闭上游连接。
- 日志记录 request_id/job_id，不记录 Authorization 或临时链接中的密钥。
- 保留当前发布版本和数据库备份；线上切换、旧表删除、网关端口/权限变化先提交变更方案给负责人确认。

## 8. 按这个顺序交付，不要一口气改完

1. **目录只读适配**：用 EDM 8 首索引建立查询投影；核对全部资源存在/hash/质量状态，不需要跑模型。
2. **合同评审**：提交 V2 OpenAPI、传输 Schema、示例 fixtures（完整/缺轨/无权限/版本不匹配）。手机与 RK 负责人确认后冻结第一版。
3. **设备与权限**：实现用户授权、设备凭据/撤销及对象访问测试。设备首次配对流程需与用户确认，不能内置公共设备密钥。
4. **准备任务**：实现幂等选歌、固定版本、设备领取、进度持久化。
5. **资产通道**：实现 Range/HEAD、短期授权、断点恢复；模拟 RK 下载全部 EDM 资源并校验 hash。
6. **Worker/迁移/监控**：复用预处理入口，补持久队列、租约重试、数据库迁移和部署回滚说明。
7. **手机和真 RK 联调**：手机选两首 EDM → RK 收到同一任务 → 完整下载/校验 → 手机看到实际进度。真实混音由 RK 负责人验收。

每一步提交代码、测试命令与真实输出；Mock 通过不能写成实机通过。
推荐后端新增模块按 catalog / preparations / device_delivery 分离，名称可在实现 PR 中调整；原算法路径暂不迁移。

## 9. 最小验收清单

- 未登录/跨用户/跨设备请求失败；任意路径、`../` 和越界 symlink 不能读到 NAS 外文件。
- EDM 8 首全部发布对象可读取并验证；任务中途发布新版本，原任务仍下载旧的固定版本。
- Silero 报告 run 或 vocals hash 不一致时拒绝混用；无人声成功与推理失败显示不同。
- 手机重复提交不重复建任务；服务重启、网断、URL 过期后可恢复，不重复下载已验证文件。
- 错误大小/hash、缺轨、degraded 状态清楚呈现；下载完成不会自动宣称引擎已播放。
- 迁移可在现有数据副本上重复验证；不会丢已有用户、歌单、标注或 NAS 发布历史。

前端待办：本次外部 APK 静态核验未声明 INTERNET 权限，前端需修复并重新构建后联调。
安装包上传及源码接入可独立处理，当前文档不声称 APK 已上传；不因此阻止后端合同设计。
仍需负责人确认的是设备配对/授权交互、RK 必需资产能力、新混音控制接口、线上切换；这些不阻止先完成目录只读适配和 Mock。
