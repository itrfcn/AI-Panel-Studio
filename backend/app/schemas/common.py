"""公共契约：分页等。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """分页查询参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")


class Page(BaseModel, Generic[T]):
    """分页响应封装。"""

    items: list[T]
    total: int
    page: int
    page_size: int
