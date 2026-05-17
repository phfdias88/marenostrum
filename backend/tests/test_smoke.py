"""Smoke test: garante que conftest funciona antes de escrever testes reais."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_two_tenants_have_different_ids(tenant_a, tenant_b):
    a_tenant, _, _ = tenant_a
    b_tenant, _, _ = tenant_b
    assert a_tenant.slug == "alpha"
    assert b_tenant.slug == "bravo"
    assert a_tenant.id != b_tenant.id


def test_auth_helper_includes_bearer(auth_a):
    r = auth_a.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["tenant_slug"] == "alpha"
