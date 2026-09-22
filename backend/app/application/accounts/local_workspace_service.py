"""One deployment-owned workspace, opened without a local password form."""
import fcntl
import secrets

from backend.app.application.accounts.auth_service import AuthServiceError
from backend.app.core.errors import raise_error
from backend.app.storage.paths import ensure_private_file


class LocalWorkspaceService:
    def __init__(self, auth):
        self.auth = auth

    def validate_storage(self):
        """Require one local identity at most, returning it when already created."""
        accounts = self.auth.repository.account_ids()
        if len(accounts) > 1:
            raise_error("conflict", "LOCAL_ACCOUNT_LIMIT_EXCEEDED", "自部署仅支持一个本地账号，此数据目录包含多个账号，无法打开工作区。")
        return accounts[0] if accounts else None

    def require_user(self, user):
        if user.account_id != self.validate_storage():
            raise_error("forbidden", "LOCAL_ACCOUNT_MISMATCH", "此会话不属于当前本地工作区，请刷新页面。")

    def session(self, token):
        # Serialize first-use account creation across backend workers. No existing
        # account, credential, configuration or business record is rewritten.
        path = self.auth.paths.auth_db.with_name("local_workspace.lock")
        ensure_private_file(path)
        with path.open("a") as lock:
            ensure_private_file(path)
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                account_id = self.validate_storage()
                if account_id is None:
                    secret = secrets.token_urlsafe(48)
                    return self.auth.sign_up(account="local", account_name="本地工作区", password=secret, confirm_password=secret)
                try:
                    user = self.auth.current_user(token)
                    if user.account_id == account_id:
                        return user, None
                except AuthServiceError as error:
                    if error.kind != "unauthenticated":
                        raise
                return self.auth.create_local_session(account_id)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
