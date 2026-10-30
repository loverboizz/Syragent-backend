"""
Live Sandbox ERP/CRM Endpoints for Testing & Demonstrating Function Calling (ReAct).

Provides realistic in-memory Vietnamese enterprise data (E-Commerce Orders, Inventory Stock,
and Support Tickets) without polluting PostgreSQL with tenant business tables.
"""

import random
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agent import Agent
from app.models.agent_tool import AgentTool
from app.models.company import Company
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.service import Service
from app.models.user import User

router = APIRouter(prefix="/sandbox", tags=["Sandbox ERP (Demo Tools)"])

# ---------------------------------------------------------------------------
# 1. Sample Orders Dataset (In-Memory)
# ---------------------------------------------------------------------------
SAMPLE_ORDERS: dict[str, dict[str, Any]] = {
    "ORD-12345": {
        "order_id": "ORD-12345",
        "customer_name": "Nguyễn Văn An",
        "customer_phone": "0901234567",
        "items": [
            {
                "product_name": "iPhone 16 Pro Max 256GB Titan Tự Nhiên",
                "quantity": 1,
                "unit_price": "34.990.000 VNĐ",
            }
        ],
        "total_amount": "34.990.000 VNĐ",
        "payment_status": "PAID (Đã thanh toán qua VNPay)",
        "order_status": "IN_TRANSIT",
        "order_status_vi": "Đang vận chuyển",
        "carrier": "Giao Hàng Nhanh (GHN)",
        "tracking_code": "GHN88291044",
        "current_location": "Bưu cục trung chuyển Quận 7, TP. Hồ Chí Minh",
        "estimated_delivery": "28/10/2026 (Trước 17:00)",
        "note": "Shipper sẽ gọi trước 30 phút khi giao hàng.",
    },
    "ORD-67890": {
        "order_id": "ORD-67890",
        "customer_name": "Trần Thị Bích",
        "customer_phone": "0912345678",
        "items": [
            {
                "product_name": "MacBook Air M3 13 inch (16GB RAM / 512GB SSD)",
                "quantity": 1,
                "unit_price": "31.490.000 VNĐ",
            }
        ],
        "total_amount": "31.490.000 VNĐ",
        "payment_status": "PAID (Chuyển khoản ngân hàng)",
        "order_status": "DELIVERED",
        "order_status_vi": "Đã giao hàng thành công",
        "carrier": "Viettel Post",
        "tracking_code": "VTP99102311",
        "delivered_at": "25/10/2026 14:20",
        "warranty_until": "25/10/2027 (Bảo hành chính hãng Apple Việt Nam 12 tháng)",
        "note": "Khách hàng đã ký nhận và kiểm tra nguyên seal.",
    },
    "ORD-99999": {
        "order_id": "ORD-99999",
        "customer_name": "Lê Hoàng Nam",
        "customer_phone": "0987654321",
        "items": [
            {
                "product_name": "Tai nghe AirPods Pro 2 cổng USB-C",
                "quantity": 1,
                "unit_price": "5.790.000 VNĐ",
            }
        ],
        "total_amount": "5.790.000 VNĐ",
        "payment_status": "COD (Thanh toán khi nhận hàng)",
        "order_status": "PROCESSING",
        "order_status_vi": "Đang đóng gói tại kho",
        "carrier": "SPX Express",
        "tracking_code": "SPXVN0019283",
        "current_location": "Kho tổng Cầu Giấy, Hà Nội",
        "estimated_delivery": "29/10/2026",
        "note": "Đơn hàng đang chờ bàn giao cho đơn vị vận chuyển.",
    },
}

