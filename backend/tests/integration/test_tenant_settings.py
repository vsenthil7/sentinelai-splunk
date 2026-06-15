"""Tenant self-service settings + BYO credentials API tests."""
from __future__ import annotations


class TestTenantSettings:
    async def test_get_settings(self, client, auth):
        resp = await client.get("/api/v1/tenant/settings", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "default"
        assert resp.json()["plan"] == "enterprise"

    async def test_update_settings_merge(self, client, auth):
        await client.put(
            "/api/v1/tenant/settings", json={"settings": {"theme": "dark"}}, headers=auth
        )
        resp = await client.put(
            "/api/v1/tenant/settings", json={"settings": {"tz": "UTC"}}, headers=auth
        )
        s = resp.json()["settings"]
        assert s["theme"] == "dark" and s["tz"] == "UTC"

    async def test_settings_admin_gated(self, client, make_user):
        analyst = await make_user("set-analyst", "analyst")
        resp = await client.get("/api/v1/tenant/settings", headers=analyst["headers"])
        assert resp.status_code == 403


class TestTenantCredentials:
    async def test_default_credentials_managed(self, client, auth):
        resp = await client.get("/api/v1/tenant/credentials", headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "managed"
        assert body["splunk_token_set"] is False

    async def test_set_byo_credentials_secret_write_only(self, client, auth):
        resp = await client.put(
            "/api/v1/tenant/credentials",
            json={
                "mode": "byo", "splunk_backend": "live",
                "splunk_host": "https://splunk.acme:8089", "splunk_token": "secret-xyz",
            },
            headers=auth,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "byo"
        assert body["splunk_host"] == "https://splunk.acme:8089"
        # Secret is reported as SET but the value is never returned anywhere.
        assert body["splunk_token_set"] is True
        assert "splunk_token" not in body
        assert "secret-xyz" not in resp.text

    async def test_invalid_mode_rejected(self, client, auth):
        resp = await client.put(
            "/api/v1/tenant/credentials", json={"mode": "weird"}, headers=auth
        )
        assert resp.status_code == 422

    async def test_invalid_backend_rejected(self, client, auth):
        resp = await client.put(
            "/api/v1/tenant/credentials", json={"splunk_backend": "telnet"}, headers=auth
        )
        assert resp.status_code == 422

    async def test_credentials_admin_gated(self, client, make_user):
        analyst = await make_user("cred-analyst", "analyst")
        resp = await client.get("/api/v1/tenant/credentials", headers=analyst["headers"])
        assert resp.status_code == 403

    async def test_byo_mock_still_runs_pipeline(self, client, auth):
        # Switch to BYO with mock backend; the pipeline must still work end-to-end.
        await client.put(
            "/api/v1/tenant/credentials",
            json={"mode": "byo", "splunk_backend": "mock", "ai_backend": "mock"},
            headers=auth,
        )
        run = await client.post("/api/v1/investigations/run", headers=auth)
        assert run.status_code == 200
        assert run.json()["total"] == 5

    async def test_credentials_update_audited(self, client, auth):
        await client.put(
            "/api/v1/tenant/credentials",
            json={"mode": "byo", "splunk_token": "zzz"}, headers=auth,
        )
        audit = await client.get("/api/v1/audit", headers=auth)
        actions = [e["action"] for e in audit.json()["entries"]]
        assert "tenant.credentials_updated" in actions
        # The secret value must never appear in the audit trail.
        assert "zzz" not in audit.text
