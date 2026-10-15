from __future__ import annotations

import re
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class Message(BaseModel):
    message: str


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(v: str) -> str:
    return _CONTROL.sub("", v).strip()


def _clean_skills(v: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in v:
        s = _clean_text(str(raw))[:60]
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:60]


CleanStr = Annotated[str, AfterValidator(_clean_text)]
SkillList = Annotated[list[str], AfterValidator(_clean_skills)]
ShortList = Annotated[list[Annotated[str, Field(max_length=100)]], Field(max_length=30), AfterValidator(_clean_skills)]
