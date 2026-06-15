"""Investigation lifecycle, execution engine, case management, incidents."""
from __future__ import annotations


class TestPipeline:
    async def test_run_creates_investigations(self, client, auth):
        resp = await client.post("/api/v1/investigations/run", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_list_and_get(self, client, auth):
        await client.post("/api/v1/investigations/run", headers=auth)
        lst = await client.get("/api/v1/investigations", headers=auth)
        iid = lst.json()["investigations"][0]["id"]
        one = await client.get(f"/api/v1/investigations/{iid}", headers=auth)
        assert one.status_code == 200
        assert one.json()["id"] == iid

    async def test_get_missing(self, client, auth):
        resp = await client.get("/api/v1/investigations/NOPE", headers=auth)
        assert resp.status_code == 404

    async def test_filter_by_severity(self, client, auth):
        await client.post("/api/v1/investigations/run", headers=auth)
        resp = await client.get("/api/v1/investigations?severity=critical", headers=auth)
        assert resp.status_code == 200
        assert all(i["detection"]["severity"] == "critical" for i in resp.json()["investigations"])

    async def test_detections_run(self, client, auth):
        resp = await client.post("/api/v1/detections/run", headers=auth)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_enrichment_present(self, client, auth):
        run = await client.post("/api/v1/investigations/run", headers=auth)
        det = run.json()["investigations"][0]["detection"]
        assert "asset_criticality" in det["enrichment"]


class TestSearch:
    async def test_search_ok(self, client, auth):
        resp = await client.post(
            "/api/v1/search",
            json={"spl": "search index=auth failed authentication"},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["event_count"] == 12

    async def test_search_malformed(self, client, auth):
        resp = await client.post("/api/v1/search", json={"spl": "garbage"}, headers=auth)
        assert resp.status_code == 400

    async def test_search_empty(self, client, auth):
        resp = await client.post("/api/v1/search", json={"spl": "  "}, headers=auth)
        assert resp.status_code == 400


class TestExecution:
    async def _first_actionable(self, client, auth):
        run = await client.post("/api/v1/investigations/run", headers=auth)
        return next(i for i in run.json()["investigations"] if i["actions"])

    async def test_execute_requires_approval(self, client, auth):
        inv = await self._first_actionable(client, auth)
        resp = await client.post(
            f"/api/v1/investigations/{inv['id']}/execute",
            json={"action_index": 0},
            headers=auth,
        )
        assert resp.status_code == 409

    async def test_approve_then_execute(self, client, auth):
        inv = await self._first_actionable(client, auth)
        iid = inv["id"]
        ap = await client.post(
            f"/api/v1/investigations/{iid}/approve",
            json={"action_index": 0},
            headers=auth,
        )
        assert ap.json()["actions"][0]["requires_approval"] is False
        ex = await client.post(
            f"/api/v1/investigations/{iid}/execute",
            json={"action_index": 0},
            headers=auth,
        )
        assert ex.status_code == 200
        action = ex.json()["actions"][0]
        assert action["executed"] is True
        assert action["execution_status"] == "success"
        assert action["rollback_token"]
        assert ex.json()["detection"]["status"] == "contained"

    async def test_approve_bad_index(self, client, auth):
        inv = await self._first_actionable(client, auth)
        resp = await client.post(
            f"/api/v1/investigations/{inv['id']}/approve",
            json={"action_index": 99},
            headers=auth,
        )
        assert resp.status_code == 404

    async def test_approve_missing_investigation(self, client, auth):
        resp = await client.post(
            "/api/v1/investigations/NOPE/approve",
            json={"action_index": 0},
            headers=auth,
        )
        assert resp.status_code == 404


class TestCaseManagement:
    async def _iid(self, client, auth):
        run = await client.post("/api/v1/investigations/run", headers=auth)
        return run.json()["investigations"][0]["id"]

    async def test_legal_transition(self, client, auth):
        iid = await self._iid(client, auth)
        resp = await client.post(
            f"/api/v1/investigations/{iid}/status",
            json={"status": "contained"},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["detection"]["status"] == "contained"

    async def test_illegal_transition(self, client, auth):
        iid = await self._iid(client, auth)
        await client.post(
            f"/api/v1/investigations/{iid}/status",
            json={"status": "contained"},
            headers=auth,
        )
        resp = await client.post(
            f"/api/v1/investigations/{iid}/status",
            json={"status": "new"},
            headers=auth,
        )
        assert resp.status_code == 409

    async def test_invalid_status(self, client, auth):
        iid = await self._iid(client, auth)
        resp = await client.post(
            f"/api/v1/investigations/{iid}/status",
            json={"status": "bogus"},
            headers=auth,
        )
        assert resp.status_code == 422

    async def test_sla(self, client, auth):
        iid = await self._iid(client, auth)
        resp = await client.get(f"/api/v1/investigations/{iid}/sla", headers=auth)
        assert resp.status_code == 200
        assert "ack_elapsed_min" in resp.json()

    async def test_assign(self, client, auth):
        iid = await self._iid(client, auth)
        resp = await client.post(
            f"/api/v1/investigations/{iid}/assign",
            json={"assignee": "analyst"},
            headers=auth,
        )
        assert resp.json()["assignee"] == "analyst"

    async def test_notes(self, client, auth):
        iid = await self._iid(client, auth)
        add = await client.post(
            f"/api/v1/investigations/{iid}/notes",
            json={"body": "Looking into this"},
            headers=auth,
        )
        assert add.status_code == 200
        listed = await client.get(f"/api/v1/investigations/{iid}/notes", headers=auth)
        assert len(listed.json()) == 1
        assert listed.json()[0]["body"] == "Looking into this"


class TestIncidents:
    async def test_correlation(self, client, auth):
        await client.post("/api/v1/investigations/run", headers=auth)
        resp = await client.get("/api/v1/incidents", headers=auth)
        assert resp.status_code == 200
        incidents = resp.json()
        assert len(incidents) >= 1
        # Incidents are risk-ranked descending.
        scores = [i["risk_score"] for i in incidents]
        assert scores == sorted(scores, reverse=True)

    async def test_get_incident(self, client, auth):
        await client.post("/api/v1/investigations/run", headers=auth)
        incs = await client.get("/api/v1/incidents", headers=auth)
        iid = incs.json()[0]["id"]
        one = await client.get(f"/api/v1/incidents/{iid}", headers=auth)
        assert one.status_code == 200

    async def test_get_incident_missing(self, client, auth):
        resp = await client.get("/api/v1/incidents/NOPE", headers=auth)
        assert resp.status_code == 404
