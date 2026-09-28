/**
 * Admin Dashboard - Main Application Controller
 * Handles tabs, modals, services CRUD, agent configuration,
 * knowledge base ingestion (PDF/Text RAG), and sub-admin management.
 */

// Global State
let currentUser = null;
let currentCompany = null;
let servicesList = [];
let selectedAgentId = null;
let selectedFile = null;

// ---------------------------------------------------------------------------
// 1. Initialization
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;

  try {
    // 1. Load User Profile & Company
    currentUser = await apiRequest("/api/v1/auth/me");
    currentCompany = await apiRequest("/api/v1/companies/me");

    // Populate Sidebar Info
    document.getElementById("sidebar-user-name").textContent = currentUser.full_name || currentUser.email;
    document.getElementById("sidebar-user-role").textContent = currentUser.role;
    document.getElementById("user-avatar-letter").textContent = (currentUser.full_name || currentUser.email)[0].toUpperCase();
    document.getElementById("sidebar-company-name").textContent = currentCompany.name || "Doanh Nghiệp";

    // Hide Sub-Admin tab if user is not SUPER_ADMIN
    if (currentUser.role !== "SUPER_ADMIN") {
      const usersNavBtn = document.getElementById("nav-users");
      if (usersNavBtn) usersNavBtn.style.display = "none";
    }

    // 2. Setup Drag & Drop Handlers
    initDropzone();

    // 3. Load initial dashboard view
    await loadDashboardOverview();
  } catch (err) {
    console.error("Initialization failed:", err);
  }
});

function logout() {
  if (confirm("Bạn có chắc chắn muốn đăng xuất khỏi Bảng điều khiển?")) {
    clearAuthSession();
  }
}

// ---------------------------------------------------------------------------
// 2. Tab Navigation
// ---------------------------------------------------------------------------
const TABS = ["overview", "services", "agents", "knowledge", "users"];
const TAB_TITLES = {
  overview: { title: "Tổng quan Hệ thống", subtitle: "Bảng chỉ số và hoạt động" },
  services: { title: "Quản lý Dịch vụ", subtitle: "Danh sách dịch vụ và mã nhúng widget" },
  agents: { title: "Cấu hình Trợ lý AI", subtitle: "Cấu hình gói cước, mô hình và khóa API bảo mật" },
  knowledge: { title: "Kho Tri thức & RAG", subtitle: "Tải lên tài liệu PDF, HTML và quản lý vector embeddings" },
  users: { title: "Phân quyền Nhân sự", subtitle: "Danh sách quản trị viên và tài khoản phụ" },
};

async function switchTab(targetTab) {
  TABS.forEach((tab) => {
    const navBtn = document.getElementById(`nav-${tab}`);
    const content = document.getElementById(`tab-content-${tab}`);

    if (tab === targetTab) {
      if (navBtn) {
        navBtn.className =
          "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all text-white bg-sky-600/20 border border-sky-500/30";
      }
      if (content) content.classList.remove("hidden");
    } else {
      if (navBtn) {
        navBtn.className =
          "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all text-slate-400 hover:text-white hover:bg-slate-800/60";
      }
      if (content) content.classList.add("hidden");
    }
  });

  // Update Header Bar
  const meta = TAB_TITLES[targetTab] || TAB_TITLES.overview;
  document.getElementById("topbar-title").textContent = meta.title;
  document.getElementById("topbar-subtitle").textContent = meta.subtitle;

  // Trigger Data Refresh for Tab
  if (targetTab === "overview") await loadDashboardOverview();
  else if (targetTab === "services") await loadServicesTab();
  else if (targetTab === "agents") await loadAgentsTab();
  else if (targetTab === "knowledge") await loadKnowledgeTab();
  else if (targetTab === "users") await loadUsersTab();
}

