# Travel Booking ChatKit Lab

This repo now contains the Phase 1, Phase 2, and Phase 3 scaffold for the travel booking AI chat lab:

- `backend/`: FastAPI app centered on a `ChatKitServer` scaffold
- `frontend/`: Next.js app using ChatKit's native React SDK bootstrap path

## What Phase 1 implements

- secure app session bootstrap using an internal JWT stored in an `HttpOnly` cookie
- `POST /api/session` returning a `client_secret`
- `POST /api/session/refresh` for silent refresh
- strict thread ownership validation before issuing a `client_secret`
- a seeded demo data store to prove cross-user thread access is blocked
- a frontend page that tests an owned thread and an intentionally foreign thread

## What Phase 2 implements

- real-time backend streaming from `POST /api/chat/message`
- server-defined `FlightCard` widget emitted after streamed assistant text
- hidden widget actions sent to `POST /api/actions`
- duplicate-click prevention in both frontend and backend
- widget expiry and validation handling
- deterministic low-cost development behavior so the architecture can be exercised without repeated live model calls

## What Phase 3 implements

- human handoff using `Thread.mode` with `ai` and `human`
- dedicated WebSocket channel for user and agent real-time handoff messages
- agent takeover and return-to-AI endpoints
- automatic AI resumption with hidden summary context
- agent disconnect recovery with a grace period
- frontend support console and user chat surface updates for handoff mode
- architecture notes in [PHASE3_NOTES.md](./PHASE3_NOTES.md)

## Run the backend

```bash
cd backend
python -m uvicorn app.main:app --reload
```

## Run backend tests

```bash
cd backend
pytest
```

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

## Phase 1 cross-check against the lab brief

- The browser talks to the FastAPI backend, not directly to OpenAI.
- The backend issues `client_secret` only after verifying session identity and thread ownership.
- Replacing the thread ID with another user's thread returns `403 Forbidden`.

## Phase 2 cross-check against the lab brief

- Responses stream in real time from the backend.
- The backend emits a custom booking widget definition.
- The frontend renders the widget from a closed registry.
- Clicking `Book Now` sends a hidden backend event rather than a visible chat message.
- Loading state is shown immediately, and duplicate clicks are blocked.

## Phase 3 cross-check against the lab brief

- Human handoff is difficult with SSE because SSE is one-directional and does not naturally support a second producer.
- The implementation uses WebSockets for human handoff while keeping SSE for AI streaming.
- Switching AI providers leaves the frontend contract unchanged because the frontend still talks only to FastAPI.
