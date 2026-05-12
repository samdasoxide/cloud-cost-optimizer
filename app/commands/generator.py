import re

from app.models.db import Finding, Resource

_EC2_DRY_RUN_NOTE = (
    "Dry-run available: append --dry-run to check permissions without making changes "
    "(returns DryRunOperation if authorised, UnauthorizedOperation otherwise)."
)

_RDS_SNAPSHOT_WARNING = (
    "WARNING: --skip-final-snapshot permanently deletes automated backups with no recovery path. "
    "Replace the --final-db-snapshot-identifier placeholder with a real name, "
    "or use --skip-final-snapshot only after confirming backup status."
)

_DRY_RUN_TYPES = frozenset({"ebs_volume", "ec2_instance", "elastic_ip", "ebs_snapshot"})


def generate_command(finding: Finding, resource: Resource) -> str:
    comment_lines = _build_comment(finding, resource)
    command_line = _build_command(resource)
    return "\n".join(comment_lines + [command_line])


def _build_comment(finding: Finding, resource: Resource) -> list[str]:
    lines = [
        f"# REVIEW BEFORE EXECUTING — flagged by {finding.rule_name} (severity: {finding.severity})",
        f"# Estimated monthly saving: ${finding.estimated_monthly_saving_usd:.2f}",
        f"# Resource: {resource.resource_id} | type: {resource.resource_type} | region: {resource.region}",
    ]
    if resource.resource_type in _DRY_RUN_TYPES:
        lines.append(f"# {_EC2_DRY_RUN_NOTE}")
    if resource.resource_type == "rds_instance":
        lines.append(f"# {_RDS_SNAPSHOT_WARNING}")
    return lines


def _build_command(resource: Resource) -> str:
    if resource.provider == "aws":
        return _aws_command(resource)
    if resource.provider == "azure":
        return _azure_command(resource)
    return f"# No decommission command available for provider: {resource.provider}"


def _aws_command(resource: Resource) -> str:
    rid = resource.resource_id
    region = resource.region
    rt = resource.resource_type

    if rt == "ebs_volume":
        return f"aws ec2 delete-volume --volume-id {rid} --region {region}"

    if rt == "ec2_instance":
        return f"aws ec2 terminate-instances --instance-ids {rid} --region {region}"

    if rt == "elastic_ip":
        return f"aws ec2 release-address --allocation-id {rid} --region {region}"

    if rt in ("ebs_snapshot", "snapshot"):
        return f"aws ec2 delete-snapshot --snapshot-id {rid} --region {region}"

    if rt == "rds_instance":
        db_id = _rds_identifier(rid)
        snapshot_id = f"{db_id}-final-snapshot"
        return (
            f"aws rds delete-db-instance"
            f" --db-instance-identifier {db_id}"
            f" --no-skip-final-snapshot"
            f" --final-db-snapshot-identifier {snapshot_id}"
            f" --region {region}"
        )

    return f"# No decommission command available for resource type: {rt}"


def _azure_command(resource: Resource) -> str:
    rg, name, server = _parse_arm_id(resource.resource_id)
    rt = resource.resource_type

    if rt == "managed_disk":
        return f"az disk delete --name {name} --resource-group {rg} --yes"

    if rt == "virtual_machine":
        return f"az vm delete --name {name} --resource-group {rg} --yes"

    if rt == "public_ip":
        # az network public-ip delete has no --yes flag (no confirmation prompt)
        return f"az network public-ip delete --name {name} --resource-group {rg}"

    if rt == "sql_database":
        if server:
            return f"az sql db delete --name {name} --server {server} --resource-group {rg} --yes"
        return f"az sql db delete --name {name} --resource-group {rg} --yes"

    return f"# No decommission command available for resource type: {rt}"


def _parse_arm_id(resource_id: str) -> tuple[str, str, str | None]:
    rg_match = re.search(r"/resourceGroups/([^/]+)/", resource_id, re.IGNORECASE)
    resource_group = rg_match.group(1) if rg_match else "UNKNOWN_RESOURCE_GROUP"
    resource_name = resource_id.rstrip("/").rsplit("/", 1)[-1]
    server_match = re.search(r"/servers/([^/]+)/", resource_id, re.IGNORECASE)
    server = server_match.group(1) if server_match else None
    return resource_group, resource_name, server


def _rds_identifier(resource_id: str) -> str:
    # CUR resource IDs for RDS may be ARNs: arn:aws:rds:region:account:db:identifier
    if resource_id.startswith("arn:aws:rds:") and ":db:" in resource_id:
        return resource_id.rsplit(":db:", 1)[-1]
    return resource_id
