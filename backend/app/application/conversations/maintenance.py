"""收尾过期会话任务；调度由应用后台运行边界负责。"""

from collections.abc import Callable, Iterable
import logging


class ConversationTaskMaintenance:
    def __init__(self, task_state, expire_account: Callable[[str], None]):
        self.task_state = task_state
        self.expire_account = expire_account

    def reconcile(self, account_ids: Iterable[str]) -> None:
        # Services sharing a data root also share this maintenance lock. The
        # repository's conditional lease updates arbitrate other processes.
        with self.task_state.maintenance_lock:
            for account_id in account_ids:
                try:
                    self.expire_account(account_id)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Conversation task maintenance failed for an account"
                    )
