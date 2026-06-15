"""Provider plane (cross-tenant super-admin) tests.

The most important assertions are the negative ones: a tenant ADMIN must NOT be
able to reach any provider endpoint, proving the provider scope is isolated.
"""
from __future__ import annotations


class TestProviderTenantManagement:
    async def test_list_tenants(self, client, provider_auth):
        resp = await client.get("/api/v1/provider/tenants", headers=provider_auth)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "default" in names
        assert "__platform__" not in names  # platform tenant hidden

    async def test_create_tenant_with_admin(self, client, provider_auth):
        resp = await client.post(
            "/api/v1/provider/tenants",
            json={
                "name": "acme-corp", "plan": "pro", "status": "active",
                "admin_username": "acme-admin", "admin_password": "password123",
            },
            headers=provider_auth,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "acme-corp"
        assert resp.json()["user_count"] == 1
        # The new tenant's admin can log in.
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "acme-admin", "password": "password123", "tenant": "acme-corp"},
        )
        assert login.status_code == 200

    async def test_create_duplicate_tenant(self, client, provider_auth):
        await client.post(
            "/api/v1/provider/tenants",
            json={"name": "dup", "plan": "pro", "status": "active",
                  "admin_username": "a", "admin_password": "password123"},
            headers=provider_auth,
        )
        resp = await client.post(
            "/api/v1/provider/tenants",
            json={"name": "dup", "plan": "pro", "status": "active",
                  "admin_username": "b", "admin_password": "password123"},
            headers=provider_auth,
        )
        assert resp.status_code == 409

    async def test_create_tenant_invalid_plan(self, client, provider_auth):
        resp = await client.post(
            "/api/v1/provider/tenants",
            json={"name": "x", "plan": "ultra", "status": "active",
                  "admin_username": "a", "admin_password": "password123"},
            headers=provider_auth,
        )
        assert resp.status_code == 422

    async def test_suspend_and_reactivate(self, client, provider_auth, seeded):
        tid = seeded["tenant_id"]
        suspend = await client.put(
            f"/api/v1/provider/tenants/{tid}/status",
            json={"status": "suspended"}, headers=provider_auth,
        )
        assert suspend.status_code == 200
        assert suspend.json()["status"] == "suspended"
        # default tenant's user now blocked
        blocked = await client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "sentinel-demo", "tenant": "default"},
        )
        assert blocked.status_code == 403
        # reactivate
        react = await client.put(
            f"/api/v1/provider/tenants/{tid}/status",
            json={"status": "active"}, headers=provider_auth,
        )
        assert react.json()["status"] == "active"

    async def test_set_plan(self, client, provider_auth, seeded):
        resp = await client.put(
            f"/api/v1/provider/tenants/{seeded['tenant_id']}/plan",
            json={"plan": "free"}, headers=provider_auth,
        )
        assert resp.status_code == 200
        assert resp.json()["plan"] == "free"

    async def test_status_missing_tenant(self, client, provider_auth):
        resp = await client.put(
            "/api/v1/provider/tenants/NOPE/status",
            json={"status": "active"}, headers=provider_auth,
        )
        assert resp.status_code == 404

    async def test_status_invalid_value(self, client, provider_auth, seeded):
        resp = await client.put(
            f"/api/v1/provider/tenants/{seeded['tenant_id']}/status",
            json={"status": "frozen"}, headers=provider_auth,
        )
        assert resp.status_code == 422

    async def test_plan_invalid_value(self, client, provider_auth, seeded):
        resp = await client.put(
            f"/api/v1/provider/tenants/{seeded['tenant_id']}/plan",
            json={"plan": "diamond"}, headers=provider_auth,
        )
        assert resp.status_code == 422

    async def test_plan_missing_tenant(self, client, provider_auth):
        resp = await client.put(
            "/api/v1/provider/tenants/NOPE/plan",
            json={"plan": "pro"}, headers=provider_auth,
        )
        assert resp.status_code == 404

    async def test_create_tenant_invalid_status(self, client, provider_auth):
        resp = await client.post(
            "/api/v1/provider/tenants",
            json={"name": "z", "plan": "pro", "status": "frozen",
                  "admin_username": "a", "admin_password": "password123"},
            headers=provider_auth,
        )
        assert resp.status_code == 422

    async def test_impersonate_missing_tenant(self, client, provider_auth):
        resp = await client.post(
            "/api/v1/provider/tenants/NOPE/impersonate", headers=provider_auth
        )
        assert resp.status_code == 404

    async def test_impersonate_tenant_without_admin(
        self, client, provider_auth, sessionmaker_
    ):
        # Create a tenant with only a viewer (no admin) -> 404 on impersonate.
        from app.db.repositories import TenantRepository, UserRepository

        async with sessionmaker_() as s:
            t = await TenantRepository(s).create("noadmin", plan="pro")
            await UserRepository(s).create(t.id, "v", "password123", role="viewer")
            await s.commit()
            tid = t.id
        resp = await client.post(
            f"/api/v1/provider/tenants/{tid}/impersonate", headers=provider_auth
        )
        assert resp.status_code == 404

    async def test_list_all_users_cross_tenant(self, client, provider_auth):
        resp = await client.get("/api/v1/provider/users", headers=provider_auth)
        assert resp.status_code == 200
        # default tenant's analyst should be visible
        assert any(u["username"] == "analyst" for u in resp.json())

    async def test_impersonate(self, client, provider_auth, seeded):
        resp = await client.post(
            f"/api/v1/provider/tenants/{seeded['tenant_id']}/impersonate",
            headers=provider_auth,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant"] == "default"
        # The impersonation token works against tenant-scoped endpoints.
        token = {"Authorization": f"Bearer {body['access_token']}"}
        inv = await client.get("/api/v1/investigations", headers=token)
        assert inv.status_code == 200


class TestProviderIsolation:
    """Tenant admin must NOT reach the provider plane."""

    async def test_tenant_admin_cannot_list_tenants(self, client, auth):
        # `auth` is the default-tenant admin.
        resp = await client.get("/api/v1/provider/tenants", headers=auth)
        assert resp.status_code == 403

    async def test_tenant_admin_cannot_create_tenant(self, client, auth):
        resp = await client.post(
            "/api/v1/provider/tenants",
            json={"name": "sneaky", "plan": "pro", "status": "active",
                  "admin_username": "x", "admin_password": "password123"},
            headers=auth,
        )
        assert resp.status_code == 403

    async def test_tenant_admin_cannot_impersonate(self, client, auth, seeded):
        resp = await client.post(
            f"/api/v1/provider/tenants/{seeded['tenant_id']}/impersonate",
            headers=auth,
        )
        assert resp.status_code == 403

    async def test_analyst_cannot_reach_provider(self, client, make_user):
        analyst = await make_user("prov-test-analyst", "analyst")
        resp = await client.get("/api/v1/provider/tenants", headers=analyst["headers"])
        assert resp.status_code == 403

    async def test_provider_requires_auth(self, client):
        resp = await client.get("/api/v1/provider/tenants")
        assert resp.status_code == 401