# ---------------------------------------------------------------------------
# 2. Sample Inventory Dataset (In-Memory)
# ---------------------------------------------------------------------------
SAMPLE_INVENTORY: list[dict[str, Any]] = [
    {
        "sku": "IP16PM-256-TN",
        "product_name": "iPhone 16 Pro Max 256GB Titan Tự Nhiên",
        "category": "Điện thoại",
        "price": "34.990.000 VNĐ",
        "in_stock": True,
        "stock_quantity": 18,
        "available_branches": [
            "Showroom Quận 1 (8 máy)",
            "Showroom Quận 7 (6 máy)",
            "Showroom Cầu Giấy - Hà Nội (4 máy)",
        ],
        "promotion": "Trả góp 0% lãi suất • Trợ giá 1.000.000đ khi thu cũ đổi mới",
        "warranty": "12 tháng chính hãng VN/A, 1 đổi 1 trong 30 ngày đầu",
    },
    {
        "sku": "MBA-M3-13-16-512",
        "product_name": "MacBook Air M3 13 inch 16GB/512GB",
        "category": "Laptop",
        "price": "31.490.000 VNĐ",
        "in_stock": True,
        "stock_quantity": 7,
        "available_branches": [
            "Showroom Quận 3 (4 máy)",
            "Showroom Đống Đa - Hà Nội (3 máy)",
        ],
        "promotion": "Tặng túi chống sốc cao cấp + Chuột không dây + Giảm 500.000đ cho Sinh viên",
        "warranty": "12 tháng chính hãng Apple Việt Nam",
    },
    {
        "sku": "APP2-USBC-2024",
        "product_name": "Tai nghe AirPods Pro 2 USB-C",
        "category": "Phụ kiện âm thanh",
        "price": "5.790.000 VNĐ",
        "in_stock": True,
        "stock_quantity": 42,
        "available_branches": ["Còn hàng tại tất cả 12 chi nhánh toàn quốc"],
        "promotion": "Giảm thêm 200.000đ khi mua kèm iPhone hoặc MacBook",
        "warranty": "12 tháng chính hãng",
    },
    {
        "sku": "S24U-512-TITAN",
        "product_name": "Samsung Galaxy S24 Ultra 512GB",
        "category": "Điện thoại",
        "price": "29.990.000 VNĐ",
        "in_stock": False,
        "stock_quantity": 0,
        "available_branches": [],
        "restock_eta": "Dự kiến về hàng lô mới vào ngày 02/11/2026",
        "promotion": "Đặt trước giảm ngay 1.500.000đ",
        "warranty": "12 tháng chính hãng Samsung Việt Nam",
    },
]


class CreateTicketPayload(BaseModel):
    order_id: str = Field(..., description="Mã đơn hàng liên quan")
    customer_phone: str | None = Field(default="Chưa cung cấp", description="Số điện thoại khách hàng")
    reason: str = Field(..., description="Nội dung yêu cầu hoàn tiền / bảo hành / khiếu nại")


@router.get(
    "/orders/{order_id}",
    summary="[Sandbox] Tra cứu thông tin & trạng thái đơn hàng theo mã",
)
async def sandbox_lookup_order(order_id: str):
    """
    Endpoint mẫu phục vụ test công cụ `lookup_order`.
    Mã đơn hàng có sẵn: ORD-12345, ORD-67890, ORD-99999.
    """
    normalized = order_id.strip().upper().lstrip("#")
    if not normalized.startswith("ORD-") and normalized.isdigit():
        normalized = f"ORD-{normalized}"

    if normalized in SAMPLE_ORDERS:
        return SAMPLE_ORDERS[normalized]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "message": f"Không tìm thấy đơn hàng có mã '{order_id}'.",
            "hint_sample_order_ids": list(SAMPLE_ORDERS.keys()),
        },
    )


@router.get(
    "/inventory/search",
    summary="[Sandbox] Kiểm tra tồn kho và giá bán sản phẩm",
)
async def sandbox_search_inventory(
    product_name: str = Query(default="", description="Tên sản phẩm hoặc mã SKU cần tra cứu"),
):
    """
    Endpoint mẫu phục vụ test công cụ `check_product_stock`.
    Từ khóa mẫu: iPhone 16, MacBook Air M3, AirPods Pro 2, Samsung S24.
    """
    q = product_name.strip().lower()
    if not q:
        return {
            "query": product_name,
            "total_matches": len(SAMPLE_INVENTORY),
            "products": SAMPLE_INVENTORY,
        }

    matches = [
        item
        for item in SAMPLE_INVENTORY
        if q in item["product_name"].lower()
        or q in item["sku"].lower()
        or q in item["category"].lower()
        or any(token in item["product_name"].lower() for token in q.split() if len(token) >= 2)
    ]

    return {
        "query": product_name,
        "total_matches": len(matches),
        "products": matches,
        "available_sample_keywords": ["iPhone 16", "MacBook Air M3", "AirPods Pro 2", "Samsung S24"],
    }


