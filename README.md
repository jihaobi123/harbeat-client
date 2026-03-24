# Street Dance MVP Backend

面向街舞舞者 App 的本地可运行 MVP 服务端，基于 `FastAPI + PostgreSQL + Redis + Docker Compose`。

## 当前能力

- 用户创建与查询
- 歌单导入
- 用户画像生成与查询
- 推荐列表获取
- 播放会话开始、事件上报、结束
- 统一 JSON 响应格式
- `/docs` OpenAPI 调试页面
- Docker Compose 一键启动 `app + postgres + redis + nginx`

## 项目结构

```text
app/
  shared/      # 配置、数据库、统一响应等通用能力
  modules/     # 按功能拆分的业务模块
    users/
      models.py
      schemas.py
      service.py
      router.py
    playlists/
    profiles/
    recommendations/
    sessions/
    health/
    router.py  # 统一注册模块路由
deploy/
  nginx.conf   # 网关代理
```

## 模块设计原则

- 每个业务功能一个文件夹，内部自带 `router / schemas / service`，需要落库时再加 `models`
- 通用能力统一放在 `app/shared/`，例如数据库连接、配置、统一响应格式
- 新增功能时，优先新建 `app/modules/<feature>/`，再在 `app/modules/router.py` 注册即可
- 模块之间如果没有直接依赖，就保持独立；只有明确复用时才引用其他模块的 service 或 model

## 启动方式

### 方式 1：本地 Python

1. 创建环境变量文件

```bash
cp .env.example .env
```

2. 按实际数据库修改 `.env`

```env
DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism
REDIS_URL=redis://localhost:6379/0
```

3. 安装依赖并启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

4. 打开文档

- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 健康检查: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 方式 2：Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

启动后访问：

- API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Nginx: [http://127.0.0.1](http://127.0.0.1)

## 联通测试建议

按这条主链路验证：

1. `POST /api/users`
2. `GET /api/users/{user_id}`
3. `POST /api/playlists/import`
4. `POST /api/profiles/generate`
5. `GET /api/profiles/{user_id}`
6. `POST /api/recommendations/for-user`
7. `POST /api/sessions/start`
8. `POST /api/sessions/event`
9. `POST /api/sessions/end`

## 示例请求

### 创建用户

```bash
curl -X POST http://127.0.0.1:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "guthrey",
    "dance_style": "hiphop",
    "level": "intermediate",
    "favorite_style": "old_school"
  }'
```

### 导入歌单

```bash
curl -X POST http://127.0.0.1:8000/api/playlists/import \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "playlist_name": "practice_list",
    "songs": [
      {
        "title": "song_a",
        "artist": "artist_a",
        "audio_url": "https://example.com/song-a.mp3"
      },
      {
        "title": "song_b",
        "artist": "artist_b",
        "audio_url": "https://example.com/song-b.mp3"
      }
    ]
  }'
```

## 数据库说明

- 应用启动时会自动创建表，方便 MVP 快速联通测试。
- 正式环境建议补 `Alembic` migration，而不是继续依赖自动建表。
- 数据库只允许服务端连接，Flutter 端不直接访问数据库。

## 当前实现边界

- JWT 配置已预留，但鉴权接口和鉴权中间件还没有接入。
- Redis 配置已接入项目结构，但当前 MVP 主要用于后续缓存/会话扩展，核心 CRUD 先以 PostgreSQL 为主。
- 推荐逻辑是规则打分版，符合“先规则推荐，后续再做 AI 推荐”的阶段目标。
