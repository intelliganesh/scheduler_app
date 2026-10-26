from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    full_name: str | None
    user_principal_name: str | None = None
    given_name: str | None = None
    surname: str | None = None
    department: str | None = None
    title: str | None = None
    company: str | None = None
    permissions: list[str] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("permissions", mode="before")
    @classmethod
    def split_permissions(cls, value):
        if isinstance(value, str):
            return [item for item in value.split(",") if item]
        return value or []


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
