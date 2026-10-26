from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.auth_service import AuthService
from app.services.mock_auth_service import MockAuthService
from app.config.menu_config import get_menu_config
from app.config.settings import get_settings
from app.utils.auth_exceptions import (
    AuthenticationUnavailableError,
    AuthorizationDeniedError,
    InvalidCredentialsError,
    LoginRateLimitedError,
)
from app.utils.security import create_access_token


class AuthController:
    def __init__(self, service: AuthService | None = None):
        self.service = service or AuthService()

    def login(self, db: Session, username: str, password: str) -> tuple[str, User]:
        try:
            if get_settings().auth_mode == "mock":
                profile = MockAuthService().authenticate(username, password)
                profile["menus"] = get_menu_config().menus_for_groups(profile["groups"])
                user = self.service.repository.upsert_from_ldap(db, profile)
                return create_access_token(user.username, profile["menus"], profile["groups"]), user
            user, menus, groups = self.service.login_with_menus(db, username, password)
            return create_access_token(user.username, menus, groups), user
        except (InvalidCredentialsError, AuthenticationUnavailableError, AuthorizationDeniedError, LoginRateLimitedError):
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise AuthenticationUnavailableError("Authentication service is unavailable.") from exc

    def me(self, db: Session, username: str) -> User | None:
        return self.service.get_user(db, username)
