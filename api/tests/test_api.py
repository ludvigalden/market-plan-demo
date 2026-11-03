"""API tests against a real PostgreSQL database; the holiday API is mocked with respx."""

from __future__ import annotations

from typing import Any

import httpx
import respx

CAMPAIGN = {
    "name": "Spring Essentials",
    "window_start": "2026-05-01",
    "window_end": "2026-05-31",
    "global_budget_eur": "200000.00",
}


async def make_campaign(client: httpx.AsyncClient, markets: list[str]) -> dict[str, Any]:
    r = await client.post("/api/campaigns", json=CAMPAIGN)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = await client.put(f"/api/campaigns/{cid}/markets", json={"market_codes": markets})
    assert r.status_code == 200, r.text
    return r.json()


async def test_healthz(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.json() == {"status": "ok", "database": "ok", "ai_provider": "stub"}
    assert r.headers["x-request-id"]


async def test_seed_markets(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/markets")
    assert [m["code"] for m in r.json()] == ["DE", "FR", "JP", "SE", "US"]


async def test_campaign_crud(client: httpx.AsyncClient) -> None:
    c = await make_campaign(client, ["se", "DE"])
    assert c["market_codes"] == ["DE", "SE"]
    r = await client.patch(f"/api/campaigns/{c['id']}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed"
    assert any(x["id"] == c["id"] for x in (await client.get("/api/campaigns")).json())
    assert (await client.delete(f"/api/campaigns/{c['id']}")).status_code == 204
    r = await client.get(f"/api/campaigns/{c['id']}")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


async def test_validation_errors_use_error_body(client: httpx.AsyncClient) -> None:
    bad = {**CAMPAIGN, "window_end": "2026-04-01"}
    r = await client.post("/api/campaigns", json=bad)
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    c = await make_campaign(client, ["SE"])
    r = await client.put(f"/api/campaigns/{c['id']}/markets", json={"market_codes": ["XX"]})
    assert r.status_code == 422 and "XX" in r.json()["message"]


async def test_market_view_flags_and_budget(client: httpx.AsyncClient) -> None:
    c = await make_campaign(client, ["SE", "US"])
    r = await client.get(f"/api/campaigns/{c['id']}/market-view")
    rows = {m["plan"]["market_code"]: m for m in r.json()["markets"]}
    assert rows["SE"]["holidays_available"] is True
    assert [(x["kind"], x["date"]) for x in rows["SE"]["clashes"]] == [
        ("launch_on_holiday", "2026-05-01")
    ]
    assert rows["US"]["clashes"][0]["kind"] == "holiday_in_window"
    assert rows["SE"]["plan"]["budget_eur"] == "100000.00"


async def test_holidays_cached_after_first_fetch(
    client: httpx.AsyncClient, nager: respx.MockRouter
) -> None:
    c = await make_campaign(client, ["JP"])
    await client.get(f"/api/campaigns/{c['id']}/market-view")
    calls = nager.calls.call_count
    await client.get(f"/api/campaigns/{c['id']}/market-view")
    assert nager.calls.call_count == calls


async def test_holiday_outage_degrades(client: httpx.AsyncClient, nager: respx.MockRouter) -> None:
    nager.routes[0].side_effect = httpx.ConnectError("down")
    # A year no other test touches, so nothing is cached yet.
    r = await client.post(
        "/api/campaigns",
        json={**CAMPAIGN, "window_start": "2031-05-01", "window_end": "2031-05-31"},
    )
    cid = r.json()["id"]
    await client.put(f"/api/campaigns/{cid}/markets", json={"market_codes": ["FR"]})
    r = await client.get(f"/api/campaigns/{cid}/market-view")
    assert r.status_code == 200
    row = r.json()["markets"][0]
    assert row["holidays_available"] is False and row["clashes"] == []
    r = await client.post(f"/api/campaigns/{cid}/suggestions")
    assert r.status_code == 200
    assert r.json()["suggestions"] == []
    assert "holidays unavailable" in r.json()["rejection_reasons"][0]


async def test_suggest_accept_reject_audit(client: httpx.AsyncClient) -> None:
    c = await make_campaign(client, ["SE", "DE"])
    r = await client.post(f"/api/campaigns/{c['id']}/suggestions")
    assert r.status_code == 200
    body = r.json()
    assert body["rejected_by_validator"] == 0
    se = [s for s in body["suggestions"] if s["market_code"] == "SE"]
    assert se[0]["action"] == "shift_start" and se[0]["new_date"] == "2026-05-04"
    assert se[0]["model_deployment"] == "stub" and se[0]["prompt_version"] == "adapt-v1"
    assert se[0]["verdict"] is None

    # Suggestions are never applied without a decision.
    view = (await client.get(f"/api/campaigns/{c['id']}/market-view")).json()
    se_plan = next(m["plan"] for m in view["markets"] if m["plan"]["market_code"] == "SE")
    assert se_plan["start_date"] == "2026-05-01" and se_plan["version"] == 1

    r = await client.post(
        f"/api/suggestions/{se[0]['id']}/accept", json={"expected_plan_version": 1}
    )
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["start_date"] == "2026-05-04"
    assert r.json()["plan"]["version"] == 2 and r.json()["plan"]["status"] == "adapted"

    r = await client.post(
        f"/api/suggestions/{se[0]['id']}/reject", json={"expected_plan_version": 2}
    )
    assert r.status_code == 409 and "already accepted" in r.json()["message"]

    de = next(s for s in body["suggestions"] if s["market_code"] == "DE")
    r = await client.post(f"/api/suggestions/{de['id']}/reject", json={"expected_plan_version": 1})
    assert r.status_code == 200
    assert r.json()["plan"]["start_date"] == "2026-05-01" and r.json()["plan"]["version"] == 2

    audit = (await client.get(f"/api/campaigns/{c['id']}/audit")).json()
    assert sorted((a["market_code"], a["verdict"]) for a in audit) == [
        ("DE", "rejected"),
        ("SE", "accepted"),
    ]
    assert all(a["decided_by"] == "demo.planner" for a in audit)


async def test_stale_version_is_409(client: httpx.AsyncClient) -> None:
    c = await make_campaign(client, ["DE"])
    body = (await client.post(f"/api/campaigns/{c['id']}/suggestions")).json()
    first, second = body["suggestions"][0], body["suggestions"][1]
    r = await client.post(
        f"/api/suggestions/{first['id']}/accept", json={"expected_plan_version": 1}
    )
    assert r.status_code == 200
    r = await client.post(
        f"/api/suggestions/{second['id']}/accept", json={"expected_plan_version": 1}
    )
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    audit = (await client.get(f"/api/campaigns/{c['id']}/audit")).json()
    assert len(audit) == 1


async def test_unknown_suggestion_404(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/suggestions/00000000-0000-0000-0000-000000000000/accept",
        json={"expected_plan_version": 1},
    )
    assert r.status_code == 404
