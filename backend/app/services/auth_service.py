from collections import defaultdict, deque
from time import monotonic

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.ldap_service import LdapService
from app.config.menu_config import get_menu_config
from app.utils.auth_exceptions import AuthorizationDeniedError, InvalidCredentialsError, LoginRateLimitedError


class LoginRateLimiter:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _key(username: str) -> str:
        # AD usernames are case-insensitive; one account must share one attempt budget.
        return username.strip().lower()

    def check(self, username: str) -> None:
        now = monotonic()
        attempts = self.attempts[self._key(username)]
        while attempts and now - attempts[0] > self.settings.login_window_seconds:
            attempts.popleft()
        if len(attempts) >= self.settings.login_max_attempts:
            raise LoginRateLimitedError("Too many login attempts. Try again later.")
        attempts.append(now)

    def clear(self, username: str) -> None:
        self.attempts.pop(self._key(username), None)


class GroupAuthorizer:
    """Maps directory groups to application access using only explicitly configured groups."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def check(self, groups: list[str]) -> None:
        allowed = self.settings.allowed_group_names
        if allowed and not allowed & {group.lower() for group in groups}:
            raise AuthorizationDeniedError("Not authorized to use this application.")

    def permissions(self, groups: list[str]) -> list[str]:
        mapping = self.settings.group_permission_map
        return sorted({permission for group in groups for permission in mapping.get(group.lower(), set())})


class AuthService:
    def __init__(
        self,
        ldap: LdapService | None = None,
        repository: UserRepository | None = None,
        limiter: LoginRateLimiter | None = None,
        authorizer: GroupAuthorizer | None = None,
    ):
        self.ldap = ldap or LdapService()
        self.repository = repository or UserRepository()
        self.limiter = limiter or LoginRateLimiter()
        self.authorizer = authorizer or GroupAuthorizer()

    def _limit_key(self, username: str) -> str:
        # "AGILE\\user", "user@agile.local" and "user" share one attempt budget.
        canonical = getattr(self.ldap, "canonical_username", None)
        if canonical is None:
            return username
        try:
            return canonical(username)
        except InvalidCredentialsError:
            return username

    def login(self, db: Session, username: str, password: str) -> User:
        user, _, _ = self.login_with_menus(db, username, password)
        return user

    def login_with_menus(self, db: Session, username: str, password: str) -> tuple[User, list[str], list[str]]:
        key = self._limit_key(username)
        self.limiter.check(key)
        profile = dict(self.ldap.authenticate(username, password))
        # Authentication succeeded; authorization is a separate, explicitly configured decision.
        groups = profile.pop("groups", None) or []
        self.authorizer.check(groups)
        profile["permissions"] = self.authorizer.permissions(groups)
        menus = get_menu_config().menus_for_groups(groups)
        user = self.repository.upsert_from_ldap(db, profile)
        self.limiter.clear(key)
        return user, menus, groups

    def get_user(self, db: Session, username: str) -> User | None:
        return self.repository.get_by_username(db, username)
