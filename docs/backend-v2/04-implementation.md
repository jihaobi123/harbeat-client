# 04｜代码怎样写：按能验收的小步实现

[返回手册](README.md)。这里是代码实现参考和任务拆分，**以下 backend_v2 目录及业务函数是计划新增，不是仓库已有可调用服务**。现有可运行辅助程序只有本手册 reference/read_delivery.py；正式模型仍在 preprocessing。

## 一、建议技术选型与进程

使用团队现有 Python/FastAPI 体系，SQLAlchemy 2、Pydantic 2、PostgreSQL、Alembic、pytest；业务 API 用单独虚拟环境，锁定依赖后提交锁文件。Jetson GPU 模型环境保持现状，不在其中升级 torch/torchaudio。新后端不需要导入 Demucs 或 SongFormer 才能启动。

首版用 PostgreSQL 保存任务并由一个独立 Worker 领取；Redis 可作缓存，但不是任务唯一真相。先限制重模型 GPU 作业并发=1，不用多个 Web worker 同时运行模型。不要求为了第一个闭环额外建设微服务或复杂消息总线。

FastAPI 的 BackgroundTasks 不是持久任务队列，重计算应与请求分离；参考 [FastAPI 官方说明](https://fastapi.tiangolo.com/tutorial/background-tasks/)。本文选择数据库队列是本项目的初期设计，不是声明框架已经自动实现恢复。

## 二、建议新增的代码结构

```text
backend_v2/
  main.py                 组装路由、错误处理、请求追踪，不启动模型
  settings.py             读取环境，缺重要配置就拒绝启动
  db.py                   新库连接和事务，不自动建表
  models/                 第03章各表
  schemas/                Pydantic请求/响应对象，禁止额外字段悄悄生效
  api/
    mobile.py             曲库、个人库、选歌任务、设备显示
    device.py             心跳、领取、续租、资源、进度
    files.py              授权后原字节GET/HEAD/Range
    admin.py              受限的导入、分析任务、授权管理
  services/
    catalog.py            读已发布结果并登记到新库
    preparation.py        权限、同风格检查、固定版本、状态机
    identity.py           用户/设备身份与授权
    delivery.py           清单组装、文件授权、进度汇总
  repositories/           SQL查询；不放HTTP或模型调用
  workers/
    analysis_worker.py    持久分析任务 -> 子进程 -> 校验 -> 入库
    reconcile.py          NAS/数据库中断后的对账与租约回收
  storage/
    published_reader.py  按现有合同读NAS，不执行模型
    path_policy.py        安全路径解析和只读文件打开
  cli/                    目录导入、只读检查、测试授权工具
  tests/                  单元、合同、数据库、下载端到端
  migrations/             Alembic显式迁移
```

不要把这些实现重新塞进旧 app 或为每个模型复制一套后端。旧 Python 转发仍保留，但新业务不依赖旧 app 启动。

## 三、步骤1：读 EDM，建立目录

先运行 [只读参考程序](reference/read_delivery.py)。输入是 root + 两份已发布索引；输出包括真实 track_id/run_id、分析对象和每首14个文件。程序不依赖数据库，也不导入模型。

`PublishedReader.read_snapshot(base_index_key, vocal_index_key, verify_audio)` 的生产实现按该程序拆分。增加大小限制、明确异常码、schema版本白名单、文件访问审计；NAS挂载检查失败时返回 NAS_UNAVAILABLE，不在本地空挂载点悄悄建目录冒充NAS。

`CatalogService.import_snapshot(snapshot)`：

1. 在事务外做文件完整性检查，记录校验时刻和固定hash。
2. 事务内登记 track/run/report/assets；冲突时比较指纹，相同可复用，不同则拒绝。
3. 所有必要文件verified后，才把目录项标成resource_status=complete。
4. 由管理员明确授权测试用户读取EDM，不把全局数据自动共享给所有用户。
5. GET /tracks 从数据库索引查询，不能每次打开全部wav计算hash。

目录入库命令需支持 dry-run，先输出将新增/冲突/缺失数量；重跑同快照不产生重复记录。tracks.jsonl可作发现线索，不是事务队列，不能“读到一行就认定全套数据成功”。

## 四、步骤2：写手机曲库接口

先实现 require_user，再实现 GET styles/tracks/track detail。路由只做四件事：解析、鉴权、调用service、返回DTO。业务判断写service，SQL写repository。

核心函数责任：

| 函数 | 输入 | 返回 / 出错 |
|---|---|---|
| require_user(token) | 手机凭据 | 当前用户；无效401，禁用403 |
| list_tracks(user_id,filters,cursor,limit) | 搜索条件 | 仅有权限的TrackSummary分页 |
| get_track(user_id,track_id) | 歌曲ID | 当前可消费固定版本详情；不存在/无权限不泄露他人记录 |
| save_to_library(user_id,track_id) | 已有歌曲ID | 创建个人收藏关系，幂等；不拷贝音轨 |

搜索覆盖 title/artist/style_labels。首版采用数据库过滤和确定性排序，不训练推荐模型；若推荐页展示策划曲目，要标“精选/目录筛选”，不编造“因为你常跳…”的个性化原因。

网络超时、空曲库、无可用分析、未授权、设备离线分别给前端明确状态。前端不使用内置示例值填充失败接口，错误界面需要可重试。

## 五、步骤3：创建固定资源任务

`PreparationService.create(user, request, idempotency_key)` 参考流程：

```python
# 流程参考，不是可直接运行的完整业务实现；所有repo方法需按第03章写。
with session.begin():
    prior = idempotency.get_or_reserve_for_update(user.id, route, key, body_hash)
    if prior.completed:
        return prior.saved_response
    permissions.require_device(user.id, request.device_id)
    # 单个短事务锁定目录版本；文件hash已在目录激活前校验，不能在此读GB文件。
    runs = catalog.lock_current_runs(request.track_ids)
    permissions.require_tracks(user.id, request.track_ids)
    validate_same_style(runs, request.style_label)
    validate_integrity_and_quality(runs, request.accept_degraded, server_policy)
    resources = delivery.freeze(runs)  # 含匹配人声报告，精确14文件/首
    job = jobs.insert_queued(user, request, resources)
    audit.record("preparation.created", job.id)
    idempotency.complete(prior, status=201, response=job.to_dto())
return job.to_dto()
```

并发同一key的两个请求必须由唯一约束和事务处理：后到者等待已占用记录完成，再比较request hash并返回同响应；不是查完不存在就各自插任务。事务失败连同幂等占位一起回滚。

资源冻结包含基础run、人声revision和所有hash，之后不再访问latest选择新版本。等待设备时不持有数据库长事务。手机重复点击、HTTP超时重发用同一个key；真正新选择用新key。

设备可离线：允许创建queued任务，手机显示“等待设备”，而不是强制失败。但设备未授权、协议不支持或歌曲缺文件要明确拒绝。建议任务有效期24小时，可配置；流量/空间检查使用实际总字节，不按“几首歌很小”估计。

## 六、步骤4：RK领取、续租与断网恢复

`claim_job(device,claim_request_id)` 必须用事务行锁。候选条件：本设备、queued、未过期、授权仍有效。排序created_at/id。`FOR UPDATE SKIP LOCKED` 避免并发领取同任务，参见 [PostgreSQL SELECT锁说明](https://www.postgresql.org/docs/14/sql-select.html)。

锁住任务后再插lease、改state，再提交。建议每台RK同时最多一个有效资源准备任务；通过锁devices行串行化该设备claim，不靠单进程asyncio.Lock。

- 同claim_request_id且原租约仍有效：返回原结果；原租约已过期：409 LEASE_EXPIRED，RK用新claim_request_id重新领取。
- renew只延长当前lease；失效lease不能复活。后台回收超时lease，将leased/downloading恢复queued，保留快照。
- 任务总有效期、权限撤销、用户取消与租约失效是不同原因；不要将取消任务重新排队。
- 心跳使用boot_id+seq；重启换boot_id。online以服务端received_at推导（建议45秒过期），不信设备传来的online=true或错误时钟。
- 上报进度以lease+seq去重，保留每文件状态，完整校验回报后才能计入verified_bytes。
- RK空间不足用明确错误DISK_FULL；设备自己清理哪些缓存由RK负责人决定，后端不下发任意rm命令。

## 七、步骤5：可靠发送大文件

后端不直接“推送音轨到手机热点IP”。公网连接由RK发起：RK → HTTPS阿里云 → 受控私网Jetson → NAS读取。所有连接由客户端/网关按可达方向发起，不能假设私网地址全球可访问。

`authorize_file(device,job_id,lease_id,asset_id)` 顺序：

1. 验证设备凭据、启用状态。
2. 检查job属于此设备，创建者权限仍有效，任务未取消/过期，lease当前有效。
3. 检查asset在preparation_files内且指纹与冻结值相同。
4. 从数据库得到storage_key，安全解析，打开只读文件；不能从请求接收任意URL/路径。
5. 核对打开的文件大小、可变性风险；发现与登记不一致立即拒绝并标invalid。
6. 返回流式原字节，处理Range/HEAD/ETag；始终关闭文件描述符。挂载/读取中断要让客户端知道下载未完成。

可以选择经鉴权后由Jetson上的内部nginx location发送文件，也可先用独立FastAPI文件响应；无论选择哪种，必须实测第02章的Range行为。内部location不得直接公网可访问，外部不能构造X-Accel-Redirect绕过鉴权。

阿里云nginx只将新API路由转到独立Jetson服务，透传Authorization、Range、If-Range、Content-Range、ETag、Content-Length，不重新转码；响应超时按大文件设置。不要直接复用旧Python网关的resp.content，整文件缓冲会吃内存且等传完才返回。旧评审站点路径保持原样。

流量事实：本次EDM8完整交付含人声JSON，112个文件，总2,826,072,608 bytes（约2.63GiB），不是ZIP的压缩体积。10Mbps有效链路纯传输理论约38分钟，实际还会更久；因此必须断点、RK缓存、真实进度，不能承诺秒级完成。新增歌曲只下载缺失版本；设备同时下载建议先限制2个文件，后续实测再调。

## 八、步骤6：新歌分析队列

第一版只支持管理员导入已获准音频/既有ZIP；手机“导入本地音频”如要上传云端，再按真机映射扩展。下载第三方平台音乐不属于本次后端方案，不在这里代用户登录平台或绕过权限。

Worker与Web API分进程：Web只写analysis_jobs，快速返回202；Worker循环领取一个queued作业，写running和lease，然后启动已有模型CLI子进程。不要在数据库事务里等待模型。

调用方式参考（参数由服务端可信配置构造，不接收shell字符串）：

```python
args = [trusted_python, "-m", "preprocessing.cli.run_same_style_preprocess",
        trusted_source_path, "--track-id", track_id,
        "--root", trusted_output_root, "--disable-adtof"]
for label in validated_style_labels:
    args += ["--style-label", label]
# 在受控release目录，用独立进程运行；不要shell=True，不拼用户输入命令。
```

注意线上release仍是旧目录，以上为新目录完成部署验证后的调用方式。上线前保存完整环境清单、模型路径与vendor；不要只复制preprocessing一个目录就切换。旧包装命令可能source环境并创建目录，不能作为“只读检查”执行。

Worker必须实现：

- 独立心跳线程/循环续lease；stdout/stderr持续读取到受限日志，避免管道堵塞。stdout可能混有模型日志，不能假设整段输出就是JSON；更稳妥由适配器输出固定结果文件并校验，或解析末尾明确记录。
- 超时与取消关闭整个模型进程组，等待子进程退出再释放GPU槽位；不要只杀父进程留下CUDA工作进程。已有文件锁须核对进程确实退出后处理。
- 映射真实阶段，不把“模型进程存在”当所有阶段成功。底层publisher只发布基础；人声失败时基础run保留，下一次只补人声再入库，不重做所有模型。
- 模型崩溃/临时I/O错误可按1分钟、5分钟、15分钟重试，最大3次；输入损坏、schema不兼容、权限、缺权重等配置问题转人工，不无限重试。
- succeeded条件：基础与人声关联校验通过、必要音频完整、目录事务完成；质量degraded仍保留，不把succeeded等同于ready准确。
- 崩溃恢复先对账是否已有完整_SUCCESS；有则验证并登记，不能仅因数据库还running就重跑。NAS与DB不是同一个事务，用可重跑登记和对账补偿。

现有publisher还有需要注意的边界：run_id由输入hash、Git短SHA和部分元数据组成，未把所有模型权重/配置纳入指纹。第二版业务job可以先记录完整config hash，但不能仅改job表就宣称底层缓存已区分所有配置。要改变模型参数/权重时，需预处理负责人补齐缓存版本设计或明确升级release，不能在相同run路径覆盖旧产物。这是后续增强项，不影响只读消费现有结果。

## 九、步骤7：部署和运维（先测试，再审批切换）

建议新增独立release指针、systemd服务和API端口；名称可用harbeat-v2-api、harbeat-v2-worker，但端口先查占用再定。服务使用非root账号，API只读published，Worker只对指定staging/failed/published目录写；模型只读，数据库最小权限。

settings至少包含：新库DATABASE_URL（秘密）、HARBEAT_PREPROCESS_ROOT、业务PUBLIC_BASE_URL、schema支持版本、质量策略版本、GPU并发、作业超时/重试、lease秒数、任务有效期、Token验证参数、日志目录。配置缺失时启动失败，不回退到仓库内历史公网地址/默认密码。

健康检查分开：livez只判断进程；readyz检查新数据库连通和NAS挂载/必要目录可读，**不运行模型**。模型环境另用管理员诊断命令验收。保留request_id/job_id/track_id/run_id日志上下文，脱敏Token、密码、签名参数。

上线前必须演练：空库迁移、导入EDM、模拟RK断点下载、重启恢复、磁盘满/挂载消失、账号撤权、并发重复请求。备份数据库并验证恢复，NAS保留旧run；新服务切回旧版本前核对数据库迁移兼容性，不通过git reset线上目录回滚。

本轮只写参考文档与只读程序，没有创建这些服务、迁库、重启网关、变更GPU环境或发布新手机接口。
