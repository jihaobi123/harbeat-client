# 03｜数据库：要保存哪些东西，怎样避免写乱

[返回手册](README.md)。以下是第二版**待实现**表设计，不是当前 Jetson 已有表。表和字段采用 snake_case。

## 一、先不要动旧库

建议第二版使用独立数据库 `harbeat_v2`、独立运行账号、独立迁移账号；与旧 `rhythm_prism` 同在 Jetson 的 PostgreSQL 上也可以，但新服务没有旧库写权限。最终隔离和账号迁移方案需项目负责人批准。本轮没有建库、建表或改权限。

为什么要分开：当前旧库与本地 ORM 有字段差异，新手机也不要求兼容旧 API。直接在旧库上试验，容易误改现有服务和数据。

新表保存编号、关系、任务和校验结果。NAS 保存大音轨和不可变分析 JSON。不要把音频转成 base64 写入 PostgreSQL，不把每个请求都变成全盘扫描。

## 二、第一阶段需要的表

PK 是主键，代表这一行的唯一编号；FK 是外键，保证指向的记录确实存在；UNIQUE 是数据库层禁止重复，不是只靠 Python if 判断。

除特别说明外，ID 用 UUID（对外 string）；NAS track_id/run_id 用 text 原样保存；hash 用 char(64)；字节数用 bigint；时间用 timestamptz；JSON用 jsonb。created_at/updated_at 由服务器生成。status/state 用 text + CHECK 枚举约束，便于显式迁移。

### 1. 用户与授权

| 表 | 最小字段与约束 | 作用 |
|---|---|---|
| users | user_id PK，display_name text，status(active/disabled)，created_at | 新后端用户主体，不默认迁移旧密码 |
| credentials | credential_id PK，user_id FK 或 device_id FK（二者恰好一个），token_digest UNIQUE，expires_at，revoked_at nullable，scope text[] | 测试阶段可撤销 Bearer 凭据；只存高熵随机 token 的 digest，不存原文。正式登录另外扩展 |
| user_track_grants | user_id FK，track_id FK，can_read bool，created_at；PK(user_id,track_id) | 谁可以看/下载哪些歌曲；曲库索引不是权限表 |
| devices | device_id PK，name，status(active/revoked)，last_seen_at nullable，boot_id nullable，heartbeat_seq bigint，available_bytes bigint nullable，capabilities jsonb | RK 注册主体和最后报告；available_bytes未知不能写0当满盘 |
| user_device_grants | user_id FK，device_id FK，can_prepare bool；PK(user_id,device_id) | 用户是否能把歌交给这台设备；知道 ID 不等于获授权 |

手机账号 Token 不能调用设备领取接口；设备 Token 不能查所有用户。管理员授权要有审计记录。测试 Token 的生成/交付经项目负责人私下完成，不硬编码到 APK、仓库或日志中。

### 2. 曲库与不可变文件

| 表 | 最小字段与约束 | 作用 |
|---|---|---|
| tracks | track_id text PK，input_sha256，title/artist nullable，duration_ms positive bigint，style_labels jsonb，current_run_id nullable，created_at/updated_at | 对手机可查询的曲库目录；元数据源自已校验 manifest |
| analysis_runs | track_id FK，analysis_run_id text，manifest_storage_key UNIQUE，manifest_sha256，schema_version，pipeline_git_sha，status，quality jsonb，analysis_summary jsonb，integrity_state(checking/verified/invalid)，verified_at；PK(track_id,analysis_run_id) | 某个基础发布版本；同 run 不更新成不同 hash |
| vocal_reports | report_id PK，track_id+analysis_run_id 复合 FK，revision text，storage_key UNIQUE，sha256，manifest_sha256，vocal_sha256，status，quality jsonb；UNIQUE(track_id,analysis_run_id,revision) | 独立人声版本；不覆盖基础 manifest |
| assets | asset_id PK，storage_key UNIQUE，sha256，size_bytes positive bigint，content_type，role，track_id+analysis_run_id FK，vocal_report_id nullable FK，audio_metadata jsonb nullable，integrity_state，verified_at | 包括音频、manifest、两种完成标记和人声 JSON；所有文件统一登记 |

