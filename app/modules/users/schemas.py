from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

UserRole = Literal["user", "admin"]
UserStatus = Literal["active", "disabled", "deleted"]


class UserCreateRequest(BaseModel):
    username: str
    dance_style: str
    level: str
    favorite_style: str
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=64)


class UserLoginRequest(BaseModel):
    username: str
    password: str


class UserUpdateRequest(BaseModel):
    dance_style: str | None = None
    level: str | None = None
    favorite_style: str | None = None
    email: EmailStr | None = None


class UserStatusUpdateRequest(BaseModel):
    status: Literal["active", "disabled"]


class UserRoleUpdateRequest(BaseModel):
    role: Literal["user", "admin"]


class UserListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = None
    status: Literal["active", "disabled"] | None = None


class UserData(BaseModel):
    id: int
    username: str
    email: str | None
    role: UserRole
    status: UserStatus
    dance_style: str
    level: str
    favorite_style: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserCreateData(BaseModel):
    user_id: int
    profile_status: str = "basic_created"


class UserLookupData(UserData):
    pass


class UserRegisterData(BaseModel):
    user_id: int
    access_token: str
    token_type: str = "bearer"


class UserLoginData(BaseModel):
    user_id: int
    access_token: str
    token_type: str = "bearer"


class UserListData(BaseModel):
    items: list[UserData]
    total: int
    page: int
    page_size: int


class SuccessData(BaseModel):
    success: bool = True

