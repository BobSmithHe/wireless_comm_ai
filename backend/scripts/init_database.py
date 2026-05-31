"""
Initialize database tables.
Run: python scripts/init_database.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config.database import engine, Base
from src.database.models import *  # noqa: F401,F403 - import all models for table creation


def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")


if __name__ == "__main__":
    init_db()
