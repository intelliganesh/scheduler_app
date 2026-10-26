"""Live Active Directory check. Run from backend/ while connected to the company network or VPN.

    .venv/bin/python scripts/ldap_live_check.py --probe          # no credentials: reachability, rootDSE, TLS
    .venv/bin/python scripts/ldap_live_check.py --authenticate   # exactly one bind with an approved test account

Settings come from backend/.env. The password is read with getpass (or LDAP_TEST_PASSWORD) and is
never printed, logged or stored. Use an IT-approved, least-privileged test account, not Administrator,
and do not re-run --authenticate in a loop.
"""
import argparse
import getpass
import os
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldap3 import ALL, Connection, Server, Tls  # noqa: E402
from ldap3.core.exceptions import LDAPException  # noqa: E402
from ldap3.utils.conv import escape_filter_chars  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.services.ldap_service import LdapService, md4_available, ntlm_session_encryption_supported  # noqa: E402

REFERENCE_GROUPS = ["Domain Admins", "Report Users", "Scheduler Users", "docker-users"]
START_TLS_OID = "1.3.6.1.4.1.1466.20037"


def report(label: str, status: str, detail: str = "") -> None:
    print(f"  {label:<34} {status:<8} {detail}")


def port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(settings) -> int:
    host, timeout = settings.ldap_host, settings.ldap_connect_timeout_seconds
    print(f"Probe of {host} (no credentials are sent)")
    reachable = {port: port_open(host, port, timeout) for port in (389, 636)}
    for port, ok in reachable.items():
        report(f"TCP {port}", "OPEN" if ok else "CLOSED", "" if ok else "unreachable: connect to the company network/VPN")
    if not any(reachable.values()):
        print("BLOCKED: the domain controller is not reachable from this machine.")
        return 2

    if reachable[389]:
        try:
            # Reading the rootDSE anonymously is standard and returns no directory data.
            connection = Connection(Server(host, port=389, get_info=ALL, connect_timeout=timeout), receive_timeout=timeout, auto_bind=True)
            info = connection.server.info
            report("rootDSE dnsHostName", "INFO", str(info.other.get("dnsHostName", ["?"])[0]))
            report("defaultNamingContext", "INFO", str(info.other.get("defaultNamingContext", ["?"])[0]))
            extensions = [extension[0] for extension in (info.supported_extensions or [])]
            report("StartTLS advertised", "YES" if START_TLS_OID in extensions else "NO")
            report("SASL mechanisms", "INFO", ", ".join(map(str, info.supported_sasl_mechanisms or [])))
            connection.unbind()
        except LDAPException as exc:
            report("rootDSE", "FAILED", type(exc).__name__)

    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=settings.ldap_ca_cert_file or None)
    for label, port, use_ssl in (("StartTLS on 389 (validated)", 389, False), ("LDAPS on 636 (validated)", 636, True)):
        if not reachable[port]:
            report(label, "SKIPPED", "port closed")
            continue
        connection = Connection(Server(host, port=port, use_ssl=use_ssl, tls=tls, connect_timeout=timeout), receive_timeout=timeout)
        try:
            connection.open()
            if not use_ssl:
                connection.start_tls()
            report(label, "OK", "certificate and hostname verified")
        except LDAPException as exc:
            report(label, "FAILED", f"{type(exc).__name__}: {str(exc)[:140]}")
        finally:
            connection.unbind()

    report("NTLM MD4 support", "OK" if md4_available() else "MISSING", "" if md4_available() else "pip install pycryptodome")
    report("ldap3 NTLM session encryption", "YES" if ntlm_session_encryption_supported() else "NO",
           "" if ntlm_session_encryption_supported() else "plain-389 NTLM is refused; use StartTLS/LDAPS")
    return 0


class LiveCheckService(LdapService):
    """Adds read-only group-existence checks on the same, already authenticated connection."""

    found_groups: dict[str, str] = {}

    def _profile(self, connection, entry, account):
        profile = super()._profile(connection, entry, account)
        for name in REFERENCE_GROUPS:
            entries = self._search(connection, f"(&(objectClass=group)(cn={escape_filter_chars(name)}))", ["cn", "groupType"], 1)
            self.found_groups[name] = "exists" if entries else "not found"
        return profile


def authenticate(settings) -> int:
    username = os.getenv("LDAP_TEST_USERNAME") or input("Approved test account (e.g. AGILE\\report.tester): ").strip()
    password = os.getenv("LDAP_TEST_PASSWORD") or getpass.getpass("Password (not echoed): ")
    print(f"One authentication attempt for {username!r} using {settings.ldap_auth_method} ...")
    service = LiveCheckService(settings)
    try:
        profile = service.authenticate(username, password)
    except Exception as exc:  # report the category only; never echo inputs
        cause = exc.__cause__
        detail = f"{type(cause).__name__}: {str(cause)[:160]}" if cause else ""
        print(f"  RESULT: {type(exc).__name__}: {exc} {detail}".replace(password, "***"))
        return 1
    finally:
        del password
    print("  RESULT: authenticated")
    groups = profile.pop("groups")
    for key, value in profile.items():
        report(key, "", value if value is not None else "(empty)")
    report("group memberships found", "", str(len(groups)))
    for name in REFERENCE_GROUPS:
        report(f"group {name!r}", service.found_groups.get(name, "?"), "member" if name in groups else "not a member")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--authenticate", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.ldap_host:
        print("LDAP_HOST is not configured in backend/.env")
        return 2
    return probe(settings) if args.probe else authenticate(settings)


if __name__ == "__main__":
    sys.exit(main())
