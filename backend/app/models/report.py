from datetime import datetime

from sqlalchemy import DateTime, Integer, Unicode, UnicodeText, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    description: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
