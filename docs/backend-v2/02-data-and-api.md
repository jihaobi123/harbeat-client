# 02｜数据和接口：从歌曲到 RK 文件

[返回手册](README.md)。本页分为“现有 NAS 格式”和“第二版建议 API”。**NAS 格式已有产物；`/api/v2` 路径是本次新设计，尚未上线，也未经过新 APK/RK 联调。**

## 一、几个必须统一的词

| 名称 | 含义和格式 |
|---|---|
| track_id | 歌曲身份，原样使用 NAS 字符串，不改成旧数据库整数 ID，不用歌名关联 |
| analysis_run_id | 某首歌的一次基础分析发布版本；和 track_id 一起固定 |
| manifest | 某个基础 run 的说明文件，包含分析信息及音轨引用 |
| storage_key | NAS 根目录下的相对路径，只供后端解析；不是可直接打开的公网 URL |
| sha256 | 文件内容指纹，64 位小写十六进制；针对原始字节，不是解析后重新输出的 JSON |
| asset_id | 新后端给一个不可变文件版本分配的 ID；不是文件名，不具有授权能力 |
| preparation_id | 手机的一次“为指定 RK 准备这些歌”的任务编号 |
| lease_id | 一次 RK 领取任务的凭据标识；超时后旧领取者不能继续更新状态 |
| request_id | 后端生成的请求追踪号；方便从报错查日志 |

API 命名用 snake_case。ID 都用字符串。日期统一 UTC ISO8601；音频时间统一整数毫秒 ms；文件大小用整数 bytes；数值未知写 null，不写 0 冒充有结果。布尔值是真正 true/false，不用字符串或 0/1。

## 二、当前 NAS 的权威结构

根目录 `HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess`。本地交付包只需替换 root，storage_key 不变。

| 文件 | 怎样找到 | 用途 |
|---|---|---|
| 基础索引 | `published/indexes/edm_8_handoff_v1.json` | 发现本次固定的 8 个 track/run；不是公共授权名单 |
| 人声索引 | `published/indexes/edm_8_vocal_activity_v1.json` | items 按 track_id + analysis_run_id 关联，processed 必须完成 |
| 单曲 latest | `published/tracks/{track_id}/latest.json` | 发现当前版本；任务创建后不再反复跟随它 |
| 基础 manifest | 索引或 latest 的 manifest_storage_key | 原样解析、原样提供下载 |
| 基础完成标记 | manifest 同目录 `_SUCCESS.json` | run_id、manifest_sha256、asset_count |
| 10 条音频 | manifest 的 assets 字段 | master 1 + Demucs 4 + MDX23C 5 |
| 人声报告 | 人声索引 vocal_activity_storage_key | 人声时间段，独立 1.0.0 合同 |
| 人声完成标记 | 人声报告同目录 `_SUCCESS.json` | vocal_activity_sha256 |

**基础索引的 items 当前不一定有 manifest_sha256。** 后端应读取 run 的 `_SUCCESS.json` 并计算 manifest hash 核对，不假设索引自带所有字段。基础 latest 是可变指针，固定 EDM 快照必须用 index 指定的 run，即使 latest 已指向别的 run。

每首在本期完整资源策略下交给 RK **14 个文件**：10 条音频 + 基础 manifest/完成标记 + 人声报告/完成标记。索引是后端发现数据用；可变 latest 不作为任务中必须下载的文件，版本绑定写入冻结的任务清单。若未来需要额外产物，要登记在清单并增加测试，不能让 RK 扫 NAS 目录猜文件。

## 三、实际 manifest 字段怎么用

不要新增顶层 `rhythm` 或 `audio` 来读取，它们不在当前合同；正确位置是 `analysis.*` 和 `assets.*`。

