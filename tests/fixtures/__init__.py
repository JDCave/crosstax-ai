"""Shared test fixtures and factory helpers."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


@pytest.fixture()
async def user_factory(db_session: AsyncSession):
    """Factory fixture to create User instances in tests."""

    async def _create(
        username: str = "testuser",
        email: str = "test@example.com",
    ) -> User:
        user = User(username=username, email=email)
        db_session.add(user)
        await db_session.flush()
        return user

    return _create
