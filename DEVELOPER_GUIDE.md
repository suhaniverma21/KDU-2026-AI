Updated agents.md
markdown# Agent Instructions for FastAPI Template

## Project Goal
Build a production-ready FastAPI template that's reusable, secure, and easy to extend.

## CRITICAL: Test-Driven Development (TDD)

**MANDATORY APPROACH:**
1. ALWAYS write tests FIRST, then implementation
2. NEVER modify tests to match implementation - tests define the specification
3. Run tests to verify they fail (RED phase)
4. Write minimal code to pass tests (GREEN phase)
5. Refactor while keeping tests passing
6. Move to next feature only after all tests pass

**Why TDD:**
- Prevents AI from "cheating" by writing tests that match buggy code
- Tests serve as specification and documentation
- Ensures code actually works as intended
- Maintains high test coverage naturally

## Project Structure
app/
├── main.py              # FastAPI app
├── core/
│   ├── config.py        # Settings
│   ├── security.py      # JWT & password hashing
│   └── logging.py       # Logging config
├── api/v1/
│   ├── router.py
│   └── endpoints/       # Route files
├── models/              # SQLAlchemy models
├── schemas/             # Pydantic schemas
├── db/
│   ├── base.py
│   └── session.py
├── services/            # Business logic
└── utils/
└── dependencies.py  # Auth dependencies
tests/
├── conftest.py          # Shared fixtures
├── test_api/            # API endpoint tests
├── test_services/       # Service layer tests
└── test_models/         # Model tests
alembic/                 # Migrations

## Non-Negotiable Rules

### Security
- NEVER hardcode secrets - use environment variables
- ALWAYS hash passwords with bcrypt
- Validate ALL inputs with Pydantic
- Use JWT tokens (access: 15-30min)
- Never log passwords or tokens

### Database
- Use async SQLAlchemy 2.0+ syntax only
- Create Base model with: id (UUID), created_at, updated_at
- Use Alembic for ALL migrations
- Proper session management with `async with`
- Separate test database from development database

### Code Standards
- Use type hints everywhere
- Async functions for all DB operations
- Structured JSON logging (no print statements)
- Proper exception handling - never expose stack traces
- Add docstrings to all public functions

### API Design
- Version APIs: `/api/v1/...`
- RESTful endpoints with plural nouns
- Consistent error responses:
```json
  {
    "detail": "Clear message"
  }
```
- Proper HTTP status codes:
  - 201 for creation
  - 204 for deletion
  - 400 for bad request
  - 401 for unauthorized
  - 403 for forbidden
  - 404 for not found
  - 409 for conflict
  - 422 for validation errors

### Testing
- pytest with separate test database
- Test every endpoint (success + error cases)
- Target: 70%+ coverage
- **Tests written BEFORE implementation**
- Use fixtures for reusable test data

## TDD Workflow

**For Every Feature:**

Write test describing expected behavior
Run test → should FAIL (RED phase)
Write minimal code to pass test
Run test → should PASS (GREEN phase)
Refactor if needed (keep tests passing)
Repeat for next test


**Never:**
- Write implementation before tests
- Modify tests to match buggy implementation
- Skip running tests after changes

## Key Patterns

**Authentication Flow:**
1. POST `/api/v1/auth/register` → hash password → save user
2. POST `/api/v1/auth/login` → verify → return JWT
3. Protected routes use `Depends(get_current_user)`

**Endpoint Structure:**
```python
@router.post("/users/", response_model=UserResponse, status_code=201)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new user."""
    # Logic here
    return created_user
```

**Service Layer:**
```python
class UserService:
    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """
        Create a new user.
        
        Args:
            db: Database session
            user_data: User creation data
            
        Returns:
            Created user
            
        Raises:
            HTTPException: If email already exists
        """
        # Business logic
        pass
```

**Dependency Pattern:**
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""
    # Verify token, get user
    pass
