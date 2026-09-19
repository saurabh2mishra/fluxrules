from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str = "business"
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str = "business"


class TokenData(BaseModel):
    username: str | None = None