// ---------------------------------------------------------------------------
// 3. Tab: Overview
// ---------------------------------------------------------------------------
async function loadDashboardOverview() {
  try {
    const services = await apiRequest("/api/v1/services/");
    servicesList = services;

    document.getElementById("stat-services-count").textContent = services.length;

    let activeAgents = 0;
    services.forEach((s) => {
      if (s.agent) activeAgents++;
    });
    document.getElementById("stat-agents-count").textContent = activeAgents;

    // Render Recent Services Table in Overview
    const tbody = document.getElementById("overview-services-tbody");
    if (!services || services.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="px-6 py-8 text-center text-slate-400">Chưa có dịch vụ nào được tạo. Hãy bấm "+ Tạo Dịch Vụ Mới"!</td></tr>`;
      return;
    }

    let totalChunks = 0;
    tbody.innerHTML = services
      .map((s) => {
        const tier = s.agent ? s.agent.ai_tier : "N/A";
        const tierBadge =
          tier === "FREE"
            ? `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">FREE</span>`
            : tier === "BYOK"
              ? `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">BYOK</span>`
              : `<span class="text-slate-400 text-xs">—</span>`;

        const statusBadge = s.is_active
          ? `<span class="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600"><span class="w-2 h-2 rounded-full bg-emerald-500"></span>Hoạt động</span>`
          : `<span class="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400"><span class="w-2 h-2 rounded-full bg-slate-300"></span>Tạm dừng</span>`;

        return `
        <tr class="hover:bg-slate-50/80 transition-colors">
          <td class="px-6 py-4 font-semibold text-slate-800">${s.name}</td>
          <td class="px-6 py-4 font-mono text-xs text-sky-700 font-medium">${s.code}</td>
          <td class="px-6 py-4">${tierBadge}</td>
          <td class="px-6 py-4">${statusBadge}</td>
          <td class="px-6 py-4 text-right">
            <button onclick="openEmbedModal('${s.code}', '${s.name.replace(/'/g, "\\'")}')"
              class="px-3 py-1.5 bg-slate-100 hover:bg-sky-50 text-slate-700 hover:text-sky-700 text-xs font-semibold rounded-lg border border-slate-200 transition-all inline-flex items-center gap-1">
              <span>Lấy mã nhúng</span> &rarr;
            </button>
          </td>
        </tr>
      `;
      })
      .join("");

    // Calculate chunks across agents
    for (const s of services) {
      if (s.agent && s.agent.id) {
        try {
          const chunks = await apiRequest(`/api/v1/agents/${s.agent.id}/documents`);
          totalChunks += chunks.length;
        } catch { }
      }
    }
    document.getElementById("stat-chunks-count").textContent = totalChunks;
  } catch (err) {
    console.error("Error loading overview:", err);
  }
}

// ---------------------------------------------------------------------------
// 4. Tab: Services Management
// ---------------------------------------------------------------------------
async function loadServicesTab() {
  try {
    const services = await apiRequest("/api/v1/services/");
    servicesList = services;

    const tbody = document.getElementById("services-list-tbody");
    if (!services || services.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-400">Doanh nghiệp chưa có dịch vụ nào.</td></tr>`;
      return;
    }

    tbody.innerHTML = services
      .map((s) => {
        const tier = s.agent ? s.agent.ai_tier : "Chưa có";
        const tierBadge =
          tier === "FREE"
            ? `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">FREE (Gemini)</span>`
            : tier === "BYOK"
              ? `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">BYOK (${s.agent.model_name || "Custom"})</span>`
              : `<span class="text-slate-400 text-xs">Chưa tạo Agent</span>`;

        const statusBadge = s.is_active
          ? `<span class="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600"><span class="w-2 h-2 rounded-full bg-emerald-500"></span>Hoạt động</span>`
          : `<span class="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400"><span class="w-2 h-2 rounded-full bg-slate-300"></span>Tạm dừng</span>`;

        return `
        <tr class="hover:bg-slate-50/80 transition-colors">
          <td class="px-6 py-4">
            <div class="font-bold text-slate-800">${s.name}</div>
            <div class="text-xs text-slate-400">Tạo ngày: ${formatDate(s.created_at)}</div>
          </td>
          <td class="px-6 py-4 font-mono text-xs font-bold text-sky-700">${s.code}</td>
          <td class="px-6 py-4 text-xs text-slate-600 truncate max-w-[180px]" title="${s.service_url}">${s.service_url}</td>
          <td class="px-6 py-4">${tierBadge}</td>
          <td class="px-6 py-4">${statusBadge}</td>
          <td class="px-6 py-4 text-right whitespace-nowrap">
            <div class="relative inline-block text-left">
              <button type="button" onclick="toggleActionDropdown(event, '${s.id}')"
                class="w-8 h-8 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 inline-flex items-center justify-center transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500/20"
                title="Thao tác">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                </svg>
              </button>
              <div id="action-menu-${s.id}"
                class="action-dropdown-menu absolute right-0 top-full mt-1.5 w-52 bg-white rounded-xl shadow-2xl border border-slate-200 py-1.5 z-50 text-left hidden divide-y divide-slate-100">
                <div class="py-1">
                  <button type="button" onclick="closeAllActionDropdowns(); openEditServiceModal('${s.id}')"
                    class="w-full px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors">
                    <span>✏️</span> Chỉnh sửa dịch vụ
                  </button>
                  <button type="button" onclick="closeAllActionDropdowns(); openEmbedModal('${s.code}')"
                    class="w-full px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors">
                    <span>&lt;/&gt;</span> Lấy mã nhúng Widget
                  </button>
                </div>
                <div class="py-1">
                  <button type="button" onclick="closeAllActionDropdowns(); goToAgentConfig('${s.id}')"
                    class="w-full px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors">
                    <span>🤖</span> Cấu hình Trợ lý AI
                  </button>
                  <button type="button" onclick="closeAllActionDropdowns(); goToKnowledge('${s.id}')"
                    class="w-full px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors">
                    <span>📚</span> Nạp & Quản lý tri thức
                  </button>
                </div>
                <div class="py-1">
                  ${s.is_active
            ? `<button type="button" onclick="closeAllActionDropdowns(); toggleServiceStatus('${s.id}', true)"
                          class="w-full px-3.5 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 flex items-center gap-2.5 transition-colors">
                          <span>⏸️</span> Tạm dừng dịch vụ
                        </button>`
            : `<button type="button" onclick="closeAllActionDropdowns(); toggleServiceStatus('${s.id}', false)"
                          class="w-full px-3.5 py-2 text-xs font-semibold text-emerald-600 hover:bg-emerald-50 flex items-center gap-2.5 transition-colors">
                          <span>▶️</span> Kích hoạt lại dịch vụ
                        </button>`
          }
                </div>
              </div>
            </div>
          </td>
        </tr>
      `;
      })
      .join("");
  } catch (err) {
    showToast(err.message || "Không thể tải danh sách dịch vụ", "error");
  }
}

