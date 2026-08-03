from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Base(DeclarativeBase):
    pass