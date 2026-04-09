# Agent Instructions for FastAPI Template

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

## Project Structureapp/
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
```json{
"detail": "Clear message"
}
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
```python@router.post("/users/", response_model=UserResponse, status_code=201)
async def create_user(
user_data: UserCreate,
db: AsyncSession = Depends(get_db)
):
"""Create a new user."""
# Logic here
return created_user

**Service Layer:**
```pythonclass UserService:
@staticmethod
async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
"""
Create a new user.    Args:
        db: Database session
        user_data: User creation data    Returns:
        Created user    Raises:
        HTTPException: If email already exists
    """
    # Business logic
    pass

**Dependency Pattern:**
```pythonasync def get_current_user(
token: str = Depends(oauth2_scheme),
db: AsyncSession = Depends(get_db)
) -> User:
"""Get current authenticated user from JWT token."""
# Verify token, get user
pass

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