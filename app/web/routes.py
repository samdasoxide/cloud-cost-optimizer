import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.commands.generator import generate_command
from app.database import get_session
from app.models.db import Finding, IngestionRun, Resource
from app.parsers import aws as aws_parser
from app.parsers import azure as azure_parser
from app.rules.engine import evaluate_all
from app.rules.idle_compute import IdleComputeRule
from app.rules.old_snapshot import OldSnapshotRule
from app.rules.unattached_volume import UnattachedVolumeRule
from app.rules.unused_public_ip import UnusedPublicIPRule

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

router = APIRouter(default_response_class=HTMLResponse)

_RULES = [
    UnattachedVolumeRule(),
    IdleComputeRule(),
    UnusedPublicIPRule(),
    OldSnapshotRule(),
]

_SUFFIX_MAP = {"aws": ".csv", "azure": ".json"}


async def _get_summary(session: AsyncSession) -> dict[str, Any]:
    total_resources: int = (
        await session.execute(select(func.count(Resource.id)))
    ).scalar_one()

    findings_agg = (
        await session.execute(
            select(func.count(Finding.id), func.sum(Finding.estimated_monthly_saving_usd))
        )
    ).one()
    total_findings: int = findings_agg[0]
    total_waste: float = float(findings_agg[1] or 0.0)

    severity_rows = (
        await session.execute(
            select(Finding.severity, func.count(Finding.id)).group_by(Finding.severity)
        )
    ).all()
    findings_by_severity: dict[str, int] = {row[0]: row[1] for row in severity_rows}

    provider_waste_rows = (
        await session.execute(
            select(
                Resource.provider,
                func.sum(Finding.estimated_monthly_saving_usd).label("waste"),
            )
            .join(Finding, Finding.resource_id == Resource.id)
            .group_by(Resource.provider)
        )
    ).all()
    waste_by_provider: dict[str, float] = {
        row[0]: float(row[1] or 0.0) for row in provider_waste_rows
    }

    provider_count_rows = (
        await session.execute(
            select(Resource.provider, func.count(Finding.id))
            .join(Finding, Finding.resource_id == Resource.id)
            .group_by(Resource.provider)
        )
    ).all()
    findings_by_provider: dict[str, int] = {row[0]: row[1] for row in provider_count_rows}

    return {
        "total_resources": total_resources,
        "total_findings": total_findings,
        "total_waste": total_waste,
        "findings_by_severity": findings_by_severity,
        "waste_by_provider": waste_by_provider,
        "findings_by_provider": findings_by_provider,
    }


async def _query_findings(
    session: AsyncSession,
    provider: str | None,
    severity: str | None,
    rule_name: str | None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Finding], int]:
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

    stmt = (
        base.options(selectinload(Finding.resource))
        .order_by(Finding.estimated_monthly_saving_usd.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), total


async def _get_rule_names(session: AsyncSession) -> list[str]:
    rows = (
        await session.execute(
            select(distinct(Finding.rule_name)).order_by(Finding.rule_name)
        )
    ).scalars().all()
    return list(rows)


@router.get("/")
async def dashboard(
    request: Request,
    provider: str | None = None,
    severity: str | None = None,
    rule_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    summary = await _get_summary(session)
    findings, total = await _query_findings(session, provider, severity, rule_name)
    rule_names = await _get_rule_names(session)

    chart_labels = json.dumps(list(summary["waste_by_provider"].keys()))
    chart_data = json.dumps([round(v, 2) for v in summary["waste_by_provider"].values()])

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            **summary,
            "findings": findings,
            "total": total,
            "rule_names": rule_names,
            "filters": {
                "provider": provider or "",
                "severity": severity or "",
                "rule_name": rule_name or "",
            },
            "chart_labels": chart_labels,
            "chart_data": chart_data,
        },
    )


@router.get("/findings-table")
async def findings_table_fragment(
    request: Request,
    provider: str | None = None,
    severity: str | None = None,
    rule_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    findings, total = await _query_findings(session, provider, severity, rule_name)
    return templates.TemplateResponse(
        request,
        "_findings_table.html",
        {"findings": findings, "total": total},
    )


@router.get("/findings/{finding_id}")
async def finding_detail(
    request: Request,
    finding_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    stmt = (
        select(Finding)
        .options(selectinload(Finding.resource))
        .where(Finding.id == finding_id)
    )
    finding = (await session.execute(stmt)).scalar_one_or_none()
    if finding is None:
        return templates.TemplateResponse(
            request,
            "detail.html",
            {"finding": None, "error": f"Finding {finding_id} not found"},
            status_code=404,
        )

    evidence_json = json.dumps(finding.evidence, indent=2) if finding.evidence else "{}"
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"finding": finding, "evidence_json": evidence_json},
    )


@router.get("/upload")
async def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html")


@router.post("/upload")
async def upload_file(
    request: Request,
    provider: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if provider not in ("aws", "azure"):
        return templates.TemplateResponse(
            request,
            "upload.html",
            {"error": "Provider must be 'aws' or 'azure'."},
            status_code=422,
        )

    content = await file.read()
    suffix = _SUFFIX_MAP[provider]

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            tmp_path = Path(tmp.name)
            resources = aws_parser.parse(tmp_path) if provider == "aws" else azure_parser.parse(tmp_path)
    except Exception as exc:
        logger.warning("Upload parse error: %s", exc)
        return templates.TemplateResponse(
            request,
            "upload.html",
            {"error": f"Failed to parse file: {exc}"},
            status_code=422,
        )

    for resource in resources:
        session.add(resource)
    await session.flush()

    findings = evaluate_all(resources, _RULES)
    for finding in findings:
        finding.decommission_command = generate_command(finding, finding.resource)
        session.add(finding)

    run = IngestionRun(
        source_file=file.filename or "unknown",
        provider=provider,
        row_count=len(resources),
        finding_count=len(findings),
    )
    session.add(run)
    await session.commit()

    logger.info(
        "Web upload: %d resources, %d findings from %s (%s)",
        len(resources),
        len(findings),
        file.filename,
        provider,
    )
    return RedirectResponse("/", status_code=303)
