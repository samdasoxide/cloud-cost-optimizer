import datetime
import json

from app.models.db import Resource
from app.rules.engine import evaluate_all
from app.rules.idle_compute import IdleComputeRule
from app.rules.old_snapshot import OldSnapshotRule
from app.rules.unattached_volume import UnattachedVolumeRule
from app.rules.unused_public_ip import UnusedPublicIPRule


def _resource(**kwargs) -> Resource:
    defaults: dict = dict(
        provider="aws",
        resource_type="unknown",
        region="us-east-1",
        resource_id="test-resource-001",
        monthly_cost_usd=50.0,
        tags={},
        last_active_date=None,
        raw_export=[],
    )
    defaults.update(kwargs)
    return Resource(**defaults)


# ---------------------------------------------------------------------------
# UnattachedVolumeRule — AWS EBS
# ---------------------------------------------------------------------------


def test_unattached_volume_triggers_for_ebs_with_unattached_operation():
    resource = _resource(
        resource_type="ebs_volume",
        monthly_cost_usd=10.0,
        raw_export=[{"lineItem/Operation": "CreateVolume-Unattached"}],
    )
    finding = UnattachedVolumeRule().evaluate(resource)
    assert finding is not None
    assert finding.rule_name == "UnattachedVolumeRule"
    assert finding.severity == "medium"
    assert finding.estimated_monthly_saving_usd == 10.0
    assert finding.evidence["operation"] == "CreateVolume-Unattached"


def test_unattached_volume_does_not_trigger_for_attached_ebs():
    resource = _resource(
        resource_type="ebs_volume",
        raw_export=[{"lineItem/Operation": "CreateVolume"}],
    )
    assert UnattachedVolumeRule().evaluate(resource) is None


# ---------------------------------------------------------------------------
# UnattachedVolumeRule — Azure managed disk
# ---------------------------------------------------------------------------


def test_unattached_volume_triggers_for_unattached_managed_disk():
    ai = json.dumps({"diskSizeGB": 512, "diskState": "Unattached", "attachedTo": None})
    resource = _resource(
        provider="azure",
        resource_type="managed_disk",
        monthly_cost_usd=35.0,
        raw_export=[{"AdditionalInfo": ai}],
    )
    finding = UnattachedVolumeRule().evaluate(resource)
    assert finding is not None
    assert finding.severity == "medium"
    assert finding.evidence["disk_state"] == "Unattached"
    assert finding.evidence["disk_size_gb"] == 512
    assert finding.estimated_monthly_saving_usd == 35.0


def test_unattached_volume_does_not_trigger_for_attached_managed_disk():
    ai = json.dumps({"diskSizeGB": 128, "diskState": "Attached", "attachedTo": "vm-prod-web-01"})
    resource = _resource(
        provider="azure",
        resource_type="managed_disk",
        raw_export=[{"AdditionalInfo": ai}],
    )
    assert UnattachedVolumeRule().evaluate(resource) is None


# ---------------------------------------------------------------------------
# IdleComputeRule — AWS EC2
# ---------------------------------------------------------------------------


def test_idle_compute_triggers_for_ec2_below_cpu_threshold():
    resource = _resource(
        resource_type="ec2_instance",
        monthly_cost_usd=69.12,
        raw_export=[{"avg_cpu_percent": 2.3, "metrics_period_days": 21}],
    )
    finding = IdleComputeRule().evaluate(resource)
    assert finding is not None
    assert finding.rule_name == "IdleComputeRule"
    assert finding.severity == "high"
    assert finding.evidence["avg_cpu_percent"] == 2.3
    assert finding.evidence["metrics_period_days"] == 21
    assert finding.estimated_monthly_saving_usd == 69.12


def test_idle_compute_does_not_trigger_for_active_ec2():
    resource = _resource(
        resource_type="ec2_instance",
        raw_export=[{"avg_cpu_percent": 45.0, "metrics_period_days": 21}],
    )
    assert IdleComputeRule().evaluate(resource) is None


# ---------------------------------------------------------------------------
# IdleComputeRule — Azure VM
# ---------------------------------------------------------------------------


def test_idle_compute_triggers_for_azure_vm_below_cpu_threshold():
    resource = _resource(
        provider="azure",
        resource_type="virtual_machine",
        monthly_cost_usd=100.0,
        raw_export=[{"avg_cpu_percent": 1.5, "metrics_period_days": 14}],
    )
    finding = IdleComputeRule().evaluate(resource)
    assert finding is not None
    assert finding.severity == "high"
    assert finding.evidence["avg_cpu_percent"] == 1.5


def test_idle_compute_does_not_trigger_when_metrics_period_too_short():
    resource = _resource(
        resource_type="ec2_instance",
        raw_export=[{"avg_cpu_percent": 2.0, "metrics_period_days": 10}],
    )
    assert IdleComputeRule().evaluate(resource) is None


# ---------------------------------------------------------------------------
# UnusedPublicIPRule — AWS Elastic IP
# ---------------------------------------------------------------------------


