import datetime
import json
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class _JSON(TypeDecorator[Any]):
    """Stores arbitrary data as a JSON string in SQLite TEXT column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return json.loads(value)


class Base(DeclarativeBase):
    pass


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    monthly_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tags: Mapped[Any] = mapped_column(_JSON, nullable=True)
    last_active_date: Mapped[datetime.date | None] = mapped_column(DateTime, nullable=True)
    raw_export: Mapped[Any] = mapped_column(_JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    findings: Mapped[list["Finding"]] = relationship(
        "Finding", back_populates="resource", cascade="all, delete-orphan"
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    estimated_monthly_saving_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[Any] = mapped_column(_JSON, nullable=True)
    decommission_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    resource: Mapped["Resource"] = relationship("Resource", back_populates="findings")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
