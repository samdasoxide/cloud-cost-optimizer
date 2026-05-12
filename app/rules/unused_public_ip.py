import json
import logging

from app.models.db import Finding, Resource
from app.rules.engine import Rule

logger = logging.getLogger(__name__)


class UnusedPublicIPRule(Rule):
    name = "UnusedPublicIPRule"
    severity = "low"

    def evaluate(self, resource: Resource) -> Finding | None:
        if resource.resource_type == "elastic_ip":
            return self._check_elastic_ip(resource)
        if resource.resource_type == "public_ip":
            return self._check_public_ip(resource)
        return None

    def _check_elastic_ip(self, resource: Resource) -> Finding | None:
        for row in resource.raw_export or []:
            usage_type = str(row.get("lineItem/UsageType", ""))
            if "IdleAddress" in usage_type:
                return Finding(
                    resource=resource,
                    rule_name=self.name,
                    severity=self.severity,
                    estimated_monthly_saving_usd=resource.monthly_cost_usd,
                    evidence={
                        "usage_type": usage_type,
                        "resource_id": resource.resource_id,
                        "monthly_cost_usd": resource.monthly_cost_usd,
                    },
                )
        return None

    def _check_public_ip(self, resource: Resource) -> Finding | None:
        for row in resource.raw_export or []:
            ai = row.get("AdditionalInfo")
            if isinstance(ai, str):
                try:
                    ai = json.loads(ai)
                except (json.JSONDecodeError, ValueError):
                    continue
            if (
                isinstance(ai, dict)
                and "associatedResource" in ai
                and ai["associatedResource"] is None
                and "ipAddress" in ai
            ):
                return Finding(
                    resource=resource,
                    rule_name=self.name,
                    severity=self.severity,
                    estimated_monthly_saving_usd=resource.monthly_cost_usd,
                    evidence={
                        "ip_address": ai.get("ipAddress"),
                        "associated_resource": None,
                        "allocation_method": ai.get("allocationMethod"),
                        "resource_id": resource.resource_id,
                    },
                )
        return None
