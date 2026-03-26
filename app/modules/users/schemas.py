from pydantic import BaseModel, ConfigDict


class UserCreateRequest(BaseModel):
    username: str
    dance_style: str
    level: str
    favorite_style: str


class UserData(BaseModel):
    id: int
    username: str
    dance_style: str
    level: str
    favorite_style: str

    model_config = ConfigDict(from_attributes=True)


class UserCreateData(BaseModel):
    user_id: int
    profile_status: str = "basic_created"


class UserLookupData(UserData):
    pass