```

## What to Avoid
- ❌ Sync database operations
- ❌ Plain text passwords
- ❌ Hardcoded configs
- ❌ Writing implementation before tests
- ❌ Modifying tests to match implementation
- ❌ Broad exception catching without handling
- ❌ Logging sensitive data (passwords, tokens)
- ❌ Exposing stack traces to API responses

## Code Quality Checklist

Before marking any feature complete, verify:
- [ ] All tests written first and passing
- [ ] Type hints on all functions
- [ ] Docstrings on public functions
- [ ] No hardcoded secrets
- [ ] Async/await used correctly
- [ ] Proper error handling
- [ ] No sensitive data in logs or responses
- [ ] Database sessions managed properly

## Success Criteria
- New dev can run it in < 10 minutes
- Adding CRUD endpoint takes < 15 minutes
- All security enforced by default
- Well-documented and extensible
- **70%+ test coverage achieved through TDD**

## Remember
This is a TEMPLATE. Keep everything generic and reusable.
**TESTS FIRST, CODE SECOND - ALWAYS.**

Updated DEVELOPER_GUIDE.md
markdown# FastAPI Template - Developer Guide

## ⚠️ Important: This Template Uses TDD

This template was built using **Test-Driven Development (TDD)**. When extending it:

1. **Write tests first** before writing any code
2. **Run tests** to see them fail (proves they work)
3. **Write code** to make tests pass
4. **Refactor** while keeping tests green

This ensures your code actually works and prevents bugs.

---

## Quick Start

### Setup (5 minutes)
```bash
# Clone and navigate
cd fastapi-template

# Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Environment variables
cp .env.example .env
# Edit .env with your database credentials

# Database setup
createdb fastapi_template_db
alembic upgrade head

# Run
uvicorn app.main:app --reload
```

Visit: http://localhost:8000/docs

---

## Environment Variables

Required in `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/test_dbname
SECRET_KEY=your-secret-key-here  # Use: openssl rand -hex 32
ENVIRONMENT=development
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
```

**Important:** 
- Never commit `.env` file
- `.env.example` is committed as a template
- Generate SECRET_KEY: `openssl rand -hex 32`

---

## Project Structure
app/
├── main.py                    # FastAPI app initialization
├── core/
│   ├── config.py              # Environment settings
│   ├── security.py            # JWT & password hashing
│   └── logging.py             # Logging config
├── api/v1/
│   ├── router.py              # Main router
│   └── endpoints/
│       ├── auth.py            # Register, login
│       ├── users.py           # User endpoints
│       └── admin.py           # Admin endpoints
├── models/
│   └── user.py                # SQLAlchemy models
├── schemas/
│   ├── user.py                # Pydantic schemas
│   └── token.py               # Token schemas
├── db/
│   ├── base.py                # Base model (id, timestamps)
│   └── session.py             # Database session
├── services/
│   └── user_service.py        # Business logic
├── middleware/
│   └── logging_middleware.py  # Request logging
└── utils/
└── dependencies.py        # get_current_user, get_db
tests/
├── conftest.py                # Pytest fixtures
├── test_api/                  # Endpoint tests
│   ├── test_auth.py
│   ├── test_users.py
│   └── test_rbac.py
├── test_services/             # Service tests
│   └── test_user_service.py
└── test_models/               # Model tests
└── test_user.py
alembic/                       # Database migrations
├── versions/                  # Migration files
└── env.py                     # Alembic config

---

## Core Concepts

### Models vs Schemas

**SQLAlchemy Model** (database):
```python
# app/models/user.py
class User(Base):
    __tablename__ = "users"
    email = Column(String, unique=True)
    hashed_password = Column(String)
```

**Pydantic Schema** (API):
```python
# app/schemas/user.py
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    # password never included!
```

**Why separate?**
- Models = database structure
- Schemas = API request/response format
- Keeps concerns separated
- Allows different validation rules

---

### Authentication Flow

1. **Register**: POST `/api/v1/auth/register`
```json
   {"email": "user@example.com", "password": "Secure123!", "full_name": "John Doe"}
