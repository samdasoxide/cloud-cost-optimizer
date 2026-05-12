import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResourceBase(BaseModel):
    provider: Literal["aws", "azure"]
    resource_type: str
    region: str
    resource_id: str
    monthly_cost_usd: float = 0.0
    tags: dict[str, str] | None = None
    last_active_date: datetime.date | None = None


class ResourceRead(ResourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime.datetime


class FindingBase(BaseModel):
    rule_name: str
    severity: Literal["low", "medium", "high", "critical"]
    estimated_monthly_saving_usd: float = 0.0
    evidence: dict[str, Any] | None = None
    decommission_command: str | None = None


class FindingRead(FindingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    detected_at: datetime.datetime
    resource: ResourceRead


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_file: str
    provider: Literal["aws", "azure"]
    row_count: int
    finding_count: int
    created_at: datetime.datetime


class IngestResponse(BaseModel):
    run_id: int
    provider: Literal["aws", "azure"]
    row_count: int
    finding_count: int
    message: str


class SummaryResponse(BaseModel):
    total_resources: int
    total_findings: int
    total_estimated_monthly_saving_usd: float
    findings_by_severity: dict[str, int]
    findings_by_rule: dict[str, int]
    top_regions_by_waste: list[dict[str, Any]]


class FindingListResponse(BaseModel):
    items: list[FindingRead]
    total: int
    page: int
    page_size: int


class ResourceListResponse(BaseModel):
    items: list[ResourceRead]
    total: int
    page: int
    page_size: int


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
