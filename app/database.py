import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Fetch DB URL from environment variables (set in docker-compose.yml)
# Default provided for local testing safety
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/docx_db")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency Injection for FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()