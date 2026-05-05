from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
            value = value[1:-1]
        os.environ.setdefault(key, value.replace("\\n", "\n"))


_load_env_file()


def _load_or_create_rsa_keys() -> tuple[str, str]:
    backend_dir = Path(__file__).resolve().parents[1]
    private_pem_path = backend_dir / "jwt-private.pem"
    public_pem_path = backend_dir / "jwt-public.pem"

    if private_pem_path.exists():
        private_pem = private_pem_path.read_text(encoding="utf-8")
        if public_pem_path.exists():
            return private_pem, public_pem_path.read_text(encoding="utf-8")

        private_key_obj = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
        derived_public_pem = private_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return private_pem, derived_public_pem

    private_key = os.getenv("JWT_PRIVATE_KEY")
    public_key = os.getenv("JWT_PUBLIC_KEY")
    if private_key and not public_key:
        private_key_obj = serialization.load_pem_private_key(private_key.encode("utf-8"), password=None)
        derived_public_pem = private_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return private_key, derived_public_pem
    if private_key and public_key:
        return private_key, public_key

    generated_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    generated_public_key = generated_private_key.public_key()
    private_pem = generated_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = generated_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


_DEFAULT_PRIVATE_KEY, _DEFAULT_PUBLIC_KEY = _load_or_create_rsa_keys()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Travel Booking ChatKit"
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    jwt_private_key: str = _DEFAULT_PRIVATE_KEY
    jwt_public_key: str = _DEFAULT_PUBLIC_KEY
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "RS256")
    jwt_cookie_name: str = os.getenv("JWT_COOKIE_NAME", "travel_app_session")
    jwt_ttl_seconds: int = int(os.getenv("JWT_TTL_SECONDS", "86400"))
    refresh_window_seconds: int = int(os.getenv("REFRESH_WINDOW_SECONDS", "300"))
    client_secret_ttl_seconds: int = int(os.getenv("CLIENT_SECRET_TTL_SECONDS", "900"))
    session_rate_limit_per_minute: int = int(os.getenv("SESSION_RATE_LIMIT_PER_MINUTE", "10"))
    chat_rate_limit_per_minute: int = int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "60"))
    allow_insecure_cookies: bool = os.getenv("ALLOW_INSECURE_COOKIES", "true").lower() == "true"
    agent_demo_key: str = os.getenv("AGENT_DEMO_KEY", "demo-agent-key")
    agent_disconnect_grace_seconds: int = int(os.getenv("AGENT_DISCONNECT_GRACE_SECONDS", "30"))


settings = Settings()
