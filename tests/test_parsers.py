import json
import textwrap
from pathlib import Path

import pytest

from app.parsers import aws as aws_parser
from app.parsers import azure as azure_parser

SAMPLE_DATA = Path(__file__).parent.parent / "sample_data"


# ---------------------------------------------------------------------------
# AWS parser
# ---------------------------------------------------------------------------

def test_aws_parse_produces_one_resource_per_unique_resource_id():
    resources = aws_parser.parse(SAMPLE_DATA / "aws_cur_sample.csv")
    assert len(resources) == 50


def test_aws_parse_maps_ec2_instance_fields_correctly():
    resources = aws_parser.parse(SAMPLE_DATA / "aws_cur_sample.csv")
    web01 = next(r for r in resources if r.resource_id == "i-0a1b2c3d4e5f60001")

    assert web01.provider == "aws"
    assert web01.resource_type == "ec2_instance"
    assert web01.region == "us-east-1"
    assert abs(web01.monthly_cost_usd - 69.12) < 0.01
    assert web01.tags.get("Name") == "prod-web-01"
    assert web01.tags.get("Environment") == "production"
    assert isinstance(web01.raw_export, list)
    assert len(web01.raw_export) >= 1


def test_aws_parse_maps_unattached_ebs_correctly():
    resources = aws_parser.parse(SAMPLE_DATA / "aws_cur_sample.csv")
    vol = next(r for r in resources if r.resource_id == "vol-0b1b2c3d4e5f60001")

    assert vol.resource_type == "ebs_volume"
    assert vol.tags.get("AttachedTo", "") == ""
    raw_op = vol.raw_export[0].get("lineItem/Operation", "")
    assert raw_op == "CreateVolume-Unattached"


def test_aws_parse_aggregates_cost_across_line_items(tmp_path: Path):
    header = (
        "identity/LineItemId,identity/TimeInterval,lineItem/UsageAccountId,"
        "lineItem/LineItemType,lineItem/UsageStartDate,lineItem/UsageEndDate,"
        "lineItem/ProductCode,lineItem/UsageType,lineItem/Operation,"
        "lineItem/AvailabilityZone,lineItem/ResourceId,lineItem/UsageAmount,"
        "lineItem/CurrencyCode,lineItem/UnblendedRate,lineItem/UnblendedCost,"
        "lineItem/BlendedCost,lineItem/LineItemDescription,product/ProductName,"
        "product/region,product/instanceType,product/operatingSystem,"
        "product/volumeType,product/location,pricing/term,pricing/unit,"
        "resourceTags/user:Name,resourceTags/user:Environment,"
        "resourceTags/user:Owner,resourceTags/user:AttachedTo,"
        "resourceTags/user:CreatedDate"
    )
    row = (
        "LI-{n},2025-04-{d}T00:00:00Z/2025-04-{e}T00:00:00Z,123456789012,Usage,"
        "2025-04-{d}T00:00:00Z,2025-04-{e}T00:00:00Z,AmazonEC2,"
        "USE1-BoxUsage:m5.large,RunInstances,us-east-1a,i-0test0000000000001,"
        "360,USD,0.09600,34.5600,34.5600,test row,Amazon Elastic Compute Cloud,"
        "us-east-1,m5.large,Linux,,US East (N. Virginia),OnDemand,Hrs,"
        "test-instance,production,test-owner,,"
    )
    csv_content = "\n".join([
        header,
        row.format(n=1, d="01", e="16"),
        row.format(n=2, d="16", e="30"),
    ])
    fixture = tmp_path / "two_rows.csv"
    fixture.write_text(csv_content)

    resources = aws_parser.parse(fixture)

    assert len(resources) == 1
    assert abs(resources[0].monthly_cost_usd - 69.12) < 0.01


def test_aws_parse_skips_row_with_missing_resource_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    # Minimal fixture — only the columns the parser requires, ResourceId empty.
    csv_content = (
        "lineItem/ResourceId,lineItem/UnblendedCost,product/region,"
        "lineItem/ProductCode,lineItem/UsageType\n"
        ",69.12,us-east-1,AmazonEC2,USE1-BoxUsage:m5.large\n"
    )
    fixture = tmp_path / "missing_id.csv"
    fixture.write_text(csv_content)

    with caplog.at_level("WARNING"):
        resources = aws_parser.parse(fixture)

    assert resources == []
    assert any("missing" in rec.message.lower() for rec in caplog.records)


# ---------------------------------------------------------------------------
# Azure parser
# ---------------------------------------------------------------------------

def test_azure_parse_produces_one_resource_per_resource_id():
    resources = azure_parser.parse(SAMPLE_DATA / "azure_billing_sample.json")
    assert len(resources) == 24


def test_azure_parse_maps_vm_fields_correctly():
    resources = azure_parser.parse(SAMPLE_DATA / "azure_billing_sample.json")
    arm_id = (
        "/subscriptions/a3b45678-1234-5678-9abc-def012345678"
        "/resourceGroups/rg-prod-eastus"
        "/providers/Microsoft.Compute/virtualMachines/vm-prod-web-01"
    )
    vm = next(r for r in resources if r.resource_id == arm_id)

    assert vm.provider == "azure"
    assert vm.resource_type == "virtual_machine"
    assert vm.region == "eastus"
    assert abs(vm.monthly_cost_usd - 69.12) < 0.01
    assert vm.tags.get("environment") == "production"
    assert isinstance(vm.raw_export, list)


def test_azure_parse_maps_unattached_disk_correctly():
    resources = azure_parser.parse(SAMPLE_DATA / "azure_billing_sample.json")
    disk = next(r for r in resources if "orphan-disk-01" in r.resource_id)

    assert disk.resource_type == "managed_disk"
    additional = json.loads(disk.raw_export[0]["AdditionalInfo"])
    assert additional["diskState"] == "Unattached"
    assert additional["attachedTo"] is None


def test_azure_parse_skips_record_with_missing_resource_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    records = [
        {
            "ResourceId": None,
            "ResourceName": "ghost-resource",
            "ConsumedService": "Microsoft.Compute",
            "MeterCategory": "Virtual Machines",
            "ResourceLocation": "eastus",
            "Cost": 50.0,
            "Date": "2025-04-30",
            "Tags": "{}",
        }
    ]
    fixture = tmp_path / "missing_id.json"
    fixture.write_text(json.dumps(records))

    with caplog.at_level("WARNING"):
        resources = azure_parser.parse(fixture)

    assert resources == []
    assert any("missing" in rec.message.lower() for rec in caplog.records)