@router.post(
    "/tickets/create",
    status_code=status.HTTP_201_CREATED,
    summary="[Sandbox] Tạo phiếu yêu cầu bảo hành / hoàn tiền (Async Ticket Pattern)",
)
async def sandbox_create_ticket(payload: CreateTicketPayload):
    """
    Endpoint mẫu phục vụ test công cụ `create_support_ticket` (ASYNC_TICKET).
    Trả về mã phiếu chờ phê duyệt theo đúng mẫu Async Ticketing.
    """
    ticket_num = random.randint(1000, 9999)
    ticket_id = f"TCK-2026-{ticket_num}"

    return {
        "ticket_id": ticket_id,
        "status": "PENDING_APPROVAL",
        "status_vi": "Đang chờ bộ phận Bảo hành & CSKH phê duyệt",
        "order_id": payload.order_id.strip().upper(),
        "customer_phone": payload.customer_phone or "Chưa cung cấp",
        "reason": payload.reason,
        "assigned_department": "Phòng Bảo Hành & Đổi Trả (Tier-2 Support)",
        "sla_eta": "Nhân viên sẽ liên hệ xác nhận qua Zalo/SĐT trong vòng 2 giờ làm việc.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 4. Syragent Platform User Support Tools (Real PostgreSQL Queries)
# ---------------------------------------------------------------------------
@router.get(
    "/syragent/account-lookup",
    summary="[Syragent Support] Tra cứu tài khoản doanh nghiệp & danh sách dịch vụ theo Email/Tên công ty",
)
async def syragent_account_lookup(
    db: Annotated[AsyncSession, Depends(get_db)],
    keyword: str = Query(..., description="Email người dùng, tên công ty, hoặc mã dịch vụ cần tìm"),
):
    """
    Giúp Syragent Support Agent xác định người dùng đang trò chuyện là ai khi họ
    chưa đăng nhập hoặc hỏi về dịch vụ của công ty mình.
    """
    kw = keyword.strip()
    if not kw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Vui lòng cung cấp từ khóa tìm kiếm (Email, Tên công ty hoặc Mã dịch vụ).",
        )

    pattern = f"%{kw}%"

    # Find matching companies via Company.name, User.email, or Service.code/name
    stmt = (
        select(Company)
        .outerjoin(User, User.company_id == Company.id)
        .outerjoin(Service, Service.company_id == Company.id)
        .where(
            or_(
                Company.name.ilike(pattern),
                User.email.ilike(pattern),
                Service.code.ilike(pattern),
                Service.name.ilike(pattern),
            )
        )
        .distinct()
        .limit(5)
    )
    res = await db.execute(stmt)
    companies = res.scalars().all()

    if not companies:
        return {
            "found": False,
            "keyword": kw,
            "total_companies": 0,
            "accounts": [],
            "message": f"Không tìm thấy doanh nghiệp hoặc tài khoản nào khớp với từ khóa '{kw}'.",
        }

    accounts_data = []
    for comp in companies:
        u_res = await db.execute(select(User).where(User.company_id == comp.id))
        users = u_res.scalars().all()
        s_res = await db.execute(select(Service).where(Service.company_id == comp.id))
        services = s_res.scalars().all()

        accounts_data.append(
            {
                "company_id": str(comp.id),
                "company_name": comp.name,
                "admin_emails": [u.email for u in users],
                "services": [
                    {
                        "service_code": s.code,
                        "service_name": s.name,
                        "is_active": s.is_active,
                        "service_url": s.service_url,
                    }
                    for s in services
                ],
            }
        )

    return {
        "found": True,
        "keyword": kw,
        "total_companies": len(accounts_data),
        "accounts": accounts_data,
    }