tracks 的 current_run 必须复合引用同 track 的 analysis_runs，不能指到另一首。可先插 tracks（current_run为空），再插 run/files，校验后设置当前指针。

新 run 导入流程是新增，不覆盖旧 run。如果某个 storage_key 已登记但 hash/size 变化，标 integrity invalid 并报警，不悄悄 UPDATE 为新字节。既有任务依赖旧版本，后台垃圾清理必须保留被任务引用的资源。本期不做自动删 NAS。

### 3. 选歌任务与进度

| 表 | 最小字段与约束 | 作用 |
|---|---|---|
| preparations | preparation_id PK，user_id FK，device_id FK，style_label，accept_degraded bool，quality_policy_version，state，attempt int，resource_set_sha256，resource_core_bytes bytea，created_at/updated_at/expires_at，error_code/message nullable | 一次固定资源任务；存准确冻结字节，JSONB用于查询但不直接代替 hash 原文 |
| preparation_tracks | preparation_id FK，position int，track_id+analysis_run_id FK，manifest_sha256，vocal_report_id FK；PK(preparation_id,position)，UNIQUE(preparation_id,track_id) | 用户选择顺序和每首版本；不要只存一个可变 playlist_id |
| preparation_files | preparation_id FK，asset_id FK，sha256，size_bytes，role；PK(preparation_id,asset_id) | 冻结本任务允许读取的每个文件；下载权限从此表查 |
| device_leases | lease_id PK，preparation_id FK，device_id FK，attempt int，claim_request_id，expires_at，revoked_at nullable；UNIQUE(device_id,claim_request_id) | 领取与续租。每个任务最多一个未撤销租约，由锁行事务维护 |
| file_progress | preparation_id FK，attempt int，asset_id FK，state，downloaded_bytes bigint，observed_sha256 nullable，error_code nullable，updated_at；PK(preparation_id,attempt,asset_id) | 每文件一次最新状态，不重复叠加下载量；复合 FK 指向 preparation_files |
| progress_requests | lease_id FK，seq bigint，body_sha256，accepted_response jsonb；PK(lease_id,seq) | 网络重发回执，避免重试重复计数和乱序 |
| idempotency_keys | principal_type，principal_id，method_path，key，request_sha256，response_status，response_body jsonb，created_at/expires_at；UNIQUE(principal_type,principal_id,method_path,key) | 创建和重试接口幂等；建议保留至少7天且不短于活动任务生命期 |
| audit_events | event_id PK，actor_type/id，action，target_type/id，request_id，metadata jsonb，created_at | 记录谁提交、取消、授权、失败和重试；不记 Token 原文 |

这些表看起来多，是把“是谁、什么文件、哪次下载、下载到了哪里”分开；可以分批实现，不能用一个内存全局 dict 替代持久化。

## 三、每次操作应该写哪些表

| 操作 | 一个数据库事务内做什么 | 不能做什么 |
|---|---|---|
| 已发布索引入库 | upsert track；insert固定run/report/assets；全部校验完成后设verified/current | 事务里重跑模型或长时间hash整个曲库 |
| 创建准备任务 | 占用幂等key；检查权限/版本；insert preparation/tracks/files；写冻结hash、审计、幂等响应 | 先返回任务ID，再异步猜测资源版本 |
| RK 领取 | 锁候选任务；再检查授权/有效期；写租约，state=leased；保存claim_request_id | 两个进程同时领取同一任务 |
| 上报进度 | 验证lease/seq；更新每文件状态；聚合汇总；保存幂等响应 | 接受客户端直接赋值prepared |
| 完成 | 锁任务；确认全部文件verified和hash匹配；state=prepared；审计 | 把下载进度当播放状态 |
| 取消 | 锁任务；state=cancelled；撤销租约与后续访问；审计 | 删除共享NAS文件或替RK强制清缓存 |
| 重试 | 仅failed/expired允许；同快照attempt+1；新进度行、新租约，state=queued | 重试时重新跟随latest换歌版本 |

权限必须在创建、领取、每个下载和上报时核对，不能只在登录时检查一次。撤销用户/设备授权后，后续新请求不再读取，即使资源 URL 被保存过。

