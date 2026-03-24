from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api import music# 新增引入：数据库引擎、基类和模型
from api import sessions # 引入新的路由
from api import playlists # 引入歌单路由

from core.database import engine, Base
from models import track 
from models import session # 引入新的模型，让 lifespan 自动建表
from models import playlist # 引入歌单模型，触发自动建表
import contextlib

# 使用寿命周期管理器，在 App 启动时自动建表
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # 自动在 PostgreSQL 中创建所有定义好的表
        await conn.run_sync(Base.metadata.create_all)
    yield

# 把 lifespan 挂载到 FastAPI 实例上
app = FastAPI(title="Street Dance App MVP", lifespan=lifespan)

# 挂载模拟 NAS 的静态文件服务
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 注册模块路由
app.include_router(music.router)
app.include_router(sessions.router) # 注册会话路由
app.include_router(playlists.router) # 注册歌单路由

@app.get("/health")
def health_check():
    return {"status": "ok"}