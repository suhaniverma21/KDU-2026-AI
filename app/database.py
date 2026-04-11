"""Simple MySQL helpers for authentication, profiles, and chat storage."""

from urllib.parse import urlparse

import mysql.connector
from mysql.connector import Error

from app.config import settings


def get_db_connection():
    """Create and return one MySQL connection."""
    try:
        # Parse the DATABASE_URL so the connection values are easy to follow.
        connection_url = settings.database_url.replace(
            "mysql+mysqlconnector://",
            "mysql://",
            1,
        )
        parsed = urlparse(connection_url)

        return mysql.connector.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
        )
    except Error as exc:
        # Raise a simple message that main.py can show in the API response.
        raise ConnectionError(f"Could not connect to MySQL: {exc}") from exc


def get_user_by_email(email: str):
    """Find one user by email and return the row as a dictionary."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, email, password_hash, location, style, created_at, updated_at
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        return cursor.fetchone()
    except Error as exc:
        raise ConnectionError(f"Could not load user: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def create_user(email: str, password_hash: str):
    """Create a new user with a hashed password."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, location, style)
            VALUES (%s, %s, %s, %s)
            """,
            (email, password_hash, "", "casual"),
        )
        connection.commit()
        return get_user_by_email(email)
    except Error as exc:
        raise ConnectionError(f"Could not create user: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def update_user_profile(email: str, location: str, style: str):
    """Update location and style, then return the latest user profile."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET location = %s, style = %s, updated_at = CURRENT_TIMESTAMP
            WHERE email = %s
            """,
            (location, style, email),
        )
        connection.commit()
        return get_user_by_email(email)
    except Error as exc:
        raise ConnectionError(f"Could not update user profile: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def save_conversation_message(
    user_id: int,
    session_id: str,
    role: str,
    content: str,
    image_url: str | None = None,
):
    """Save one chat message for a user and session.

    We save both user and assistant messages so the full conversation
    can be shown again later.
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO conversations (user_id, session_id, role, content, image_url)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, session_id, role, content, image_url),
        )
        connection.commit()
    except Error as exc:
        raise ConnectionError(f"Could not save conversation message: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def get_conversation_history(user_id: int, session_id: str, limit: int = 10):
    """Return recent messages for one session in display order.

    This is our short-term memory for one session. We first load a small
    number of newest rows, then reverse them so both the frontend and the
    model can read them oldest to newest.
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT role, content, image_url, created_at
            FROM conversations
            WHERE user_id = %s AND session_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, session_id, limit),
        )
        messages = cursor.fetchall()
        messages.reverse()
        return messages
    except Error as exc:
        raise ConnectionError(f"Could not load conversation history: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def search_past_conversations(user_id: int, query: str, limit: int = 3):
    """Search older conversation messages for the same user.

    This is our first cross-session memory step. We use a simple LIKE query
    instead of embeddings so the logic stays easy to read and learn from.
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        search_text = f"%{query}%"
        cursor.execute(
            """
            SELECT session_id, role, content, created_at
            FROM conversations
            WHERE user_id = %s AND content LIKE %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, search_text, limit),
        )
        return cursor.fetchall()
    except Error:
        # Cross-session memory should never break normal chat.
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def get_session_message_count(user_id: int, session_id: str) -> int:
    """Return how many messages exist in the current session."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM conversations
            WHERE user_id = %s AND session_id = %s
            """,
            (user_id, session_id),
        )
        result = cursor.fetchone()
        return int(result[0]) if result else 0
    except Error as exc:
        raise ConnectionError(f"Could not count session messages: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def get_old_messages_for_summary(user_id: int, session_id: str, keep_recent: int = 5):
    """Load older session messages and leave the most recent ones out.

    We summarize older messages but keep the latest few messages in full
    detail because they are usually the most important for the next reply.
    """
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT role, content, created_at
            FROM conversations
            WHERE user_id = %s AND session_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, session_id),
        )
        messages = cursor.fetchall()
        if len(messages) <= keep_recent:
            return []
        return messages[:-keep_recent]
    except Error as exc:
        raise ConnectionError(f"Could not load old messages for summary: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def save_or_update_session_summary(user_id: int, session_id: str, summary: str):
    """Create or update the saved summary for one session."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO conversation_summaries (user_id, session_id, summary)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE summary = VALUES(summary), updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, session_id, summary),
        )
        connection.commit()
    except Error as exc:
        raise ConnectionError(f"Could not save session summary: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def get_session_summary(user_id: int, session_id: str) -> str:
    """Return the saved summary text for one session, if it exists."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT summary
            FROM conversation_summaries
            WHERE user_id = %s AND session_id = %s
            LIMIT 1
            """,
            (user_id, session_id),
        )
        result = cursor.fetchone()
        if not result:
            return ""
        return result["summary"] or ""
    except Error as exc:
        raise ConnectionError(f"Could not load session summary: {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