// Modal: Create Service
function openCreateServiceModal() {
  document.getElementById("modal-service").classList.remove("hidden");
  document.getElementById("modal-service-title").textContent = "Thêm Dịch Vụ Mới";
  document.getElementById("service-id-input").value = "";
  document.getElementById("service-name-input").value = "";
  document.getElementById("service-code-input").value = "";
  document.getElementById("service-url-input").value = "http://localhost:8000";
  document.getElementById("service-status-container").classList.add("hidden");
  document.getElementById("submit-service-btn-text").textContent = "Tạo Dịch Vụ & Trợ Lý AI";
  document.getElementById("modal-service").classList.remove("hidden");
}

// Modal: Edit Service
async function openEditServiceModal(serviceId) {
  try {
    const service = await apiRequest(`/api/v1/services/${serviceId}`);
    if (!service) return;

    document.getElementById("modal-service-title").textContent = `Chỉnh Sửa: ${service.name}`;
    document.getElementById("service-id-input").value = service.id;
    document.getElementById("service-name-input").value = service.name;
    document.getElementById("service-code-input").value = service.code;
    document.getElementById("service-url-input").value = service.service_url;
    document.getElementById("service-status-input").checked = service.is_active;
    document.getElementById("service-status-container").classList.remove("hidden");
    document.getElementById("submit-service-btn-text").textContent = "Lưu Cập Nhật";
    document.getElementById("modal-service").classList.remove("hidden");
  } catch (err) {
    showToast(err.message || "Không thể tải thông tin dịch vụ", "error");
  }
}

// Toggle Service Status: Deactivate / Reactivate
async function toggleServiceStatus(serviceId, currentActive, serviceName) {
  if (!serviceName) {
    const s = servicesList.find((item) => item.id === serviceId);
    serviceName = s ? s.name : "dịch vụ này";
  }

  const newStatus = !currentActive;
  const actionText = newStatus ? "kích hoạt lại" : "tạm dừng";
  const confirmMsg = newStatus
    ? `Bạn có chắc muốn kích hoạt lại dịch vụ "${serviceName}" không?\nChat Widget trên website sẽ bắt đầu phục vụ khách hàng trở lại.`
    : `Bạn có chắc muốn tạm dừng dịch vụ "${serviceName}" không?\nKhi tạm dừng, Chat Widget trên website sẽ ngưng phục vụ khách hàng.`;

  if (!confirm(confirmMsg)) {
    return;
  }

  try {
    if (newStatus) {
      // Re-activate via PATCH
      await apiRequest(`/api/v1/services/${serviceId}`, {
        method: "PATCH",
        json: { is_active: true },
      });
      showToast(`Đã kích hoạt lại dịch vụ "${serviceName}" thành công!`, "success");
    } else {
      // Deactivate via DELETE
      await apiRequest(`/api/v1/services/${serviceId}`, { method: "DELETE" });
      showToast(`Đã tạm dừng dịch vụ "${serviceName}"!`, "success");
    }
    await loadServicesTab();
    await loadDashboardOverview();
  } catch (err) {
    showToast(err.message || `Lỗi khi ${actionText} dịch vụ`, "error");
  }
}

