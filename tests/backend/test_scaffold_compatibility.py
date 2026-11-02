"""Rule history guards must not interfere with the teammate's generic repository."""

from backend.models.user import User
from backend.repositories.base import BaseRepository


class Users(BaseRepository[User]):
    model = User


async def test_original_repository_crud_remains_available(db_session):
    repository = Users(db_session)
    user = await repository.create(User(username="compatibility", email="demo@example.invalid"))
    assert await repository.get_by_id(user.id) is user
    user.email = "updated@example.invalid"
    await db_session.flush()
    assert user in await repository.list_all()
    await repository.delete(user)
    assert await repository.get_by_id(user.id) is None