| JSON 路径 | 类型 / 单位 | 后端与消费者用途 |
|---|---|---|
| source.title / artist | string 或 null | 曲库显示；没有时显示原文件名，不伪造艺人 |
| source.duration_ms | integer，ms | 时长 |
| source.input_sha256 | SHA256 | 原音频去重与旧数据映射，不能按标题去重 |
| source.style_labels | string[] | 用户目录标签，保留原文；先限定同风格 |
| status | ready / degraded / unavailable | 基础质量状态，不是下载状态 |
| pipeline | object | Git 和模型来源，整体保留 |
| assets.master | Asset | 原曲，格式可能 MP3，不保证 WAV |
| assets.stems.vocals/drums/bass/other | 4 个 Asset | Demucs 四轨 |
| assets.drum_stems.status | 质量状态 | 五轨可用性 |
| assets.drum_stems.kick/snare/hihat/tom/cymbal | Asset 或 null | 实际 MDX23C 五轨；本期完整任务不能缺轨 |
| analysis.tempo.bpm / confidence / stability / needs_review | number / nullable / bool | 列表用 bpm，详情保留置信与复核状态 |
| analysis.beat_grid.beats_ms | integer[] | 真实节拍序列 |
| analysis.beat_grid.bars_ms / downbeats_ms | integer[] | 当前发布器两字段都写小节序列；不能解释成两套独立模型的原始检测 |
| analysis.beat_grid.time_signature | numerator / denominator | 3/4、4/4 等；null 时不能默认 4/4 |
| analysis.sections.source / fallback_used / items | string / bool / array | 正式段落、来源和失败回退；每段 start_ms/end_ms/label 等以 schema 为准 |
| analysis.key | name / camelot / confidence / needs_review | 调性信息，不要求后端重新识别 |
| analysis.energy / transition_windows | object / array | 保留现有能量与候选窗口；后端不决定最终接歌点 |
| analysis.drum_groups | object | 五组语义特征及代理风险；不是音频文件列表 |
| quality.modules / quality_flags / needs_review | object / string[] / bool | 原样暴露给 RK，不能清空或改成成功 |

每个 Asset 的字段为 `storage_key`、`sha256`、`size_bytes`、`content_type`、`sample_rate_hz`、`channels`、`duration_ms`。实际字段以 [基础 Schema](../../contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json) 为准，后端不统一转码、不裁切、不改变采样率；RK 再决定怎样解码。

人声报告字段：`intervals[] = {start_ms,end_ms}`，相对于原曲起点，左闭右开、不重叠；`active_duration_ms` 是检出总时长，`coverage_ratio` 是占比不是准确率。`source` 必须与基础 manifest 的 track_id、analysis_run_id、manifest_sha256、manifest_storage_key、vocals storage_key/SHA256 六项一致。成功但 intervals=[] 是未检出；缺报告/模型失败不能伪装为空数组成功。

## 四、后端必须做的读取校验

顺序不可省略：

1. 读取指定索引快照，找 track/run，不用歌名。
2. 安全解析 storage_key：拒绝绝对路径、`..`、反斜线、NUL；resolve 后必须仍在 published 根内。下载 API 不接受客户端直接传路径。
3. 读取 manifest 原始字节，计算 SHA256；校验基础 schema、track/run、完成标记和 asset_count。
4. 枚举明确的 master + 4 stems + 5 drums；每项检查文件存在、大小、SHA256。正式 catalog 激活前完整校验；列表请求不反复读取 GB 音轨。
5. 读取绑定同一 run 的人声报告，校验 schema、hash、完成标记、六项关联、时长与区间。
6. 独立判断“文件齐全”和“质量允许”：unavailable 或缺必要文件必须拒绝；degraded 仅在明确策略允许时准备，并将标记继续传递。
7. 把固定 run、各文件 key/hash/size、人声 revision 写数据库，任务领取/重试都使用这个版本。

只读参考程序实现第 1—5 步的主要校验，默认不重算音频 hash；生产权限和任务持久化须按后续章节添加。

## 五、第二版 API 通用规则（建议）

所有路径以 `/api/v2` 开头，通过统一 HTTPS 入口访问。手机用用户 Bearer Token，RK 用设备 Bearer Token，不能共用一把全局 Token。访问某个 ID 之前检查当前账号/设备对它的权限。

成功 JSON 统一 `{request_id, data}`；分页 data 为 `{items,next_cursor}`。错误 JSON 为 `{request_id,error:{code,message,retryable,details}}`，同时使用正确 HTTP 状态，禁止所有错误都返回 HTTP 200。文件接口返回原始字节，没有 JSON 包装。

错误码最低要求：401 AUTH_REQUIRED/TOKEN_EXPIRED；403 FORBIDDEN；404 NOT_FOUND（也可用于隐藏他人对象）；409 IDEMPOTENCY_CONFLICT/STALE_VERSION/LEASE_EXPIRED/STYLE_MISMATCH/QUALITY_REVIEW_REQUIRED/INVALID_STATE；422 INVALID_REQUEST；429 RATE_LIMITED；503 NAS_UNAVAILABLE；500 INTERNAL_ERROR。错误不包含绝对路径、数据库连接串或堆栈。

所有创建任务请求必带 `Idempotency-Key`（随机 UUID）。相同用户+路由+key+相同请求体，返回原任务，不重复创建；相同 key 不同请求体返回 409。接口草案的格式不是 APK 已有实现，冻结前用 OpenAPI 和 DTO 测试统一。

## 六、手机端接口与具体字段

本节先定义纯歌曲交付的核心接口。真实页面还需要个人库、推荐、试听、准备检查和配对；逐按钮和字段补充见 [06：真机页面对应](06-phone-page-mapping.md)。Pad 配置传输尚待范围确认，不能当成现有14文件歌曲合同的一部分。

