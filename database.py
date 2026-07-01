from sqlalchemy import create_engine

from dotenv import load_dotenv
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings


# Default to SQLite if nothing is in the .env file
DATABASE_URL = settings.DATABASE_URL

# Automatically apply the SQLite-specific multithreading fix if needed
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    # Postgres setup
    engine = create_engine(DATABASE_URL)

sessionLocal = sessionmaker(bind=engine, autoflush= False, autocommit = False )

Base = declarative_base()

def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()