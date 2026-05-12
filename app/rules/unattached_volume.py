import json
import logging

from app.models.db import Finding, Resource
from app.rules.engine import Rule

logger = logging.getLogger(__name__)


class UnattachedVolumeRule(Rule):
    name = "UnattachedVolumeRule"
    severity = "medium"

    def evaluate(self, resource: Resource) -> Finding | None:
        if resource.resource_type == "ebs_volume":
            return self._check_ebs(resource)
        if resource.resource_type == "managed_disk":
            return self._check_managed_disk(resource)
        return None

    def _check_ebs(self, resource: Resource) -> Finding | None:
        for row in resource.raw_export or []:
            if row.get("lineItem/Operation") == "CreateVolume-Unattached":
                return Finding(
                    resource=resource,
                    rule_name=self.name,
                    severity=self.severity,
                    estimated_monthly_saving_usd=resource.monthly_cost_usd,
                    evidence={
                        "operation": "CreateVolume-Unattached",
                        "resource_id": resource.resource_id,
                        "monthly_cost_usd": resource.monthly_cost_usd,
                    },
                )
        return None

    def _check_managed_disk(self, resource: Resource) -> Finding | None:
        for row in resource.raw_export or []:
            ai = row.get("AdditionalInfo")
            if isinstance(ai, str):
                try:
                    ai = json.loads(ai)
                except (json.JSONDecodeError, ValueError):
                    continue
            if isinstance(ai, dict) and ai.get("diskState") == "Unattached":
                return Finding(
                    resource=resource,
                    rule_name=self.name,
                    severity=self.severity,
                    estimated_monthly_saving_usd=resource.monthly_cost_usd,
                    evidence={
                        "disk_state": "Unattached",
                        "disk_size_gb": ai.get("diskSizeGB"),
                        "attached_to": ai.get("attachedTo"),
                        "resource_id": resource.resource_id,
                    },
                )
        return None
