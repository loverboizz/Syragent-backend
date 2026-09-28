/**
 * Admin Dashboard - API Client & Utility Module
 * Handles JWT authentication, API calls, error handling, and toast notifications.
 */

const TOKEN_KEY = "ai_agent_jwt_token";
const USER_KEY = "ai_agent_user_info";

// ---------------------------------------------------------------------------
// Auth Storage Helpers
// ---------------------------------------------------------------------------
function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getUser() {
  const data = localStorage.getItem(USER_KEY);
  try {
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

function setAuthSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
}

function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  if (!window.location.pathname.includes("login")) {
    window.location.href = "/admin/login";
  }
}

function requireAuth() {
  const token = getToken();
  if (!token) {
    clearAuthSession();
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Unified API Request Wrapper
// ---------------------------------------------------------------------------
async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const headers = options.headers || {};

  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Handle JSON bodies
  let body = options.body;
  if (options.json) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      body,
    });

    // Handle 401 Unauthorized
    if (response.status === 401) {
      if (!window.location.pathname.includes("login")) {
        showToast("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", "error");
        setTimeout(clearAuthSession, 1200);
      }
      throw new Error("Unauthorized");
    }

    // Parse Response
    let data;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errorMsg =
        (data && typeof data === "object" && (data.detail || data.message)) ||
        `Lỗi hệ thống (${response.status})`;
      throw new Error(errorMsg);
    }

    return data;
  } catch (err) {
    console.error(`API Error [${options.method || "GET"} ${url}]:`, err);
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Toast Notifications
// ---------------------------------------------------------------------------
function showToast(message, type = "success") {
  let toastContainer = document.getElementById("toast-container");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toast-container";
    toastContainer.className = "fixed top-5 right-5 z-[999999] flex flex-col gap-2 pointer-events-none";
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement("div");
  toast.className = `pointer-events-auto px-4 py-3 rounded-xl shadow-xl text-sm font-medium flex items-center gap-3 transition-all duration-300 transform translate-y-[-10px] opacity-0 border ${
    type === "success"
      ? "bg-white text-emerald-800 border-emerald-200"
      : type === "error"
      ? "bg-white text-rose-800 border-rose-200"
      : "bg-white text-sky-800 border-sky-200"
  }`;

  const iconSvg =
    type === "success"
      ? `<svg class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`
      : type === "error"
      ? `<svg class="w-5 h-5 text-rose-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`
      : `<svg class="w-5 h-5 text-sky-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;

  toast.innerHTML = `
    ${iconSvg}
    <span class="flex-1">${message}</span>
  `;

  toastContainer.appendChild(toast);

  // Trigger enter animation
  requestAnimationFrame(() => {
    toast.classList.remove("translate-y-[-10px]", "opacity-0");
    toast.classList.add("translate-y-0", "opacity-100");
  });

  // Auto remove
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-[-10px]");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatDate(dateStr) {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

