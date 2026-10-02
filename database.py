import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kiosco.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}


def _crear_engine(url):
    """Railway entrega la URL sin especificar el driver de Postgres ("postgresql://" a secas).
    Sin decirlo explícito, qué driver elige SQLAlchemy por default depende de la versión instalada
    en cada build — nos pasó: un deploy nuevo instaló una versión que intentó usar psycopg v3 (no
    está en requirements.txt) en vez de psycopg2, y el backend entero no llegaba ni a arrancar.
    Se fuerza psycopg2 (el que está declarado) y, si por algún motivo no está disponible en el
    entorno, se cae a psycopg v3 en vez de romper el arranque."""
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        try:
            import psycopg2  # noqa: F401
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        except ImportError:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, connect_args=connect_args)


engine = _crear_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
