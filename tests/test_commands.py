import datetime
from typing import Any

from app.commands.generator import generate_command
from app.models.db import Finding, Resource


def _resource(**kwargs: Any) -> Resource:
    defaults: dict[str, Any] = dict(
        provider="aws",
        resource_type="unknown",
        region="us-east-1",
        resource_id="r-000001",
        monthly_cost_usd=50.0,
        tags={},
        last_active_date=None,
        raw_export=[],
    )
    defaults.update(kwargs)
    return Resource(**defaults)


def _finding(resource: Resource, **kwargs: Any) -> Finding:
    defaults: dict[str, Any] = dict(
        resource=resource,
        rule_name="TestRule",
        severity="medium",
        estimated_monthly_saving_usd=resource.monthly_cost_usd,
        evidence={},
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def _azure_arm(rg: str, provider: str, resource_type: str, name: str, extra: str = "") -> str:
    sub = "a3b45678-1234-5678-9abc-def012345678"
    base = f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{resource_type}/{name}"
    return base + extra


# ---------------------------------------------------------------------------
# Comment header
# ---------------------------------------------------------------------------


def test_command_includes_rule_name_and_saving_in_comment() -> None:
    resource = _resource(resource_type="ebs_volume", resource_id="vol-abc123", monthly_cost_usd=30.0)
    finding = _finding(resource, rule_name="UnattachedVolumeRule", estimated_monthly_saving_usd=30.0)
    cmd = generate_command(finding, resource)
    assert "UnattachedVolumeRule" in cmd
    assert "$30.00" in cmd


def test_comment_includes_resource_id_and_region() -> None:
    resource = _resource(resource_type="ebs_volume", resource_id="vol-abc123", region="eu-west-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "vol-abc123" in cmd
    assert "eu-west-1" in cmd


# ---------------------------------------------------------------------------
# AWS — UnattachedVolumeRule (ebs_volume → ec2 delete-volume)
# ---------------------------------------------------------------------------


def test_aws_ebs_volume_command_format() -> None:
    resource = _resource(
        resource_type="ebs_volume",
        resource_id="vol-0b1b2c3d4e5f60001",
        region="us-east-1",
    )
    finding = _finding(resource, rule_name="UnattachedVolumeRule", severity="medium")
    cmd = generate_command(finding, resource)
    assert "aws ec2 delete-volume" in cmd
    assert "--volume-id vol-0b1b2c3d4e5f60001" in cmd
    assert "--region us-east-1" in cmd


def test_aws_ebs_volume_command_includes_dry_run_note() -> None:
    resource = _resource(resource_type="ebs_volume", resource_id="vol-abc", region="us-east-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "--dry-run" in cmd


# ---------------------------------------------------------------------------
# AWS — IdleComputeRule (ec2_instance → ec2 terminate-instances)
# ---------------------------------------------------------------------------


def test_aws_ec2_instance_command_format() -> None:
    resource = _resource(
        resource_type="ec2_instance",
        resource_id="i-0a1b2c3d4e5f60001",
        region="us-west-2",
    )
    finding = _finding(resource, rule_name="IdleComputeRule", severity="high")
    cmd = generate_command(finding, resource)
    assert "aws ec2 terminate-instances" in cmd
    assert "--instance-ids i-0a1b2c3d4e5f60001" in cmd
    assert "--region us-west-2" in cmd


def test_aws_ec2_instance_command_includes_dry_run_note() -> None:
    resource = _resource(resource_type="ec2_instance", resource_id="i-abc", region="us-east-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "--dry-run" in cmd


# ---------------------------------------------------------------------------
# AWS — UnusedPublicIPRule (elastic_ip → ec2 release-address)
# ---------------------------------------------------------------------------


def test_aws_elastic_ip_command_format() -> None:
    resource = _resource(
        resource_type="elastic_ip",
        resource_id="eipalloc-0a1b2c3d4e5f60001",
        region="us-east-1",
    )
    finding = _finding(resource, rule_name="UnusedPublicIPRule", severity="low")
    cmd = generate_command(finding, resource)
    assert "aws ec2 release-address" in cmd
    assert "--allocation-id eipalloc-0a1b2c3d4e5f60001" in cmd
    assert "--region us-east-1" in cmd


def test_aws_elastic_ip_command_includes_dry_run_note() -> None:
    resource = _resource(resource_type="elastic_ip", resource_id="eipalloc-abc", region="us-east-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "--dry-run" in cmd


# ---------------------------------------------------------------------------
# AWS — OldSnapshotRule (ebs_snapshot → ec2 delete-snapshot)
# ---------------------------------------------------------------------------


def test_aws_ebs_snapshot_command_format() -> None:
    resource = _resource(
        resource_type="ebs_snapshot",
        resource_id="snap-0a1b2c3d4e5f60001",
        region="eu-west-1",
    )
    finding = _finding(resource, rule_name="OldSnapshotRule", severity="low")
    cmd = generate_command(finding, resource)
    assert "aws ec2 delete-snapshot" in cmd
    assert "--snapshot-id snap-0a1b2c3d4e5f60001" in cmd
    assert "--region eu-west-1" in cmd


def test_aws_ebs_snapshot_command_includes_dry_run_note() -> None:
    resource = _resource(resource_type="ebs_snapshot", resource_id="snap-abc", region="us-east-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "--dry-run" in cmd


# ---------------------------------------------------------------------------
# AWS — RDS (rds_instance → rds delete-db-instance)
# ---------------------------------------------------------------------------


def test_aws_rds_command_format() -> None:
    resource = _resource(
        resource_type="rds_instance",
        resource_id="mydb-prod",
        region="us-east-1",
    )
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "aws rds delete-db-instance" in cmd
    assert "--db-instance-identifier mydb-prod" in cmd
    assert "--no-skip-final-snapshot" in cmd
    assert "--final-db-snapshot-identifier mydb-prod-final-snapshot" in cmd
    assert "--region us-east-1" in cmd


def test_aws_rds_command_includes_snapshot_warning() -> None:
    resource = _resource(resource_type="rds_instance", resource_id="mydb", region="us-east-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "--skip-final-snapshot" in cmd
    assert "WARNING" in cmd


def test_aws_rds_strips_arn_prefix_from_resource_id() -> None:
    arn = "arn:aws:rds:us-east-1:123456789012:db:mydb-prod"
    resource = _resource(resource_type="rds_instance", resource_id=arn, region="us-east-1")
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "--db-instance-identifier mydb-prod" in cmd
    assert "arn:aws:rds" not in cmd.split("\n")[-1]


def test_aws_rds_command_has_no_dry_run_note() -> None:
    resource = _resource(resource_type="rds_instance", resource_id="mydb", region="us-east-1")
    finding = _finding(resource)
    # RDS delete-db-instance does not support --dry-run (AWS CLI v2 confirmed)
    cmd = generate_command(finding, resource)
    lines = [ln for ln in cmd.splitlines() if not ln.startswith("#")]
    assert "--dry-run" not in " ".join(lines)


# ---------------------------------------------------------------------------
# Azure — UnattachedVolumeRule (managed_disk → az disk delete)
# ---------------------------------------------------------------------------


def test_azure_managed_disk_command_format() -> None:
    arm_id = _azure_arm("rg-prod-eastus", "Microsoft.Compute", "disks", "orphan-disk-01")
    resource = _resource(
        provider="azure",
        resource_type="managed_disk",
        resource_id=arm_id,
        region="eastus",
    )
    finding = _finding(resource, rule_name="UnattachedVolumeRule", severity="medium")
    cmd = generate_command(finding, resource)
    assert "az disk delete" in cmd
    assert "--name orphan-disk-01" in cmd
    assert "--resource-group rg-prod-eastus" in cmd
    assert "--yes" in cmd


# ---------------------------------------------------------------------------
# Azure — IdleComputeRule (virtual_machine → az vm delete)
# ---------------------------------------------------------------------------


def test_azure_virtual_machine_command_format() -> None:
    arm_id = _azure_arm(
        "rg-prod-eastus", "Microsoft.Compute", "virtualMachines", "vm-legacy-analytics"
    )
    resource = _resource(
        provider="azure",
        resource_type="virtual_machine",
        resource_id=arm_id,
        region="eastus",
    )
    finding = _finding(resource, rule_name="IdleComputeRule", severity="high")
    cmd = generate_command(finding, resource)
    assert "az vm delete" in cmd
    assert "--name vm-legacy-analytics" in cmd
    assert "--resource-group rg-prod-eastus" in cmd
    assert "--yes" in cmd


# ---------------------------------------------------------------------------
# Azure — UnusedPublicIPRule (public_ip → az network public-ip delete)
# ---------------------------------------------------------------------------


def test_azure_public_ip_command_format() -> None:
    arm_id = _azure_arm(
        "rg-prod-eastus", "Microsoft.Network", "publicIPAddresses", "pip-old-test-01"
    )
    resource = _resource(
        provider="azure",
        resource_type="public_ip",
        resource_id=arm_id,
        region="eastus",
    )
    finding = _finding(resource, rule_name="UnusedPublicIPRule", severity="low")
    cmd = generate_command(finding, resource)
    assert "az network public-ip delete" in cmd
    assert "--name pip-old-test-01" in cmd
    assert "--resource-group rg-prod-eastus" in cmd
    # az network public-ip delete has no --yes flag (confirmed against Azure CLI docs)
    last_line = cmd.splitlines()[-1]
    assert "--yes" not in last_line


# ---------------------------------------------------------------------------
# Azure — sql_database → az sql db delete (requires --server)
# ---------------------------------------------------------------------------


def test_azure_sql_database_command_format() -> None:
    arm_id = _azure_arm(
        "rg-prod-eastus",
        "Microsoft.Sql",
        "servers",
        "sql-prod",
        extra="/databases/sqldb-prod-main",
    )
    resource = _resource(
        provider="azure",
        resource_type="sql_database",
        resource_id=arm_id,
        region="eastus",
    )
    finding = _finding(resource)
    cmd = generate_command(finding, resource)
    assert "az sql db delete" in cmd
    assert "--name sqldb-prod-main" in cmd
    assert "--server sql-prod" in cmd
    assert "--resource-group rg-prod-eastus" in cmd
    assert "--yes" in cmd
