from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Any

from chatkit.store import NotFoundError, Store
from chatkit.types import Attachment, Page, ThreadItem, ThreadMetadata

from .models import AuthContext, MessageRecord, ThreadRecord, WidgetSchema


class InMemoryStore(Store[AuthContext]):
    def __init__(self) -> None:
        now = int(time.time())
        self._lock = threading.Lock()
        self._threads: dict[str, ThreadRecord] = {
            "thread_alice_paris": ThreadRecord(
                id="thread_alice_paris",
                user_id="usr_alice",
                title="Paris summer booking",
                created_at=now,
                updated_at=now,
                metadata={"context_summary": "Alice planning Paris trip in July."},
            ),
            "thread_alice_delhi": ThreadRecord(
                id="thread_alice_delhi",
                user_id="usr_alice",
                title="Delhi work trip",
                created_at=now,
                updated_at=now,
                metadata={"context_summary": "Alice comparing work-trip flight options."},
            ),
            "thread_bob_tokyo": ThreadRecord(
                id="thread_bob_tokyo",
                user_id="usr_bob",
                title="Tokyo family vacation",
                created_at=now,
                updated_at=now,
                metadata={"context_summary": "Bob planning a family trip to Tokyo."},
            ),
            "thread_bob_mumbai": ThreadRecord(
                id="thread_bob_mumbai",
                user_id="usr_bob",
                title="Mumbai long weekend",
                created_at=now,
                updated_at=now,
                metadata={"context_summary": "Bob checking a Mumbai weekend itinerary."},
            ),
        }
        self._messages: dict[str, list[MessageRecord]] = defaultdict(list)
        self._client_secrets: dict[str, dict[str, int | str]] = {}
        self._widgets: dict[str, dict[str, WidgetSchema]] = defaultdict(dict)
        self._widget_action_state: dict[str, dict[str, str]] = defaultdict(dict)
        self._chatkit_items: dict[str, list[ThreadItem]] = defaultdict(list)
        self._attachments: dict[str, Attachment] = {}

    def generate_thread_id(self, context: AuthContext) -> str:
        return f"thread_{uuid.uuid4().hex[:10]}"

    def generate_item_id(self, item_type: str, thread: ThreadMetadata, context: AuthContext) -> str:
        prefix_map = {
            "message": "msg",
            "tool_call": "tc",
            "workflow": "wf",
            "task": "task",
            "attachment": "att",
            "sdk_hidden_context": "hidden",
        }
        prefix = prefix_map.get(item_type, "item")
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    def list_threads_for_user(self, user_id: str) -> list[ThreadRecord]:
        return [deepcopy(thread) for thread in self._threads.values() if thread.user_id == user_id]

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        thread = self._threads.get(thread_id)
        return deepcopy(thread) if thread else None

    def set_thread_mode(self, thread_id: str, mode: str) -> ThreadRecord | None:
        with self._lock:
            thread = self._threads.get(thread_id)
            if not thread:
                return None
            thread.mode = mode  # type: ignore[assignment]
            thread.updated_at = int(time.time())
            return deepcopy(thread)

    def user_owns_thread(self, user_id: str, thread_id: str) -> bool:
        thread = self._threads.get(thread_id)
        return bool(thread and thread.user_id == user_id)

    def _require_owned_thread_record(self, user_id: str, thread_id: str) -> ThreadRecord:
        thread = self._threads.get(thread_id)
        if not thread or thread.user_id != user_id:
            raise NotFoundError(f"Thread {thread_id} not found.")
        return thread

    def save_client_secret(self, user_id: str, thread_id: str, expires_at: int) -> tuple[str, str]:
        with self._lock:
            session_id = f"cksess_{uuid.uuid4().hex[:16]}"
            client_secret = f"ck_local_{uuid.uuid4().hex}"
            self._client_secrets[client_secret] = {
                "session_id": session_id,
                "user_id": user_id,
                "thread_id": thread_id,
                "expires_at": expires_at,
            }
        return session_id, client_secret

    def get_client_secret_record(self, client_secret: str) -> dict[str, int | str] | None:
        return self._client_secrets.get(client_secret)

    def add_message(self, thread_id: str, role: str, content: str | dict, *, hidden: bool = False) -> MessageRecord:
        with self._lock:
            record = MessageRecord(
                id=f"msg_{uuid.uuid4().hex[:12]}",
                thread_id=thread_id,
                role=role,  # type: ignore[arg-type]
                content=content,
                timestamp=int(time.time()),
                status="delivered",
                hidden=hidden,
            )
            self._messages[thread_id].append(record)
        return deepcopy(record)

    def list_visible_messages(self, thread_id: str, since: str | None = None) -> list[MessageRecord]:
        messages = [deepcopy(message) for message in self._messages[thread_id] if not message.hidden]
        if since is None:
            return messages

        matched = False
        filtered: list[MessageRecord] = []
        for message in messages:
            if matched:
                filtered.append(message)
            elif message.id == since:
                matched = True
        return filtered

    def save_widget(self, thread_id: str, widget: WidgetSchema) -> None:
        with self._lock:
            self._widgets[thread_id][widget.id] = deepcopy(widget)

    def get_widget(self, thread_id: str, widget_id: str) -> WidgetSchema | None:
        widget = self._widgets[thread_id].get(widget_id)
        return deepcopy(widget) if widget else None

    def list_widgets(self, thread_id: str) -> list[WidgetSchema]:
        return [deepcopy(widget) for widget in self._widgets[thread_id].values()]

    def update_widget_state(self, thread_id: str, widget_id: str, state: str) -> WidgetSchema | None:
        with self._lock:
            widget = self._widgets[thread_id].get(widget_id)
            if not widget:
                return None
            widget.state = state  # type: ignore[assignment]
            widget.version += 1
            return deepcopy(widget)

    def set_widget_action_state(self, widget_id: str, action_id: str, state: str) -> None:
        with self._lock:
            self._widget_action_state[widget_id][action_id] = state

    def get_widget_action_state(self, widget_id: str, action_id: str) -> str | None:
        return self._widget_action_state[widget_id].get(action_id)

    async def load_thread(self, thread_id: str, context: AuthContext) -> ThreadMetadata:
        thread = self._require_owned_thread_record(context.user_id, thread_id)
        return self._to_thread_metadata(thread)

    async def save_thread(self, thread: ThreadMetadata, context: AuthContext) -> None:
        with self._lock:
            existing = self._threads.get(thread.id)
            if existing and existing.user_id != context.user_id:
                raise NotFoundError(f"Thread {thread.id} not found.")
            created_at = existing.created_at if existing else int(thread.created_at.timestamp())
            user_id = existing.user_id if existing else context.user_id
            mode = existing.mode if existing else "ai"
            metadata = deepcopy(existing.metadata) if existing else {}
            metadata.update(thread.metadata)
            self._threads[thread.id] = ThreadRecord(
                id=thread.id,
                user_id=user_id,
                title=thread.title or (existing.title if existing else "New conversation"),
                created_at=created_at,
                updated_at=int(time.time()),
                mode=mode,
                metadata=metadata,
            )

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: AuthContext,
    ) -> Page[ThreadItem]:
        self._require_owned_thread_record(context.user_id, thread_id)
        items = [item.model_copy(deep=True) for item in self._chatkit_items[thread_id]]
        items.sort(key=lambda item: item.created_at, reverse=(order == "desc"))

        if after:
            after_index = next((index for index, item in enumerate(items) if item.id == after), None)
            if after_index is not None:
                items = items[after_index + 1 :]

        sliced = items[:limit]
        has_more = len(items) > limit
        next_after = sliced[-1].id if has_more and sliced else None
        return Page[ThreadItem](data=sliced, has_more=has_more, after=next_after)

    async def save_attachment(self, attachment: Attachment, context: AuthContext) -> None:
        with self._lock:
            self._attachments[attachment.id] = attachment.model_copy(deep=True)

    async def load_attachment(self, attachment_id: str, context: AuthContext) -> Attachment:
        attachment = self._attachments.get(attachment_id)
        if not attachment:
            raise NotFoundError(f"Attachment {attachment_id} not found.")
        return attachment.model_copy(deep=True)

    async def delete_attachment(self, attachment_id: str, context: AuthContext) -> None:
        with self._lock:
            self._attachments.pop(attachment_id, None)

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: AuthContext,
    ) -> Page[ThreadMetadata]:
        threads = [self._to_thread_metadata(thread) for thread in self._threads.values() if thread.user_id == context.user_id]
        threads.sort(key=lambda thread: thread.created_at, reverse=(order == "desc"))

        if after:
            after_index = next((index for index, thread in enumerate(threads) if thread.id == after), None)
            if after_index is not None:
                threads = threads[after_index + 1 :]

        sliced = threads[:limit]
        has_more = len(threads) > limit
        next_after = sliced[-1].id if has_more and sliced else None
        return Page[ThreadMetadata](data=sliced, has_more=has_more, after=next_after)

    async def add_thread_item(self, thread_id: str, item: ThreadItem, context: AuthContext) -> None:
        self._require_owned_thread_record(context.user_id, thread_id)
        with self._lock:
            self._chatkit_items[thread_id].append(item.model_copy(deep=True))

    async def save_item(self, thread_id: str, item: ThreadItem, context: AuthContext) -> None:
        self._require_owned_thread_record(context.user_id, thread_id)
        with self._lock:
            items = self._chatkit_items[thread_id]
            for index, existing in enumerate(items):
                if existing.id == item.id:
                    items[index] = item.model_copy(deep=True)
                    return
            items.append(item.model_copy(deep=True))

    async def load_item(self, thread_id: str, item_id: str, context: AuthContext) -> ThreadItem:
        self._require_owned_thread_record(context.user_id, thread_id)
        for item in self._chatkit_items[thread_id]:
            if item.id == item_id:
                return item.model_copy(deep=True)
        raise NotFoundError(f"Item {item_id} not found.")

    async def delete_thread(self, thread_id: str, context: AuthContext) -> None:
        self._require_owned_thread_record(context.user_id, thread_id)
        with self._lock:
            self._threads.pop(thread_id, None)
            self._chatkit_items.pop(thread_id, None)
            self._messages.pop(thread_id, None)
            self._widgets.pop(thread_id, None)

    async def delete_thread_item(self, thread_id: str, item_id: str, context: AuthContext) -> None:
        self._require_owned_thread_record(context.user_id, thread_id)
        with self._lock:
            self._chatkit_items[thread_id] = [item for item in self._chatkit_items[thread_id] if item.id != item_id]

    def _to_thread_metadata(self, thread: ThreadRecord) -> ThreadMetadata:
        return ThreadMetadata(
            id=thread.id,
            title=thread.title,
            created_at=datetime.fromtimestamp(thread.created_at),
            metadata=deepcopy(thread.metadata),
        )
