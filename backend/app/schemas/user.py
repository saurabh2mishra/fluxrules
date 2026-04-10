from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

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
    username: Optional[str] = None
