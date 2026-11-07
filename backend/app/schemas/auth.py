from pydantic import BaseModel, Field


class LoginReq(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


class RefreshReq(BaseModel):
    refresh_token: str


class PasswordReq(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ForgotReq(BaseModel):
    """忘记密码：只交账号名，新口令走邮件，响应里永远没有口令。"""
    username: str = Field(min_length=1, max_length=64)
