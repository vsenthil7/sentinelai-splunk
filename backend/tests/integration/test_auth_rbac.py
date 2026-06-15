"""Auth, RBAC, and multi-tenant isolation tests."""
from __future__ import annotations

from app.db.repositories import TenantRepository, UserRepository


class TestAuth:
    async def test_login_success(self, client, seeded):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "sentinel-demo", "tenant": "default"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "admin"
        assert body["tenant"] == "default"
        assert body["access_token"]

    async def test_login_bad_password(self, client, seeded):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "wrong", "tenant": "default"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_tenant(self, client, seeded):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "sentinel-demo", "tenant": "ghost"},
        )
        assert resp.status_code == 401

    async def test_login_missing_field(self, client, seeded):
        resp = await client.post("/api/v1/auth/login", json={"username": "x"})
        assert resp.status_code == 422

    async def test_protected_without_token(self, client):
        resp = await client.post("/api/v1/search", json={"spl": "search x"})
        assert resp.status_code == 401

    async def test_protected_malformed_header(self, client):
        resp = await client.post(
            "/api/v1/search", json={"spl": "search x"}, headers={"Authorization": "Token z"}
        )
        assert resp.status_code == 401

    async def test_protected_bad_token(self, client):
        resp = await client.post(
            "/api/v1/search",
            json={"spl": "search x"},
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401

    async def test_logout_revokes_token(self, client, auth):
        # Token works first.
        assert (await client.get("/api/v1/investigations", headers=auth)).status_code == 200
        # Logout revokes it.
        assert (await client.post("/api/v1/auth/logout", headers=auth)).status_code == 204
        # Same token now rejected.
        after = await client.get("/api/v1/investigations", headers=auth)
        assert after.status_code == 401

    async def test_logout_audited(self, client, auth):
        await client.post("/api/v1/auth/logout", headers=auth)
        # Re-login to read audit (old token now revoked).
        relog = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "sentinel-demo", "tenant": "default"},
        )
        h = {"Authorization": f"Bearer {relog.json()['access_token']}"}
        audit = await client.get("/api/v1/audit", headers=h)
        assert "auth.logout" in [e["action"] for e in audit.json()["entries"]]


class TestRBAC:
    async def test_viewer_cannot_run(self, client, make_user):
        viewer = await make_user("v1", "viewer")
        resp = await client.post("/api/v1/investigations/run", headers=viewer["headers"])
        assert resp.status_code == 403

    async def test_viewer_can_read(self, client, make_user):
        viewer = await make_user("v2", "viewer")
        resp = await client.get("/api/v1/investigations", headers=viewer["headers"])
        assert resp.status_code == 200

    async def test_analyst_cannot_approve(self, client, make_user):
        analyst = await make_user("a1", "analyst")
        await client.post("/api/v1/investigations/run", headers=analyst["headers"])
        lst = await client.get("/api/v1/investigations", headers=analyst["headers"])
        iid = lst.json()["investigations"][0]["id"]
        resp = await client.post(
            f"/api/v1/investigations/{iid}/approve",
            json={"action_index": 0},
            headers=analyst["headers"],
        )
        assert resp.status_code == 403

    async def test_responder_can_approve(self, client, make_user):
        responder = await make_user("r1", "responder")
        run = await client.post("/api/v1/investigations/run", headers=responder["headers"])
        inv = next(i for i in run.json()["investigations"] if i["actions"])
        resp = await client.post(
            f"/api/v1/investigations/{inv['id']}/approve",
            json={"action_index": 0},
            headers=responder["headers"],
        )
        assert resp.status_code == 200

    async def test_non_admin_cannot_read_audit(self, client, make_user):
        analyst = await make_user("a2", "analyst")
        resp = await client.get("/api/v1/audit", headers=analyst["headers"])
        assert resp.status_code == 403


class TestTenantIsolation:
    async def test_cross_tenant_invisible(self, client, sessionmaker_, seeded):
        # Create a second tenant + admin.
        async with sessionmaker_() as s:
            globex = await TenantRepository(s).ensure("globex")
            await UserRepository(s).create(globex.id, "guser", "password123", role="admin")
            await s.commit()
        # Default-tenant analyst creates investigations.
        admin_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "sentinel-demo", "tenant": "default"},
        )
        ha = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        run = await client.post("/api/v1/investigations/run", headers=ha)
        default_iid = run.json()["investigations"][0]["id"]
        # Globex admin sees none of them.
        g_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "guser", "password": "password123", "tenant": "globex"},
        )
        hg = {"Authorization": f"Bearer {g_login.json()['access_token']}"}
        listed = await client.get("/api/v1/investigations", headers=hg)
        assert listed.json()["total"] == 0
        cross = await client.get(f"/api/v1/investigations/{default_iid}", headers=hg)
        assert cross.status_code == 404