## 四、准备任务状态表

| 状态 | 含义 | 谁能推进到下一步 |
|---|---|---|
| queued | 文件版本已固定，等待指定 RK | claim → leased；用户 → cancelled；任务有效期耗尽 → expired |
| leased | RK 已领取 | 进度 → downloading；租约超时 → queued（保留快照和attempt，不接受旧lease） |
| downloading | 有文件下载/校验回报 | complete → prepared；明确不可恢复错误 → failed |
| prepared | 所有文件校验完成 | 终态；不因此产生playing；是否撤回待RK协议，不能自动重置 |
| failed | 此次尝试失败 | 用户retry → queued（attempt+1）或cancelled |
| expired | 整个任务过期，不只是租约过期 | 用户retry经授权检查后 → queued（attempt+1、重设期限） |
| cancelled | 用户取消，后续权限停止 | 终态；要重新准备需新任务 |

leased/downloading 租约到期可重新领取，但仍校验同一个资源集合。已有文件缓存由 RK 重新确认；服务器不因超时删除 NAS。跨租约旧回报一律拒绝。attempt 是用户重试次数，lease 是一次连接领取，它们不是同一个概念。

## 五、分析新歌时再增加的表

`imports`：import_id、user_id、source_storage_key、input_sha256、original_filename、size_bytes、style_labels、state、error、created_at。只保存已完成上传/人工导入的受控文件，不能让客户端给任意服务器路径。

`analysis_jobs`：job_id、track_id、import_id、pipeline_config_sha256、release_git_sha、state(queued/running/succeeded/failed/cancel_requested)、stage、attempt、lease_owner、lease_expires_at、heartbeat_at、next_retry_at、base_run_id nullable、vocal_report_id nullable、error_code/message、created_at/updated_at。UNIQUE(track_id,input_sha256,pipeline_config_sha256,release_git_sha) 对应幂等生产意图（input_sha256 需存本表）。

`analysis_attempts`：attempt_id、job_id FK、attempt、started_at/finished_at、exit_code、sanitized_log_key、worker_release、output_binding jsonb。历史尝试不能只被最后一个error覆盖。

阶段与真实程序对应：copy_master、core、demucs、stem_features、mdx23c、publish_base、vocal_activity、register_catalog。现有 `_STATE.json` 仅是临时进度辅助，不是完整可靠数据库队列；别伪造实时细粒度百分比。

## 六、真机页面带来的后续表（先确定范围）

- `user_library(user_id,track_id,saved_at)`：个人收藏关系，**不是**访问授权。移出个人曲库不删除全局歌曲或NAS。
- `playlists(playlist_id,user_id,name,version)`、`playlist_tracks(playlist_id,position,track_id)`：歌单和顺序。
- `user_preferences(user_id,version,style_labels,bpm_min,bpm_max,level)`：个人偏好；现场能量/切歌不能自动写入个人长期画像。
- `preparation_drafts(draft_id,user_id,version,track_ids,pad_preset_id,updated_at)`：若要跨手机恢复草稿才由后端存；本地草稿也可先由App保存，不创建下载任务。
- `pairing_challenges`：6位码的带密钥摘要、device_id、expires_at、used_at、attempts、issuer；一次消费、限流、到期废止，不能存万能码000000。
- `pad_presets` / `pad_preset_versions` / `device_applied_presets`：只有项目负责人确认Pad下发范围后新增；手机编辑版和RK已生效版必须分开，不能以保存成功当设备同步成功。
- `playback_sessions` / `device_events`：现场事实和历史记录，须RK真实事件；不使用旧sessions表默认为新协议。

## 七、迁移与回滚要求

用 Alembic 管理显式版本；第一份迁移只作用于独立测试库。验收：空库可升级；重启不自动建表；重复执行升级不破坏数据；能从备份还原并校验条数/外键。

正式上线前列出：旧库是否迁用户、ID映射、切换窗口、备份验证、回滚后新写数据如何处理。未确认前不 drop 旧表，不整库覆盖，不让后端服务账号拥有超级用户权限。NAS 单独备份，数据库备份不等于音轨也备份了。
