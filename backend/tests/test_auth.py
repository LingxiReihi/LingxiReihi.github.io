async def test_login_success(client, admin_user):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["user"]["username"] == "admin"


async def test_login_wrong_password(client, admin_user):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["code"] == 40101


async def test_login_lockout_after_5_failures(client, admin_user):
    for _ in range(5):
        await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "wrong"})
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    assert r.status_code == 423
    body = r.json()
    assert body["code"] == 42300
    assert body["data"]["retry_after"] >= 1


async def test_me_requires_token(client, admin_user):
    r = await client.get("/api/v1/admin/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == 40100


async def test_me_with_token(client, admin_user):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    token = r.json()["data"]["access_token"]
    r2 = await client.get("/api/v1/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["data"]["username"] == "admin"


async def test_refresh(client, admin_user):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    refresh = r.json()["data"]["refresh_token"]
    r2 = await client.post("/api/v1/admin/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    assert r2.json()["data"]["access_token"]


async def test_change_password_invalidates_old_tokens(client, admin_user):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": "admin", "password": "test-pass-123"})
    token = r.json()["data"]["access_token"]
    r2 = await client.post("/api/v1/admin/auth/password",
                           json={"old_password": "test-pass-123", "new_password": "new-pass-456"},
                           headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    r3 = await client.get("/api/v1/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 401  # token_version 递增，旧 token 全端失效


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["code"] == 0
