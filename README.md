# FastAPI Production Template

A production-ready FastAPI template for building secure, testable, and extensible REST APIs with JWT authentication, RBAC, async SQLAlchemy, Alembic migrations, and a TDD-first workflow.

## Features

- JWT authentication with user registration and login
- Protected endpoints with bearer-token authentication
- Role-based access control with `user` and `admin` roles
- Async SQLAlchemy 2.0 database layer
- Alembic database migrations
- Pydantic v2 request validation and response models
- CORS middleware for browser-based clients
- Structured JSON request logging with request IDs
- Pytest-based automated test suite
- Auto-generated OpenAPI docs via Swagger UI and ReDoc
- PostgreSQL-first configuration with optional SQLite fallback for local-only experiments

## Tech Stack

| Component | Technology |
|---|---|
| API framework | FastAPI |
| ASGI server | Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Database drivers | `aiosqlite`, `asyncpg` |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | JWT via `python-jose` |
| Password hashing | `passlib[bcrypt]` + `bcrypt` |
| Testing | pytest, pytest-asyncio, httpx |
| Logging | Python `logging` with JSON formatter |

## Prerequisites

- Python 3.11+
- `pip`
- PostgreSQL 15+ or Docker for local database setup
- SQLite only if you intentionally choose the fallback configuration

## Quick Start

Set the project up in a few minutes:

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd Fast-API-Template

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Start PostgreSQL
docker compose up -d postgres

# 5. Copy environment variables
copy .env.example .env
# macOS / Linux: cp .env.example .env

# 6. Run database migrations
alembic upgrade head

# 7. Start the development server
uvicorn app.main:app --reload
```

Once the server is running, open:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## Environment Variables

This project reads configuration from `.env` using `pydantic-settings`.

Current variables from `.env.example`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Main application database connection string |
| `TEST_DATABASE_URL` | Separate database used by the test suite |
| `SECRET_KEY` | Secret used to sign JWT access tokens |
| `ALGORITHM` | JWT signing algorithm, currently `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime in minutes |
| `ENVIRONMENT` | Runtime environment, such as `development` |
| `LOG_LEVEL` | Logging level for structured request logs |
| `LOG_FORMAT` | `auto`, `json`, or `text` for environment-aware logging |
| `CORS_ORIGINS` | Comma-separated list of allowed browser origins |

Example:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_template
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_template_test
SECRET_KEY=change-this-to-a-random-string-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ENVIRONMENT=development
LOG_LEVEL=INFO
LOG_FORMAT=auto
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

Generate a secure `SECRET_KEY` with:

```bash
openssl rand -hex 32
```

Important notes:

- Never commit your real `.env` file
- Use a different `SECRET_KEY` for every environment
- Keep `TEST_DATABASE_URL` separate from `DATABASE_URL`
- PostgreSQL is the default path; SQLite is a deliberate fallback override

## Project Structure

```text
Fast-API-Template/
+-- app/
|   +-- main.py                    # FastAPI app setup, middleware, routers
|   +-- api/
|   |   +-- v1/
|   |       +-- router.py          # Versioned API router
|   |       +-- endpoints/
|   |           +-- admin.py       # Admin-only endpoints
|   |           +-- auth.py        # Registration and login
|   |           +-- users.py       # Protected user endpoints
|   +-- core/
|   |   +-- config.py              # Environment-backed settings
|   |   +-- logging.py             # JSON logging configuration
|   |   +-- security.py            # Password hashing and JWT creation
|   +-- db/
|   |   +-- base.py                # Shared SQLAlchemy base model
|   |   +-- session.py             # Async engine and session factory
|   +-- middleware/
|   |   +-- logging_middleware.py  # Request ID and request logging
|   +-- models/
|   |   +-- user.py                # User model and role enum
|   +-- schemas/
|   |   +-- token.py               # Token schemas
|   |   +-- user.py                # User request/response schemas
|   +-- services/
|   |   +-- user_service.py        # User business logic
|   +-- utils/
|       +-- dependencies.py        # DB, auth, and RBAC dependencies
+-- alembic/
|   +-- env.py                     # Alembic environment config
|   +-- versions/                  # Migration files
+-- tests/
|   +-- conftest.py                # Shared pytest fixtures
|   +-- test_api/                  # Endpoint and auth tests
|   +-- test_middleware/           # CORS and logging tests
|   +-- test_models/               # Model tests
+-- .env.example                   # Environment variable template
+-- alembic.ini                    # Alembic CLI config
+-- requirements.txt               # Runtime dependencies
+-- requirements-dev.txt           # Test/dev dependencies
+-- pytest.ini                     # Pytest configuration
```

## API Documentation

