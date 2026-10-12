from typing import Generic, TypeVar
from pydantic import BaseModel

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class BulkError(BaseModel):
    type: str          # "not_found" | "conflict" | "business_rule" | "error"
    message: str


class BulkFailure(BaseModel, Generic[TIn]):
    index: int
    input: TIn
    error: BulkError


class BulkSummary(BaseModel):
    total: int
    succeeded: int
    failed: int
    atomic: bool
    committed: bool


class BulkResult(BaseModel, Generic[TOut, TIn]):
    summary: BulkSummary
    succeeded: list[TOut]
    failed: list[BulkFailure[TIn]]