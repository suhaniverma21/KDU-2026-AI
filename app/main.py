"""FastAPI app entry point for health checks, auth, profile APIs, chat, weather, and images."""

import json

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.image import analyze_image
from app.agents.router import route_request
from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.chat_service import (
    build_cross_session_memory_text,
    build_session_summary_text,
    generate_chat_reply,
    summarize_conversation_messages,
)
from app.database import (
    create_user,
    get_conversation_history,
    get_db_connection,
    get_old_messages_for_summary,
    get_session_message_count,
    get_session_summary,
    get_user_by_email,
    save_conversation_message,
    save_or_update_session_summary,
    search_past_conversations,
    update_user_profile,
)
from app.middleware.style_middleware import normalize_style
from app.models import (
    ChatRequest,
    ChatResponse,
    ConversationHistoryResponse,
    ConversationMessageResponse,
    DatabaseStatusResponse,
    ErrorResponse,
    HealthResponse,
    HistoryResponse,
    ImageAnalysisResponse,
    MessageResponse,
    ProfileResponse,
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserSignupRequest,
    WeatherResponse,
)
from app.tools.weather_tool import get_weather
from app.utils.safety import (
    get_output_guardrail_decision,
    get_prompt_guardrail_decision,
    is_approved_route,
    is_valid_location_text,
    validate_chat_input,
    validate_image_request,
    validate_text_output,
)


app = FastAPI(title="Multimodal AI Assistant")

# CORS allows the frontend running on localhost:5173 to call this API
# from the browser during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


REFERENCE_KEYWORDS = [
    "earlier",
    "before",
    "last time",
    "previous",
    "you said",
    "we discussed",
]

SUMMARY_TRIGGER_COUNT = 12
SUMMARY_KEEP_RECENT = 5
SAFE_CHAT_FALLBACK = (
    "I’m here to help safely and can’t adopt that behavior, "
    "but I can still help with your request in a safe way."
)


