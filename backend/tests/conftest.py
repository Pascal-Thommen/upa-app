"""Pytest configuration and global test fixtures for UPA App backend."""

import pytest
from src.database import Base, engine


@pytest.fixture(autouse=True, scope="session")
def setup_database_schema():
    """Ensures database schema and tables are created before running tests."""
    Base.metadata.create_all(bind=engine)
    yield