def test_unused_public_ip_triggers_for_idle_elastic_ip():
    resource = _resource(
        resource_type="elastic_ip",
        monthly_cost_usd=3.65,
        raw_export=[{"lineItem/UsageType": "USE1-ElasticIP:IdleAddress"}],
    )
    finding = UnusedPublicIPRule().evaluate(resource)
    assert finding is not None
    assert finding.rule_name == "UnusedPublicIPRule"
    assert finding.severity == "low"
    assert "IdleAddress" in finding.evidence["usage_type"]
    assert finding.estimated_monthly_saving_usd == 3.65


def test_unused_public_ip_does_not_trigger_for_active_elastic_ip():
    resource = _resource(
        resource_type="elastic_ip",
        raw_export=[{"lineItem/UsageType": "USE1-ElasticIP:ElasticIP"}],
    )
    assert UnusedPublicIPRule().evaluate(resource) is None


# ---------------------------------------------------------------------------
# UnusedPublicIPRule — Azure public IP
# ---------------------------------------------------------------------------


def test_unused_public_ip_triggers_for_unassociated_azure_pip():
    ai = json.dumps(
        {"ipAddress": "20.50.60.71", "allocationMethod": "Static", "associatedResource": None}
    )
    resource = _resource(
        provider="azure",
        resource_type="public_ip",
        monthly_cost_usd=5.0,
        raw_export=[{"AdditionalInfo": ai}],
    )
    finding = UnusedPublicIPRule().evaluate(resource)
    assert finding is not None
    assert finding.evidence["ip_address"] == "20.50.60.71"
    assert finding.evidence["associated_resource"] is None


def test_unused_public_ip_does_not_trigger_for_associated_azure_pip():
    ai = json.dumps(
        {"ipAddress": "20.10.20.30", "allocationMethod": "Static", "associatedResource": "vm-prod-web-01"}
    )
    resource = _resource(
        provider="azure",
        resource_type="public_ip",
        raw_export=[{"AdditionalInfo": ai}],
    )
    assert UnusedPublicIPRule().evaluate(resource) is None


# ---------------------------------------------------------------------------
# OldSnapshotRule
# ---------------------------------------------------------------------------


def test_old_snapshot_triggers_for_snapshot_older_than_90_days():
    old_date = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
    resource = _resource(
        resource_type="ebs_snapshot",
        monthly_cost_usd=8.0,
        tags={"CreatedDate": old_date},
    )
    finding = OldSnapshotRule().evaluate(resource)
    assert finding is not None
    assert finding.rule_name == "OldSnapshotRule"
    assert finding.severity == "low"
    assert finding.evidence["age_days"] >= 120
    assert finding.evidence["threshold_days"] == 90
    assert finding.estimated_monthly_saving_usd == 8.0


def test_old_snapshot_does_not_trigger_for_recent_snapshot():
    recent_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    resource = _resource(
        resource_type="ebs_snapshot",
        tags={"CreatedDate": recent_date},
    )
    assert OldSnapshotRule().evaluate(resource) is None


def test_old_snapshot_does_not_trigger_when_no_creation_date():
    resource = _resource(resource_type="ebs_snapshot", tags={}, raw_export=[])
    assert OldSnapshotRule().evaluate(resource) is None


def test_old_snapshot_reads_creation_date_from_raw_export():
    old_date = (datetime.date.today() - datetime.timedelta(days=95)).isoformat()
    resource = _resource(
        resource_type="ebs_snapshot",
        monthly_cost_usd=4.0,
        raw_export=[{"creation_date": old_date}],
    )
    finding = OldSnapshotRule().evaluate(resource)
    assert finding is not None
    assert finding.evidence["age_days"] >= 95


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------


def test_evaluate_all_runs_all_rules_against_all_resources():
    old_date = (datetime.date.today() - datetime.timedelta(days=200)).isoformat()
    resources = [
        _resource(
            resource_type="ebs_volume",
            resource_id="vol-unattached-001",
            monthly_cost_usd=10.0,
            raw_export=[{"lineItem/Operation": "CreateVolume-Unattached"}],
        ),
        _resource(
            resource_type="ebs_snapshot",
            resource_id="snap-old-001",
            monthly_cost_usd=8.0,
            tags={"CreatedDate": old_date},
        ),
    ]
    rules = [UnattachedVolumeRule(), OldSnapshotRule()]
    findings = evaluate_all(resources, rules)
    assert len(findings) == 2
    rule_names = {f.rule_name for f in findings}
    assert "UnattachedVolumeRule" in rule_names
    assert "OldSnapshotRule" in rule_names


def test_evaluate_all_skips_non_matching_resources():
    resource = _resource(resource_type="s3_bucket", resource_id="my-bucket")
    rules = [UnattachedVolumeRule(), IdleComputeRule(), UnusedPublicIPRule(), OldSnapshotRule()]
    findings = evaluate_all([resource], rules)
    assert findings == []
