"""独立生成和更新会话标题，管理标题后台任务及其取消。"""

import json
import threading
from typing import Any


from backend.app.core.cancellation import (
    CancellationToken,
    OperationCancelledError,
)
from backend.app.domain.conversations.titles import (
    SESSION_TITLE_MAX_CHARS, SESSION_TITLE_TARGET_CJK_CHARACTERS,
    SESSION_TITLE_TARGET_WORDS, SESSION_TITLE_FOCUS_KEYWORDS, UNTITLED_CONVERSATION,
)


class ConversationTitleTasks:
    def __init__(
        self,
        repository,
        model_catalog,
        task_state,
        *,
        prepare_attachments,
        prepare_request,
    ):
        self.repository = repository
        self.model_catalog = model_catalog
        self.task_state = task_state
        self.prepare_attachments = prepare_attachments
        self.prepare_request = prepare_request

    def start(self, account_id: str, turn, user_message: dict[str, Any]):
        session_id = str(turn["session_id"])
        initial_title = str(user_message.get("initial_session_title") or "")
        session_row = self.repository.session_row(account_id, session_id)
        should_generate = (
            bool(user_message.get("generate_session_title"))
            and not bool(session_row["is_title_manual"])
            and session_row["title"]
            == self.repository.initial_session_title(initial_title)
        )
        if not should_generate:
            return None

        job_key = (account_id, session_id)
        cancellation_token = CancellationToken()

        def generate() -> None:
            try:
                cancellation_token.raise_if_cancelled()
                generated_title = self.generate(
                    account_id,
                    turn,
                    user_message,
                    cancellation_token=cancellation_token,
                )
                cancellation_token.raise_if_cancelled()
                self.repository.replace_initial_session_title(
                    account_id,
                    session_id,
                    initial_title,
                    generated_title,
                )
            except OperationCancelledError:
                return
            finally:
                with self.task_state.lock:
                    current = self.task_state.titles.get(job_key)
                    if current is not None and current[0] is threading.current_thread():
                        self.task_state.titles.pop(job_key, None)

        thread = threading.Thread(
            target=generate,
            name=f"serenita-title-{turn['turn_id']}",
            daemon=True,
        )
        with self.task_state.lock:
            existing = self.task_state.titles.get(job_key)
            if existing is not None:
                existing[1].cancel()
            self.task_state.titles[job_key] = (thread, cancellation_token)
        thread.start()
        return thread

    def cancel(self, account_id: str, session_id: str) -> bool:
        with self.task_state.lock:
            current = self.task_state.titles.get((account_id, session_id))
        if current is None:
            return False
        current[1].cancel()
        return True

    def generate(
        self,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        *,
        cancellation_token: CancellationToken,
    ) -> str:
        cancellation_token.raise_if_cancelled()
        title_seed = self.seed(
            str(user_message.get("content") or ""),
            list(user_message.get("context_resources") or []),
        )
        fallback_title = self.repository.generate_session_title(title_seed)
        model = self.model_catalog.default_model_for_account(
            account_id,
            "title",
        ) or self.model_catalog.default_model_for_account(account_id, "chat")
        if not model:
            cancellation_token.raise_if_cancelled()
            return fallback_title

        title_model = model
        attachment_parts: list[dict[str, Any]] = []
        try:
            title_model, attachment_parts = self.prepare_attachments(
                account_id,
                str(turn["session_id"]),
                list(user_message.get("context_resources") or []),
                model,
            )
        except Exception:
            # A text-only title model can still name the session from the
            # persisted attachment names in title_seed.
            pass
        messages = session_title_messages(title_seed)
        if attachment_parts:
            messages[-1]["content"] = [
                {"type": "text", "text": str(messages[-1]["content"])},
                *attachment_parts,
            ]
        try:
            result = self.model_catalog.complete_chat_for_account(
                account_id=account_id,
                model=title_model,
                model_request=self.prepare_request(
                    messages, purpose="session_title_metadata"
                ),
                thinking_mode="default",
                cancellation_token=cancellation_token,
            )
        except OperationCancelledError:
            raise
        except Exception:
            cancellation_token.raise_if_cancelled()
            return fallback_title

        cancellation_token.raise_if_cancelled()
        generated_title = self.repository.clean_generated_session_title(result.content)
        return (
            generated_title
            if generated_title != UNTITLED_CONVERSATION
            else fallback_title
        )

    @staticmethod
    def seed(
        raw_text: str,
        context_resources: list[dict[str, Any]],
    ) -> str:
        text = " ".join(str(raw_text or "").split())
        if text:
            return text
        names = [
            " ".join(str(resource.get("original_filename") or "").split())
            for resource in context_resources
            if str(resource.get("resource_type") or "") == "file"
            and str(resource.get("original_filename") or "").strip()
        ]
        if names:
            visible_names = names[:3]
            suffix = (
                f"等 {len(names)} 个附件" if len(names) > len(visible_names) else ""
            )
            return "、".join(visible_names) + suffix
        return ATTACHMENT_ONLY_USER_PROMPT


ATTACHMENT_ONLY_USER_PROMPT = "请阅读并总结附件内容。"


SESSION_TITLE_SYSTEM_PROMPT = "\n".join(
    (
        "仅根据当前轮次的用户输入和附件内容生成简洁的会话标题。",
        "只输出标题本身的一行纯文本，不要引号、前缀、解释、Markdown、XML 或代码。",
        (
            "使用输入的语言，优先保留能表达"
            + "和".join(SESSION_TITLE_FOCUS_KEYWORDS)
            + "的关键词。"
        ),
        (
            f"中文标题以约 {SESSION_TITLE_TARGET_CJK_CHARACTERS} 个汉字为目标，"
            f"最多 {SESSION_TITLE_MAX_CHARS} 个字符；非中文标题以约 "
            f"{SESSION_TITLE_TARGET_WORDS} 个词为目标。"
        ),
    )
)


def session_title_messages(
    title_seed: str,
) -> list[dict[str, Any]]:
    """Build the isolated, JSON-framed auxiliary title request."""
    payload = {
        "title_seed": str(title_seed or ""),
    }
    return [
        {"role": "system", "content": SESSION_TITLE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请从以下 JSON 生成会话标题：\n"
                + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            ),
        },
    ]