// Backward compatibility alias
function deleteService(serviceId, serviceName) {
  toggleServiceStatus(serviceId, true, serviceName);
}

// Dropdown menu toggle for table actions
function toggleActionDropdown(event, serviceId) {
  event.stopPropagation();
  const menu = document.getElementById(`action-menu-${serviceId}`);
  const isAlreadyOpen = menu && !menu.classList.contains("hidden");
  closeAllActionDropdowns();
  if (menu && !isAlreadyOpen) {
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;

    if (spaceBelow < 250) {
      menu.classList.remove("top-full", "mt-1.5");
      menu.classList.add("bottom-full", "mb-1.5");
    } else {
      menu.classList.remove("bottom-full", "mb-1.5");
      menu.classList.add("top-full", "mt-1.5");
    }

    menu.classList.remove("hidden");
  }
}

function closeAllActionDropdowns() {
  document.querySelectorAll(".action-dropdown-menu").forEach((el) => {
    el.classList.add("hidden");
  });
}

document.addEventListener("click", () => {
  closeAllActionDropdowns();
});

document.getElementById("create-service-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const editId = document.getElementById("service-id-input").value;
  const name = document.getElementById("service-name-input").value.trim();
  const code = document.getElementById("service-code-input").value.trim().toLowerCase();
  const service_url = document.getElementById("service-url-input").value.trim();
  const is_active = document.getElementById("service-status-input").checked;
  const btn = document.getElementById("submit-service-btn");
  const btnText = document.getElementById("submit-service-btn-text");

  btn.disabled = true;
  const originalText = btnText.textContent;
  btnText.textContent = editId ? "Đang lưu..." : "Đang tạo...";

  try {
    if (editId) {
      // 1. UPDATE Existing Service
      await apiRequest(`/api/v1/services/${editId}`, {
        method: "PATCH",
        json: { name, code, service_url, is_active },
      });
      showToast(`Đã cập nhật dịch vụ "${name}" thành công!`, "success");
    } else {
      // 2. CREATE New Service
      const newService = await apiRequest("/api/v1/services/", {
        method: "POST",
        json: { name, code, service_url },
      });

      // Automatically initialize a default FREE Agent for this service
      try {
        await apiRequest("/api/v1/agents/", {
          method: "POST",
          json: {
            service_id: newService.id,
            llm_provider: "google",
            ai_tier: "FREE",
            model_name: "models/gemini-3.6-flash",
          },
        });
      } catch { }

      showToast(`Đã tạo thành công dịch vụ "${name}"!`, "success");
    }

    closeModal("modal-service");
    await loadServicesTab();
    await loadDashboardOverview();
  } catch (err) {
    showToast(err.message || "Thao tác thất bại. Vui lòng kiểm tra lại thông tin.", "error");
  } finally {
    btn.disabled = false;
    btnText.textContent = originalText;
  }
});

// Modal: Embed Code
function openEmbedModal(serviceCode, serviceName) {
  if (!serviceName) {
    const s = servicesList.find((item) => item.code === serviceCode || item.id === serviceCode);
    if (s) {
      serviceName = s.name;
      serviceCode = s.code;
    }
  }
  const modal = document.getElementById("modal-embed");
  document.getElementById("embed-modal-service-name").textContent = `Dịch vụ: ${serviceName || serviceCode} (${serviceCode})`;

  const origin = window.location.origin;
  const scriptTag = `<!-- AI Service Agent Embeddable Chat Widget -->\n<script src="${origin}/widget.js" data-service="${serviceCode}"></script>`;
  document.getElementById("embed-code-textarea").value = scriptTag;

  modal.classList.remove("hidden");
}

function copyEmbedCode() {
  const textarea = document.getElementById("embed-code-textarea");
  textarea.select();
  navigator.clipboard.writeText(textarea.value);

  const btnText = document.getElementById("embed-copy-text");
  const original = btnText.textContent;
  btnText.textContent = "Đã Sao Chép Vào Clipboard! ✓";
  showToast("Đã sao chép mã nhúng thành công! Dán vào trước thẻ </body> của website.", "success");

  setTimeout(() => {
    btnText.textContent = original;
  }, 2500);
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.add("hidden");
}

