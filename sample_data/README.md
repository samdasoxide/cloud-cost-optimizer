# Sample Billing Export Fixtures

Deterministic fixtures for the rules engine. Billing period: **April 2025**.

---

## Files

### `aws_cur_sample.csv`

**Schema:** AWS Cost and Usage Report (CUR) 2.0  
**Reference:** https://docs.aws.amazon.com/cur/latest/userguide/data-dictionary.html  
**Rows:** 50 data rows, 30 columns

Column families used: `identity/*`, `lineItem/*`, `product/*`, `pricing/*`, `resourceTags/user:*`

| Resource type | Count | Active | Orphaned |
|---|---|---|---|
| EC2 instances | 10 | 7 | 3 (idle — low `lineItem/UsageAmount`) |
| EBS volumes (attached) | 12 | 8 (active EC2) + 4 (idle EC2) | 0 |
| EBS volumes (unattached) | 4 | 0 | 4 |
| EBS snapshots | 4 | 0 | 4 (all >8 months old) |
| Elastic IPs | 7 | 3 (associated, $0) | 4 (unassociated) |
| RDS instances | 6 | 3 | 3 (idle) |
| S3 buckets | 7 | 5 | 2 (no recent access) |

#### Orphan signals by resource type

**Unattached EBS volumes** (`vol-0b1b2c3d4e5f600{01-04}`):  
`lineItem/Operation = "CreateVolume-Unattached"` and `resourceTags/user:AttachedTo` is empty.

**Idle EC2 instances** (`i-0b1b2c3d4e5f600{01-03}`):  
`lineItem/UsageAmount` is 2, 12, or 24 (out of 720 hours). Their root EBS volumes still bill for the full month — the low compute hours combined with full-price storage is the waste signal.

**Unassociated Elastic IPs** (`eipalloc-0b1b2c3d00{1-4}`):  
`lineItem/UsageType` ends in `IdleAddress` (e.g. `USE1-ElasticIP:IdleAddress`). Associated EIPs appear with `ElasticIP:ElasticIP` and `lineItem/UnblendedCost = 0`.

**Old EBS snapshots** (`snap-0a1b2c3d4e5f600{1-4}`):  
`lineItem/Operation = "CreateSnapshot"` with `resourceTags/user:CreatedDate` ranging from 2024-01-15 to 2024-08-05 (all >8 months before the April 2025 billing period).

**Idle RDS instances** (`dev-mysql-01`, `test-postgres-01`, `old-analytics-db`):  
Same hourly rate as active instances — waste is inferred from `resourceTags/user:CreatedDate` (old) and `environment = development/analytics` combined with high cost. `old-analytics-db` is a `db.r5.2xlarge` Multi-AZ at $754.56/month with `CreatedDate = 2024-05-30`.

**Stale S3 buckets** (`old-project-data-archive`, `ml-experiments-dump`):  
`resourceTags/user:CreatedDate` of 2024-09-01 and 2025-01-05 respectively with no subsequent activity tags. Real billing exports carry no "last access" field; the signal comes from tag hygiene and naming convention.

---

### `azure_billing_sample.json`

**Schema:** Azure Cost Management Usage Details — EA account format  
**Reference:** https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/understand-usage-details-fields  
**Records:** 24

Fields used: `BillingAccountId/Name`, `SubscriptionId/Name`, `ResourceGroup`, `ResourceLocation`, `ResourceId` (full ARM path), `ResourceName`, `ConsumedService`, `MeterCategory/SubCategory`, `MeterId/Name`, `ProductName`, `ChargeType`, `Date`, `Quantity`, `UnitOfMeasure`, `EffectivePrice`, `Cost`, `BillingCurrency`, `PricingModel`, `Tags`, `AdditionalInfo`

| Resource type | Count | Active | Orphaned |
|---|---|---|---|
| Virtual Machines | 5 | 3 | 2 (idle — low `Quantity`) |
| Managed Disks | 11 | 7 | 4 (`diskState: Unattached`) |
| Public IP Addresses | 5 | 2 | 3 (`associatedResource: null`) |
| SQL Databases | 4 | 2 | 2 (idle, old `lastActivity` tag) |

#### Orphan signals by resource type

**Unattached managed disks** (`orphan-disk-0{1-4}`):  
`AdditionalInfo` JSON contains `"diskState": "Unattached"` and `"attachedTo": null`. Real Azure billing exports do not include a disk state field natively; this mirrors a common pattern where operators populate `AdditionalInfo` or enrich exports via Azure Resource Graph.

**Idle VMs** (`vm-dev-test-01`, `vm-legacy-analytics`):  
`Quantity` is 3 and 8 respectively (out of 720 hours). `AdditionalInfo` includes `"powerState": "deallocated"`. Their OS and data disks continue billing at full price, visible as separate records with `diskState: Attached`.

**Unassociated Public IPs** (`pip-old-test-01`, `pip-old-test-02`, `pip-old-dev-01`):  
`AdditionalInfo` JSON contains `"associatedResource": null`. Associated IPs show the VM name in that field.

**Idle SQL databases** (`sqldb-dev-scratch`, `sqldb-old-project`):  
`Tags` contains `"lastActivity"` dates of `2025-01-15` and `2024-12-01` (91+ and 120+ days before the billing period). `sqldb-old-project` has an empty `owner` tag and sits in `rg-legacy-westeurope`.

---

## Resource ID conventions

| Provider | Format |
|---|---|
| AWS EC2 | `i-0[hex]{17}` |
| AWS EBS volume | `vol-0[hex]{17}` |
| AWS EBS snapshot | `snap-0[hex]{17}` |
| AWS EIP | `eipalloc-0[hex]{9}` |
| AWS RDS | `arn:aws:rds:REGION:123456789012:db:NAME` |
| AWS S3 | bucket name (no ARN prefix in CUR ResourceId) |
| Azure (all) | `/subscriptions/UUID/resourceGroups/NAME/providers/NS/TYPE/NAME` |
