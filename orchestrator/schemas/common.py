from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.generics import GenericModel


T = TypeVar("T")


class ApiError(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detail: str


class PaginationMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    has_next: bool


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    meta: PaginationMeta


class TimestampedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime