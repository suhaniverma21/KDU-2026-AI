from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from chatkit.types import AssistantMessageContent, AssistantMessageItem
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .chatkit_server import StreamingResult, TravelChatKitServer, sse_event
from .config import settings
from .models import (
    ActionResponse,
    AgentMessageRequest,
    AgentReturnRequest,
    AgentTakeoverRequest,
    AuthContext,
    CancelStreamRequest,
    ChatMessageRequest,
    DemoLoginRequest,
    DemoLoginResponse,
    SessionBootstrapRequest,
    SessionResponse,
    ThreadMessagesResponse,
    ThreadSummary,
    WidgetActionRequest,
)
from .security import decode_internal_jwt, get_auth_context, get_cookie_token, mint_internal_jwt, should_refresh
from .store import InMemoryStore


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[int]] = defaultdict(deque)

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> None:
        now = int(time.time())
        bucket = self._buckets[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= max_requests:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded.")
        bucket.append(now)


class HandoffConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[str, set[WebSocket]]] = defaultdict(lambda: {"user": set(), "agent": set()})
        self._disconnect_tasks: dict[str, asyncio.Task[None]] = {}

    async def connect(self, thread_id: str, role: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[thread_id][role].add(websocket)
        task = self._disconnect_tasks.pop(thread_id, None)
        if task:
            task.cancel()

    def disconnect(self, thread_id: str, role: str, websocket: WebSocket) -> bool:
        self._connections[thread_id][role].discard(websocket)
        return len(self._connections.get(thread_id, {}).get("agent", set())) == 0

    async def broadcast(self, thread_id: str, role: str | None, payload: dict[str, Any]) -> None:
        target_roles = [role] if role else ["user", "agent"]
        for target_role in target_roles:
            sockets = list(self._connections.get(thread_id, {}).get(target_role, set()))
            for socket in sockets:
                try:
                    await socket.send_json(payload)
                except RuntimeError:
                    self._connections[thread_id][target_role].discard(socket)

    def schedule_agent_disconnect_reset(self, thread_id: str, callback: Any) -> None:
        async def delayed_reset() -> None:
            try:
                await asyncio.sleep(settings.agent_disconnect_grace_seconds)
                await callback(thread_id)
            except asyncio.CancelledError:
                return

        existing = self._disconnect_tasks.pop(thread_id, None)
        if existing:
            existing.cancel()
        self._disconnect_tasks[thread_id] = asyncio.create_task(delayed_reset())


store = InMemoryStore()
chatkit_server = TravelChatKitServer(store)
rate_limiter = InMemoryRateLimiter()
handoff_manager = HandoffConnectionManager()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=token,
        httponly=True,
        secure=not settings.allow_insecure_cookies,
        samesite="lax",
        max_age=settings.jwt_ttl_seconds,
    )


def issue_client_secret(user_id: str, thread_id: str) -> SessionResponse:
    expires_at = int(time.time()) + settings.client_secret_ttl_seconds
    session_id, client_secret = store.save_client_secret(user_id, thread_id, expires_at)
    return SessionResponse(
        client_secret=client_secret,
        expires_at=expires_at,
        thread_id=thread_id,
        session_id=session_id,
    )


