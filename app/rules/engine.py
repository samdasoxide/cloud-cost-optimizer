import logging
from abc import ABC, abstractmethod
from typing import Literal

from app.models.db import Finding, Resource

logger = logging.getLogger(__name__)


class Rule(ABC):
    name: str
    severity: Literal["low", "medium", "high"]

    @abstractmethod
    def evaluate(self, resource: Resource) -> Finding | None: ...


def evaluate_all(resources: list[Resource], rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    for resource in resources:
        for rule in rules:
            try:
                finding = rule.evaluate(resource)
                if finding is not None:
                    findings.append(finding)
            except Exception:
                logger.warning(
                    "Rule %s failed on resource %s",
                    rule.name,
                    resource.resource_id,
                    exc_info=True,
                )
    return findings