function goToAgentConfig(serviceId) {
  switchTab("agents");
  setTimeout(() => {
    const select = document.getElementById("agent-config-service-select");
    if (select) {
      select.value = serviceId;
      onServiceSelectForAgent(serviceId);
    }
  }, 100);
}

function goToKnowledge(serviceId) {
  switchTab("knowledge");
  setTimeout(() => {
    const select = document.getElementById("knowledge-service-select");
    if (select) {
      select.value = serviceId;
      onKnowledgeServiceChange(serviceId);
    }
  }, 100);
}

// ---------------------------------------------------------------------------
// 5. Tab: AI Agent Configuration
// ---------------------------------------------------------------------------
async function loadAgentsTab() {
  try {
    const services = await apiRequest("/api/v1/services/");
    servicesList = services;

    const select = document.getElementById("agent-config-service-select");
    if (!services || services.length === 0) {
      select.innerHTML = `<option value="">Chưa có dịch vụ nào. Hãy tạo dịch vụ trước.</option>`;
      return;
    }

    select.innerHTML = services.map((s) => `<option value="${s.id}">${s.name} (${s.code})</option>`).join("");

    // Load config for first service
    await onServiceSelectForAgent(services[0].id);
  } catch (err) {
    showToast("Lỗi khi tải thông tin cấu hình AI", "error");
  }
}

async function onServiceSelectForAgent(serviceId) {
  if (!serviceId) return;

  try {
    const service = await apiRequest(`/api/v1/services/${serviceId}`);
    let agent = service ? service.agent : null;

    if (!agent) {
      // Create agent if not exists
      const created = await apiRequest("/api/v1/agents/", {
        method: "POST",
        json: {
          service_id: serviceId,
          llm_provider: "google",
          model_name: "models/gemini-3.6-flash",
          ai_tier: "FREE",
        },
      });
      agent = created;
      if (service) service.agent = created;
    }

    const currentAgent = agent;
    selectedAgentId = currentAgent.id;
    document.getElementById("agent-config-id").value = currentAgent.id;

    if (currentAgent.ai_tier === "BYOK") {
      document.getElementById("tier-byok").checked = true;
      toggleBYOKFields(true);
      document.getElementById("agent-provider").value = currentAgent.llm_provider || "google";
      document.getElementById("agent-model-name").value = currentAgent.model_name || "gemini-3.6-flash";
      document.getElementById("agent-api-key").value = "";
      document.getElementById("agent-api-key").placeholder = "•••••••••••• (Đã có khóa bảo mật trong DB, nhập mới để đổi)";
    } else {
      document.getElementById("tier-free").checked = true;
      toggleBYOKFields(false);
      document.getElementById("agent-model-name").value = "gemini-3.6-flash";
    }
  } catch (err) {
    showToast(err.message || "Lỗi tải cấu hình Agent", "error");
  }
}

function toggleBYOKFields(isByok) {
  const container = document.getElementById("byok-details-container");
  if (isByok) {
    container.classList.remove("hidden");
  } else {
    container.classList.add("hidden");
  }
}

function toggleApiKeyMask() {
  const input = document.getElementById("agent-api-key");
  input.type = input.type === "password" ? "text" : "password";
}