| 接口 | 请求 | data 返回内容 | 服务器动作 |
|---|---|---|---|
| GET /me | 用户 Token | user_id:string、display_name:string、role:string | 返回当前账号；登录方式/其他资料字段待前端确认 |
| GET /styles | 无 | items:[{label:string,track_count:int}] | 只统计用户有权限的目录标签 |
| GET /tracks | style:string、q:string 可选，cursor:string 可选，limit:int=20，最大100 | items:TrackSummary[]、next_cursor:string/null | DB 查询，不触发模型；limit 越界422 |
| GET /tracks/{track_id} | track_id | TrackSummary + pinned_analysis:{analysis_run_id,manifest_sha256} + analysis:现有完整对象 + vocal_summary | 检查权限，返回某个固定快照，不暗中重分析 |
| GET /devices | 无 | items:[{device_id,name,online,last_seen_at,available_bytes,capabilities_version}] | 仅本人已授权设备，在线值从服务器收到心跳的时间推导 |
| POST /preparations | PreparationCreate（下表），Idempotency-Key | 201，Preparation | 一次事务固定所有选歌与文件；不执行混音 |
| GET /preparations/{id} | id | Preparation | 仅创建者/获准管理员；状态来自持久化记录 |
| POST /preparations/{id}/cancel | 空对象 | Preparation | 幂等；撤销后续领取/下载权限，RK 停止旧任务，不抹除已下载文件 |
| POST /preparations/{id}/retry | 空对象，Idempotency-Key | Preparation | failed/expired 才能重试；保持原资源版本，增加 attempt，清除旧租约 |

**TrackSummary 字段：** track_id、title、artist、duration_ms、style_labels、bpm（可 null）、key_name（可 null）、analysis_status、needs_review、quality_flags、resource_status、can_prepare、blocked_reasons、analysis_run_id。resource_status=complete/missing/checking；can_prepare 由服务端质量策略+权限+完整性计算，不单看 status=ready。

**PreparationCreate 字段：**

| 字段 | 格式与规则 |
|---|---|
| device_id | 必填字符串；必须是当前用户获准设备 |
| track_ids | 必填、有序、无重复字符串数组；本期建议2—20首，实际最小数量待 RK 确认；一个非法就整体拒绝 |
| style_label | 必填字符串；每首 source.style_labels 都必须包含这个准确标签 |
| accept_degraded | 必填 bool，默认 false；true 只是用户确认，仍须服务端策略允许，不能绕过服务端限制 |

首阶段只发送“用户选歌顺序”，不承诺就是最终混音顺序。后端不调 Pair Score 排序。

**Preparation 字段：** preparation_id、device_id、state、attempt:int、created_at、updated_at、expires_at、style_label、track_ids、resource_set_sha256、files_total、bytes_total、verified_files、verified_bytes、progress_ratio（0—1）、last_device_report_at:null/string、error:null/object、needs_review、quality_flags。progress_ratio 为 verified_bytes / bytes_total；缓存文件只有校验成功才计入，不把重试下载字节重复累加。

歌单可在主链路完成后添加：GET/POST `/playlists`，PATCH/DELETE `/playlists/{id}`，PUT `/playlists/{id}/tracks`。创建 body={name}，改名 body={name,expected_version}，替换列表 body={track_ids,expected_version}；返回 playlist_id/name/version/track_ids。每次修改版本+1，不匹配409。提交准备时把歌单展开成 track_ids 快照，不让 RK 读取可变歌单。

## 七、RK 资源交付接口

| 接口 | 输入 | 输出与规则 |
|---|---|---|
| POST /device/heartbeat | {boot_id:string,report_seq:int,available_bytes:int,capabilities:{resource_contracts:string[],audio_formats:string[]}} | {server_time,next_heartbeat_seconds:15}；身份从设备 Token 取，不信 body 的 device_id |
| POST /device/jobs/claim | {claim_request_id:UUID} | {job:null} 或 {job:Preparation,lease_id,lease_expires_at}；原子领取一个自己的 queued 任务，同 request_id 重试返回原租约 |
| POST /device/jobs/{id}/renew | {lease_id} | {lease_expires_at}；建议租期90秒、每30秒续租，均可配置；使用服务器时间 |
| GET /device/jobs/{id}/resources | Header `X-Lease-Id` | 冻结的 ResourceSet，校验设备、任务、attempt、有效租约 |
| GET/HEAD /device/jobs/{id}/files/{asset_id} | X-Lease-Id、设备 Token；GET 可带 Range | 只允许该任务已冻结的文件；支持断点，详见下节 |
| POST /device/jobs/{id}/progress | Progress（下表） | {accepted_seq,state,verified_files,verified_bytes}；拒绝过期租约；重复 seq 幂等 |
| POST /device/jobs/{id}/complete | {lease_id,resource_set_sha256} | Preparation，全部资源校验回执齐全才能变为 prepared |

