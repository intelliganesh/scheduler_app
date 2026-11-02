from sqlalchemy import bindparam, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, make_transient_to_detached
from sqlalchemy.orm.attributes import set_committed_value

from app.models.user import User
from app.utils.query_store import query_store

PROFILE_FIELDS = ("email", "full_name", "user_principal_name", "given_name", "surname", "department", "title", "company")


def _statement(query_id: str, parameters: dict):
    """Load SQL by number and bind values with the existing model's driver types."""
    try:
        sql = query_store.get(query_id)
    except (OSError, ValueError, KeyError) as exc:
        raise SQLAlchemyError("Authentication SQL definitions are unavailable.") from exc
    command = text(sql)
    for field in parameters:
        column = User.__table__.c.id if field == "user_id" else User.__table__.c[field]
        command = command.bindparams(bindparam(field, type_=column.type))
    return command


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> User | None:
        parameters = {"username": username}
        command = _statement("5", parameters).columns(**{column.key: column.type for column in User.__table__.columns})
        row = db.execute(command, parameters).mappings().first()
        if row is None:
            return None
        existing = db.identity_map.get(db.identity_key(User, row["id"]))
        if existing is not None:
            state = inspect(existing)
            for field, value in row.items():
                if field in state.expired_attributes or field not in state.dict:
                    set_committed_value(existing, field, value)
            return existing
        user = User(**dict(row))
        make_transient_to_detached(user)
        # Hydrate/associate the identity without generating an ORM SELECT or write.
        return db.merge(user, load=False)

    def upsert_from_ldap(self, db: Session, profile: dict[str, str | None]) -> User:
        user = self.get_by_username(db, profile["username"])
        values = {field: profile.get(field) for field in PROFILE_FIELDS}
        values["permissions"] = ",".join(profile.get("permissions") or []) or None
        values["is_active"] = True
        if user is None:
            parameters = {"username": profile["username"], **values}
            db.execute(_statement("6", parameters), parameters)
        else:
            changed = {field: value for field, value in values.items() if getattr(user, field) != value}
            if changed:
                parameters = {"user_id": user.id, **values}
                db.execute(_statement("7", parameters), parameters)
        db.commit()
        # Reload generated IDs/defaults and expired fields through query 8, keeping
        # the original commit boundary and the same session-associated User object.
        return self.get_by_username(db, profile["username"])