document.getElementById("agent-config-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const agentId = document.getElementById("agent-config-id").value;
  if (!agentId) return;

  const ai_tier = document.querySelector('input[name="ai_tier"]:checked').value;
  const btn = document.getElementById("save-agent-btn");

  const payload = {
    ai_tier: ai_tier,
  };

  if (ai_tier === "BYOK") {
    payload.llm_provider = document.getElementById("agent-provider").value;
    payload.model_name = document.getElementById("agent-model-name").value.trim() || "gemini-3.6-flash";
    const key = document.getElementById("agent-api-key").value.trim();
    if (key) {
      payload.api_key = key;
    }
  } else {
    payload.model_name = "gemini-3.6-flash";
  }

  btn.disabled = true;
  btn.textContent = "Đang lưu...";

  try {
    await apiRequest(`/api/v1/agents/${agentId}`, {
      method: "PATCH",
      json: payload,
    });
    showToast("Đã cập nhật cấu hình AI Agent thành công!", "success");
    await loadServicesTab();
  } catch (err) {
    showToast(err.message || "Không thể cập nhật cấu hình Agent", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>Lưu Cấu Hình AI</span>`;
  }
});

// ---------------------------------------------------------------------------
// 6. Tab: Knowledge Base & RAG Ingestion
// ---------------------------------------------------------------------------
async function loadKnowledgeTab() {
  try {
    const services = await apiRequest("/api/v1/services/");
    servicesList = services;

    const select = document.getElementById("knowledge-service-select");
    if (!services || services.length === 0) {
      select.innerHTML = `<option value="">Chưa có dịch vụ nào</option>`;
      return;
    }

    select.innerHTML = services.map((s) => `<option value="${s.id}">${s.name} (${s.code})</option>`).join("");
    await onKnowledgeServiceChange(services[0].id);
  } catch (err) {
    showToast("Lỗi khi tải kho tri thức", "error");
  }
}

async function onKnowledgeServiceChange(serviceId) {
  if (!serviceId) return;
  try {
    const service = await apiRequest(`/api/v1/services/${serviceId}`);
    if (!service) {
      document.getElementById("chunks-tbody").innerHTML = `<tr><td colspan="5" class="px-6 py-6 text-center text-slate-400">Không tìm thấy thông tin dịch vụ.</td></tr>`;
      selectedAgentId = null;
      return;
    }

    let agent = service.agent;
    if (!agent) {
      // Auto-create agent if service doesn't have one yet
      try {
        const created = await apiRequest("/api/v1/agents/", {
          method: "POST",
          json: {
            service_id: serviceId,
            llm_provider: "google",
            model_name: "models/gemini-3.6-flash",
            ai_tier: "FREE",
          },
        });
        agent = created;
      } catch (agentErr) {
        document.getElementById("chunks-tbody").innerHTML = `<tr><td colspan="5" class="px-6 py-6 text-center text-slate-400">Dịch vụ này chưa có Trợ lý AI. Vui lòng vào tab 'Cấu hình Trợ lý AI' để kích hoạt.</td></tr>`;
        selectedAgentId = null;
        return;
      }
    }

    selectedAgentId = agent.id;
    await loadAgentChunks(selectedAgentId);
  } catch (err) {
    selectedAgentId = null;
    document.getElementById("chunks-tbody").innerHTML = `<tr><td colspan="5" class="px-6 py-6 text-center text-rose-500">Lỗi khi tải tri thức: ${err.message}</td></tr>`;
  }
}

async function loadAgentChunks(agentId) {
  const tbody = document.getElementById("chunks-tbody");
  tbody.innerHTML = `<tr><td colspan="5" class="px-6 py-6 text-center text-slate-400">Đang truy vấn Supabase pgvector...</td></tr>`;

  try {
    const chunks = await apiRequest(`/api/v1/agents/${agentId}/documents`);
    if (!chunks || chunks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="px-6 py-8 text-center text-slate-400">Chưa có đoạn tri thức nào. Hãy tải file hoặc nhập văn bản ở trên!</td></tr>`;
      return;
    }

    tbody.innerHTML = chunks
      .map(
        (c, idx) => `
      <tr class="hover:bg-slate-50/80 transition-colors">
        <td class="px-6 py-4 font-mono text-xs text-slate-400">${idx + 1}</td>
        <td class="px-6 py-4 text-xs font-semibold text-sky-800 truncate max-w-[160px]" title="${c.source || "—"}">
          📄 ${c.source || "Trực tiếp"}
        </td>
        <td class="px-6 py-4 text-xs text-slate-700">
          <div class="line-clamp-2 max-w-xl font-normal leading-relaxed">${escapeHtml(c.content)}</div>
        </td>
        <td class="px-6 py-4 text-xs text-slate-400 whitespace-nowrap">${formatDate(c.created_at)}</td>
        <td class="px-6 py-4 text-right">
          <button onclick="deleteChunk('${agentId}', '${c.id}')"
            class="text-slate-400 hover:text-rose-600 p-1.5 rounded-lg hover:bg-rose-50 transition-colors" title="Xóa đoạn này">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="px-6 py-6 text-center text-rose-500">Lỗi khi tải tri thức: ${err.message}</td></tr>`;
  }
}

// Drag & Drop
function initDropzone() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");

  if (!dropzone || !fileInput) return;

  dropzone.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("border-sky-500", "bg-sky-50/40");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("border-sky-500", "bg-sky-50/40");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("border-sky-500", "bg-sky-50/40");
    if (e.dataTransfer.files.length > 0) {
      onFileSelected(e.dataTransfer.files);
    }
  });
}

let selectedFiles = [];

