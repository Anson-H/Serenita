import errno
import os
import re
import shutil
import stat
import threading
import uuid
from pathlib import Path


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]+$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
_HARDENED_TREES: set[Path] = set()
_HARDENED_TREES_LOCK = threading.Lock()
_ACCOUNT_DIRECTORIES = (
    "config",
    "conversations/db_storage",
    "conversations/sessions",
    "conversations/attachments",
    "favorites/db_storage",
    "members/db_storage",
    "reports/db_storage",
    "reports/attachments",
)

# Every path below this module contains account or application-private data.
# Setting the process umask once makes files created by direct Path/shutil calls
# private as well; the helpers below enforce the same boundary on current data.
os.umask(0o077)


def _safe_component(value: str, *, label: str) -> str:
    """Return a path component after rejecting traversal and separators."""
    if not value or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def canonical_account_id(value: str) -> str:
    """Return a canonical UUID account id suitable for use as a path component."""
    try:
        parsed = uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("invalid account_id") from exc
    canonical = str(parsed)
    if str(value) != canonical:
        raise ValueError("invalid account_id")
    return canonical


def data_root() -> Path:
    configured_root = os.environ.get("DATA_ROOT")
    if configured_root:
        return Path(configured_root)
    return Path(__file__).resolve().parents[3] / "serenita_files"


def ensure_private_directory(path: Path | str) -> Path:
    directory = Path(path)
    if directory.is_symlink():
        raise ValueError("private directory cannot be a symlink")
    directory.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    directory.chmod(PRIVATE_DIRECTORY_MODE)
    return directory


def ensure_private_file(path: Path | str) -> Path:
    private_file = Path(path)
    try:
        mode = private_file.lstat().st_mode
    except FileNotFoundError:
        return private_file
    if stat.S_ISLNK(mode):
        raise ValueError("private file cannot be a symlink")
    if stat.S_IMODE(mode) != PRIVATE_FILE_MODE:
        try:
            private_file.chmod(PRIVATE_FILE_MODE)
        except OSError as exc:
            # Transient SQLite sidecars can disappear between exists() and
            # chmod(). Only that expected TOCTOU outcome is safe to ignore.
            if exc.errno != errno.ENOENT:
                raise
    return private_file


def harden_private_tree(path: Path | str) -> None:
    """Harden a private tree without following symbolic links."""
    root = Path(path)
    if not root.exists():
        return
    if root.is_symlink():
        raise ValueError("private directory cannot be a symlink")
    if root.is_file():
        ensure_private_file(root)
        return

    root.chmod(PRIVATE_DIRECTORY_MODE)
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current_root)
        current_path.chmod(PRIVATE_DIRECTORY_MODE)
        for directory_name in directory_names:
            directory = current_path / directory_name
            if directory.is_symlink():
                continue
            directory.chmod(PRIVATE_DIRECTORY_MODE)
        for file_name in file_names:
            private_file = current_path / file_name
            if private_file.is_symlink():
                continue
            private_file.chmod(PRIVATE_FILE_MODE)


def harden_private_ancestors(path: Path | str, boundary: Path | str) -> None:
    """Harden an existing directory chain, bounded to the private data root."""
    directory = Path(path)
    private_root = Path(boundary)
    try:
        relative = directory.relative_to(private_root)
    except ValueError:
        return

    current = private_root
    candidates = [current]
    for component in relative.parts:
        current = current / component
        candidates.append(current)
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.is_symlink():
            raise ValueError("private directory cannot be a symlink")
        if candidate.is_dir():
            candidate.chmod(PRIVATE_DIRECTORY_MODE)


def harden_private_tree_once(path: Path | str) -> None:
    root = Path(path)
    if not root.exists():
        return
    cache_key = root.resolve()
    with _HARDENED_TREES_LOCK:
        if cache_key in _HARDENED_TREES:
            return
        harden_private_tree(root)
        _HARDENED_TREES.add(cache_key)


class AppPaths:
    def __init__(self, root: Path):
        self.root = root

    def account_root(self, account_id: str) -> Path:
        account_path = self.root / "accounts" / canonical_account_id(account_id)
        harden_private_ancestors(account_path, self.root)
        harden_private_tree_once(account_path)
        return account_path

    def create_account_tree(self, account_id: str) -> Path:
        account_root = self.account_root(account_id)
        ensure_private_directory(account_root.parent)
        account_root.mkdir(mode=PRIVATE_DIRECTORY_MODE, exist_ok=False)
        try:
            for relative_path in _ACCOUNT_DIRECTORIES:
                ensure_private_directory(account_root / relative_path)
        except Exception:
            shutil.rmtree(account_root, ignore_errors=True)
            raise
        return account_root

    def require_account_tree(self, account_id: str) -> Path:
        account_root = self.account_root(account_id)
        if not account_root.is_dir():
            raise FileNotFoundError(account_root)
        return account_root

    @property
    def auth_db(self) -> Path:
        auth_directory = self.root / "all_users" / "auth"
        harden_private_ancestors(auth_directory, self.root)
        harden_private_tree_once(auth_directory)
        return auth_directory / "auth.db"

    def config_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "config" / "settings.db"

    def conversations_db(self, account_id: str) -> Path:
        return (
            self.account_root(account_id)
            / "conversations"
            / "db_storage"
            / "conversations.db"
        )

    def favorites_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "favorites" / "db_storage" / "favorites.db"

    def members_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "members" / "db_storage" / "members.db"

    def reports_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "reports" / "db_storage" / "reports.db"

    def medical_logs_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "medical_logs" / "db_storage" / "medical_logs.db"

    def body_metrics_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "body_metrics" / "db_storage" / "body_metrics.db"

    def medications_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "medications" / "db_storage" / "medications.db"

    def notifications_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "notifications" / "db_storage" / "notifications.db"

    def background_tasks_db(self, account_id: str) -> Path:
        return self.account_root(account_id) / "background_tasks" / "db_storage" / "background_tasks.db"

    def medication_files_dir(self, account_id: str) -> Path:
        return self.account_root(account_id) / "medications" / "files"

    def report_attachments_dir(self, account_id: str) -> Path:
        return self.account_root(account_id) / "reports" / "attachments"

    def report_attachment_path(
        self, account_id: str, resource_id: str, extension: str
    ) -> Path:
        safe_resource_id = _safe_component(resource_id, label="resource_id")
        safe_extension = extension.lower().lstrip(".")
        if safe_extension not in {"jpg", "jpeg", "png", "heic", "pdf", "txt"}:
            raise ValueError("invalid report file extension")
        return self.report_attachments_dir(account_id) / (
            f"{safe_resource_id}.{safe_extension}"
        )

    @property
    def provider_master_key(self) -> Path:
        secrets_directory = self.root / "all_users" / "secrets"
        harden_private_ancestors(secrets_directory, self.root)
        harden_private_tree_once(secrets_directory)
        return secrets_directory / "provider_master.key"

    @property
    def web_access_master_key(self) -> Path:
        secrets_directory = self.root / "all_users" / "secrets"
        harden_private_ancestors(secrets_directory, self.root)
        harden_private_tree_once(secrets_directory)
        return secrets_directory / "web_access_master.key"


def app_paths() -> AppPaths:
    return AppPaths(data_root())
