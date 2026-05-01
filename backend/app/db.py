from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.settings import settings


class Base(DeclarativeBase):
    pass


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[str] = mapped_column(String(120), index=True)
    component_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(5), index=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))


class RCARecord(Base):
    __tablename__ = "rca_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_item_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    incident_start: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    incident_end: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    root_cause_category: Mapped[str] = mapped_column(String(120))
    fix_applied: Mapped[str] = mapped_column(Text())
    prevention_steps: Mapped[str] = mapped_column(Text())
    mttr_minutes: Mapped[float] = mapped_column(Float())
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))


class IncidentAggregation(Base):
    __tablename__ = "incident_aggregations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_start: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    component_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(5), index=True)
    count: Mapped[int] = mapped_column(Integer)


engine = create_async_engine(settings.postgres_url, echo=False, future=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
