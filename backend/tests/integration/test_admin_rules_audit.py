"""Admin user management, rule management, audit, notifications, system."""
from __future__ import annotations


class TestAdmin:
    async def test_list_users(self, client, auth):
        resp = await client.get("/api/v1/admin/users", headers=auth)
        assert resp.status_code == 200
        assert any(u["username"] == "analyst" for u in resp.json())

    async def test_create_user(self, client, auth):
        resp = await client.post(
            "/api/v1/admin/users",
            json={"username": "bob", "password": "password123", "role": "responder"},
            headers=auth,
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "responder"

    async def test_create_duplicate(self, client, auth):
        await client.post(
            "/api/v1/admin/users",
            json={"username": "dup", "password": "password123", "role": "analyst"},
            headers=auth,
        )
        resp = await client.post(
            "/api/v1/admin/users",
            json={"username": "dup", "password": "password123", "role": "analyst"},
            headers=auth,
        )
        assert resp.status_code == 409

    async def test_create_bad_role(self, client, auth):
        resp = await client.post(
            "/api/v1/admin/users",
            json={"username": "x", "password": "password123", "role": "king"},
            headers=auth,
        )
        assert resp.status_code == 422

    async def test_change_role(self, client, auth):
        created = await client.post(
            "/api/v1/admin/users",
            json={"username": "carol", "password": "password123", "role": "viewer"},
            headers=auth,
        )
        uid = created.json()["id"]
        resp = await client.put(
            f"/api/v1/admin/users/{uid}/role", json={"role": "analyst"}, headers=auth
        )
        assert resp.json()["role"] == "analyst"

    async def test_link_identity(self, client, auth):
        created = await client.post(
            "/api/v1/admin/users",
            json={"username": "dave", "password": "password123", "role": "analyst"},
            headers=auth,
        )
        uid = created.json()["id"]
        resp = await client.post(
            f"/api/v1/admin/users/{uid}/link-identity",
            json={"external_id": "okta|xyz"},
            headers=auth,
        )
        assert resp.json()["external_id"] == "okta|xyz"

    async def test_delete_user(self, client, auth):
        created = await client.post(
            "/api/v1/admin/users",
            json={"username": "erin", "password": "password123", "role": "viewer"},
            headers=auth,
        )
        uid = created.json()["id"]
        resp = await client.delete(f"/api/v1/admin/users/{uid}", headers=auth)
        assert resp.status_code == 204

    async def test_cannot_delete_self(self, client, auth, seeded):
        resp = await client.delete(
            f"/api/v1/admin/users/{seeded['admin_id']}", headers=auth
        )
        assert resp.status_code == 409

    async def test_delete_missing(self, client, auth):
        resp = await client.delete("/api/v1/admin/users/NOPE", headers=auth)
        assert resp.status_code == 404

    async def test_admin_gated(self, client, make_user):
        analyst = await make_user("a9", "analyst")
        resp = await client.get("/api/v1/admin/users", headers=analyst["headers"])
        assert resp.status_code == 403


class TestRules:
    async def test_list_rules(self, client, auth):
        resp = await client.get("/api/v1/rules", headers=auth)
        assert resp.status_code == 200
        assert len(resp.json()) == 5
        assert all(r["enabled"] for r in resp.json())

    async def test_mitre_coverage(self, client, auth):
        resp = await client.get("/api/v1/rules/mitre-coverage", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["total_rules"] == 5

    async def test_disable_rule_affects_pipeline(self, client, auth):
        await client.put("/api/v1/rules/R002", json={"enabled": False}, headers=auth)
        run = await client.post("/api/v1/investigations/run", headers=auth)
        titles = [i["detection"]["title"] for i in run.json()["investigations"]]
        assert not any("outbound network" in t for t in titles)

    async def test_toggle_unknown_rule(self, client, auth):
        resp = await client.put("/api/v1/rules/R999", json={"enabled": False}, headers=auth)
        assert resp.status_code == 404

    async def test_toggle_requires_admin(self, client, make_user):
        analyst = await make_user("a8", "analyst")
        resp = await client.put(
            "/api/v1/rules/R001", json={"enabled": False}, headers=analyst["headers"]
        )
        assert resp.status_code == 403


class TestAudit:
    async def test_audit_records_and_chain_valid(self, client, auth):
        await client.post("/api/v1/investigations/run", headers=auth)
        resp = await client.get("/api/v1/audit", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["chain_valid"] is True
        actions = [e["action"] for e in resp.json()["entries"]]
        assert "investigation.created" in actions
        assert "auth.login.success" in actions

    async def test_failed_login_audited(self, client, auth):
        await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "wrong", "tenant": "default"},
        )
        resp = await client.get("/api/v1/audit", headers=auth)
        actions = [e["action"] for e in resp.json()["entries"]]
        assert "auth.login.failed" in actions


class TestNotifications:
    async def test_high_risk_alerts(self, client, auth):
        await client.post("/api/v1/investigations/run", headers=auth)
        resp = await client.get("/api/v1/notifications", headers=auth)
        assert resp.status_code == 200
        events = [n["event"] for n in resp.json()["notifications"]]
        assert "investigation.high_risk" in events


class TestSystem:
    async def test_health(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_liveness(self, client):
        resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    async def test_readiness_ok(self, client):
        resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True
        assert resp.json()["checks"]["database"] is True

    async def test_readiness_degraded_when_splunk_down(self, client):
        from app.api import deps

        deps._splunk.set_healthy(False)  # type: ignore[attr-defined]
        try:
            resp = await client.get("/api/v1/health/ready")
            assert resp.status_code == 503
        finally:
            deps._splunk.set_healthy(True)  # type: ignore[attr-defined]

    async def test_metrics(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "sentinel_requests_total" in resp.text

    async def test_request_id_header(self, client):
        resp = await client.get("/api/v1/health")
        assert "x-request-id" in resp.headers

    async def test_ai_models_catalog(self, client, auth):
        resp = await client.get("/api/v1/ai/models", headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        # Security triage routes to the Foundation security model.
        assert body["task_routing"]["security_triage"] == "Foundation-Sec-1.1-8B-Instruct"
        ids = {m["model_id"] for m in body["catalog"]}
        assert "Foundation-Sec-1.1-8B-Instruct" in ids
        assert "Cisco-DeepTimeSeries" in ids

    async def test_ai_models_requires_auth(self, client):
        resp = await client.get("/api/v1/ai/models")
        assert resp.status_code == 401


class TestTenantStatus:
    async def test_suspended_tenant_blocks_login(self, client, sessionmaker_, seeded):
        from app.db.repositories import TenantRepository

        async with sessionmaker_() as s:
            await TenantRepository(s).set_status(seeded["tenant_id"], "suspended")
            await s.commit()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "sentinel-demo", "tenant": "default"},
        )
        assert resp.status_code == 403
        assert "suspended" in resp.json()["detail"].lower()

    async def test_suspended_tenant_blocks_existing_token(
        self, client, auth, sessionmaker_, seeded
    ):
        # auth fixture already logged in; now suspend and existing token must fail.
        from app.db.repositories import TenantRepository

        async with sessionmaker_() as s:
            await TenantRepository(s).set_status(seeded["tenant_id"], "suspended")
            await s.commit()
        resp = await client.get("/api/v1/investigations", headers=auth)
        assert resp.status_code == 403