def error_response(
    message: str,
    status_code: int,
    details: object | None = None,
) -> JSONResponse:
    """Return errors in one consistent JSON shape.

    Structured output matters because frontend code and API users can rely
    on the same error format instead of handling many different shapes.
    """
    error_model = ErrorResponse(error=message, details=details)
    # jsonable_encoder converts values like bytes and datetimes into a
    # JSON-safe shape so error responses never crash while being returned.
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(error_model.model_dump()),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    """Convert FastAPI HTTP errors into the shared error schema."""
    return error_response(
        message=str(exc.detail),
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Return request validation failures in the shared error schema."""
    return error_response(
        message="Validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details=exc.errors(),
    )


def extract_city_from_message(message: str) -> str | None:
    """Try to find a city name from simple phrases like 'weather in Bengaluru'."""
    lowered = message.lower()
    for separator in [" in ", " at ", " for "]:
        if separator in lowered:
            city = message[lowered.rfind(separator) + len(separator):].strip(" ?!.,")
            if city:
                return city
    return None


def refers_to_past_conversation(message: str) -> bool:
    """Check whether the user is asking about something from the past."""
    lowered = message.lower()
    return any(keyword in lowered for keyword in REFERENCE_KEYWORDS)


def build_search_query_from_message(message: str) -> str:
    """Create a small keyword query for simple database searching.

    We remove a few common reference phrases so the LIKE search focuses on
    the main topic words instead of words like "earlier" or "before".
    """
    lowered = message.lower()
    for keyword in REFERENCE_KEYWORDS:
        lowered = lowered.replace(keyword, " ")
    return " ".join(lowered.split())



@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Small endpoint to confirm the API is running."""
    return HealthResponse(status="ok")


@app.get("/db-check", response_model=DatabaseStatusResponse, responses={500: {"model": ErrorResponse}})
async def db_check():
    """Try a simple MySQL query to confirm the database connection works."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        connection.close()
        return DatabaseStatusResponse(database="connected")
    except Exception as exc:
        return error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.post("/signup", response_model=MessageResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def signup(request: UserSignupRequest):
    """Create a new user and save a hashed password."""
    try:
        existing_user = get_user_by_email(request.email)
        if existing_user:
            return error_response("User already exists", status.HTTP_400_BAD_REQUEST)

        password_hash = hash_password(request.password)
        create_user(request.email, password_hash)
        return MessageResponse(message="User created successfully")
    except Exception as exc:
        return error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.post("/login", response_model=TokenResponse, responses={401: {"model": ErrorResponse}})
async def login(request: UserLoginRequest):
    """Verify email and password, then return a JWT."""
    try:
        user = get_user_by_email(request.email)
        if not user:
            return error_response("Invalid email or password", status.HTTP_401_UNAUTHORIZED)

        if not verify_password(request.password, user["password_hash"]):
            return error_response("Invalid email or password", status.HTTP_401_UNAUTHORIZED)

        token = create_access_token({"sub": user["email"]})
        return TokenResponse(access_token=token)
    except Exception as exc:
        return error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.get("/profile", response_model=ProfileResponse, responses={401: {"model": ErrorResponse}})
async def get_profile(current_user=Depends(get_current_user)):
    """Return the logged-in user's profile."""
    return ProfileResponse(
        email=current_user["email"],
        location=current_user["location"] or "",
        style=current_user["style"] or "casual",
    )


@app.put(
    "/profile",
    response_model=ProfileResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_profile(
    request: UserProfileUpdateRequest,
    current_user=Depends(get_current_user),
):
    """Update the logged-in user's location and style."""
    try:
        user = update_user_profile(
            email=current_user["email"],
            location=request.location,
            style=request.style,
        )
        return ProfileResponse(
            email=user["email"],
            location=user["location"] or "",
            style=user["style"] or "casual",
        )
    except Exception as exc:
        return error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.post(
    "/chat",
    response_model=ChatResponse | WeatherResponse | ImageAnalysisResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(request: ChatRequest, current_user=Depends(get_current_user)):
    """Save a user message, then handle weather or general chat.

    We first ask the router which flow to use. Routing keeps the decision
    logic in one place and makes the endpoint easier to read.
    """
    try:
        # Prompt-injection and jailbreak attempts are checked in layers:
        # 1. fast rule-based checks
        # 2. a lightweight classifier for paraphrased attempts
        # Stronger layers are needed because phrase-only matching is easy to bypass.
        guardrail_decision = get_prompt_guardrail_decision(request.message)
        if guardrail_decision.should_block:
            return error_response(
                "Request violates safety policy",
                status.HTTP_400_BAD_REQUEST,
                guardrail_decision.reason,
            )

        # Input guardrails check the request before we spend time on routing,
        # memory lookup, or model calls.
        input_error = validate_chat_input(
            message=request.message,
            session_id=request.session_id,
            image_url=request.image_url,
            image_path=request.image_path,
        )
        if input_error:
            return error_response(input_error, status.HTTP_400_BAD_REQUEST)

        # Load the user's preferred response style from the database profile.
        # If it is missing, we keep the behavior simple and default to casual.
        user_style = normalize_style(current_user.get("style"))
        image_reference = request.image_url or request.image_path
        selected_route = route_request(
            message=request.message,
            image_url=request.image_url,
            image_path=request.image_path,
        )

        # Processing guardrails make sure routing stays inside the approved
        # paths we support in this project.
        if not is_approved_route(selected_route):
            return error_response("Invalid route", status.HTTP_400_BAD_REQUEST)

        if selected_route == "image":
            image_error = validate_image_request(
                image_url=request.image_url,
                image_path=request.image_path,
            )
            if image_error:
                return error_response(image_error, status.HTTP_400_BAD_REQUEST)

        # session_id is a simple label that groups messages from one conversation.
        save_conversation_message(
            user_id=current_user["id"],
            session_id=request.session_id,
            role="user",
            content=request.message,
            image_url=image_reference,
        )

        if selected_route == "image":
            image_result, image_model = analyze_image(
                message=request.message,
                image_url=request.image_url,
                image_path=request.image_path,
                style=user_style,
            )
            image_result["route"] = "image"
            image_result["model_used"] = image_model
            image_response = ImageAnalysisResponse(**image_result)

            save_conversation_message(
                user_id=current_user["id"],
                session_id=request.session_id,
                role="assistant",
                content=json.dumps(image_result),
            )

            return image_response

        if selected_route == "weather":
            # First look for a city in the user's message.
            # If no city is mentioned, fall back to the user's saved profile location.
            city = extract_city_from_message(request.message)
            if not city:
                city = (current_user["location"] or "").strip()

            if not city or not is_valid_location_text(city):
                return error_response(
                    "Location not set. Please update your profile.",
                    status.HTTP_400_BAD_REQUEST,
                )

            weather_data = await get_weather(city)
            weather_data["route"] = "weather"
            weather_data["model_used"] = None
            weather_response = WeatherResponse(**weather_data)

            # Save a readable assistant message so history still shows the answer.
            assistant_message = (
                f"Weather in {weather_response.location}: "
                f"{weather_response.summary}, {weather_response.temperature} C"
            )
            weather_output_error = validate_text_output(assistant_message)
            if weather_output_error:
                return error_response(weather_output_error, status.HTTP_500_INTERNAL_SERVER_ERROR)
            save_conversation_message(
                user_id=current_user["id"],
                session_id=request.session_id,
                role="assistant",
                content=assistant_message,
            )

            return weather_response

        # Short-term memory means we only send the recent messages from
        # this same session. That gives the model context without pulling
        # in old conversations from other sessions.
        session_summary = ""
        try:
            message_count = get_session_message_count(
                user_id=current_user["id"],
                session_id=request.session_id,
            )

            # When a session gets long, we summarize the older part and keep
            # only the latest few messages in full detail.
            if message_count > SUMMARY_TRIGGER_COUNT:
                old_messages = get_old_messages_for_summary(
                    user_id=current_user["id"],
                    session_id=request.session_id,
                    keep_recent=SUMMARY_KEEP_RECENT,
                )
                if old_messages:
                    summary_text, _summary_model = summarize_conversation_messages(old_messages)
                    if summary_text:
                        save_or_update_session_summary(
                            user_id=current_user["id"],
                            session_id=request.session_id,
                            summary=summary_text,
                        )

            session_summary = build_session_summary_text(
                get_session_summary(
                    user_id=current_user["id"],
                    session_id=request.session_id,
                )
            )
        except Exception:
            # Summarization should help when available, but it should never
            # break the normal chat flow if something goes wrong.
            session_summary = ""

        history_messages = get_conversation_history(
            user_id=current_user["id"],
            session_id=request.session_id,
            limit=SUMMARY_KEEP_RECENT,
        )

        # Cross-session memory is only used when the message sounds like
        # the user is referring to something discussed before. The queries
        # always use the authenticated user's id, so one user cannot load
        # another user's memory.
        cross_session_memory = ""
        if selected_route == "memory_chat" or refers_to_past_conversation(request.message):
            search_query = build_search_query_from_message(request.message)
            if search_query:
                past_messages = search_past_conversations(
                    user_id=current_user["id"],
                    query=search_query,
                    limit=3,
                )
                cross_session_memory = build_cross_session_memory_text(past_messages)

        reply, chat_model = generate_chat_reply(
            history_messages,
            style=user_style,
            user_message=request.message,
            should_sanitize_user_message=guardrail_decision.should_sanitize,
            cross_session_memory=cross_session_memory,
            session_summary=session_summary,
        )

        # Output guardrails protect the user even if the model still tries to
        # follow an unsafe persona override. In that case we return a safe
        # backend-generated fallback instead of the raw model output.
        output_decision = get_output_guardrail_decision(reply)
        if output_decision.should_block:
            reply = SAFE_CHAT_FALLBACK

        save_conversation_message(
            user_id=current_user["id"],
            session_id=request.session_id,
            role="assistant",
            content=reply,
        )

        return ChatResponse(
            session_id=request.session_id,
            reply=reply,
            style=user_style,
            route=selected_route,
            model_used=chat_model,
        )
    except ValueError as exc:
        return error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as exc:
        return error_response(
            f"Could not generate chat reply: {exc}",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@app.get("/history", response_model=HistoryResponse, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def history(session_id: str = Query(..., min_length=1), current_user=Depends(get_current_user)):
    """Return recent saved messages for one chat session."""
    try:
        messages = get_conversation_history(
            user_id=current_user["id"],
            session_id=session_id,
        )
        return HistoryResponse(
            session_id=session_id,
            messages=[
                ConversationMessageResponse(
                    role=message["role"],
                    content=message["content"],
                    created_at=message["created_at"],
                )
                for message in messages
            ],
        )
    except Exception as exc:
        return error_response(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
