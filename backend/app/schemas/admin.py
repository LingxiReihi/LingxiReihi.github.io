"""后台管理 DTO。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TagRef(BaseModel):
    id: int | None = None
    name: str | None = None


class ContentUpsert(BaseModel):
    type: Literal["article", "model", "chat"]
    status: Literal["draft", "published", "archived"] = "draft"
    title: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=200)
    summary: str = ""
    body_md: str = ""
    cover_asset_id: int | None = None
    media_kind: Literal["3d", "render", "animation"] | None = None
    tags: list[TagRef] = []
    extra: dict = {}
    asset_ids: list[int] = []
    column_id: int | None = None


class ContentPatch(BaseModel):
    """PUT 全量更新复用同结构（type 不可变）。"""
    status: Literal["draft", "published", "archived"] | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=200)
    summary: str | None = None
    body_md: str | None = None
    cover_asset_id: int | None = None
    media_kind: Literal["3d", "render", "animation"] | None = None
    tags: list[TagRef] | None = None
    extra: dict | None = None
    asset_ids: list[int] | None = None
    column_id: int | None = None


class StatusReq(BaseModel):
    status: Literal["draft", "published", "archived"]


class TagReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: Literal["article", "model", "chat"] = "article"


class ColumnReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    slug: str | None = Field(None, max_length=128)
    summary: str = ""
    sort_order: int = 0
    type: Literal["article", "model", "chat"] = "article"
    parent_id: int | None = None


SETTINGS_GROUPS = ("site", "nav", "footer", "mail")   # profile 组已废：资料跟人走；home 组已废：首页改版成 最新/热门/团队 三段，四类型开关与精选内容再无消费者


class ProfileReq(BaseModel):
    """自己改自己的资料（简介/技能/经历同样自理；改别人的仅 super，走账号端点）。"""
    nickname: str | None = Field(None, min_length=1, max_length=64)
    avatar: str | None = Field(None, max_length=255)
    signature: str | None = Field(None, max_length=200)
    social_links: list[dict] | None = None
    bio_md: str | None = None
    skills: list[dict] | None = None
    experience: list[dict] | None = None


class GrantReq(BaseModel):
    """一条授权：column_id 为空即全局作用域。"""
    permission: str
    column_id: int | None = None


class AdminCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=120,
                       pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    nickname: str = Field("", max_length=64)
    note: str = Field("", max_length=128)
    role: str = "staff"
    grants: list[GrantReq] = []

    @field_validator("email", "username", mode="before")
    @classmethod
    def _strip(cls, v):
        # 粘贴带首尾空格不该被拒；中间含空格仍由 pattern 判格式错
        return v.strip() if isinstance(v, str) else v


class AdminUpdate(BaseModel):
    nickname: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=128)
    email: str | None = Field(None, min_length=3, max_length=120,
                              pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    is_active: bool | None = None
    role: str | None = None
    password: str | None = Field(None, min_length=1, max_length=128)
    # 资料字段：仅 super 可代改他人（服务层拒非 super）
    avatar: str | None = Field(None, max_length=255)
    signature: str | None = Field(None, max_length=200)
    social_links: list[dict] | None = None
    bio_md: str | None = None
    skills: list[dict] | None = None
    experience: list[dict] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _strip_email(cls, v):
        return v.strip() if isinstance(v, str) else v


class GrantsReq(BaseModel):
    grants: list[GrantReq] = []


class AnnouncementReq(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body_md: str = ""
    status: Literal["draft", "published"] = "published"
    published_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v):
        if v is not None and not v.strip():
            raise ValueError("标题不能为空")
        return v.strip() if isinstance(v, str) else v


class AnnouncementPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    body_md: str | None = None
    status: Literal["draft", "published"] | None = None
    published_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v):
        if v is not None and not v.strip():
            raise ValueError("标题不能为空")
        return v.strip() if isinstance(v, str) else v


class AnnouncementReadReq(BaseModel):
    ids: list[int] = []
