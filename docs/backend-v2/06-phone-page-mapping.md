# 06｜按新 APK 的真实页面设计后端

[返回手册](README.md)。2026-09-13，通过 ADB 查看用户已安装的 `com.example.harbeat`。安装包指纹与 [01 的 APK](01-current-state.md) 一致，不是旧 mobile 页面。以下“页面观察”来自真机；所有 `/api/v2` 接口是本次**建议新增**，尚未联网联调。新前端源码仍待提供。

## 一、先分清四件事

| 用户看到的东西 | 实际应该表示什么 | 谁保存真相 |
|---|---|---|
| 曲库、歌单、选歌草稿 | 用户收藏/组织/选择歌曲 | 后端个人关系表；草稿首版可由手机本地保存 |
| PREP 03 检查通过 | 有权访问、文件齐全、版本兼容，允许提交 | Jetson 检查；不代表 RK 已下载 |
| PREP 04 资源准备完成 | 指定 RK 已校验指定版本全部文件 | RK 逐文件回执 + 后端任务记录 |
| 现场正在播放、Pad 已生效 | 设备当前实际执行状态 | RK 快照和命令结果，不能由手机自行写成功 |

真机 PREP 04 写着“已完成 Mock 校验”，即页面演示完成，不是资源真实传输完成。后端接入时必须替换数据来源，不能保留定时器把进度从 0 加到 100 的演示路径。

## 二、首页：汇总，不发播放命令

**页面观察：** RK3588 ONLINE、设备名、18ms；“今晚的 CYPHER / 18 首歌曲 / Pad 预设待同步”；继续准备；手机播放；连接设备。底栏：首页、音乐、设备、我的。

后端第一阶段不必新增复杂首页接口：手机组合 `GET /devices` 与 `GET /preparations/{id}`，加本地草稿即可。将来需要聚合可新增 `GET /home`，但不能再维护一套与原接口不同的在线/任务状态。

- ONLINE 按最近心跳推导，过期显示“离线/状态过期”；未配对显示“未连接”，不是自动填一个展示设备。
- 延迟必须说明测量对象和时间，例如手机到 API 的 RTT 不等于 RK 音频输出延迟。无测量为 null，页面显示“暂无”。
- “18 首”从当前草稿或任务选歌列表计算；不能固定写 18。继续准备恢复原草稿，不能创建第二个下载任务。
- 手机播放是手机输出；是否开始试听由用户操作。它不能改变 RK 的播放状态。

## 三、音乐页：推荐、搜索、个人曲库、歌单

**页面观察：** 音乐页有推荐/搜索/曲库/歌单；推荐展示标题、艺人、BPM、舞种偏好，含试听、加入曲库、存为候选、换一批；搜索提示“歌曲/艺人/舞种”，有“导入本地音频”；个人曲库当前为空。歌单有创建、编辑、删除，详情含播放全部、加入准备和移除单曲。

所有 JSON 接口沿用 [02 的返回包装和错误规则](02-data-and-api.md)。下表中的路径均省略 `/api/v2`。

| 页面动作 | 建议接口与输入 | 返回/保存 | 必须避免的错误 |
|---|---|---|---|
| 查歌、搜歌 | GET /tracks?style=&q=&cursor=&limit= | TrackSummary 分页；数据库过滤 | 每次搜索跑模型；按歌名当唯一 ID |
| 换一批推荐 | GET /recommendations?style=&bpm_min=&bpm_max=&cursor= | items:TrackSummary[]、next_cursor、strategy=`catalog_filter_v1` | 假装已经有成熟个性化模型；重复分页不稳定 |
| 查看个人曲库 | GET /me/library?cursor=&limit= | 用户收藏的 TrackSummary 分页 | 把 NAS 全局 157 首当用户已收藏 |
| 加入个人曲库 | PUT /me/library/{track_id}，空 body | {track_id,saved:true}，重复幂等 | 复制/重分析音轨；收藏关系当访问授权 |
| 移出个人曲库 | DELETE /me/library/{track_id} | {track_id,saved:false}，不存在也成功 | 删除 NAS 或影响其他用户/既有任务 |
| 存为候选 | 首版手机本地草稿操作 | 本地有序 track_ids；同 ID 不重复 | 每勾选一首就提交下载任务 |
| 试听 | GET/HEAD /tracks/{track_id}/preview，用户 Token | 对获准 master 原字节流，支持 Range | 给手机 RK Token；所有歌曲都播放包内同一个 preview.wav |
| 创建/改名/排序/删除歌单 | 第02章歌单接口 | playlist_id、name、track_ids、version | 删除歌单时删音轨；无版本覆盖别人修改 |
| 歌单加入准备 | 手机读歌单版本并展开 track_ids | 合入本地草稿，去重并保持顺序 | RK 执行时重新读可变歌单 |
| 歌单播放全部 | 手机本地播放，或另行约定 RK 命令 | 需明确当前输出目标 | 和“资源准备任务”混为一谈 |