FastAPI generates interactive documentation automatically:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Example: Register a User

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "SecurePass123!",
    "full_name": "John Doe"
  }'
```

### Example: Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john@example.com&password=SecurePass123!"
```

### Example: Access a Protected Endpoint

```bash
curl "http://localhost:8000/api/v1/users/me" \
  -H "Authorization: Bearer <access_token>"
```

## Testing

The template is built with TDD in mind: tests first, implementation second.

Run the full test suite:

```bash
pytest -v
```

Run with coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

Run a specific file:

```bash
pytest tests/test_api/test_auth.py -v
```

Coverage target:

- Minimum target: `70%+`
- Current project expectation: keep coverage healthy as new features are added

## Database Migrations

Alembic manages schema changes.

Start the local PostgreSQL service:

```bash
docker compose up -d postgres
```

Apply all migrations:

```bash
alembic upgrade head
```

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "Describe your schema change"
```

Roll back one migration:

```bash
alembic downgrade -1
```

Check current migration version:

```bash
alembic current
```

View migration history:

```bash
alembic history
```

## Extending the Template

The recommended workflow is always:

1. Write tests first
2. Run them and confirm they fail
3. Implement the smallest working solution
4. Re-run tests until green
5. Refactor safely

### Example: Adding a `posts` Resource

1. Create tests in `tests/test_api/test_posts.py`
   Define the behavior for creating, listing, and protecting posts.
2. Add a model in `app/models/post.py`
   Define the SQLAlchemy table and relationships.
3. Add schemas in `app/schemas/post.py`
   Separate create/update/response schemas.
4. Generate a migration
   Run `alembic revision --autogenerate -m "Add posts table"` and then `alembic upgrade head`.
5. Add a service in `app/services/post_service.py`
   Keep business logic outside the route layer.
6. Add endpoints in `app/api/v1/endpoints/posts.py`
   Use `Depends(get_db)` and auth dependencies as needed.
7. Register the router in `app/api/v1/router.py`
8. Re-run tests and refactor

Minimal example:

```python
@router.post("/", status_code=201, response_model=PostResponse)
async def create_post(
    post_data: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PostResponse:
    post = await PostService.create_post(db, post_data, current_user.id)
    return PostResponse.model_validate(post)
```

## Deployment

This repository includes a lightweight PostgreSQL Docker Compose setup for local development and production-like testing.

### Basic Production Guidance

- Use PostgreSQL instead of SQLite
- Set a strong `SECRET_KEY`
- Restrict `CORS_ORIGINS` to trusted frontend origins only
- Run behind a production ASGI process and reverse proxy
- Keep `.env` values environment-specific

Start without reload in a production-style environment:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker Option

Start the bundled PostgreSQL container:

```bash
docker compose up -d postgres
```

Then use the PostgreSQL values from `.env.example` in your `.env` file.

### Security Checklist

- Store secrets in environment variables
- Never log passwords or bearer tokens
- Use HTTPS in production
- Use PostgreSQL with separate prod and test databases
- Rotate secrets when compromised
- Keep dependency versions updated

## Troubleshooting

### `401 Unauthorized`

- Check the `Authorization` header format: `Bearer <token>`
- Make sure the token is not expired
- Verify the user still exists and is active
- Confirm the `SECRET_KEY` matches the signing environment

### Database connection errors

- Verify `DATABASE_URL` is correct
- Ensure the database service is running
- For PostgreSQL, confirm the user, password, host, and port

### Migration issues

- Run `alembic current` to inspect the current revision
- Run `alembic history` to see available revisions
- If the database is out of sync in development, reset carefully before reapplying migrations

### CORS issues in the browser

- Ensure the frontend origin is listed in `CORS_ORIGINS`
- Confirm the request is going to the expected backend URL
- Recheck browser preflight requests in the network tab

### Tests failing unexpectedly

- Confirm the virtual environment is active
- Ensure dev dependencies are installed
- Check that the test DB URL points to a separate test database
- Re-run a single failing file with `-v` for more context

## Contributing

Contributions are welcome. Please keep changes aligned with the template goals.

Guidelines:

- Follow TDD: tests first, code second
- Use async SQLAlchemy patterns
- Add type hints and docstrings
- Keep route logic thin and push business rules into services
- Avoid logging secrets or credentials
- Run tests before opening a PR

Suggested workflow:

```bash
git checkout -b feature/your-change
pytest -v
pytest --cov=app --cov-report=term-missing
```

## License

This project is intended to use the MIT License. Add a `LICENSE` file before publishing or distributing the template.

## Useful References

- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0: https://docs.sqlalchemy.org/en/20/
- Alembic: https://alembic.sqlalchemy.org/
- Pydantic: https://docs.pydantic.dev/
- pytest: https://docs.pytest.org/
