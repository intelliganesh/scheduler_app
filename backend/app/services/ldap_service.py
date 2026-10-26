import hashlib
import inspect
import ssl
from contextlib import contextmanager

from ldap3 import ALL, NTLM, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

from app.config.settings import Settings, get_settings
from app.utils.auth_exceptions import AuthenticationUnavailableError, InvalidCredentialsError

USER_ATTRIBUTES = [
    "sAMAccountName", "userPrincipalName", "displayName", "givenName", "sn", "mail",
    "department", "title", "company", "memberOf", "primaryGroupID", "objectSid",
]
INVALID_CREDENTIALS = 49
# LDAP_MATCHING_RULE_IN_CHAIN: matches groups the user belongs to directly or through nesting.
NESTED_MEMBERSHIP_RULE = "1.2.840.113556.1.4.1941"
# Characters Active Directory does not allow in sAMAccountName.
INVALID_ACCOUNT_CHARACTERS = set('"/\\[]:;|=,+*?<>@')


def ntlm_session_encryption_supported() -> bool:
    """ldap3 2.9.1 negotiates the NTLM seal flag but never encrypts; builds that do accept `session_security`."""
    return "session_security" in inspect.signature(Connection.__init__).parameters


def md4_available() -> bool:
    """NTLM needs MD4, which OpenSSL 3 disables; ldap3 then falls back to pycryptodome."""
    try:
        hashlib.new("md4")
        return True
    except ValueError:
        try:
            from Crypto.Hash import MD4  # noqa: F401
            return True
        except ImportError:
            return False


def sid_to_string(raw: bytes) -> str:
    sub_authorities = [int.from_bytes(raw[8 + 4 * i:12 + 4 * i], "little") for i in range(raw[1])]
    return "-".join(["S", str(raw[0]), str(int.from_bytes(raw[2:8], "big")), *map(str, sub_authorities)])