@router.get(
    "/syragent/diagnose/{service_code}",
    summary="[Syragent Support] Chẩn đoán trạng thái kỹ thuật của Dịch vụ & AI Agent",
)
async def syragent_diagnose_service(
    service_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Truy vấn trực tiếp PostgreSQL của Syragent để kiểm tra sức khỏe cấu hình của một
    dịch vụ (service_code): trạng thái kích hoạt, tên miền whitelist, mô hình AI,
    số lượng đoạn tri thức RAG đã nạp, và số lượng công cụ Action Gateway.
    """
    clean_code = service_code.strip().lower()
    svc_res = await db.execute(select(Service).where(func.lower(Service.code) == clean_code))
    service = svc_res.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SERVICE_NOT_FOUND",
                "message": f"Không tìm thấy dịch vụ nào có mã '{service_code}' trên hệ thống Syragent.",
            },
        )

    comp_res = await db.execute(select(Company).where(Company.id == service.company_id))
    company = comp_res.scalar_one_or_none()

    agent_res = await db.execute(select(Agent).where(Agent.service_id == service.id))
    agent = agent_res.scalar_one_or_none()

    knowledge_chunks_count = 0
    knowledge_sources: list[str] = []
    active_tools_count = 0
    active_tools_list: list[dict[str, str]] = []
    health_warnings: list[str] = []

    if not service.is_active:
        health_warnings.append(
            "Dịch vụ đang ở trạng thái TẠM NGƯNG (is_active=False). Widget nhúng sẽ không phản hồi cho đến khi bật lại."
        )

    if not agent:
        health_warnings.append(
            "Dịch vụ chưa được khởi tạo cấu hình AI Agent. Vui lòng vào tab '1. Cấu Hình AI' và bấm Lưu cấu hình."
        )
    else:
        cnt_res = await db.execute(
            select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.agent_id == agent.id)
        )
        knowledge_chunks_count = cnt_res.scalar() or 0

        src_res = await db.execute(
            select(KnowledgeChunk.source)
            .where(KnowledgeChunk.agent_id == agent.id)
            .distinct()
        )
        knowledge_sources = [row[0] for row in src_res.all() if row[0]]

        if knowledge_chunks_count == 0:
            health_warnings.append(
                "AI Agent chưa có tài liệu tri thức RAG nào (0 đoạn vector). Hãy vào tab '2. Kho Tri Thức (RAG)' để tải lên file PDF/DOCX/TXT."
            )

        tools_res = await db.execute(
            select(AgentTool).where(
                AgentTool.agent_id == agent.id,
                AgentTool.is_active.is_(True),
            )
        )
        active_tools = tools_res.scalars().all()
        active_tools_count = len(active_tools)
        active_tools_list = [
            {
                "tool_name": t.name,
                "method": t.http_method.value if hasattr(t.http_method, "value") else str(t.http_method),
                "execution_mode": t.action_type.value if hasattr(t.action_type, "value") else str(t.action_type),
            }
            for t in active_tools
        ]

    status_summary = (
        "HOẠT ĐỘNG TỐT (HEALTHY)"
        if not health_warnings
        else f"CẦN CHÚ Ý ({len(health_warnings)} cảnh báo)"
    )

    return {
        "service_code": service.code,
        "service_name": service.name,
        "company_name": company.name if company else "Không xác định",
        "is_active": service.is_active,
        "whitelisted_service_url": service.service_url,
        "agent_configured": agent is not None,
        "llm_provider": agent.llm_provider if agent else None,
        "llm_model": agent.model_name if agent else None,
        "knowledge_chunks_count": knowledge_chunks_count,
        "knowledge_documents": knowledge_sources,
        "active_tools_count": active_tools_count,
        "active_tools": active_tools_list,
        "health_status": status_summary,
        "health_warnings": health_warnings,
    }


@router.get(
    "/syragent/embed-code/{service_code}",
    summary="[Syragent Support] Tạo mã nhúng Widget JS & hướng dẫn tích hợp cho Dịch vụ",
)
async def syragent_get_embed_code(
    service_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Trả về đoạn mã nhúng HTML <script> chuẩn xác theo mã dịch vụ của người dùng
    kèm lưu ý cấu hình CORS Domain Whitelist.
    """
    clean_code = service_code.strip().lower()
    svc_res = await db.execute(select(Service).where(func.lower(Service.code) == clean_code))
    service = svc_res.scalar_one_or_none()

    actual_code = service.code if service else clean_code
    whitelisted_url = service.service_url if service else "Chưa đăng ký (Cần khai báo URL website trong cấu hình dịch vụ)"

    script_tag = (
        f'<script src="https://syragent-backend.onrender.com/widget.js" '
        f'data-service="{actual_code}" defer></script>'
    )

    return {
        "service_code": actual_code,
        "service_exists_in_db": service is not None,
        "service_name": service.name if service else "Dịch vụ mẫu",
        "whitelisted_domain": whitelisted_url,
        "embed_script_html": script_tag,
        "integration_steps": [
            "Bước 1: Sao chép thẻ <script> bên trên và dán vào ngay trước thẻ đóng </body> trong file index.html hoặc layout gốc của website.",
            f"Bước 2: Đảm bảo tên miền website nhúng khớp với URL đã đăng ký trong dịch vụ ({whitelisted_url}) để không bị chặn bởi bộ lọc bảo mật CORS Whitelist.",
            "Bước 3: Tải lại trang web, bong bóng chat Syragent sẽ xuất hiện ở góc dưới màn hình.",
        ],
    }


class SandboxSampleTestRequest(BaseModel):
    tool_name: str = Field(..., description="Tên công cụ mẫu cần chạy thử")
    test_parameters: dict[str, Any] = Field(default_factory=dict, description="Tham số truyền vào để chạy thử")


@router.post(
    "/test-sample-tool",
    summary="[Sandbox] Chạy thử công cụ mẫu & mô phỏng luồng suy luận ReAct (Không lưu vào Agent)",
)
async def sandbox_test_sample_tool(
    payload: SandboxSampleTestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cho phép doanh nghiệp bấm chạy thử công cụ mẫu ngay trên giao diện để hiểu cách
    Action Gateway gọi API và cách AI Agent tổng hợp câu trả lời, hoàn toàn độc lập
    và KHÔNG thêm công cụ mẫu vào danh sách công cụ thực tế của AI Agent.
    """
    import time

    start_time = time.perf_counter()
    tool_name = payload.tool_name.strip()
    params = payload.test_parameters or {}

    try:
        if tool_name == "lookup_syragent_account":
            keyword = str(params.get("keyword", "")).strip() or "syragent"
            data = await syragent_account_lookup(db=db, keyword=keyword)
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            if data["found"]:
                first = data["accounts"][0]
                svc_codes = ", ".join(f"`{s['service_code']}` ({s['service_name']})" for s in first["services"]) or "Chưa có dịch vụ"
                ai_reply = (
                    f"Dạ em đã tìm thấy thông tin tài khoản doanh nghiệp **{first['company_name']}**:\n"
                    f"- **Email quản trị:** {', '.join(first['admin_emails'])}\n"
                    f"- **Danh sách dịch vụ (service_code):** {svc_codes}"
                )
            else:
                ai_reply = data["message"]
            return {
                "success": True,
                "status_code": 200,
                "response_time_ms": elapsed,
                "error": None,
                "data": data,
                "simulated_ai_reply": ai_reply,
            }

        elif tool_name == "check_syragent_service":
            service_code = str(params.get("service_code", "")).strip() or "syragent-agent"
            data = await syragent_diagnose_service(service_code=service_code, db=db)
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            warnings_txt = (
                "\n".join(f"  ⚠️ {w}" for w in data["health_warnings"])
                if data["health_warnings"]
                else "  ✅ Tất cả thông số cấu hình đều hoạt động tốt!"
            )
            ai_reply = (
                f"Dạ em đã kiểm tra kỹ thuật dịch vụ **`{data['service_code']}`** ({data['service_name']}):\n"
                f"- **Trạng thái:** {'Đang hoạt động' if data['is_active'] else 'Đang tạm ngưng'} | **Mô hình AI:** `{data['llm_model']}`\n"
                f"- **Kho tri thức RAG:** {data['knowledge_chunks_count']} đoạn vector ({len(data['knowledge_documents'])} tài liệu)\n"
                f"- **Công cụ ReAct đang bật:** {data['active_tools_count']} công cụ\n"
                f"- **Chẩn đoán:**\n{warnings_txt}"
            )
            return {
                "success": True,
                "status_code": 200,
                "response_time_ms": elapsed,
                "error": None,
                "data": data,
                "simulated_ai_reply": ai_reply,
            }

        elif tool_name == "get_widget_embed_code":
            service_code = str(params.get("service_code", "")).strip() or "syragent-agent"
            data = await syragent_get_embed_code(service_code=service_code, db=db)
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            ai_reply = (
                f"Dạ đây là mã nhúng Widget Chat cho dịch vụ **`{data['service_code']}`**:\n"
                f"```html\n{data['embed_script_html']}\n```\n"
                f"- **Domain được phép nhúng (Whitelist):** `{data['whitelisted_domain']}`"
            )
            return {
                "success": True,
                "status_code": 200,
                "response_time_ms": elapsed,
                "error": None,
                "data": data,
                "simulated_ai_reply": ai_reply,
            }

        elif tool_name == "lookup_order":
            order_id = str(params.get("order_id", "")).strip()
            if not order_id:
                return {
                    "success": False,
                    "status_code": 422,
                    "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "error": "Thiếu tham số bắt buộc: 'order_id'",
                    "data": None,
                    "simulated_ai_reply": None,
                }
            data = await sandbox_lookup_order(order_id)
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            ai_reply = (
                f"Dạ em đã kiểm tra đơn hàng **{data['order_id']}** của anh/chị **{data['customer_name']}**:\n"
                f"- **Trạng thái hiện tại:** {data['order_status_vi']} ({data['carrier']} - Mã vận đơn: `{data['tracking_code']}`)\n"
                f"- **Tổng thanh toán:** {data['total_amount']} ({data['payment_status']})\n"
                f"- **Ghi chú:** {data.get('note', '')}"
            )
            return {
                "success": True,
                "status_code": 200,
                "response_time_ms": elapsed,
                "error": None,
                "data": data,
                "simulated_ai_reply": ai_reply,
            }

        elif tool_name == "check_product_stock":
            product_name = str(params.get("product_name", "")).strip()
            data = await sandbox_search_inventory(product_name=product_name)
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            if data["total_matches"] > 0:
                first = data["products"][0]
                stock_text = (
                    f"Còn hàng ({first['stock_quantity']} sản phẩm)"
                    if first["in_stock"]
                    else f"Tạm hết hàng ({first.get('restock_eta', '')})"
                )
                ai_reply = (
                    f"Dạ đối với sản phẩm **{first['product_name']}** (Mã SKU: `{first['sku']}`):\n"
                    f"- **Giá bán niêm yết:** {first['price']}\n"
                    f"- **Tình trạng kho:** {stock_text}\n"
                    f"- **Ưu đãi đi kèm:** {first['promotion']}"
                )
            else:
                ai_reply = f"Dạ hiện tại hệ thống kho chưa tìm thấy sản phẩm khớp với từ khóa '{product_name}'."

            return {
                "success": True,
                "status_code": 200,
                "response_time_ms": elapsed,
                "error": None,
                "data": data,
                "simulated_ai_reply": ai_reply,
            }

        elif tool_name == "create_support_ticket":
            order_id = str(params.get("order_id", "")).strip()
            reason = str(params.get("reason", "")).strip()
            customer_phone = str(params.get("customer_phone", "0901234567")).strip()
            if not order_id or not reason:
                return {
                    "success": False,
                    "status_code": 422,
                    "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "error": "Thiếu tham số bắt buộc: 'order_id' hoặc 'reason'",
                    "data": None,
                    "simulated_ai_reply": None,
                }
            data = await sandbox_create_ticket(
                CreateTicketPayload(
                    order_id=order_id,
                    customer_phone=customer_phone,
                    reason=reason,
                )
            )
            elapsed = round((time.perf_counter() - start_time) * 1000, 2)
            ai_reply = (
                f"Dạ em đã khởi tạo thành công phiếu yêu cầu hỗ trợ bảo hành/đổi trả cho đơn hàng **{data['order_id']}**:\n"
                f"- **Mã phiếu hỗ trợ:** `{data['ticket_id']}`\n"
                f"- **Trạng thái:** {data['status_vi']} (`{data['status']}`)\n"
                f"- **Cam kết xử lý (SLA):** {data['sla_eta']}"
            )
            return {
                "success": True,
                "status_code": 201,
                "response_time_ms": elapsed,
                "error": None,
                "data": data,
                "simulated_ai_reply": ai_reply,
            }

        else:
            return {
                "success": False,
                "status_code": 400,
                "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
                "error": f"Công cụ mẫu '{tool_name}' không tồn tại trong Sandbox.",
                "data": None,
                "simulated_ai_reply": None,
            }

    except HTTPException as exc:
        elapsed = round((time.perf_counter() - start_time) * 1000, 2)
        err_msg = (
            exc.detail.get("message")
            if isinstance(exc.detail, dict)
            else str(exc.detail)
        )
        return {
            "success": False,
            "status_code": exc.status_code,
            "response_time_ms": elapsed,
            "error": err_msg,
            "data": exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail},
            "simulated_ai_reply": f"Dạ hệ thống kiểm tra không tìm thấy mã đơn hàng này ({err_msg}). Anh/chị vui lòng kiểm tra lại mã đơn giúp em nhé!",
        }


