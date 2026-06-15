"""Quota enforcement integration tests."""
from __future__ import annotations


class TestQuotaEndpoint:
    async def test_quota_headroom(self, client, auth):
        resp = await client.get("/api/v1/tenant/quota", headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        # default tenant seeds as enterprise -> unlimited.
        assert body["plan"] == "enterprise"
        kinds = {q["kind"]: q for q in body["quotas"]}
        assert kinds["search"]["limit"] == -1

    async def test_quota_admin_gated(self, client, make_user):
        analyst = await make_user("quota-analyst", "analyst")
        resp = await client.get("/api/v1/tenant/quota", headers=analyst["headers"])
        assert resp.status_code == 403


class TestQuotaEnforcement:
    async def test_free_plan_blocks_when_exceeded(self, client, auth, sessionmaker_, seeded):
        # Put the default tenant on the free plan and pre-fill usage to the cap.
        from app.db.repositories import TenantRepository
        from app.services.metering import KIND_SEARCH, MeteringService

        async with sessionmaker_() as s:
            await TenantRepository(s).set_plan(seeded["tenant_id"], "free")
            # free plan = 100 searches/month; pre-load 100 to hit the limit.
            await MeteringService(s).record(seeded["tenant_id"], KIND_SEARCH, quantity=100)
            await s.commit()
        # Next run needs 5 searches but 0 remain -> 429.
        resp = await client.post("/api/v1/investigations/run", headers=auth)
        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "quota_exceeded"

    async def test_enterprise_never_blocked(self, client, auth, sessionmaker_, seeded):
        from app.db.repositories import TenantRepository
        from app.services.metering import KIND_SEARCH, MeteringService

        async with sessionmaker_() as s:
            await TenantRepository(s).set_plan(seeded["tenant_id"], "enterprise")
            await MeteringService(s).record(seeded["tenant_id"], KIND_SEARCH, quantity=1_000_000)
            await s.commit()
        resp = await client.post("/api/v1/investigations/run", headers=auth)
        assert resp.status_code == 200

    async def test_quota_reflects_usage(self, client, auth, sessionmaker_, seeded):
        # Switch to pro, run once, confirm quota 'used' increments.
        from app.db.repositories import TenantRepository

        async with sessionmaker_() as s:
            await TenantRepository(s).set_plan(seeded["tenant_id"], "pro")
            await s.commit()
        await client.post("/api/v1/investigations/run", headers=auth)
        resp = await client.get("/api/v1/tenant/quota", headers=auth)
        kinds = {q["kind"]: q for q in resp.json()["quotas"]}
        assert kinds["search"]["used"] >= 5
        assert kinds["search"]["limit"] == 10_000