RK 暂无任务时正常返回 job=null，不是404。领取是 POST，因为会更改服务器记录。GET 不消耗队列任务。设备心跳只能证明在线，不能自动证明有歌曲、能播放或已完成任务。

**ResourceSet：** schema_name=`harbeat_resource_set`、schema_version=`0.1.0-draft`、preparation_id、resource_set_sha256、tracks[]、files[]。tracks 每项包含 position（从0起）、track_id、analysis_run_id、manifest_sha256、vocal_activity_sha256、status、quality_flags。files 每项包含 asset_id、track_id、role、storage_key、sha256、size_bytes、content_type、download_path。role 固定为 master、stems.vocals/drums/bass/other、drums.kick/snare/hihat/tom/cymbal、manifest、base_success、vocal_activity、vocal_success。storage_key 用于在 RK 还原 published 相对结构，但不能直接拿它请求任意文件。

resource_set_sha256 对冻结核心 `{tracks,files}` 的 JSON 计算：UTF-8、key排序、紧凑分隔符、禁止 NaN；files 按 asset_id 排序，tracks 按 position 排序；**计算时 files 不含 download_path，核心也不含 resource_set_sha256 自身或租约**。服务器存下准确字节，RK 按同一规则校验。下载路径为相对 API 路径，不含长效密钥；租约续期不改变资源集合。

**Progress：** lease_id:string、seq:int（每个 lease 从1单调增加）、files:[{asset_id,state,downloaded_bytes,observed_sha256,error_code}]。state=downloading/verified/failed；downloaded_bytes 在0与登记大小之间；observed_sha256 仅 verified 时必填，必须与登记值一致。记录每个文件最新情况后，后端自己汇总，**不信客户端直接报“100%”或总字节**。重复同 seq 同 body 返回已接受结果，不同 body 返回409；未知 asset_id、其他任务文件拒绝。旧 seq 返回409并给当前 accepted_seq。完成后继续允许同一有效身份读取自己的任务结果，不能把 prepared 任务再次领取成 queued。

后端只能校验“回报格式和 hash 是否匹配预期”；无法远程证明 RK 确实读过每个字节。RK 验收程序必须真实计算下载文件 hash，不能照抄服务端 hash 当校验结果。

## 八、大文件下载规则

- 标准下载 GET=200；合法单区间 Range=206，含 Content-Range、Content-Length；越界=416，Content-Range 为 `bytes */总大小`。
- HEAD 返回同等 metadata、不含 body；提供 Accept-Ranges: bytes、强 ETag（文件 SHA256 加引号）、Content-Type、Content-Length。HEAD 的 Range 可按 HTTP 规则忽略。
- 建议首版只支持一个 Range；不支持的多区间请求可以忽略 Range 返回完整200，不能错误切第一段。客户端见200须从头写，不能追加到旧半文件。
- If-Range 与 ETag 不匹配返回完整200；暂停续传沿用同一个 asset_id/hash。401刷新设备凭据、租约过期重新领取后继续下载相同版本，不重新解析 latest。
- 不把 MP3/WAV gzip、不转码；业务 JSON可压缩，但需要作为原文件验证 hash 的 manifest 下载不可重序列化。
- FastAPI/代理必须流式传输，不能 `read_bytes()`/`resp.content` 一次加载整条音轨。私网连接和租约可以在开始时校验；取消任务无法追回已发送字节，后续新请求必须拒绝。
- 浏览器/手机的文件试听若需要，单独实现获准的 master 读取，不开放整 NAS；本期不能把 RK Token 暴露给手机。

HTTP 行为依据 [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)。具体字节流性能、Range 与代理透传需按验收表实际测试，不能仅认为框架默认支持。

## 九、播放控制与登录：明确留待确认，不伪装已实现

资源交付的终态叫 prepared（文件准备完成），不是 playing。Live 页面需要的播放状态必须来自 RK；云端收到命令返回 accepted 也不是 executed。

建议后续单独设计 `/devices/{id}/commands` 与 `/device/commands/...`，包含 command_id、type、目标 session/version、过期时间、执行回执。允许的 play/pause/next/seek/音量范围和延迟目标由 RK/前端确认后才增加，本文不替他们定义混音算法或姿态命令。

当前 APK 未证实登录流程。开发期用项目负责人私下发放的、可撤销短期测试用户/设备凭据；不要提供无鉴权公网接口。正式密码/验证码登录、账号迁移、设备配对流程另行评审，不能复用旧 SHA256 密码方案当成熟鉴权。