试听建议首版鉴权后读取原曲，手机自行控制试听长度；不在请求中临时转码。若播放器不能加 Authorization，采用短时、单资源、可撤销票据，并限制日志泄露，不能用长效全局 key。本轮没有点击试听，因此不声称现有 APK 的试听就是远端歌曲。

“导入本地音频”确有按钮，但点击后是本地播放器导入还是上传曲库仍未验证。**第一阶段不默认开放公网上传。** 若确认云端导入：前端选文件 → 受限上传暂存区 → 服务端验证大小/媒体类型/实际解码及 SHA256 → 创建 imports/analysis_jobs → 异步状态查询 → 完成后进入个人库。用户只传文件、文件名和风格标签，不传 NAS 路径或 shell 命令。上传大小上限、配额、支持格式和权利声明需先确认。

## 四、准备四步：具体接什么接口

### PREP 01：选择音乐

**页面观察：** “每次选择都会保留在当前草稿”；支持整歌单加入、逐曲勾选；未选歌时继续按钮不可用。

首版草稿由手机保存 `{device_id,style_label,track_ids,accept_degraded}`。后端不在每次点击写 preparations。单个条目的 UI 状态与 NAS 分析状态分开。返回上一步不能丢选择，也不能改变已提交任务。

若后续需要跨手机同步，加草稿接口和 version 乐观锁；这是额外功能，不是打通 EDM 传输必须项。手机的可继续条件与服务器最终校验要一致；准备最少选几首由 RK 确认，当前接口建议 2—20，不把建议当已冻结产品规则。

### PREP 02：选择 PAD

**页面观察：** CYPHER FUN、8 槽、App v3、编辑 Pad 预设。编辑页写“固定安全控制不会出现在这里”，展示 AIR HORN/CROWD UP/HIT 等槽位。概览显示 4 已配置，但槽位页及检查页是 3 个，应由同一个槽位数组计算，不能分别硬编码。

**范围待项目负责人确认：** 后端是否负责 Pad 配置和音效文件的存储/下发。若本期只做歌曲，前端应明确提示“Pad 同步尚未接入”，不得打绿勾。不能因为跳过 Pad 就宣称整个原有准备流程已完成。

如纳入，建议单独采用以下初步合同（不是目前 NAS 音乐合同的一部分）：

- Preset：preset_id、owner_user_id、name、version、schema_version、slots；最多 8 槽，slot_index=1—8 且唯一。
- Slot：slot_index、label、effect_asset_id（空槽为 null）；执行模式/音量范围由 RK 确认后加入，不接受任意脚本或路径。
- EffectAsset：asset_id、sha256、size_bytes、content_type、duration_ms、sample_rate_hz、channels；音效格式及长度上限由 RK 提供。
- GET/POST /pad-presets、GET/PATCH /pad-presets/{id}；修改必带 expected_version，冲突409，返回不可变新版本。
- 任务要冻结 preset_id + version + config_sha256；额外文件进入任务文件清单。此时不再是恰好 14 文件/首，需升级资源草案 schema 和验收，不能塞进歌曲 manifest 假装旧合同已有。
- “App v3”是编辑版本；“Device v2”来自 RK 应用回执。下载成功、配置保存成功、设备实际应用成功是三个状态。

此项获准前，第02章纯歌曲 ResourceSet 不增加 Pad 字段。后端不负责手环/戒指姿态映射或固定安全按键执行。

### PREP 03：检查资源

**页面观察：** 检查目标设备在线、已选歌曲、Pad 已配置、RK 协议兼容。

新增建议 `POST /preparations/preflight`，body 与 PreparationCreate 相同；它**只检查、不创建任务、不分配租约、不运行模型**。成功包装 data：

| 字段 | 类型/含义 |
|---|---|
| can_submit | bool，服务端按阻塞项计算 |
| checks | 数组，每项 {code,status,blocking,message}；status=passed/failed/unknown/not_supported |
| checked_at | 服务器 UTC 时间 |
| device_id / track_ids | 检查目标和有序选择 |
| resolved_tracks | [{track_id,analysis_run_id,manifest_sha256,vocal_activity_sha256}] |
| files_total / bytes_total | 按真实资源计算，不用 MP3 压缩体积代替所有分轨 |
| needs_review / quality_flags | 原样保留质量风险 |

check code 至少含 authorization、resources、same_style、quality、device_online、protocol、disk_space。离线/未知空间可提示非阻塞并排队；协议明确不支持、未授权、缺文件、未经允许的质量风险是阻塞。前端仍不能无条件显示“目标在线”。Pad 未纳入时单独显示 not_supported，不能 passed。

