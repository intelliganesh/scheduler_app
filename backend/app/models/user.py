from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Unicode, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    __tablename__ = "users"
    # SQL Server treats NULLs as equal in unique constraints, so email uniqueness
    # applies only to non-NULL values (AD accounts may have no mail attribute).
    __table_args__ = (
        Index("ix_users_email", "email", unique=True, mssql_where=text("email IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Unicode(128), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    user_principal_name: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    given_name: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    surname: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    department: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    title: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    company: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    # Comma-separated application permissions derived from configured AD group mappings.
    permissions: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
