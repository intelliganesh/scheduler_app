from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User

PROFILE_FIELDS = ("email", "full_name", "user_principal_name", "given_name", "surname", "department", "title", "company")


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.scalar(select(User).where(User.username == username))

    def upsert_from_ldap(self, db: Session, profile: dict[str, str | None]) -> User:
        user = self.get_by_username(db, profile["username"])
        if user is None:
            user = User(username=profile["username"])
            db.add(user)
        for field in PROFILE_FIELDS:
            setattr(user, field, profile.get(field))
        user.permissions = ",".join(profile.get("permissions") or []) or None
        user.is_active = True
        db.commit()
        db.refresh(user)
        return user