def require_owned_thread(user_id: str, thread_id: str) -> None:
    if not store.get_thread(thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This conversation no longer exists.")
    if not store.user_owns_thread(user_id, thread_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this conversation.")


def require_valid_client_secret(user_id: str, thread_id: str, client_secret: str) -> dict[str, int | str]:
    record = store.get_client_secret_record(client_secret)
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client secret.")
    if int(record["expires_at"]) <= int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client secret expired.")
    if record["user_id"] != user_id or record["thread_id"] != thread_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this conversation.")
    return record


def require_agent_key(agent_key: str | None) -> None:
    if agent_key != settings.agent_demo_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials.")


async def broadcast_human_mode_user_message(thread_id: str, text: str) -> None:
    message = store.add_message(thread_id, "user", text)
    await handoff_manager.broadcast(
        thread_id,
        "agent",
        {
            "event": "user_message",
            "thread_id": thread_id,
            "message": message.model_dump(),
        },
    )


async def resume_ai_after_agent_disconnect(thread_id: str) -> None:
    thread = store.get_thread(thread_id)
    if not thread or thread.mode != "human":
        return
    store.set_thread_mode(thread_id, "ai")
    store.add_message(
        thread_id,
        "tool",
        {"kind": "handoff_resume", "summary": "Agent disconnected unexpectedly. AI resumed automatically."},
        hidden=True,
    )
    await handoff_manager.broadcast(
        thread_id,
        "user",
        {
            "event": "ai_resumed",
            "thread_id": thread_id,
            "thread_mode": "ai",
            "message": "Your agent became unavailable. The AI assistant has resumed.",
        },
    )


chatkit_server.set_human_message_callback(broadcast_human_mode_user_message)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/dev/login", response_model=DemoLoginResponse)
def dev_login(payload: DemoLoginRequest, response: Response, request: Request) -> DemoLoginResponse:
    rate_limiter.check(f"login:{request.client.host if request.client else 'unknown'}", settings.session_rate_limit_per_minute)
    threads = store.list_threads_for_user(payload.user_id)
    if not threads:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown demo user.")

    default_thread = threads[0]
    token = mint_internal_jwt(payload.user_id, default_thread.id)
    set_auth_cookie(response, token)
    return DemoLoginResponse(
        user_id=payload.user_id,
        thread_ids=[thread.id for thread in threads],
        default_thread_id=default_thread.id,
    )


@app.post("/api/session", response_model=SessionResponse)
def create_session(
    payload: SessionBootstrapRequest,
    request: Request,
    cookie_token: str = Depends(get_cookie_token),
) -> SessionResponse:
    rate_limiter.check(f"session:{request.client.host if request.client else 'unknown'}", settings.session_rate_limit_per_minute)
    auth = decode_internal_jwt(cookie_token)
    if not store.get_thread(payload.thread_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This conversation no longer exists.")
    if not store.user_owns_thread(auth.user_id, payload.thread_id):
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    return issue_client_secret(auth.user_id, payload.thread_id)


@app.post("/api/session/refresh", response_model=SessionResponse)
def refresh_session(
    payload: SessionBootstrapRequest,
    response: Response,
    auth=Depends(get_auth_context),
) -> SessionResponse:
    require_owned_thread(auth.user_id, payload.thread_id)
    new_token = mint_internal_jwt(auth.user_id, payload.thread_id)
    set_auth_cookie(response, new_token)
    return issue_client_secret(auth.user_id, payload.thread_id)


@app.get("/api/threads", response_model=list[ThreadSummary])
def list_threads(auth=Depends(get_auth_context)) -> list[ThreadSummary]:
    return [
        ThreadSummary(id=thread.id, title=thread.title, mode=thread.mode)
        for thread in store.list_threads_for_user(auth.user_id)
    ]


@app.get("/api/thread/{thread_id}")
def get_thread(thread_id: str, auth=Depends(get_auth_context)) -> dict[str, Any]:
    require_owned_thread(auth.user_id, thread_id)
    return store.get_thread(thread_id).model_dump()  # type: ignore[union-attr]


@app.get("/api/thread/{thread_id}/messages", response_model=ThreadMessagesResponse)
def get_thread_messages(
    thread_id: str,
    since: str | None = Query(default=None),
    auth=Depends(get_auth_context),
) -> ThreadMessagesResponse:
    require_owned_thread(auth.user_id, thread_id)
    thread = store.get_thread(thread_id)
    return ThreadMessagesResponse(
        messages=store.list_visible_messages(thread_id, since=since),
        widgets=store.list_widgets(thread_id),
        thread_mode=thread.mode if thread else "ai",
    )


@app.get("/api/session/status")
def session_status(auth=Depends(get_auth_context)) -> dict[str, Any]:
    return {
        "user_id": auth.user_id,
        "thread_id": auth.thread_id,
        "expires_at": auth.expires_at,
        "refresh_recommended": should_refresh(auth.expires_at),
    }


@app.post("/api/chat/message")
async def chat_message(payload: ChatMessageRequest, request: Request, auth=Depends(get_auth_context)) -> StreamingResponse:
    rate_limiter.check(f"chat:{auth.user_id}", settings.chat_rate_limit_per_minute)
    require_owned_thread(auth.user_id, payload.thread_id)
    require_valid_client_secret(auth.user_id, payload.thread_id, payload.client_secret)
    thread = store.get_thread(payload.thread_id)

    if thread and thread.mode == "human":
        human_message = store.add_message(payload.thread_id, "user", payload.text)

        async def human_mode_stream():
            stream_id = f"stream_human_{human_message.id}"
            yield sse_event("status", {"status": "submitted", "stream_id": stream_id, "message_id": human_message.id})
            await handoff_manager.broadcast(
                payload.thread_id,
                "agent",
                {
                    "event": "user_message",
                    "thread_id": payload.thread_id,
                    "message": human_message.model_dump(),
                },
            )
            yield sse_event("human_mode", {"thread_mode": "human", "message": "You are now connected with a support agent."})
            yield sse_event("stream_end", {"status": "ready", "stream_id": stream_id})

        return StreamingResponse(human_mode_stream(), media_type="text/event-stream")

    stream_id, event_iterator = await chatkit_server.stream_message(auth=auth, thread_id=payload.thread_id, text=payload.text)
    headers = {"X-Stream-Id": stream_id}
    return StreamingResponse(event_iterator, media_type="text/event-stream", headers=headers)


@app.post("/api/chat/cancel")
def cancel_chat_stream(payload: CancelStreamRequest, auth=Depends(get_auth_context)) -> dict[str, Any]:
    require_owned_thread(auth.user_id, payload.thread_id)
    chatkit_server.cancel_stream(payload.stream_id)
    return {"stream_id": payload.stream_id, "status": "cancelled"}


@app.post("/api/actions", response_model=ActionResponse)
async def widget_action(payload: WidgetActionRequest, auth=Depends(get_auth_context)) -> ActionResponse:
    rate_limiter.check(f"action:{auth.user_id}", settings.chat_rate_limit_per_minute)
    require_owned_thread(auth.user_id, payload.thread_id)
    require_valid_client_secret(auth.user_id, payload.thread_id, payload.client_secret)

    try:
        assistant_message, widget = await chatkit_server.handle_action(auth=auth, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found.") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This offer is no longer available. Search again?") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Action already completed.") from exc

    return ActionResponse(
        assistant_message=assistant_message,
        widget=widget,
        widget_id=payload.widget_id,
        action_id=payload.action_id,
    )


@app.post("/api/agent/takeover")
async def agent_takeover(
    payload: AgentTakeoverRequest,
    x_agent_key: str | None = Header(default=None),
) -> dict[str, Any]:
    require_agent_key(x_agent_key)
    thread = store.get_thread(payload.thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This conversation no longer exists.")
    store.set_thread_mode(payload.thread_id, "human")
    await handoff_manager.broadcast(
        payload.thread_id,
        None,
        {
            "event": "agent_joined",
            "thread_id": payload.thread_id,
            "agent_name": payload.agent_name,
            "thread_mode": "human",
            "message": "You are now connected with a support agent.",
        },
    )
    return {"thread_id": payload.thread_id, "thread_mode": "human", "agent_name": payload.agent_name}


@app.post("/api/agent/message")
async def agent_message(
    payload: AgentMessageRequest,
    x_agent_key: str | None = Header(default=None),
) -> dict[str, Any]:
    require_agent_key(x_agent_key)
    thread = store.get_thread(payload.thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This conversation no longer exists.")
    if thread.mode != "human":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Thread is not in human handoff mode.")

    message = store.add_message(payload.thread_id, "assistant", f"{payload.agent_name}: {payload.text}")
    thread_metadata = await store.load_thread(payload.thread_id, context=AuthContext(user_id=thread.user_id, thread_id=payload.thread_id, issued_at=0, expires_at=0))
    await store.add_thread_item(
        payload.thread_id,
        AssistantMessageItem(
            id=store.generate_item_id("message", thread_metadata, AuthContext(user_id=thread.user_id, thread_id=payload.thread_id, issued_at=0, expires_at=0)),
            thread_id=payload.thread_id,
            created_at=datetime.fromtimestamp(message.timestamp),
            content=[AssistantMessageContent(text=f"{payload.agent_name}: {payload.text}")],
        ),
        context=AuthContext(user_id=thread.user_id, thread_id=payload.thread_id, issued_at=0, expires_at=0),
    )
    await handoff_manager.broadcast(
        payload.thread_id,
        "user",
        {
            "event": "human_agent_message",
            "thread_id": payload.thread_id,
            "agent_name": payload.agent_name,
            "message": message.model_dump(),
        },
    )
    await handoff_manager.broadcast(
        payload.thread_id,
        "agent",
        {
            "event": "agent_message_echo",
            "thread_id": payload.thread_id,
            "agent_name": payload.agent_name,
            "message": message.model_dump(),
        },
    )
    return {"status": "delivered", "message": message.model_dump()}


@app.post("/api/agent/return-to-ai")
async def agent_return_to_ai(
    payload: AgentReturnRequest,
    x_agent_key: str | None = Header(default=None),
) -> dict[str, Any]:
    require_agent_key(x_agent_key)
    thread = store.get_thread(payload.thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This conversation no longer exists.")
    store.add_message(
        payload.thread_id,
        "tool",
        {"kind": "handoff_summary", "summary": payload.summary, "agent_name": payload.agent_name},
        hidden=True,
    )
    store.set_thread_mode(payload.thread_id, "ai")
    await handoff_manager.broadcast(
        payload.thread_id,
        None,
        {
            "event": "ai_resumed",
            "thread_id": payload.thread_id,
            "thread_mode": "ai",
            "message": "The support handoff ended. The AI assistant has resumed.",
        },
    )
    return {"thread_id": payload.thread_id, "thread_mode": "ai"}


@app.websocket("/ws/handoff/{thread_id}")
async def handoff_websocket(
    websocket: WebSocket,
    thread_id: str,
    role: str = Query(default="user"),
    agent_key: str | None = Query(default=None),
) -> None:
    if role not in {"user", "agent"}:
        await websocket.close(code=1008)
        return

    if role == "user":
        cookie_token = websocket.cookies.get(settings.jwt_cookie_name)
        if not cookie_token:
            await websocket.close(code=4401)
            return
        try:
            auth = decode_internal_jwt(cookie_token)
            require_owned_thread(auth.user_id, thread_id)
        except HTTPException:
            await websocket.close(code=4403)
            return
    else:
        if agent_key != settings.agent_demo_key:
            await websocket.close(code=4401)
            return

    await handoff_manager.connect(thread_id, role, websocket)
    thread = store.get_thread(thread_id)
    await websocket.send_json(
        {
            "event": "connected",
            "thread_id": thread_id,
            "role": role,
            "thread_mode": thread.mode if thread else "ai",
        }
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        no_agents_left = handoff_manager.disconnect(thread_id, role, websocket)
        if role == "agent" and no_agents_left:
            handoff_manager.schedule_agent_disconnect_reset(thread_id, resume_ai_after_agent_disconnect)


@app.post("/api/chatkit")
async def chatkit_endpoint(request: Request, auth=Depends(get_auth_context)) -> Response:
    body = await request.body()
    result = await chatkit_server.process(body, auth)
    if isinstance(result, StreamingResult):
        return StreamingResponse(result, media_type="text/event-stream")
    if hasattr(result, "json"):
        return Response(content=result.json, media_type="application/json")
    return JSONResponse({"detail": "Unexpected ChatKit response."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
