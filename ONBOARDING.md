# HarBeat 维护者交接配置手册

> **本文档的目的**：让下一任维护者从零开始，按顺序操作即可拿到 HarBeat 全部三台节点的控制权。
>
> **配套阅读**：[`HANDOVER.md`](HANDOVER.md) 介绍业务架构、模块、数据流；本文档只讲**怎么配置 / 怎么接管 / 怎么运维**。
>
> **版本**：2026-04-27 修订（已反映 Jetson 重装到 `markpen117@gmail.com` tailnet、阿里云 ECS 与 Jetson 均已 systemd 化的当前状态）

---

## 目录

- [0. TL;DR：5 分钟速览](#0-tldr5-分钟速览)
- [1. 系统拓扑与当前事实](#1-系统拓扑与当前事实)
- [2. 交接前置准备（你给下任的东西）](#2-交接前置准备你给下任的东西)
- [3. Tailscale 配置](#3-tailscale-配置)
  - [3.1 方案 A：tailnet 直接转交（推荐）](#31-方案-atailnet-直接转交推荐)
  - [3.2 方案 B：下任用自己的 Tailscale 账号](#32-方案-b下任用自己的-tailscale-账号)
- [4. 阿里云 ECS 配置](#4-阿里云-ecs-配置)
  - [4.1 控制台与账号](#41-控制台与账号)
  - [4.2 SSH 与基础信息](#42-ssh-与基础信息)
  - [4.3 关键文件与服务](#43-关键文件与服务)
  - [4.4 nginx 配置](#44-nginx-配置)
  - [4.5 cloud_gateway 配置](#45-cloud_gateway-配置)
  - [4.6 切换到下任 tailnet 时必改项](#46-切换到下任-tailnet-时必改项)
- [5. Jetson Orin NX 配置](#5-jetson-orin-nx-配置)
  - [5.1 物理与登录](#51-物理与登录)
  - [5.2 关键文件与服务](#52-关键文件与服务)
  - [5.3 .env 内容](#53-env-内容)
  - [5.4 数据库 / Redis](#54-数据库--redis)
  - [5.5 systemd 服务](#55-systemd-服务)
  - [5.6 Tailscale 重新登录步骤](#56-tailscale-重新登录步骤)
- [6. 凭证与密码清单](#6-凭证与密码清单)
- [7. 第一天验收清单（让下任跑一遍）](#7-第一天验收清单让下任跑一遍)
- [8. 日常运维 Cheat Sheet](#8-日常运维-cheat-sheet)
- [9. 故障排查决策树](#9-故障排查决策树)
- [10. 推荐的硬性改进项](#10-推荐的硬性改进项)
- [附录 A：systemd 单元文件全文](#附录-asystemd-单元文件全文)
- [附录 B：常用 curl 一键体检](#附录-b常用-curl-一键体检)

---

## 0. TL;DR：5 分钟速览

下任要拿到三个东西，三件事就齐了：

1. **Tailscale tailnet 访问权**（同账号 or 自己重新登录两台机器）
2. **阿里云 ECS root 登录**（`8.136.120.255`，控制台账号 + SSH 密码）
3. **Jetson 本地访问**（`mark` 用户密码 + 物理位置）

只要这三块到位，公网 `http://8.136.120.255/` 就在他控制下了。其它（数据库密码、Spotify Key、Git 协作权限）属于二级凭证，按 [第 6 节](#6-凭证与密码清单)清单交。

---

## 1. 系统拓扑与当前事实

### 拓扑图

```text
浏览器
   │ HTTP :80
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 阿里云 ECS    8.136.120.255   (Ubuntu 22.04, 2核4G, 杭州)    │
│  ├─ nginx (systemd)            :80  反代到 :8080             │
│  ├─ cloud_gateway (systemd)    :8080  FastAPI 透传到 Jetson │
│  └─ tailscaled (systemd)       加入 markpen117@ tailnet      │
└─────────────────────────────────────────────────────────────┘
   │ Tailscale 加密虚拟网（100.x.x.x）
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Jetson Orin NX   tailnet IP: 100.87.142.21（以 tailscale ip 为准）│
│  ├─ harbeat (systemd, FastAPI uvicorn)  :8000  业务后端     │
│  ├─ postgresql 14 (systemd)             :5432  本地数据库   │
│  ├─ redis-server (systemd)              :6379  缓存/任务锁  │
│  ├─ tailscaled (systemd)                加入同一 tailnet     │
│  └─ /home/mark/harbeat/data/           音频/模型/向量索引   │
└─────────────────────────────────────────────────────────────┘
```

### 当前事实表（**更新本表是每次维护交接的硬性要求**）

| 项目 | 当前值 | 备注 |
|---|---|---|
| 公网入口 | `http://8.136.120.255/` | 阿里云 ECS 公网 IP |
| 阿里云控制台账号 | `nick6331***`（请确认） | ECS 在此账号下 |
| ECS hostname | `iZbp15a9gsa7lz3xezxc1lZ` | |
| ECS tailnet IP | `100.125.245.31` | 由 `tailscale ip -4` 给出，可能重连后变化 |
| Jetson tailnet IP | `100.87.142.21` | **以 `tailscale ip -4` 实时查询为准**，不要硬编码 |
| Jetson 局域网 IP | 用 `ip a` 现场查 | 网线接的本地 NAT |
| Tailscale 账号 | `markpen117@gmail.com` | 控制台 https://login.tailscale.com/admin |
| Git 远端 | `https://github.com/jihaobi123/harbeat-client.git` | 主分支 `feature/superpowered-player` |
| 数据库连接 | `postgresql://harbeat@127.0.0.1:5432/rhythm_prism` | Jetson 本地 |

> ⚠️ 已废弃：旧 Jetson `100.91.30.53`（在 `wwwxxx0501@` tailnet 下）和旧 RDS `pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com`，文档/代码若残留这些字符串均为历史遗留，可以无视。

---

## 2. 交接前置准备（你给下任的东西）

打钩交付，缺一不可：

- [ ] 本文档（`ONBOARDING.md`）+ 业务文档（[`HANDOVER.md`](HANDOVER.md)）的 Git 仓库读权限
- [ ] **Tailscale**：邀请他加入 tailnet（[3.1](#31-方案-atailnet-直接转交推荐)）或告知重做流程（[3.2](#32-方案-b下任用自己的-tailscale-账号)）
- [ ] **阿里云**：账号 + 密码（含二次验证手机或 RAM 子账号）
- [ ] **ECS root**：SSH 密码或公钥
- [ ] **Jetson**：物理位置、`mark` 用户密码、显示器/HDMI 准备方式
- [ ] [第 6 节](#6-凭证与密码清单)的密码清单（**走密码管理器，绝不进 Git**）
- [ ] GitHub 仓库 `jihaobi123/harbeat-client` 的 collaborator 权限
- [ ] 一通 30 分钟当面会议，跑一遍 [第 7 节](#7-第一天验收清单让下任跑一遍)的验收清单

---

## 3. Tailscale 配置

> Tailscale 是这套系统的网络底座。**ECS 和 Jetson 必须在同一个 tailnet**，否则 ECS 永远找不到 Jetson，公网访问就是 hang 住。

### 3.1 方案 A：tailnet 直接转交（推荐）

适合：你不再需要这个 tailnet，或者下任接手后由他主导。

**步骤**：

1. 用 `markpen117@gmail.com` 登录 https://login.tailscale.com/admin/settings/general
2. **Settings → User Management → Invite users** → 输入下任邮箱（必须是 Google / GitHub / Microsoft 等支持的 SSO）
3. 下任收到邮件接受邀请后，在控制台 → **Machines** 页，把他设为 **Owner / Admin**
4. 控制台 → **Machines** → 给两台机器打开 **"Disable key expiry"**，否则默认 90 天 key 过期，机器会突然 offline
5. （可选）你想完全退出：**Settings → Account → Leave tailnet**

**好处**：
- 两台机器的 100.x IP **保持不变**
- 阿里云 ECS 的 `JETSON_BASE_URL` 不用改
- 全程零停机

### 3.2 方案 B：下任用自己的 Tailscale 账号

适合：tailnet 不交、由他自己开新 tailnet 接手。这种方案两台机器都要重新登录 tailnet，**Jetson 的 100.x IP 会变**，必须同步改阿里云那边的 `JETSON_BASE_URL`。

#### 3.2.1 ECS 切 tailnet

```bash
ssh root@8.136.120.255

tailscale logout                                    # 退出旧 tailnet
nohup tailscale up --hostname=harbeat-aliyun-ecs --accept-routes \
    > /tmp/tsup.log 2>&1 &
sleep 5
cat /tmp/tsup.log
# 输出会包含:  To authenticate, visit: https://login.tailscale.com/a/xxxxx
# 把这个 URL 复制到任意一台浏览器，用下任账号登录授权

# 授权后验证：
tailscale status         # 应该看到 ECS 自己 + Jetson（如果也已切了）
tailscale ip -4          # 记下 ECS 的新 100.x IP（用不上但备查）
```

#### 3.2.2 Jetson 切 tailnet

通过 VNC 或局域网 SSH 进入 Jetson（**不要走 tailnet SSH**，因为 tailnet 即将断）：

```bash
sudo tailscale logout
sudo tailscale up --hostname=jetson --accept-routes
# 同样浏览器授权

tailscale ip -4          # ★把这个 IP 记下来，下面要写进 ECS 的 .env
```

#### 3.2.3 修改 ECS 的 JETSON_BASE_URL（必做）

```bash
ssh root@8.136.120.255

# 用上一步拿到的 Jetson 新 IP 替换 <NEW_IP>
NEW_IP="100.x.x.x"
sed -i "s|^JETSON_BASE_URL=.*|JETSON_BASE_URL=http://${NEW_IP}:8000|" /opt/harbeat-api/.env
cat /opt/harbeat-api/.env

systemctl restart cloud_gateway
systemctl status cloud_gateway --no-pager | head -10
curl -sS http://127.0.0.1:8080/health        # 应返回 200
curl -sS http://127.0.0.1/                   # 应返回 200 + index.html
```

#### 3.2.4 控制台收尾

- https://login.tailscale.com/admin/machines → 两台机器都打开 **"Disable key expiry"**
- 给关键节点写有意义的 hostname（已用 `harbeat-aliyun-ecs` / `jetson`）

---

## 4. 阿里云 ECS 配置

### 4.1 控制台与账号

| 项 | 值 |
|---|---|
| 主账号 | `nick6331***`（请确认/补全） |
| 控制台 | https://ecs.console.aliyun.com/ |
| 实例 ID | `i-bp15a9gsa7lz3xezxc1lz`（hostname 含 ID） |
| 区域 | 华东1（杭州） |
| 规格 | 2 vCPU / 4 GB |
| 公网 IP | `8.136.120.255` |
| 系统 | Ubuntu 22.04 |

**控制台必须确认的设置**（建议截图存档）：

1. **实例 → 安全组 → 入方向规则**，必须包含：
   - `22/tcp` 0.0.0.0/0 ALLOW（SSH）
   - `80/tcp` 0.0.0.0/0 ALLOW（HTTP）
   - 不要开 `8080/8000/5432/6379` 等内部端口给公网
   - 如配 HTTPS 再开 `443/tcp`
2. **续费提醒**：到期前邮件通知。当前到期时间请在控制台查看并记入交接备忘。
3. **快照策略**（如有）：建议每周对系统盘自动快照保留 4 份。

### 4.2 SSH 与基础信息

```bash
ssh root@8.136.120.255            # 密码走密码管理器交接
```

> Jetson 上 `mark` 用户已配公钥免密到 ECS，必要时可从 Jetson 跳板。

### 4.3 关键文件与服务

```text
/etc/nginx/sites-enabled/default              # Nginx 配置
/etc/nginx/nginx.conf                          # Nginx 主配置
/var/log/nginx/{access,error}.log              # Nginx 日志
/opt/harbeat-api/                              # cloud_gateway 项目
  ├── app/main.py                              # FastAPI 透传代码
  ├── .env                                     # JETSON_BASE_URL 在这里
  ├── .env.bak.*                               # 历史备份
  └── .venv/                                   # Python 虚拟环境
/etc/systemd/system/cloud_gateway.service      # systemd 单元
/var/log/cloud_gateway.log                     # cloud_gateway 运行日志
/etc/systemd/system/tailscaled.service         # Tailscale（apt 自带）
```

systemd 服务列表（都应 active running）：

```bash
systemctl status nginx cloud_gateway tailscaled --no-pager
```

### 4.4 nginx 配置

当前 `/etc/nginx/sites-enabled/default` 内容（请保持）：

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 500m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 30s;
        proxy_send_timeout 300s;
    }
}
```

改完务必：

```bash
nginx -t && systemctl reload nginx
```

### 4.5 cloud_gateway 配置

`/opt/harbeat-api/.env`：

```ini
JETSON_BASE_URL=http://100.87.142.21:8000
# 如有需要可加：
# HTTP_TIMEOUT=300
```

`/opt/harbeat-api/app/main.py` 是一个 ~50 行的 FastAPI，三个路由：

- `GET /health` — gateway 自身健康
- `GET /jetson/health` — 通过 tailnet 透传 Jetson 的 `/health`
- `/{path:path}` — 通用透传（任意方法，包括上传文件）

**注意**：代码里没有调 `python-dotenv`，所以 `.env` 必须靠 systemd 的 `EnvironmentFile=` 注入。手动 `python -m uvicorn ...` 不会自动读 `.env`，会用代码里写死的旧默认值——**这是一个之前已经踩过的坑**，systemd 化以后才彻底规避。

### 4.6 切换到下任 tailnet 时必改项

只有一项：`/opt/harbeat-api/.env` 里的 `JETSON_BASE_URL`，改完 `systemctl restart cloud_gateway` 即可。

---

## 5. Jetson Orin NX 配置

### 5.1 物理与登录

| 项 | 值 |
|---|---|
| 硬件 | NVIDIA Jetson Orin NX（8GB / 16GB RAM） |
| 系统 | Ubuntu (JetPack 6.x, ARM64, CUDA 11.4+) |
| 用户 | `mark`（密码走密码管理器） |
| 物理位置 | （**请补充**：放在哪、电源如何接、网络如何接） |
| VNC | 现场或同局域网时使用，端口 `:5901` 默认 |
| 局域网 SSH | `ssh mark@<局域网 IP>`（用 `ip a` 查） |
| 远程 SSH | `ssh mark@<tailnet IP>`（如 `100.87.142.21`） |

**首次接管后立刻做**：

```bash
# 在你自己电脑上
ssh-copy-id mark@<jetson tailnet IP>     # 推公钥免密
# 之后改密
ssh mark@<jetson tailnet IP>
passwd                                   # 改 mark 的密码并记入密码管理器
```

### 5.2 关键文件与服务

```text
/home/mark/harbeat/                       # 项目根（git 仓库）
  ├── app/                                # FastAPI 业务代码
  ├── web/                                # 前端源码
  │   └── dist/                           # 构建产物（FastAPI 直接挂载）
  ├── data/
  │   ├── music-files/                    # 音频原文件 ⚠️ 持久数据，需备份
  │   ├── songs/                          # 下载的歌曲
  │   ├── clap_model/                     # CLAP 模型权重 ~600MB
  │   └── chroma_db/                      # 向量索引 ⚠️ 持久数据，需备份
  ├── .env                                # 环境变量（DATABASE_URL/JWT_SECRET 等）
  └── uvicorn.log                         # 运行日志（systemd 也写到这里）

/home/mark/venvs/harbeat/                 # Python 虚拟环境
  └── bin/uvicorn                         # systemd 用的 uvicorn

/var/lib/postgresql/14/main/              # PostgreSQL 数据目录 ⚠️ 持久数据

/etc/systemd/system/harbeat.service       # 后端 systemd 单元
/etc/systemd/system/postgresql.service    # apt 自带
/etc/systemd/system/redis-server.service  # apt 自带
/etc/systemd/system/tailscaled.service    # apt 自带
```

服务总览（都应 active running）：

```bash
sudo systemctl status harbeat postgresql redis-server tailscaled --no-pager
```

### 5.3 .env 内容

`/home/mark/harbeat/.env` 模板（**当前真实值走密码管理器**）：

```ini
APP_NAME=Street Dance MVP API
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000

DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@127.0.0.1:5432/rhythm_prism
REDIS_URL=redis://127.0.0.1:6379/0

JWT_SECRET=<32 字节随机串，建议接管后立刻轮换>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080

UPLOAD_DIR=/home/mark/harbeat/data/music-files

SPOTIPY_CLIENT_ID=<...>
SPOTIPY_CLIENT_SECRET=<...>
```

**轮换 `JWT_SECRET` 的影响**：所有用户的现有 token 失效，下次访问会被强制登出。这是**接管时强烈建议做的安全动作**。

### 5.4 数据库 / Redis

```bash
# 状态
sudo systemctl status postgresql redis-server

# 连接 PostgreSQL（密码默认 Hb12345678，建议接管后改）
PGPASSWORD=Hb12345678 psql -h 127.0.0.1 -U harbeat -d rhythm_prism
\dt                                       # 列所有表
\d library_songs                          # 看某表结构

# 改 PG 密码
ALTER USER harbeat WITH PASSWORD '<new pw>';
# 改完同步到 .env 的 DATABASE_URL
```

**手动备份**：

```bash
mkdir -p /home/mark/backups
pg_dump -h 127.0.0.1 -U harbeat rhythm_prism | gzip \
    > /home/mark/backups/db_$(date +%F).sql.gz
```

**自动备份（强烈建议加 cron）**：

```bash
crontab -e
# 添加：每天 03:00 备份并保留 14 天
0 3 * * * pg_dump -h 127.0.0.1 -U harbeat rhythm_prism 2>/dev/null | gzip > /home/mark/backups/db_$(date +\%F).sql.gz && find /home/mark/backups -name 'db_*.sql.gz' -mtime +14 -delete
```

### 5.5 systemd 服务

`/etc/systemd/system/harbeat.service`（已创建，详见 [附录 A](#附录-asystemd-单元文件全文)）。

常用：

```bash
sudo systemctl status harbeat
sudo systemctl restart harbeat
sudo journalctl -u harbeat -f
tail -f /home/mark/harbeat/uvicorn.log
```

**部署新代码标准流程**：

```bash
cd /home/mark/harbeat
git pull
# 后端依赖变了：
/home/mark/venvs/harbeat/bin/pip install -r requirements.jetson.txt
# 前端代码变了：
cd web && npm install && npm run build && cd ..
# 重启
sudo systemctl restart harbeat
sudo journalctl -u harbeat -n 50 --no-pager       # 看启动是否 OK
```

### 5.6 Tailscale 重新登录步骤

VNC 或局域网 SSH 上 Jetson 后：

```bash
sudo tailscale logout
sudo tailscale up --hostname=jetson --accept-routes
# 屏幕输出 https://login.tailscale.com/a/xxxxx → 浏览器授权
tailscale status
tailscale ip -4               # ★ 同步给 ECS 改 .env
```

---

## 6. 凭证与密码清单

> ⚠️ **下面所有 `<...>` 实际值都通过密码管理器（1Password / Bitwarden / Lastpass）交接，绝不写进 Git。**

| 类别 | 名称 | 用途 / 在哪用 |
|---|---|---|
| 阿里云 | 主账号 + 密码 + 二次验证 | 控制台、ECS 续费、安全组管理 |
| 阿里云 | ECS root 密码 / SSH 私钥 | `ssh root@8.136.120.255` |
| Jetson | `mark` 用户密码 | 本地 / 远程登录 |
| Jetson | sudo 密码 | 同上（Ubuntu 默认 sudo 用账号密码） |
| Jetson | `mark` 的 SSH 私钥（如有） | 跳板登 ECS |
| 数据库 | `harbeat` PostgreSQL 密码（默认 `Hb12345678`） | `.env` `DATABASE_URL` |
| 后端 | `JWT_SECRET` | `.env` |
| Spotify | `SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET` | `.env` |
| Tailscale | 账号登录方式（Google SSO `markpen117@gmail.com`） | https://login.tailscale.com/admin |
| GitHub | 仓库协作者 | https://github.com/jihaobi123/harbeat-client |
| 域名（如有） | DNS 解析账号 | 解析到 `8.136.120.255` |

**接管后强烈建议立刻轮换**：
- PostgreSQL `harbeat` 密码 → 同步改 `.env` → `systemctl restart harbeat`
- `JWT_SECRET` → `systemctl restart harbeat`（用户会被强制重登）
- ECS root 密码（aliyun 控制台 → 重置实例密码）

---

## 7. 第一天验收清单（让下任跑一遍）

按顺序执行，每一步必须看到 ✅ 才往下走。

### 7.1 网络

```bash
curl -sS -o /dev/null -w "/      : %{http_code}\n" http://8.136.120.255/
curl -sS -o /dev/null -w "/health: %{http_code}\n" http://8.136.120.255/health
```

期望：`/  : 200` 和 `/health: 200`。

### 7.2 阿里云 ECS

```bash
ssh root@8.136.120.255 << 'EOF'
echo '--- services ---'
systemctl is-active nginx cloud_gateway tailscaled
echo '--- ports ---'
ss -ltnp | grep -E ':80|:8080'
echo '--- tailnet ---'
tailscale status | head -5
echo '--- gateway -> jetson ---'
curl -m 5 -sS http://127.0.0.1:8080/health && echo
EOF
```

期望：三个 `active`、80 和 8080 监听、tailnet 看见 Jetson、gateway `/health` 返回 200。

### 7.3 Jetson

```bash
ssh mark@<Jetson tailnet IP> << 'EOF'
echo '--- services ---'
sudo systemctl is-active harbeat postgresql redis-server tailscaled
echo '--- backend ---'
curl -m 5 -sS http://127.0.0.1:8000/health && echo
echo '--- db ---'
PGPASSWORD=Hb12345678 psql -h 127.0.0.1 -U harbeat -d rhythm_prism -c "select count(*) from library_songs;"
echo '--- disk ---'
df -h /home/mark/harbeat/data
EOF
```

期望：四个 `active`、`/health` 200、SQL 查询有结果、磁盘剩余空间合理（建议 > 20GB）。

### 7.4 业务端到端

浏览器打开 `http://8.136.120.255/`：

- [ ] 注册一个测试账号 `test@xxx.com`
- [ ] 登录成功，看见空曲库页面
- [ ] 上传一首 mp3
- [ ] 等 1~2 分钟，曲库列表里出现这首歌，BPM/Key 显示出来
- [ ] 点进去能看到 4 轨 stem 播放器
- [ ] 退出登录，重新登录还能进得去

全部打钩 → 交接成功。

---

## 8. 日常运维 Cheat Sheet

### 阿里云 ECS

```bash
ssh root@8.136.120.255

# 状态
systemctl status nginx cloud_gateway --no-pager
ss -ltnp | grep -E ':80|:8080'
tailscale status

# 重启
systemctl restart cloud_gateway        # 改了 .env 必做
systemctl reload nginx                 # 改了 nginx 配置必做

# 日志
journalctl -u cloud_gateway -f
tail -f /var/log/cloud_gateway.log
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### Jetson

```bash
ssh mark@<jetson tailnet IP>

# 状态
sudo systemctl status harbeat postgresql redis-server tailscaled --no-pager
ss -ltnp | grep -E ':8000|:5432|:6379'

# 重启 / 部署
sudo systemctl restart harbeat
sudo journalctl -u harbeat -f
tail -f /home/mark/harbeat/uvicorn.log

# 数据库
PGPASSWORD=Hb12345678 psql -h 127.0.0.1 -U harbeat -d rhythm_prism

# 备份
pg_dump -h 127.0.0.1 -U harbeat rhythm_prism | gzip > /home/mark/backups/db_$(date +%F).sql.gz
```

### 部署一次新代码

```bash
# Jetson
cd /home/mark/harbeat
git pull
cd web && npm install && npm run build && cd ..
sudo systemctl restart harbeat
sudo journalctl -u harbeat -n 30 --no-pager
```

---

## 9. 故障排查决策树

> 所有"页面打不开"问题按这个流程走，5 分钟内可定位到那一段。

```text
浏览器打不开 http://8.136.120.255/
  │
  ├─ Test-NetConnection / telnet 8.136.120.255 80 通吗？
  │     不通 → 阿里云安全组没开 80 / ECS 死机 / 公网欠费
  │     通 → 继续
  │
  ▼
ssh root@8.136.120.255
  │
  ├─ systemctl is-active nginx cloud_gateway
  │     有 inactive → systemctl restart 它 → 看 journalctl
  │     都 active → 继续
  │
  ├─ curl -m 5 http://127.0.0.1:8080/health
  │     超时/000 → cloud_gateway 卡死 → systemctl restart cloud_gateway
  │     200 → 继续
  │
  ├─ tailscale status   ← 看 Jetson 是否 online
  │     Jetson offline → 去 Jetson 修 tailscale（VNC 或局域网 SSH）
  │     Jetson online 但 IP 跟 .env 里的不一致 → 改 .env 的 JETSON_BASE_URL
  │     一致 → 继续
  │
  ├─ curl -m 5 http://<jetson ip>:8000/health  ← ECS 直连 Jetson
  │     超时/000 → Jetson uvicorn 挂了 → ssh mark@jetson + systemctl restart harbeat
  │     200 → 但 curl http://127.0.0.1:8080/ 仍超时 → cloud_gateway 进程卡了 → restart
  │
  └─ curl -m 5 http://127.0.0.1/    ← 经 nginx
        超时 → nginx 卡死 → systemctl restart nginx
        200 → 应该公网也通了，再 curl 一次公网验证
```

**常见症状对照**：

| 症状 | 真因 | 修法 |
|---|---|---|
| 公网 30s hang，TCP 通 | tailnet 不通 / `JETSON_BASE_URL` 指错 / Jetson 后端挂 | 看 tailscale status；改 .env；重启 harbeat |
| 公网 502 Bad Gateway | cloud_gateway 没起来 | `systemctl status cloud_gateway` |
| 公网 200 但所有 API 401 | JWT_SECRET 改过，token 失效 | 用户重登；正常现象 |
| 上传歌曲一直卡在"分析中" | Jetson 8GB 内存 + Demucs/CLAP OOM | 重启 harbeat；考虑加 swap |
| `tailscale status` 显示节点 offline 4h+ | tailscaled 挂了 | `sudo systemctl restart tailscaled` |
| 改了 ECS 的 `.env` 但行为没变化 | 没重启 cloud_gateway | `systemctl restart cloud_gateway` |

---

## 10. 推荐的硬性改进项

接管后值得排优先级做的事：

1. **加 PostgreSQL 自动备份 cron**（[5.4](#54-数据库--redis)）— 现在数据库只在 Jetson 一份，磁盘炸就完蛋。
2. **轮换敏感凭证**：`JWT_SECRET`、PG 密码、ECS root 密码。
3. **加 HTTPS**：买/绑域名 → `certbot --nginx`，避免明文 token。
4. **Tailscale 控制台关掉 key expiry**：否则机器 90 天后会突然 offline。
5. **写一个状态页 / 心跳监控**：用 UptimeRobot 或者 cron 每分钟 curl `/health`，失败邮件告警。
6. **Jetson 加 swap**：8GB 内存上跑 Demucs+CLAP 偶尔 OOM，加 8GB swap 能救命。
7. **整理 `scripts/` 目录**：当前根目录有大量 `_diag_*` / `_check_*` 调试脚本，建议归档到 `scripts/_legacy/` 或删除。
8. **HANDOVER.md 同步当前事实**：里面 Jetson IP 仍写的是已废弃的 `100.91.30.53`、systemd 章节写的是"暂无"，可一次性扫平。

---

## 附录 A：systemd 单元文件全文

### A.1 阿里云 ECS：`/etc/systemd/system/cloud_gateway.service`

```ini
[Unit]
Description=Harbeat Cloud Gateway (FastAPI proxy to Jetson)
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/harbeat-api
EnvironmentFile=/opt/harbeat-api/.env
ExecStart=/opt/harbeat-api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/var/log/cloud_gateway.log
StandardError=append:/var/log/cloud_gateway.log

[Install]
WantedBy=multi-user.target
```

启用：

```bash
systemctl daemon-reload
systemctl enable --now cloud_gateway
```

### A.2 Jetson：`/etc/systemd/system/harbeat.service`

```ini
[Unit]
Description=Harbeat FastAPI Backend
After=network-online.target postgresql.service redis-server.service tailscaled.service
Wants=network-online.target postgresql.service redis-server.service tailscaled.service

[Service]
Type=simple
User=mark
Group=mark
WorkingDirectory=/home/mark/harbeat
EnvironmentFile=/home/mark/harbeat/.env
ExecStart=/home/mark/venvs/harbeat/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/home/mark/harbeat/uvicorn.log
StandardError=append:/home/mark/harbeat/uvicorn.log
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now harbeat
```

---

## 附录 B：常用 curl 一键体检

把这个保存成 `~/bin/harbeat-check.sh` 给下任，平时跑一下就知道整条链路死活。

```bash
#!/usr/bin/env bash
# 一键体检：在任何一台能联网的机器上跑

PUB="http://8.136.120.255"

echo "=== 公网 ==="
for path in / /health /api/auth/me; do
    code=$(curl -m 8 -sS -o /dev/null -w "%{http_code}" "${PUB}${path}")
    printf "  %-20s %s\n" "$path" "$code"
done

echo
echo "=== 阿里云 ECS（需 SSH） ==="
ssh -o ConnectTimeout=5 root@8.136.120.255 '
    systemctl is-active nginx cloud_gateway tailscaled | paste -d" " - - -
    curl -m 5 -sS -o /dev/null -w "gateway /health: %{http_code}\n" http://127.0.0.1:8080/health
    tailscale status | head -5
'
```

期望全部 200 / active。

---

## 文档约定

- 修改本文档后请更新顶部"版本"行 + 第 1 节"当前事实表"。
- 任何 IP/账号变更必须**当天**同步进本文档，否则下下任继续踩坑。
- 凭证类信息**永远不进 Git**，本文档只放占位符（`<...>`）。

*交接顺利。*