function onFileSelected(files) {
  if (!files || files.length === 0) return;
  selectedFiles = Array.from(files);
  const totalSize = selectedFiles.reduce((acc, f) => acc + f.size, 0);
  const fileLabel = document.getElementById("file-label");
  const uploadBtn = document.getElementById("upload-file-btn");

  if (selectedFiles.length === 1) {
    fileLabel.innerHTML = `Đã chọn: <strong class="text-sky-700">${selectedFiles[0].name}</strong> (${(selectedFiles[0].size / 1024).toFixed(1)} KB)`;
    uploadBtn.innerHTML = `<span>Bắt Đầu Vector Hóa (1 File)</span>`;
  } else {
    fileLabel.innerHTML = `Đã chọn: <strong class="text-sky-700">${selectedFiles.length} file</strong> (${(totalSize / 1024).toFixed(1)} KB)<br><span class="text-[11px] text-slate-500 truncate block max-w-sm mx-auto mt-0.5">${selectedFiles.map(f => f.name).join(", ")}</span>`;
    uploadBtn.innerHTML = `<span>Bắt Đầu Vector Hóa (${selectedFiles.length} File)</span>`;
  }
  uploadBtn.disabled = false;
}

async function submitFileUpload() {
  if (!selectedFiles || selectedFiles.length === 0) {
    showToast("Vui lòng kéo thả hoặc chọn ít nhất một file trước!", "error");
    return;
  }

  if (!selectedAgentId) {
    showToast("Chưa chọn dịch vụ có Trợ lý AI! Vui lòng chọn dịch vụ ở phía trên.", "error");
    return;
  }

  const btn = document.getElementById("upload-file-btn");
  btn.disabled = true;
  btn.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Đang trích xuất & Vector hóa ${selectedFiles.length} file...`;

  const formData = new FormData();
  for (const f of selectedFiles) {
    formData.append("files", f);
  }

  try {
    const res = await apiRequest(`/api/v1/agents/${selectedAgentId}/documents/upload`, {
      method: "POST",
      body: formData,
    });

    const successCount = res.files_processed ? res.files_processed.filter(f => f.status === 'success').length : 1;
    const totalChunks = res.total_chunks_created || res.chunks_created || 0;

    showToast(`Đã nạp thành công ${successCount} file với ${totalChunks} đoạn tri thức!`, "success");
    selectedFiles = [];
    document.getElementById("file-input").value = "";
    document.getElementById("file-label").innerHTML = `Kéo thả một hoặc nhiều file vào đây hoặc <span class="text-sky-600">bấm chọn file</span>`;
    await loadAgentChunks(selectedAgentId);
    await loadDashboardOverview();
  } catch (err) {
    showToast(err.message || "Lỗi khi upload file", "error");
  } finally {
    btn.disabled = selectedFiles.length === 0;
    btn.innerHTML = `<span>Bắt Đầu Vector Hóa File</span>`;
  }
}

async function submitTextIngest() {
  if (!selectedAgentId) {
    showToast("Chưa chọn dịch vụ có Trợ lý AI! Vui lòng chọn dịch vụ ở phía trên.", "error");
    return;
  }

  const source = document.getElementById("text-ingest-source").value.trim() || "Văn bản trực tiếp";
  const content = document.getElementById("text-ingest-content").value.trim();

  if (!content) {
    showToast("Vui lòng nhập nội dung văn bản!", "error");
    return;
  }

  const btn = document.getElementById("upload-text-btn");
  btn.disabled = true;
  btn.textContent = "Đang cắt đoạn & Vector hóa...";

  try {
    const res = await apiRequest(`/api/v1/agents/${selectedAgentId}/documents/text`, {
      method: "POST",
      json: { source, content },
    });

    showToast(`Đã tạo thành công ${res.chunks_created} đoạn tri thức mới!`, "success");
    document.getElementById("text-ingest-content").value = "";
    document.getElementById("text-ingest-source").value = "";
    await loadAgentChunks(selectedAgentId);
    await loadDashboardOverview();
  } catch (err) {
    showToast(err.message || "Lỗi khi nạp văn bản", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Lưu & Vector Hóa Văn Bản";
  }
}

async function deleteChunk(agentId, chunkId) {
  if (!confirm("Bạn có chắc muốn xóa đoạn tri thức này khỏi kho vector?")) return;
  try {
    await apiRequest(`/api/v1/agents/${agentId}/documents/${chunkId}`, {
      method: "DELETE",
    });
    showToast("Đã xóa đoạn tri thức.", "success");
    await loadAgentChunks(agentId);
    await loadDashboardOverview();
  } catch (err) {
    showToast(err.message || "Không thể xóa chunk", "error");
  }
}

async function wipeAllChunksForAgent() {
  if (!selectedAgentId) return;
  if (!confirm("CẢNH BÁO: Thao tác này sẽ xóa vĩnh viễn TOÀN BỘ tri thức vector của Agent này! Bạn có chắc chắn không?")) return;

  try {
    await apiRequest(`/api/v1/agents/${selectedAgentId}/documents`, {
      method: "DELETE",
    });
    showToast("Đã dọn dẹp toàn bộ tri thức của Agent!", "success");
    await loadAgentChunks(selectedAgentId);
    await loadDashboardOverview();
  } catch (err) {
    showToast(err.message || "Lỗi khi xóa tri thức", "error");
  }
}

// ---------------------------------------------------------------------------
// 7. Tab: Sub-Admin Users Management
// ---------------------------------------------------------------------------
async function loadUsersTab() {
  const tbody = document.getElementById("users-tbody");
  tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-slate-400">Đang tải danh sách nhân sự...</td></tr>`;

  try {
    const users = await apiRequest("/api/v1/users/");
    if (!users || users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-slate-400">Không có dữ liệu nhân sự.</td></tr>`;
      return;
    }

    tbody.innerHTML = users
      .map((u) => {
        const isSelf = u.id === currentUser.id;
        const roleBadge =
          u.role === "SUPER_ADMIN"
            ? `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">SUPER ADMIN</span>`
            : `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">SUB ADMIN</span>`;

        const statusBadge = u.is_active
          ? `<span class="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600"><span class="w-2 h-2 rounded-full bg-emerald-500"></span>Hoạt động</span>`
          : `<span class="inline-flex items-center gap-1.5 text-xs font-medium text-rose-600"><span class="w-2 h-2 rounded-full bg-rose-400"></span>Đã khóa</span>`;

        const toggleBtn = isSelf
          ? `<span class="text-xs text-slate-400 italic">Đang đăng nhập</span>`
          : `
          <button onclick="toggleUserStatus('${u.id}', ${u.is_active})"
            class="px-2.5 py-1 rounded-lg text-xs font-semibold border ${u.is_active
            ? "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100"
            : "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
          } transition-all">
            ${u.is_active ? "Khóa tài khoản" : "Mở khóa"}
          </button>
        `;

        return `
        <tr class="hover:bg-slate-50/80 transition-colors">
          <td class="px-6 py-4 font-bold text-slate-800">${u.full_name || "—"}</td>
          <td class="px-6 py-4 font-mono text-xs text-slate-600">${u.email}</td>
          <td class="px-6 py-4">${roleBadge}</td>
          <td class="px-6 py-4">${statusBadge}</td>
          <td class="px-6 py-4 text-xs text-slate-400">${formatDate(u.created_at)}</td>
          <td class="px-6 py-4 text-right">${toggleBtn}</td>
        </tr>
      `;
      })
      .join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-rose-500">Lỗi: ${err.message}</td></tr>`;
  }
}

