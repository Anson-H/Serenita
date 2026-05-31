import os
from pathlib import Path


def data_root() -> Path:
    configured_root = os.environ.get("SERENITA_DATA_ROOT")
    if configured_root:
        return Path(configured_root)
    return Path(__file__).resolve().parents[3] / "serenita_files"


class AppPaths:
    def __init__(self, root: Path):
        self.root = root

    def account_root(self, account: str) -> Path:
        return self.root / account

    @property
    def auth_db(self) -> Path:
        return self.root / "all_users" / "auth" / "auth_info.db"

    @property
    def legacy_login_db(self) -> Path:
        return self.root / "all_users" / "login" / "key_info.db"

    def account_auth_dir(self, account: str) -> Path:
        return self.root / "all_users" / "auth" / account

    def legacy_account_login_dir(self, account: str) -> Path:
        return self.root / "all_users" / "login" / account

    def config_db(self, account: str) -> Path:
        return self.account_root(account) / "config" / "config.db"

    def conversations_db(self, account: str) -> Path:
        return self.account_root(account) / "conversations" / "db_storage" / "sessions.db"

    def favorites_db(self, account: str) -> Path:
        return self.account_root(account) / "favorites" / "db_storage" / "favorites.db"


def app_paths() -> AppPaths:
    return AppPaths(data_root())
