import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.commands.generator import generate_command
from app.database import get_session
from app.models.db import Finding, IngestionRun, Resource
from app.models.schemas import (
    FindingListResponse,
    FindingRead,
    IngestResponse,
    SummaryResponse,
)
from app.parsers import aws as aws_parser
from app.parsers import azure as azure_parser
from app.rules.engine import evaluate_all
from app.rules.idle_compute import IdleComputeRule
from app.rules.old_snapshot import OldSnapshotRule
from app.rules.unattached_volume import UnattachedVolumeRule
from app.rules.unused_public_ip import UnusedPublicIPRule

logger = logging.getLogger(__name__)

router = APIRouter()

_RULES = [
    UnattachedVolumeRule(),
    IdleComputeRule(),
    UnusedPublicIPRule(),
    OldSnapshotRule(),
]

_SUFFIX_MAP = {"aws": ".csv", "azure": ".json"}


@router.post(
    "/ingest",
    response_model=IngestResponse,
    tags=["ingestion"],
    summary="Ingest a billing export and run the rules engine",
)
async def ingest(
    provider: str = Form(..., description="Cloud provider: 'aws' or 'azure'"),
    file: UploadFile = File(..., description="Billing export file (CSV for AWS, JSON for Azure)"),
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    if provider not in ("aws", "azure"):
        raise HTTPException(status_code=422, detail="provider must be 'aws' or 'azure'")

    content = await file.read()
    suffix = _SUFFIX_MAP[provider]

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        tmp_path = Path(tmp.name)

        if provider == "aws":
            resources = aws_parser.parse(tmp_path)
        else:
            resources = azure_parser.parse(tmp_path)

    if not resources:
        run = IngestionRun(
            source_file=file.filename or "unknown",
            provider=provider,
            row_count=0,
            finding_count=0,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return IngestResponse(
            run_id=run.id,
            provider=provider,
            row_count=0,
            finding_count=0,
            message="No resources parsed from the uploaded file.",
        )

    for resource in resources:
        session.add(resource)
    await session.flush()

    findings = evaluate_all(resources, _RULES)

    for finding in findings:
        resource_ref = finding.resource
        finding.decommission_command = generate_command(finding, resource_ref)
        session.add(finding)

    run = IngestionRun(
        source_file=file.filename or "unknown",
        provider=provider,
        row_count=len(resources),
        finding_count=len(findings),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    logger.info(
        "Ingested %d resources, %d findings from %s (%s)",
        len(resources),
        len(findings),
        file.filename,
        provider,
    )
    return IngestResponse(
        run_id=run.id,
        provider=provider,
        row_count=len(resources),
        finding_count=len(findings),
        message=f"Ingested {len(resources)} resources, generated {len(findings)} findings.",
    )


@router.get(
    "/findings",
    response_model=FindingListResponse,
    tags=["findings"],
    summary="List findings with optional filters and pagination",
)
async def list_findings(
    provider: str | None = None,
    severity: str | None = None,
    rule_name: str | None = None,
    offset: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> FindingListResponse:
    base = select(Finding)
    if provider:
        base = base.join(Finding.resource).where(Resource.provider == provider)
    if severity:
        base = base.where(Finding.severity == severity)
    if rule_name:
        base = base.where(Finding.rule_name == rule_name)

    total: int = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    result_stmt = (
        base.options(selectinload(Finding.resource))
        .order_by(Finding.id)
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(result_stmt)).scalars().all()

    page_size = limit if limit > 0 else 20
    page = (offset // page_size) + 1

    return FindingListResponse(
        items=list(rows),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/findings/{finding_id}",
    response_model=FindingRead,
    tags=["findings"],
    summary="Get a single finding with full resource detail and decommission command",
)
async def get_finding(
    finding_id: int,
    session: AsyncSession = Depends(get_session),
) -> FindingRead:
    stmt = (
        select(Finding)
        .options(selectinload(Finding.resource))
        .where(Finding.id == finding_id)
    )
    finding = (await session.execute(stmt)).scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")
    return finding


@router.get(
    "/summary",
    response_model=SummaryResponse,
    tags=["summary"],
    summary="Aggregate statistics: total waste, counts by severity and rule",
)
async def summary(session: AsyncSession = Depends(get_session)) -> SummaryResponse:
    total_resources: int = (
        await session.execute(select(func.count(Resource.id)))
    ).scalar_one()

    findings_agg = (
        await session.execute(
            select(func.count(Finding.id), func.sum(Finding.estimated_monthly_saving_usd))
        )
    ).one()
    total_findings: int = findings_agg[0]
    total_saving: float = float(findings_agg[1] or 0.0)

    severity_rows = (
        await session.execute(
            select(Finding.severity, func.count(Finding.id)).group_by(Finding.severity)
        )
    ).all()
    findings_by_severity: dict[str, int] = {row[0]: row[1] for row in severity_rows}

    rule_rows = (
        await session.execute(
            select(Finding.rule_name, func.count(Finding.id)).group_by(Finding.rule_name)
        )
    ).all()
    findings_by_rule: dict[str, int] = {row[0]: row[1] for row in rule_rows}

    region_rows = (
        await session.execute(
            select(
                Resource.region,
                func.sum(Finding.estimated_monthly_saving_usd).label("waste"),
            )
            .join(Finding, Finding.resource_id == Resource.id)
            .group_by(Resource.region)
            .order_by(func.sum(Finding.estimated_monthly_saving_usd).desc())
            .limit(10)
        )
    ).all()
    top_regions = [
        {"region": row[0], "estimated_monthly_saving_usd": float(row[1] or 0.0)}
        for row in region_rows
    ]

    return SummaryResponse(
        total_resources=total_resources,
        total_findings=total_findings,
        total_estimated_monthly_saving_usd=total_saving,
        findings_by_severity=findings_by_severity,
        findings_by_rule=findings_by_rule,
        top_regions_by_waste=top_regions,
    )
