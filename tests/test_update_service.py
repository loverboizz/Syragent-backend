"""
Integration test for Updating and Deactivating/Reactivating a Service.
"""

import asyncio
import httpx

BASE_URL = "http://localhost:8000"


async def test_update_service():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin_dashboard_test@gascolae.vn",
                "password": "SecurePass123!",
            },
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[PASS] Authenticated successfully as test admin")

        # 2. Get Services
        srv_res = await client.get("/api/v1/services/", headers=headers)
        assert srv_res.status_code == 200
        services = srv_res.json()
        assert len(services) > 0
        service = services[0]
        service_id = service["id"]
        original_name = service["name"]
        print(f"[PASS] Found service to test update: '{original_name}' ({service_id})")

        # 3. Update Service Name and URL via PATCH
        updated_name = original_name + " (Đã Cập Nhật 2026)"
        updated_url = "https://gascolae.vn/dich-vu-cap-nhat"
        patch_res = await client.patch(
            f"/api/v1/services/{service_id}",
            headers=headers,
            json={
                "name": updated_name,
                "service_url": updated_url,
            },
        )
        assert patch_res.status_code == 200, f"PATCH failed: {patch_res.text}"
        patch_data = patch_res.json()
        assert patch_data["name"] == updated_name
        assert patch_data["service_url"].rstrip("/") == updated_url.rstrip("/")
        print(f"[PASS] PATCH /api/v1/services/{service_id} updated name and URL successfully!")

        # 4. Verify via GET
        get_res = await client.get(f"/api/v1/services/{service_id}", headers=headers)
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["name"] == updated_name
        print("[PASS] GET /api/v1/services/{id} confirmed updated data in database")

        # 5. Soft-delete / Deactivate Service via DELETE
        del_res = await client.delete(f"/api/v1/services/{service_id}", headers=headers)
        assert del_res.status_code == 204
        print(f"[PASS] DELETE /api/v1/services/{service_id} soft-deactivated service (HTTP 204)")

        # Verify is_active is now False
        get_inactive = await client.get(f"/api/v1/services/{service_id}", headers=headers)
        assert get_inactive.status_code == 200
        assert get_inactive.json()["is_active"] is False
        print("[PASS] Verified service status is now inactive (is_active=False)")

        # 6. Re-activate Service via PATCH
        reactivate_res = await client.patch(
            f"/api/v1/services/{service_id}",
            headers=headers,
            json={"is_active": True, "name": original_name},
        )
        assert reactivate_res.status_code == 200
        assert reactivate_res.json()["is_active"] is True
        assert reactivate_res.json()["name"] == original_name
        print("[PASS] Re-activated service and restored original name!")

        print("\n[ALL TESTS PASS] Service update and deactivation/reactivation are 100% operational!")


if __name__ == "__main__":
    asyncio.run(test_update_service())

