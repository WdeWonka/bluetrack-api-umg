from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from src.core.config import settings

# Motor SQLAlchemy
engine = create_engine(
    settings.DATABASE_URL,
    echo=True,      # True solo en desarrollo (muestra las queries)
    future=True
)

# SessionLocal: fábrica de sesiones
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Dependencia para inyectar sesión en rutas y servicios
def get_db() -> Generator[Session, None, None]:
    """
    Crea una sesión de base de datos y la cierra al finalizar el request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