只读检查与提交之间数据可能变化。因此真正 `POST /preparations` 必须再次检查并冻结 run/files；不能信任手机上传的检查成功值或沿用过期结果。接口返回409时保留草稿、展示具体阻塞原因，不自动换曲或默认接受 degraded。

### PREP 04：同步就绪

将真实 `POST /preparations` 放在检查后的明确“开始准备/同步”操作上（当前“继续”的含义需前端调整文案）。前端保存 preparation_id；网络重试复用 Idempotency-Key，之后轮询 GET preparation，建议可见时每2秒，退后台暂停或降低频率。

显示 queued→等待设备、leased→设备已领取、downloading→已校验字节进度、prepared→资源准备完成；failed 显示错误与重试，cancelled/expired 单独显示。原 READY100 必须由 prepared 驱动。

**“开始使用”不是提交资源的同义词。** 若仅进入 Live 页面，可以读取 RK 快照；若需要自动播放，必须单独发已约定的播放命令并等 RK 回执。本轮没有点击该按钮，所以其实际副作用仍待源码/联调确认。

## 五、设备页面与六位配对码

**页面观察：** 输出 MAIN OUT/STEREO、空间68%、曲目126、18ms；说明 RK 当前播放事实源；Pad App v3/Device v2待同步；播放测试音、使用配对码连接。配对页要求输入 RK 屏幕六位码，文案说连接15秒后超时。

设备列表的 available_bytes/capabilities 来自已认证 RK 心跳；建议扩展 `storage_total_bytes`、`cached_track_count`、`output:{name,channel_mode}`、`snapshot_seq`、`reported_at`，未知值为 null。空间百分比由 available/total 计算，并写明是已用还是可用。不要把曲库总157当RK缓存126。

配对建议协议（待登录/设备所有权策略评审）：

1. 已预注册且持有设备凭据的 RK 请求 `POST /device/pairing-challenges`。服务端生成六位随机码、challenge_id、expires_at，返回该设备显示；不在手机上创建任意设备身份。
2. 已登录手机提交 `POST /device-pairings`，body={code:string}（保留前导零）、Idempotency-Key。
3. 服务端验证挑战未过期/未消费、配对策略允许，原子消费并写 user_device_grants；返回 device_id、name、paired_at。重复同key返回原结果。
4. 错误对用户统一为 PAIRING_INVALID_OR_EXPIRED；按账号/IP/设备限流并记录失败，禁止遍历六位码枚举设备。活动码应全局唯一并以带服务器密钥的摘要存储，短时有效；不要因空间小而仅存普通无密钥 hash。

“15秒”是当前页面连接等待文案，**不是已证实的配对码有效期**。建议挑战寿命120秒待确认。请求超时后先用同key重试/刷新设备列表确认是否已绑定，不能提示成功后实际上无权访问。是否允许设备被多人绑定或转移所有者需项目负责人决定。

测试音会操作输出，属于 RK 命令，不能由普通心跳或配对接口顺带触发。本轮没有测试音和真实配对操作。

## 六、我的页面与现场状态

**页面观察：** 用户资料、舞种偏好、水平、使用记录；文案明确“活动播放不写入个人画像”，现场换歌和能量调整不改变长期推荐。

建议 GET /me 返回 user_id、display_name、preferences:{version,style_labels,bpm_min,bpm_max,level}。PATCH /me/preferences 必带 expected_version；BPM上下限须正数且 min≤max，水平/舞种取受控字典。本轮未查看编辑表单，不冻结额外性别、生日等未确认字段。

现场事件写独立记录，不自动更新 preferences。使用记录由真实 RK session 产生；未有事件显示空，不用演示播放累计。正式登录页未核实，认证设计不能从用户资料页推测。

Live 未实看。只从 AOT 发现 LIVE / RK FACT、前后切歌等线索。下一步需要前端源码和 RK 负责人确认 snapshot、命令类型、过期和执行回执；本手册不对未见页面编造按钮清单。

## 七、前端交接时必须一起完成

1. 提供这份 APK 对应源码、构建版本及真实入口配置，声明 INTERNET 后重新构建。没有联网权限，后端写好也不能由此包正常请求网络。
2. 把演示 Repository/本地 Mock 与远端实现分开，生产包请求失败不得降级成演示成功。
3. 前后端一起导出 OpenAPI、生成或核对 DTO；字段为 null、空数组、401/409/503 都要有 UI 状态。
4. 用真实 EDM track_id 替换展示曲目；试听核实原曲一致，下载进度来自 RK，不是手机预估。
5. 对本章待确认项逐项登记：Pad范围、导入含义、登录与配对策略、最少选歌数、Live命令。未确认项可以先关闭入口，但不宣称功能完成。
