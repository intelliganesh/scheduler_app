from app.utils.auth_exceptions import InvalidCredentialsError
from app.config.settings import get_settings
from app.config.menu_config import get_mock_menu_config

MOCK_USERS = {
    "demo_admin": {"password": "DemoAdmin!2026", "full_name": "Demo Administrator", "email": "demo_admin@example.local", "groups": ["GR_DEMO_ADMINS"]},
    "demo_author": {"password": "DemoAuthor!2026", "full_name": "Demo Report Author", "email": "demo_author@example.local", "groups": ["GR_DEMO_REPORT_AUTHORS", "GR_DEMO_FINANCE"]},
    "demo_viewer": {"password": "DemoViewer!2026", "full_name": "Demo Viewer", "email": "demo_viewer@example.local", "groups": ["GR_DEMO_VIEWERS"]},
}

# Backward-compatible export for integrations that imported the old demo map.
# The YAML policy remains the single source of truth.
SAMPLE_GROUP_MENUS = {
    group: get_mock_menu_config().menus_for_groups([group])
    for group in {group for user in MOCK_USERS.values() for group in user["groups"]}
}

if get_settings().mock_testexpert_password:
    MOCK_USERS["testexpert@yopmail.com"] = {
        "password": get_settings().mock_testexpert_password,
        "full_name": "Test Expert",
        "email": "testexpert@yopmail.com",
        "groups": ["GR_DEMO_ADMINS"],
    }


def menus_for_groups(groups: list[str]) -> list[str]:
    return get_mock_menu_config().menus_for_groups(groups)


class MockAuthService:
    def authenticate(self, username: str, password: str) -> dict[str, object]:
        record = MOCK_USERS.get(username)
        if record is None or record["password"] != password:
            raise InvalidCredentialsError("Invalid username or password.")
        groups = record["groups"]
        return {"username": username, "email": record["email"], "full_name": record["full_name"], "groups": groups, "menus": menus_for_groups(groups)}
