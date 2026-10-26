"""Load and evaluate the small, file-based menu authorization policy."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def normalize_group_name(group: str) -> str:
    """Return a stable, case-insensitive group key for AD or mock values."""
    value = str(group or "").strip()
    if not value:
        return ""
    # LDAP group claims may be a full DN. The CN is the directory group name
    # and is what administrators normally use in menu.yaml.
    for part in value.split(","):
        if part.strip().lower().startswith("cn="):
            value = part.split("=", 1)[1].strip()
            break
    return value.lower()


class MenuConfig:
    def __init__(self, menus: list[dict[str, Any]]):
        self._menus = tuple(menus)

    @property
    def items(self) -> list[dict[str, str]]:
        return [
            {"id": str(item["id"]), "label": str(item.get("label", item["id"])), "path": str(item.get("path", "/"))}
            for item in self._menus
        ]

    def menus_for_groups(self, groups: list[str]) -> list[str]:
        group_keys = {normalize_group_name(group) for group in groups}
        return [str(item["id"]) for item in self._menus if group_keys.intersection(normalize_group_name(group) for group in item.get("groups", []))]

    def items_for_groups(self, groups: list[str]) -> list[dict[str, str]]:
        allowed = set(self.menus_for_groups(groups))
        return [item for item in self.items if item["id"] in allowed]


@lru_cache
def _load_menu_config(filename: str) -> MenuConfig:
    path = Path(__file__).with_name(filename)
    if not path.is_file():
        raise ValueError(f"Menu configuration file is missing: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Menu configuration is invalid YAML: {path}") from exc
    menus = document.get("menus")
    if not isinstance(menus, list) or not all(isinstance(item, dict) and item.get("id") for item in menus):
        raise ValueError(f"Menu configuration must contain a list of menu entries: {path}")
    ids = [str(item["id"]) for item in menus]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Menu configuration contains duplicate menu ids: {path}")
    for item in menus:
        if not isinstance(item.get("groups"), list) or not all(isinstance(group, str) and group.strip() for group in item["groups"]):
            raise ValueError(f"Each menu must define a non-empty list of group names: {path}")
    return MenuConfig(menus)


def get_menu_config() -> MenuConfig:
    """Return the legacy mock policy for backwards-compatible integrations."""
    return _load_menu_config("mock_menu.yaml")


def get_ldap_menu_config() -> MenuConfig:
    """Load the menu policy used for real LDAP/Active Directory logins."""
    return _load_menu_config("menu.yaml")


def get_mock_menu_config() -> MenuConfig:
    """Load the local demo/mock authentication menu policy."""
    return _load_menu_config("mock_menu.yaml")
