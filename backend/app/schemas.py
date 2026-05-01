from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class WorkItemStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SignalIn(BaseModel):
    component_id: str = Field(min_length=3, max_length=120)
    component_type: str = Field(min_length=2, max_length=80)
    message: str = Field(min_length=3, max_length=5000)
    latency_ms: Optional[int] = None
    metadata: dict = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class RCAIn(BaseModel):
    incident_start: datetime
    incident_end: datetime
    root_cause_category: str = Field(min_length=2, max_length=120)
    fix_applied: str = Field(min_length=5, max_length=5000)
    prevention_steps: str = Field(min_length=5, max_length=5000)


class StatusUpdateIn(BaseModel):
    new_status: WorkItemStatus
