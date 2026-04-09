"""Admin-only endpoints for user management."""

from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.schemas.error import ErrorResponse
from app.schemas.user import PaginatedUsers, UserResponse, UserRoleUpdate
from app.services.user_service import UserService
from app.utils.dependencies import get_db, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/users",
    response_model=PaginatedUsers,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def list_all_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN.value)),
) -> PaginatedUsers:
    """List all users with pagination. Admin only."""
    _ = admin
    skip = (page - 1) * size
    users, total = await UserService.get_all_users(db, skip=skip, limit=size)
    pages = math.ceil(total / size) if total > 0 else 0
    return PaginatedUsers(
        items=[UserResponse.model_validate(user) for user in users],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def delete_user(
    user_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN.value)),
) -> Response:
    """Delete a user by id. Admin only."""
    _ = admin
    deleted = await UserService.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def update_user_role(
    role_update: UserRoleUpdate,
    user_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN.value)),
) -> UserResponse:
    """Update a user's role. Admin only."""
    _ = admin
    user = await UserService.update_user_role(db, user_id, role_update.role)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)
