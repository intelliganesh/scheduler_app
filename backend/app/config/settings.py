from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-this-development-secret-before-use"
PLACEHOLDER_JWT_SECRET = "replace-with-a-long-random-secret-at-least-32-characters"


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Generate Report API"
    api_prefix: str = "/api"
    database_url: str | None = None
    db_dialect: str = "mysql"
    db_host: str = "localhost"
    db_port: int | None = None
    db_name: str = "generate_report"
    db_user: str = "report_user"
    db_password: str = "change-me"
    mssql_driver: str = "ODBC Driver 18 for SQL Server"
    # Enable only when the configured SQL Server uses a trusted local certificate.
    mssql_trust_server_certificate: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    ldap_enabled: bool = False
    ldap_host: str = ""
    ldap_port: int = 636
    ldap_base_dn: str = ""
    # UPN suffix, e.g. agile.local (user@agile.local).
    ldap_domain: str = ""
    # NetBIOS domain, e.g. AGILE (AGILE\user); required for NTLM.
    ldap_netbios_domain: str = ""
    # SIMPLE or NTLM. Either method still requires LDAPS/StartTLS unless NTLM
    # session encryption is genuinely available (see LdapService).
    ldap_auth_method: str = "SIMPLE"
    ldap_ntlm_session_encryption: bool = True
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_use_ssl: bool = True
    ldap_start_tls: bool = False
    ldap_ca_cert_file: str = ""
    ldap_connect_timeout_seconds: int = 5
    ldap_search_timeout_seconds: int = 5
    ldap_nested_groups: bool = True
    ldap_group_size_limit: int = 500
    # Semicolon-separated group names allowed to sign in; empty allows any authenticated user.
    ldap_allowed_groups: str = ""
    # "Group A=perm1,perm2;Group B=perm3". Groups that are not listed grant nothing.
    ldap_group_permissions: str = ""
    login_max_attempts: int = 5
    login_window_seconds: int = 60
    auth_mode: str = "ldap"
    mock_testexpert_password: str = ""
    generated_reports_dir: str = "../generated_reports"
    uploads_dir: str = "uploads"
    max_report_rows: int = 1000
    max_upload_bytes: int = 16384
    max_email_recipients: int = 10

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url

        if self.db_dialect.lower() == "mysql":
            port = self.db_port or 3306
            return f"mysql+pymysql://{self.db_user}:{quote_plus(self.db_password)}@{self.db_host}:{port}/{self.db_name}"
        if self.db_dialect.lower() in {"mssql", "sqlserver"}:
            port = self.db_port or 1433
            driver = quote_plus(self.mssql_driver)
            trust = "yes" if self.mssql_trust_server_certificate else "no"
            return (
                f"mssql+pyodbc://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
                f"@{self.db_host}:{port}/{self.db_name}?driver={driver}&Encrypt=yes&TrustServerCertificate={trust}"
            )
        raise ValueError("DB_DIALECT must be 'mysql' or 'mssql'.")

    @property
    def jwt_secret_is_secure(self) -> bool:
        return len(self.jwt_secret_key) >= 32 and self.jwt_secret_key not in {DEFAULT_JWT_SECRET, PLACEHOLDER_JWT_SECRET}

    @property
    def allowed_group_names(self) -> set[str]:
        return {name.strip().lower() for name in self.ldap_allowed_groups.split(";") if name.strip()}

    @property
    def group_permission_map(self) -> dict[str, set[str]]:
        mapping: dict[str, set[str]] = {}
        for item in self.ldap_group_permissions.split(";"):
            group, separator, permissions = item.partition("=")
            if not separator or not group.strip():
                continue
            mapping.setdefault(group.strip().lower(), set()).update(p.strip() for p in permissions.split(",") if p.strip())
        return mapping

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