```
   Returns: User data (no password)

2. **Login**: POST `/api/v1/auth/login`
```json
   {"username": "user@example.com", "password": "Secure123!"}
```
   Returns: `{"access_token": "...", "token_type": "bearer"}`

3. **Use token**: Add header to requests:
Authorization: Bearer <your_token>

4. **Access protected route**: GET `/api/v1/users/me`
Headers: Authorization: Bearer <token>
Returns: User profile data

---

## Extending the Template (TDD Approach)

### Adding a New Resource (e.g., Posts)

**Always follow TDD: Tests → Code → Refactor**

#### Step 1: Write Tests First

Create `tests/test_api/test_posts.py`:
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_post_success(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/posts/",
        json={"title": "Test Post", "content": "Test content"},
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Post"
    assert "id" in data
    assert "author_id" in data

@pytest.mark.asyncio
async def test_create_post_without_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/posts/",
        json={"title": "Test", "content": "Content"}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_list_posts(client: AsyncClient):
    response = await client.get("/api/v1/posts/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

**Run tests (should FAIL):**
```bash
pytest tests/test_api/test_posts.py -v
```

#### Step 2: Create Model

`app/models/post.py`:
```python
from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Post(Base):
    __tablename__ = "posts"
    
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
```

#### Step 3: Create Schemas

`app/schemas/post.py`:
```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)

class PostResponse(BaseModel):
    id: UUID
    title: str
    content: str
    author_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True
```

#### Step 4: Create Migration

```bash
alembic revision --autogenerate -m "Add posts table"
alembic upgrade head
```

#### Step 5: Create Service

`app/services/post_service.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.post import Post
from app.schemas.post import PostCreate

class PostService:
    @staticmethod
    async def create_post(
        db: AsyncSession, 
        post_data: PostCreate, 
        author_id: UUID
    ) -> Post:
        """Create a new post."""
        post = Post(**post_data.dict(), author_id=author_id)
        db.add(post)
        await db.commit()
        await db.refresh(post)
        return post
    
    @staticmethod
    async def get_posts(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 10
    ) -> list[Post]:
        """Get list of posts."""
        result = await db.execute(
            select(Post).offset(skip).limit(limit)
        )
        return result.scalars().all()
```

#### Step 6: Create Endpoints

`app/api/v1/endpoints/posts.py`:
```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.post import PostCreate, PostResponse
from app.services.post_service import PostService
from app.utils.dependencies import get_db, get_current_user
from app.models.user import User

