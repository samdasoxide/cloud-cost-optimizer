import datetime
import logging

from app.models.db import Finding, Resource
from app.rules.engine import Rule

logger = logging.getLogger(__name__)

_SNAPSHOT_TYPES = frozenset({"ebs_snapshot", "managed_snapshot", "snapshot"})
_TAG_DATE_KEYS = frozenset({"createddate", "created_date", "created-date", "created date"})
_RAW_DATE_KEYS = ("creation_date", "snapshot_date")
_MAX_AGE_DAYS = 90


def _extract_creation_date(resource: Resource) -> datetime.date | None:
    for key, value in (resource.tags or {}).items():
        if key.lower() in _TAG_DATE_KEYS:
            try:
                return datetime.date.fromisoformat(str(value)[:10])
            except ValueError:
                pass

    for row in resource.raw_export or []:
        for key in _RAW_DATE_KEYS:
            raw = row.get(key)
            if raw:
                try:
                    return datetime.date.fromisoformat(str(raw)[:10])
                except ValueError:
                    pass

    return None


class OldSnapshotRule(Rule):
    name = "OldSnapshotRule"
    severity = "low"

    def evaluate(self, resource: Resource) -> Finding | None:
        if resource.resource_type not in _SNAPSHOT_TYPES:
            return None

        creation_date = _extract_creation_date(resource)
        if creation_date is None:
            return None

        age_days = (datetime.date.today() - creation_date).days
        if age_days > _MAX_AGE_DAYS:
            return Finding(
                resource=resource,
                rule_name=self.name,
                severity=self.severity,
                estimated_monthly_saving_usd=resource.monthly_cost_usd,
                evidence={
                    "creation_date": creation_date.isoformat(),
                    "age_days": age_days,
                    "threshold_days": _MAX_AGE_DAYS,
                    "resource_id": resource.resource_id,
                },
            )

        return None
