import datetime
import json
import logging
from pathlib import Path

from app.models.db import Resource

logger = logging.getLogger(__name__)

_SERVICE_METER_TO_TYPE: dict[tuple[str, str], str] = {
    ("Microsoft.Compute", "Virtual Machines"): "virtual_machine",
    ("Microsoft.Compute", "Storage"): "managed_disk",
    ("Microsoft.Network", "Virtual Network"): "public_ip",
    ("Microsoft.Sql", "SQL Database"): "sql_database",
}


def _resource_type(record: dict) -> str:
    key = (
        str(record.get("ConsumedService", "")),
        str(record.get("MeterCategory", "")),
    )
    return _SERVICE_METER_TO_TYPE.get(key, "unknown")


def _parse_tags(raw: object) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items() if v is not None and str(v).strip()}
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def parse(file_path: Path) -> list[Resource]:
    try:
        with open(file_path, encoding="utf-8") as fh:
            records = json.load(fh)
    except Exception:
        logger.exception("Failed to read Azure billing file %s", file_path)
        return []

    if not isinstance(records, list):
        logger.error("Azure billing file %s must contain a JSON array", file_path)
        return []

    grouped: dict[str, list[dict]] = {}
    for record in records:
        resource_id = record.get("ResourceId") or record.get("InstanceId")
        if not resource_id or not str(resource_id).strip():
            logger.warning(
                "Skipped Azure record with missing ResourceId (ResourceName=%s)",
                record.get("ResourceName"),
            )
            continue
        grouped.setdefault(str(resource_id), []).append(record)

    resources: list[Resource] = []

    for resource_id, group_records in grouped.items():
        try:
            monthly_cost = sum(
                float(r.get("Cost") or 0) for r in group_records
            )
            ref = group_records[0]
            resource_type = _resource_type(ref)
            region = str(ref.get("ResourceLocation") or "unknown").strip() or "unknown"
            tags = _parse_tags(ref.get("Tags"))

            last_active: datetime.date | None = None
            raw_date = ref.get("Date")
            if raw_date:
                try:
                    last_active = datetime.date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    pass

            resources.append(
                Resource(
                    provider="azure",
                    resource_type=resource_type,
                    region=region,
                    resource_id=resource_id,
                    monthly_cost_usd=round(monthly_cost, 4),
                    tags=tags,
                    last_active_date=last_active,
                    raw_export=group_records,
                )
            )
        except Exception:
            logger.warning(
                "Skipped Azure resource_id '%s' in %s due to unexpected error",
                resource_id,
                file_path,
                exc_info=True,
            )

    return resources
