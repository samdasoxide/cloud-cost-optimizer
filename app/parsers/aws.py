import datetime
import logging
from pathlib import Path

import pandas as pd

from app.models.db import Resource

logger = logging.getLogger(__name__)

_PRODUCT_CODE_TO_TYPE: dict[str, str] = {
    "AmazonRDS": "rds_instance",
    "AmazonS3": "s3_bucket",
}

_USAGE_TYPE_FRAGMENTS: list[tuple[str, str]] = [
    ("BoxUsage", "ec2_instance"),
    ("VolumeUsage", "ebs_volume"),
    ("SnapshotUsage", "ebs_snapshot"),
    ("ElasticIP", "elastic_ip"),
]


def _resource_type(usage_type: str, product_code: str) -> str:
    if product_code in _PRODUCT_CODE_TO_TYPE:
        return _PRODUCT_CODE_TO_TYPE[product_code]
    for fragment, rtype in _USAGE_TYPE_FRAGMENTS:
        if fragment in usage_type:
            return rtype
    return "unknown"


def _best_resource_type(group: pd.DataFrame) -> str:
    for _, row in group.iterrows():
        rt = _resource_type(
            str(row.get("lineItem/UsageType", "")),
            str(row.get("lineItem/ProductCode", "")),
        )
        if rt != "unknown":
            return rt
    return "unknown"


def _extract_tags(row: pd.Series) -> dict[str, str]:
    tags: dict[str, str] = {}
    for col in row.index:
        if col.startswith("resourceTags/user:"):
            key = col.removeprefix("resourceTags/user:")
            val = row[col]
            if pd.notna(val) and str(val).strip():
                tags[key] = str(val)
    return tags


def parse(file_path: Path) -> list[Resource]:
    try:
        df = pd.read_csv(file_path, dtype=str)
    except Exception:
        logger.exception("Failed to read AWS CUR file %s", file_path)
        return []

    required = {
        "lineItem/ResourceId",
        "lineItem/UnblendedCost",
        "product/region",
        "lineItem/ProductCode",
        "lineItem/UsageType",
    }
    missing = required - set(df.columns)
    if missing:
        logger.error("AWS CUR file %s missing required columns: %s", file_path, missing)
        return []

    empty_mask = df["lineItem/ResourceId"].isna() | (df["lineItem/ResourceId"].str.strip() == "")
    skipped = int(empty_mask.sum())
    if skipped:
        logger.warning(
            "Skipped %d row(s) in %s with missing lineItem/ResourceId", skipped, file_path
        )
    df = df[~empty_mask]

    resources: list[Resource] = []

    for resource_id, group in df.groupby("lineItem/ResourceId", sort=False):
        try:
            monthly_cost = (
                pd.to_numeric(group["lineItem/UnblendedCost"], errors="coerce")
                .fillna(0.0)
                .sum()
            )
            ref = group.iloc[0]
            resource_type = _best_resource_type(group)
            region = str(ref.get("product/region", "") or "unknown").strip() or "unknown"
            tags = _extract_tags(ref)

            last_active: datetime.date | None = None
            raw_end = ref.get("lineItem/UsageEndDate")
            if raw_end and pd.notna(raw_end):
                try:
                    last_active = datetime.date.fromisoformat(str(raw_end)[:10])
                except ValueError:
                    pass

            resources.append(
                Resource(
                    provider="aws",
                    resource_type=resource_type,
                    region=region,
                    resource_id=str(resource_id),
                    monthly_cost_usd=round(float(monthly_cost), 4),
                    tags=tags,
                    last_active_date=last_active,
                    raw_export=group.to_dict(orient="records"),
                )
            )
        except Exception:
            logger.warning(
                "Skipped resource_id '%s' in %s due to unexpected error",
                resource_id,
                file_path,
                exc_info=True,
            )

    return resources
