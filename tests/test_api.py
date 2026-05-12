import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models.db import Base

SAMPLE_DATA = Path(__file__).parent.parent / "sample_data"


@pytest.fixture()
def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    test_engine = create_async_engine(db_url, echo=False)
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_get_session():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()

    async def _dispose() -> None:
        await test_engine.dispose()

    asyncio.run(_dispose())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def test_ingest_aws_cur_returns_summary(client: TestClient) -> None:
    csv_file = SAMPLE_DATA / "aws_cur_sample.csv"
    with csv_file.open("rb") as fh:
        response = client.post(
            "/api/ingest",
            data={"provider": "aws"},
            files={"file": ("aws_cur_sample.csv", fh, "text/csv")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "aws"
    assert body["row_count"] == 50
    assert body["finding_count"] > 0
    assert body["run_id"] >= 1


def test_ingest_rejects_invalid_provider(client: TestClient) -> None:
    response = client.post(
        "/api/ingest",
        data={"provider": "gcp"},
        files={"file": ("dummy.csv", b"a,b\n1,2", "text/csv")},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Findings list
# ---------------------------------------------------------------------------


def _ingest_aws(client: TestClient) -> None:
    csv_file = SAMPLE_DATA / "aws_cur_sample.csv"
    with csv_file.open("rb") as fh:
        client.post(
            "/api/ingest",
            data={"provider": "aws"},
            files={"file": ("aws_cur_sample.csv", fh, "text/csv")},
        )


def test_findings_list_returns_results_after_ingest(client: TestClient) -> None:
    _ingest_aws(client)
    response = client.get("/api/findings")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    assert len(body["items"]) > 0


def test_findings_list_items_contain_expected_fields(client: TestClient) -> None:
    _ingest_aws(client)
    response = client.get("/api/findings")
    item = response.json()["items"][0]
    assert "rule_name" in item
    assert "severity" in item
    assert "estimated_monthly_saving_usd" in item
    assert "decommission_command" in item
    assert "resource" in item


def test_findings_list_contains_known_rule_names(client: TestClient) -> None:
    _ingest_aws(client)
    response = client.get("/api/findings")
    rule_names = {item["rule_name"] for item in response.json()["items"]}
    known_rules = {"UnattachedVolumeRule", "UnusedPublicIPRule", "OldSnapshotRule", "IdleComputeRule"}
    assert rule_names & known_rules, f"Expected at least one known rule, got: {rule_names}"


def test_findings_list_severity_filter(client: TestClient) -> None:
    _ingest_aws(client)
    response = client.get("/api/findings?severity=medium")
    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert item["severity"] == "medium"


def test_findings_list_rule_name_filter(client: TestClient) -> None:
    _ingest_aws(client)
    response = client.get("/api/findings?rule_name=UnusedPublicIPRule")
    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert item["rule_name"] == "UnusedPublicIPRule"


def test_findings_list_pagination(client: TestClient) -> None:
    _ingest_aws(client)
    page1 = client.get("/api/findings?offset=0&limit=2").json()
    page2 = client.get("/api/findings?offset=2&limit=2").json()
    assert page1["page_size"] == 2
    assert page2["page"] == 2
    if page1["total"] > 2:
        ids_p1 = {item["id"] for item in page1["items"]}
        ids_p2 = {item["id"] for item in page2["items"]}
        assert ids_p1.isdisjoint(ids_p2)


# ---------------------------------------------------------------------------
# Finding detail
# ---------------------------------------------------------------------------


def test_finding_detail_returns_full_record(client: TestClient) -> None:
    _ingest_aws(client)
    finding_id = client.get("/api/findings").json()["items"][0]["id"]
    response = client.get(f"/api/findings/{finding_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == finding_id
    assert "evidence" in body
    assert "decommission_command" in body
    assert body["resource"]["provider"] == "aws"


def test_finding_detail_404_for_missing_id(client: TestClient) -> None:
    response = client.get("/api/findings/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_returns_zeros_on_empty_db(client: TestClient) -> None:
    response = client.get("/api/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_resources"] == 0
    assert body["total_findings"] == 0
    assert body["total_estimated_monthly_saving_usd"] == 0.0


def test_summary_reflects_ingested_data(client: TestClient) -> None:
    _ingest_aws(client)
    response = client.get("/api/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_resources"] == 50
    assert body["total_findings"] > 0
    assert body["total_estimated_monthly_saving_usd"] > 0.0
    assert len(body["findings_by_severity"]) > 0
    assert len(body["findings_by_rule"]) > 0
    assert len(body["top_regions_by_waste"]) > 0
