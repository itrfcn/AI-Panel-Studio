"""
Database engine and session factory (SQLAlchemy 2.0 + SQLite).

设计要点：
- SQLite 默认开启外键约束（PRAGMA foreign_keys = ON），对齐 schema.md §1 设计原则
- 使用 sessionmaker 工厂 + FastAPI 依赖注入 get_db
- check_same_thread=False：FastAPI 多线程下安全使用 SQLite
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# SQLite 外键约束默认关闭，需在连接时开启
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """每个 SQLite 连接建立时自动开启外键约束。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


engine = create_engine(
    settings.DATABASE_URL,
    # SQLite 多线程下需要禁用 same_thread 检查
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    echo=False,  # dev 调试可改 True
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：注入数据库 Session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_engine() -> None:
    """建表入口（仅用于运行时 fallback；首选 scripts/init_db.py）。"""
    # 触发所有模型导入，确保 metadata 注册
    from app.models import (  # noqa: F401  pylint: disable=unused-import
        topic,
        guest,
        transcript,
        event_point,
        insight,
    )

    Base.metadata.create_all(bind=engine)