function openCreateUserModal() {
  document.getElementById("modal-user").classList.remove("hidden");
  document.getElementById("user-fullname-input").value = "";
  document.getElementById("user-email-input").value = "";
  document.getElementById("user-password-input").value = "";
}

document.getElementById("create-user-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const full_name = document.getElementById("user-fullname-input").value.trim();
  const email = document.getElementById("user-email-input").value.trim();
  const password = document.getElementById("user-password-input").value;
  const btn = document.getElementById("submit-user-btn");

  btn.disabled = true;
  btn.textContent = "Đang tạo...";

  try {
    await apiRequest("/api/v1/users/", {
      method: "POST",
      json: { full_name, email, password },
    });
    showToast(`Đã tạo tài khoản Sub-Admin cho ${full_name}!`, "success");
    closeModal("modal-user");
    await loadUsersTab();
  } catch (err) {
    showToast(err.message || "Không thể tạo tài khoản Sub-Admin", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Tạo Tài Khoản Sub-Admin";
  }
});

async function toggleUserStatus(userId, currentActive) {
  const actionName = currentActive ? "khóa" : "mở khóa";
  if (!confirm(`Bạn có chắc muốn ${actionName} tài khoản này?`)) return;

  try {
    await apiRequest(`/api/v1/users/${userId}/status`, {
      method: "PATCH",
      json: { is_active: !currentActive },
    });
    showToast(`Đã ${actionName} tài khoản thành công.`, "success");
    await loadUsersTab();
  } catch (err) {
    showToast(err.message || "Thao tác thất bại", "error");
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function escapeHtml(text) {
  if (!text) return "";
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