router = APIRouter(prefix="/posts", tags=["posts"])

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new post."""
    return await PostService.create_post(db, post_data, current_user.id)

@router.get("/", response_model=list[PostResponse])
async def list_posts(
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """List all posts."""
    return await PostService.get_posts(db, skip, limit)
```

#### Step 7: Register Router

In `app/api/v1/router.py`:
```python
from app.api.v1.endpoints import auth, users, admin, posts

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(admin.router)
api_router.include_router(posts.router)  # Add this
```

#### Step 8: Run Tests (should PASS now)

```bash
pytest tests/test_api/test_posts.py -v
```

---

### Adding Role-Based Access Control

**Step 1: Write Tests** (`tests/test_api/test_rbac.py`)

**Step 2: Add role to User model**:
```python
from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

class User(Base):
    # ... existing fields
    role = Column(String, default=UserRole.USER.value)
```

**Step 3: Create migration**:
```bash
alembic revision --autogenerate -m "Add role to users"
alembic upgrade head
```

**Step 4: Create dependency** (`app/utils/dependencies.py`):
```python
from fastapi import HTTPException, status

def require_role(required_role: UserRole):
    async def role_checker(
        current_user: User = Depends(get_current_user)
    ):
        if current_user.role != required_role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker
```

**Step 5: Protect endpoints**:
```python
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    admin: User = Depends(require_role(UserRole.ADMIN))
):
    # Only admins can access
    pass
```

---

## Testing

### Run Tests
```bash
pytest                          # Run all tests
pytest -v                       # Verbose
pytest --cov=app               # With coverage
pytest tests/test_api/         # Specific directory
pytest -k "test_register"      # Run tests matching name
```

### Writing Tests (TDD Style)

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_feature_success(client: AsyncClient):
    """Test successful case."""
    response = await client.post("/api/v1/endpoint", json={...})
    assert response.status_code == 201
    # More assertions

@pytest.mark.asyncio
async def test_feature_error(client: AsyncClient):
    """Test error case."""
    response = await client.post("/api/v1/endpoint", json={...})
    assert response.status_code == 422
    # Verify error message
```

### Common Fixtures

Available in `tests/conftest.py`:
- `client` - AsyncClient for API testing
- `db_session` - Test database session
- `test_user` - Regular user
- `admin_user` - Admin user
- `auth_headers` - Headers with valid auth token

---

## Common Tasks

### Database Migration
```bash
# Create migration after model changes
alembic revision --autogenerate -m "description"

# Review generated migration in alembic/versions/

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View history
alembic history

# Check current version
alembic current
```

### Add Pagination
```python
from fastapi import Query

@router.get("/posts/")
async def list_posts(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    skip = (page - 1) * size
    posts = await PostService.get_posts(db, skip=skip, limit=size)
    return posts
```

### Background Tasks
```python
from fastapi import BackgroundTasks

def send_email(email: str, message: str):
    # Email sending logic
    pass

@router.post("/notify")
async def notify(
    email: str,
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(send_email, email, "Welcome!")
    return {"message": "Notification queued"}
```

---

## Troubleshooting

### Database connection error
```bash
# Check .env DATABASE_URL
# Ensure PostgreSQL is running
ps aux | grep postgres  # Linux/Mac
# Test connection
psql -U username -d dbname
```

### Migration issues
```bash
# Check current state
alembic current

# Reset (DEVELOPMENT ONLY - loses data!)
alembic downgrade base
alembic upgrade head

# If stuck, delete versions and recreate
rm alembic/versions/*.py
alembic revision --autogenerate -m "Initial"
alembic upgrade head
```

### 401 Unauthorized
- Check Authorization header format: `Bearer <token>`
- Verify token hasn't expired (30 min default)
- Ensure user exists and is_active=true
- Check SECRET_KEY matches in .env

### Tests failing
```bash
# Run with verbose output
pytest -v

# Run specific test
pytest tests/test_api/test_auth.py::test_register_new_user_success -v

# See print statements
pytest -s

# Stop on first failure
pytest -x
```

### Import errors
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Best Practices

### ✅ DO:
- Write tests before code (TDD)
- Use async/await for all DB operations
- Validate inputs with Pydantic
- Use type hints everywhere
- Add docstrings to functions
- Log errors, not sensitive data
- Use environment variables for config
- Keep services focused (single responsibility)

### ❌ DON'T:
- Hardcode secrets
- Store plain text passwords
- Use sync database operations
- Skip input validation
- Expose stack traces in production
- Modify tests to match buggy code
- Write code before tests

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app entry point |
| `app/core/config.py` | Environment configuration |
| `app/core/security.py` | JWT and password hashing |
| `app/utils/dependencies.py` | Reusable dependencies |
| `tests/conftest.py` | Pytest fixtures |
| `.env` | Environment variables (never commit) |
| `.env.example` | Environment template (commit this) |

---

## Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Pydantic](https://docs.pydantic.dev/)
- [Alembic](https://alembic.sqlalchemy.org/)
- [pytest](https://docs.pytest.org/)

---

## Getting Help

1. Check this guide first
2. Review `agents.md` for development guidelines
3. Check the design document
4. Look at existing tests for examples
5. Check FastAPI documentation

---

**Remember: Tests First, Code Second!** 🧪 → 💻