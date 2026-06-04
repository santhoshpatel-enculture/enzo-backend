"""User Pydantic schemas for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserLogin(BaseModel):
    """Login request body."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    """Change password request body."""
    currentPassword: str = Field(..., min_length=8, max_length=128)
    newPassword: str = Field(..., min_length=8, max_length=128)


class UserProfile(BaseModel):
    """Public user profile returned by the API."""
    id: str
    email: str
    firstName: str
    lastName: str
    department: str
    designation: str
    manager: str
    location: str
    isAdmin: bool = False
    role: str = "Employee"
    userId: str | None = None
    managerId: str | None = None
    managerEmail: str | None = None
    mustChangePassword: bool = False
    adminRole: str | None = None
    adminTenantIds: list[str] = []
    tenantId: str | None = None
    createdAt: datetime | None = None


class AuthResponse(BaseModel):
    """Successful login response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    user: UserProfile