class LdapService:
    """Authenticates against Active Directory without persisting LDAP passwords."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def auth_method(self) -> str:
        return self.settings.ldap_auth_method.strip().upper()

    @property
    def uses_ntlm_session_encryption(self) -> bool:
        # Only without TLS: AD rejects NTLM sealing inside an LDAPS/StartTLS connection.
        settings = self.settings
        if settings.ldap_use_ssl or settings.ldap_start_tls:
            return False
        return self.auth_method == "NTLM" and settings.ldap_ntlm_session_encryption and ntlm_session_encryption_supported()

    def canonical_username(self, username: str) -> str:
        """Returns the sAMAccountName for `user`, `AGILE\\user` or `user@agile.local`."""
        settings = self.settings
        name = username.strip()
        if "\\" in name:
            domain, _, name = name.partition("\\")
            if domain.strip().lower() != settings.ldap_netbios_domain.strip().lower():
                raise InvalidCredentialsError("Invalid username or password.")
        elif "@" in name:
            name, _, suffix = name.rpartition("@")
            if suffix.strip().lower() != settings.ldap_domain.strip().lower():
                raise InvalidCredentialsError("Invalid username or password.")
        name = name.strip()
        if not name or len(name) > 64 or INVALID_ACCOUNT_CHARACTERS & set(name):
            raise InvalidCredentialsError("Invalid username or password.")
        return name

    def authenticate(self, username: str, password: str) -> dict:
        settings = self.settings
        # An empty password makes AD perform an "unauthenticated bind", which succeeds.
        if not username.strip() or not password:
            raise InvalidCredentialsError("Invalid username or password.")
        if not settings.ldap_enabled or not settings.ldap_host or not settings.ldap_base_dn:
            raise AuthenticationUnavailableError("LDAP authentication is not configured.")
        if self.auth_method not in {"SIMPLE", "NTLM"}:
            raise AuthenticationUnavailableError("LDAP_AUTH_METHOD must be SIMPLE or NTLM.")
        if self.auth_method == "NTLM" and not settings.ldap_netbios_domain:
            raise AuthenticationUnavailableError("NTLM requires LDAP_NETBIOS_DOMAIN.")
        if self.auth_method == "NTLM" and not md4_available():
            raise AuthenticationUnavailableError("NTLM requires MD4 support; install pycryptodome.")
        if not settings.ldap_use_ssl and not settings.ldap_start_tls and not self.uses_ntlm_session_encryption:
            raise AuthenticationUnavailableError("Secure LDAP must be enabled.")
        account = self.canonical_username(username)

        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=settings.ldap_ca_cert_file or None,
        )
        server = Server(
            settings.ldap_host,
            port=settings.ldap_port,
            use_ssl=settings.ldap_use_ssl,
            tls=tls,
            connect_timeout=settings.ldap_connect_timeout_seconds,
            get_info=ALL,
        )
        try:
            if settings.ldap_bind_dn:
                return self._authenticate_via_search(server, account, password)
            with self._bind(server, self._principal(account), password) as connection:
                entry = self._find_user(connection, account)
                if entry is None:
                    # The bind worked, so the account exists but its entry cannot be read.
                    raise AuthenticationUnavailableError("Directory entry is not readable.")
                return self._profile(connection, entry, account)
        except (InvalidCredentialsError, AuthenticationUnavailableError):
            raise
        except LDAPException as exc:
            raise AuthenticationUnavailableError("LDAP service is unavailable.") from exc

    def _authenticate_via_search(self, server: Server, account: str, password: str) -> dict:
        settings = self.settings
        with self._bind(server, settings.ldap_bind_dn, settings.ldap_bind_password, service_account=True) as lookup:
            entry = self._find_user(lookup, account)
            if entry is None:
                raise InvalidCredentialsError("Invalid username or password.")
            user = entry.entry_dn if self.auth_method == "SIMPLE" else self._principal(account)
            with self._bind(server, user, password):
                pass
            return self._profile(lookup, entry, account)

    def _principal(self, account: str) -> str:
        if self.auth_method == "NTLM":
            return f"{self.settings.ldap_netbios_domain}\\{account}"
        return f"{account}@{self.settings.ldap_domain}"

    @contextmanager
    def _bind(self, server: Server, user: str, password: str, service_account: bool = False):
        settings = self.settings
        options = {
            "user": user,
            "password": password,
            "authentication": NTLM if self.auth_method == "NTLM" else SIMPLE,
            "auto_bind": False,
            "receive_timeout": settings.ldap_search_timeout_seconds,
        }
        if self.uses_ntlm_session_encryption:
            from ldap3 import ENCRYPT

            options["session_security"] = ENCRYPT
        connection = Connection(server, **options)
        try:
            if settings.ldap_start_tls:
                connection.open()
                connection.start_tls()
            if not connection.bind():
                # Only "invalidCredentials" means a wrong password; anything else (for example
                # strongerAuthRequired when the DC demands signing) is a configuration problem.
                if service_account or self._result_code(connection) != INVALID_CREDENTIALS:
                    raise AuthenticationUnavailableError("LDAP service is unavailable.")
                raise InvalidCredentialsError("Invalid username or password.")
            yield connection
        finally:
            connection.unbind()

    @staticmethod
    def _result_code(connection: Connection) -> int | None:
        result = connection.result
        return result.get("result") if isinstance(result, dict) else None

    def _search(self, connection: Connection, search_filter: str, attributes: list[str], size_limit: int) -> list:
        connection.search(
            self.settings.ldap_base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=attributes,
            size_limit=size_limit,
            time_limit=self.settings.ldap_search_timeout_seconds,
        )
        if self._result_code(connection) not in (None, 0, 4):  # 4 = sizeLimitExceeded, entries still usable
            raise AuthenticationUnavailableError("LDAP search failed.")
        return list(connection.entries)

    def _find_user(self, connection: Connection, account: str):
        search_filter = f"(&(objectCategory=person)(objectClass=user)(sAMAccountName={escape_filter_chars(account)}))"
        entries = self._search(connection, search_filter, USER_ATTRIBUTES, size_limit=2)
        return entries[0] if len(entries) == 1 else None

    def _profile(self, connection: Connection, entry, account: str) -> dict:
        value = self._value
        given_name, surname = value(entry, "givenName"), value(entry, "sn")
        return {
            "username": value(entry, "sAMAccountName") or account,
            "email": value(entry, "mail"),
            "full_name": value(entry, "displayName") or " ".join(filter(None, [given_name, surname])) or account,
            "user_principal_name": value(entry, "userPrincipalName"),
            "given_name": given_name,
            "surname": surname,
            "department": value(entry, "department"),
            "title": value(entry, "title"),
            "company": value(entry, "company"),
            "groups": self._group_names(connection, entry),
        }

    def _group_names(self, connection: Connection, entry) -> list[str]:
        settings = self.settings
        names = {self._common_name(dn) for dn in self._values(entry, "memberOf")}
        if settings.ldap_nested_groups:
            nested_filter = f"(&(objectClass=group)(member:{NESTED_MEMBERSHIP_RULE}:={escape_filter_chars(entry.entry_dn)}))"
            names.update(self._value(group, "cn") for group in self._search(connection, nested_filter, ["cn"], settings.ldap_group_size_limit))
        primary_sid = self._primary_group_sid(entry)
        if primary_sid:
            primary_filter = f"(&(objectClass=group)(objectSid={escape_filter_chars(primary_sid)}))"
            names.update(self._value(group, "cn") for group in self._search(connection, primary_filter, ["cn"], 1))
        return sorted(name for name in names if name)

    def _primary_group_sid(self, entry) -> str | None:
        """The primary group (usually Domain Users) is not listed in memberOf; it is the user's domain SID + primaryGroupID."""
        rid = self._value(entry, "primaryGroupID")
        if not rid or "objectSid" not in entry:
            return None
        sid = entry["objectSid"].value
        if isinstance(sid, (bytes, bytearray)):
            sid = sid_to_string(bytes(sid))
        if not isinstance(sid, str) or not sid.startswith("S-"):
            return None
        return f"{sid.rsplit('-', 1)[0]}-{rid}"

    @staticmethod
    def _values(entry, attribute: str) -> list[str]:
        if attribute not in entry:
            return []
        return [str(value) for value in entry[attribute].values if str(value).strip()]

    @classmethod
    def _value(cls, entry, attribute: str) -> str | None:
        values = cls._values(entry, attribute)
        return values[0].strip() if values else None

    @staticmethod
    def _common_name(dn: str) -> str | None:
        try:
            attribute, value, _ = parse_dn(dn)[0]
        except (LDAPException, IndexError, ValueError):
            return None
        # parse_dn keeps RFC 4514 escapes such as "\," in the value.
        return value.replace("\\", "") if attribute.upper() == "CN" else None
