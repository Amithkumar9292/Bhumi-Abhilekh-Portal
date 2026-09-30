"""Common Pydantic schemas used across the API."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str = "1.0.0"
    disclaimer: str = (
        "⚠️ DEMO SYSTEM — All data is synthetic. "
        "This system is NOT legally binding."
    )
