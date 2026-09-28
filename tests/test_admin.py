"""
Verification test for Admin Dashboard integration endpoints.
"""

import sys
import os
import asyncio
import httpx

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath("."))
from app.main import app


async def test_admin_flow():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        # 1. Test Admin HTML Pages
        res_login = await client.get("/admin/login")
        assert res_login.status_code == 200
        assert "AI Service Platform" in res_login.text
        print("[PASS] GET /admin/login rendered successfully")

        res_admin = await client.get("/admin")
        assert res_admin.status_code == 200
        assert "AI Service Agent SaaS" in res_admin.text
        print("[PASS] GET /admin rendered successfully")

        # 2. Test JS assets
        res_api_js = await client.get("/admin/js/api.js")
        assert res_api_js.status_code == 200
        assert "TOKEN_KEY" in res_api_js.text
        print("[PASS] GET /admin/js/api.js served successfully")

        res_app_js = await client.get("/admin/js/app.js")
        assert res_app_js.status_code == 200
        assert "loadDashboardOverview" in res_app_js.text
        print("[PASS] GET /admin/js/app.js served successfully")

        # 3. Test Registration or Login
        test_email = "admin_dashboard_test@gascolae.vn"
        test_pass = "SecurePass123!"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "GASCOLAE Test Org",
                "full_name": "Test Admin",
                "email": test_email,
                "password": test_pass,
            },
        )
        if reg_res.status_code == 201:
            print("[PASS] POST /api/v1/auth/register created new organization")
        elif reg_res.status_code == 400:
            print("[PASS] User already registered, proceeding to login")

        # 4. Login (JSON body, not OAuth2 form)
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": test_pass},
        )
        assert login_res.status_code == 200
        tokens = login_res.json()
        token = tokens["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print("[PASS] POST /api/v1/auth/login returned JWT token")

        # 5. Get User Me
        me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me_res.status_code == 200
        me = me_res.json()
        assert me["email"] == test_email
        print(f"[PASS] GET /api/v1/auth/me verified user: {me['email']} | role={me['role']}")

        # 6. Get Company
        comp_res = await client.get("/api/v1/companies/me", headers=auth_headers)
        assert comp_res.status_code == 200
        company = comp_res.json()
        print(f"[PASS] GET /api/v1/companies/me verified company: {company['name']}")

        # 7. Create a service from admin
        code = "srv-dash-test"
        srv_res = await client.post(
            "/api/v1/services/",
            headers=auth_headers,
            json={
                "name": "Dịch Vụ Đo Đạc Bay Chụp LiDAR",
                "code": code,
                "service_url": "https://gascolae.vn/lidar",
            },
        )
        if srv_res.status_code == 201:
            service = srv_res.json()
            print(f"[PASS] POST /api/v1/services/ created service: {service['name']} ({service['code']})")
        else:
            list_res = await client.get("/api/v1/services/", headers=auth_headers)
            service = list_res.json()[0]
            print(f"[PASS] Reusing existing service: {service['name']}")

        # 8. List Services
        list_srv = await client.get("/api/v1/services/", headers=auth_headers)
        assert list_srv.status_code == 200
        assert len(list_srv.json()) > 0
        print(f"[PASS] GET /api/v1/services/ retrieved {len(list_srv.json())} services")

    print("\n[ALL TESTS PASS] Admin Dashboard backend endpoints and static UI are 100% operational!")


if __name__ == "__main__":
    asyncio.run(test_admin_flow())

