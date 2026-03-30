from sqlalchemy import text

from app.db import Base, engine
from app.models import RecommendationLog, Song, Track, User, UserInteractionLog, UserRadar


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("✅ 数据库初始化完成（已确保 pgvector 扩展 + 建表）")
