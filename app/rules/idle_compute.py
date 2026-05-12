import logging

from app.models.db import Finding, Resource
from app.rules.engine import Rule

logger = logging.getLogger(__name__)

_COMPUTE_TYPES = frozenset({"ec2_instance", "virtual_machine"})
_CPU_THRESHOLD_PCT = 5.0
_MIN_METRICS_DAYS = 14


class IdleComputeRule(Rule):
    name = "IdleComputeRule"
    severity = "high"

    def evaluate(self, resource: Resource) -> Finding | None:
        if resource.resource_type not in _COMPUTE_TYPES:
            return None

        for row in resource.raw_export or []:
            avg_cpu = row.get("avg_cpu_percent")
            period_days = row.get("metrics_period_days")
            if avg_cpu is None or period_days is None:
                continue
            try:
                avg_cpu = float(avg_cpu)
                period_days = int(period_days)
            except (ValueError, TypeError):
                continue

            if avg_cpu < _CPU_THRESHOLD_PCT and period_days >= _MIN_METRICS_DAYS:
                return Finding(
                    resource=resource,
                    rule_name=self.name,
                    severity=self.severity,
                    estimated_monthly_saving_usd=resource.monthly_cost_usd,
                    evidence={
                        "avg_cpu_percent": avg_cpu,
                        "metrics_period_days": period_days,
                        "cpu_threshold_pct": _CPU_THRESHOLD_PCT,
                        "resource_type": resource.resource_type,
                        "resource_id": resource.resource_id,
                    },
                )

        return None
