/**
 * AI Service Agent - Embeddable Chat Widget
 * Pure JavaScript, no external dependencies.
 *
 * Usage:
 * <script src="http://localhost:8000/widget.js" data-service="s0257"></script>
 */

(function () {
  // Prevent duplicate initialization
  if (window.__AI_AGENT_WIDGET_LOADED__) return;
  window.__AI_AGENT_WIDGET_LOADED__ = true;

  function initWidget() {
    // 1. Detect configuration from the current script tag
    const currentScript =
      document.currentScript ||
      document.querySelector("script[data-service]") ||
      document.querySelector("script[src*='widget.js']");

    const serviceCode = currentScript ? currentScript.getAttribute("data-service") || "s0257" : "s0257";

    // Compute API base URL
    let apiBase = currentScript ? currentScript.getAttribute("data-api") : null;
    if (!apiBase && currentScript && currentScript.src) {
      try {
        const parsed = new URL(currentScript.src);
        apiBase = `${parsed.protocol}//${parsed.host}`;
      } catch (e) {
        apiBase = "http://localhost:8000";
      }
    }
    if (!apiBase) apiBase = "http://localhost:8000";

    // 2. Inject CSS Styles
    const styleEl = document.createElement("style");
    styleEl.textContent = `
      .ai-widget-container {
        --ai-primary: #0284c7;
        --ai-primary-hover: #0369a1;
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 9999999;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        line-height: 1.5;
      }
      .ai-widget-container.pos-left {
        left: 24px;
        right: auto;
      }
      .ai-widget-window.pos-left {
        left: 24px;
        right: auto;
        transform-origin: bottom left;
      }
      
      .ai-widget-button {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: var(--ai-primary);
        color: #ffffff;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        outline: none;
      }
      .ai-widget-button:hover {
        transform: scale(1.08);
        background: var(--ai-primary-hover);
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
      }
      .ai-widget-button svg {
        width: 30px;
        height: 30px;
        fill: currentColor;
        transition: transform 0.3s ease;
      }

      .ai-widget-window {
        position: fixed;
        bottom: 96px;
        right: 24px;
        width: 380px;
        height: 580px;
        max-width: calc(100vw - 32px);
        max-height: calc(100vh - 120px);
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.18);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        transform-origin: bottom right;
        opacity: 0;
        pointer-events: none;
        transform: scale(0.85) translateY(20px);
        border: 1px solid #e2e8f0;
        z-index: 9999999;
      }

      .ai-widget-window.open {
        opacity: 1;
        pointer-events: auto;
        transform: scale(1) translateY(0);
      }

      .ai-widget-header {
        background: var(--ai-primary);
        color: #ffffff;
        padding: 16px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 1px solid rgba(255, 255, 255, 0.15);
      }
      .ai-widget-header-title {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .ai-widget-avatar {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.22);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        overflow: hidden;
        flex-shrink: 0;
      }
      .ai-widget-avatar img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 50%;
      }
      .ai-widget-name {
        font-weight: 700;
        font-size: 15px;
        color: #ffffff;
      }
      .ai-widget-status {
        font-size: 11px;
        color: rgba(255, 255, 255, 0.85);
        display: flex;
        align-items: center;
        gap: 5px;
      }
      .ai-widget-status::before {
        content: '';
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #10b981;
        display: inline-block;
      }
      .ai-widget-close {
        background: transparent;
        border: none;
        color: #ffffff;
        cursor: pointer;
        font-size: 20px;
        padding: 4px 8px;
        border-radius: 6px;
        opacity: 0.8;
        transition: opacity 0.2s;
      }
      .ai-widget-close:hover {
        opacity: 1;
        background: rgba(255, 255, 255, 0.15);
      }

      .ai-widget-body {
        flex: 1;
        padding: 16px;
        overflow-y: auto;
        background: #f8fafc;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .ai-msg {
        max-width: 85%;
        padding: 12px 16px;
        border-radius: 14px;
        font-size: 13.5px;
        line-height: 1.55;
        word-break: break-word;
      }
      .ai-msg-bot {
        align-self: flex-start;
        background: #ffffff;
        color: #1e293b;
        border: 1px solid #e2e8f0;
        border-bottom-left-radius: 4px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
      }
      .ai-msg-user {
        align-self: flex-end;
        background: var(--ai-primary);
        color: #ffffff;
        border-bottom-right-radius: 4px;
      }
      .ai-msg-sources {
        margin-top: 8px;
        padding-top: 6px;
        border-top: 1px dashed #cbd5e1;
        font-size: 11px;
        color: #64748b;
      }

      .ai-typing {
        display: none;
        align-self: flex-start;
        background: #ffffff;
        padding: 10px 14px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        gap: 4px;
        align-items: center;
      }
      .ai-typing span {
        width: 6px;
        height: 6px;
        background: #94a3b8;
        border-radius: 50%;
        animation: ai-blink 1.2s infinite ease-in-out both;
      }
      .ai-typing span:nth-child(1) { animation-delay: -0.32s; }
      .ai-typing span:nth-child(2) { animation-delay: -0.16s; }
      @keyframes ai-blink {
        0%, 80%, 100% { transform: scale(0); }
        40% { transform: scale(1); }
      }

      .ai-starter-prompts {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 10px;
      }
      .ai-starter-chip {
        background: #f1f5f9;
        color: #334155;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 5px 11px;
        font-size: 11.5px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        text-align: left;
      }
      .ai-starter-chip:hover {
        background: var(--ai-primary);
        color: #ffffff;
        border-color: var(--ai-primary);
      }

      .ai-widget-footer {
        padding: 12px 16px;
        background: #ffffff;
        border-top: 1px solid #e2e8f0;
        display: flex;
        gap: 8px;
        align-items: center;
      }
      .ai-widget-input {
        flex: 1;
        border: 1px solid #cbd5e1;
        padding: 10px 14px;
        border-radius: 20px;
        font-size: 13.5px;
        outline: none;
        transition: border-color 0.2s;
      }
      .ai-widget-input:focus {
        border-color: var(--ai-primary);
      }
      .ai-widget-send {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: var(--ai-primary);
        color: #ffffff;
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
        outline: none;
      }
      .ai-widget-send:hover {
        background: var(--ai-primary-hover);
      }
      .ai-widget-send svg {
        width: 18px;
        height: 18px;
        fill: #ffffff;
        margin-left: 2px;
      }

      @media (max-width: 480px) {
        .ai-widget-window {
          bottom: 0;
          right: 0;
          width: 100vw;
          height: 100vh;
          max-width: 100vw;
          max-height: 100vh;
          border-radius: 0;
        }
      }
    `;
    document.head.appendChild(styleEl);

    // 3. Inject Widget HTML
    const container = document.createElement("div");
    container.className = "ai-widget-container";
    container.innerHTML = `
      <button class="ai-widget-button" id="ai-widget-btn" title="Trò chuyện với Trợ lý AI">
        <svg viewBox="0 0 24 24">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
        </svg>
      </button>
      <div class="ai-widget-window" id="ai-widget-win">
        <div class="ai-widget-header">
          <div class="ai-widget-header-title">
            <div class="ai-widget-avatar" id="ai-widget-avatar">🤖</div>
            <div>
              <div class="ai-widget-name" id="ai-widget-name">Trợ Lý AI</div>
              <div class="ai-widget-status" id="ai-widget-status">Trực tuyến • Sẵn sàng hỗ trợ</div>
            </div>
          </div>
          <button class="ai-widget-close" id="ai-widget-close-btn">&times;</button>
        </div>
        <div class="ai-widget-body" id="ai-widget-msgs">
          <div class="ai-msg ai-msg-bot">
            <div id="ai-widget-initial-greeting">
              Xin chào Quý khách! 👋 Em là Trợ lý AI của dịch vụ. Quý khách cần hỗ trợ thông tin gì về quy trình, báo giá hoặc kỹ thuật của dịch vụ này ạ?
            </div>
            <div class="ai-starter-prompts" id="ai-widget-starter-chips"></div>
          </div>
          <div class="ai-typing" id="ai-widget-typing">
            <span></span><span></span><span></span>
          </div>
        </div>
        <form class="ai-widget-footer" id="ai-widget-form">
          <input type="text" class="ai-widget-input" id="ai-widget-input" placeholder="Nhập câu hỏi của bạn..." autocomplete="off"/>
          <button type="submit" class="ai-widget-send" title="Gửi câu hỏi">
            <svg viewBox="0 0 24 24">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
          </button>
        </form>
      </div>
    `;
    document.body.appendChild(container);

    // 4. Widget Logic & Handlers
    const btn = document.getElementById("ai-widget-btn");
    const win = document.getElementById("ai-widget-win");
    const closeBtn = document.getElementById("ai-widget-close-btn");
    const form = document.getElementById("ai-widget-form");
    const input = document.getElementById("ai-widget-input");
    const msgs = document.getElementById("ai-widget-msgs");
    const typing = document.getElementById("ai-widget-typing");

    let isOpen = false;

    // Persistent Visitor ID (stored per domain in localStorage)
    const VISITOR_KEY = "ai_widget_visitor_id";
    let visitorId = "";
    try {
      visitorId = localStorage.getItem(VISITOR_KEY) || "";
      if (!visitorId) {
        visitorId = "vis_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
        localStorage.setItem(VISITOR_KEY, visitorId);
      }
    } catch (e) {
      visitorId = "vis_fallback_" + Date.now();
    }

    function toggleChat(openState) {
      isOpen = openState !== undefined ? openState : !isOpen;
      if (isOpen) {
        win.classList.add("open");
        input.focus();
      } else {
        win.classList.remove("open");
      }
    }

    btn.addEventListener("click", () => toggleChat());
    closeBtn.addEventListener("click", () => toggleChat(false));

    // Restore conversation history when returning
    async function loadChatHistory() {
      try {
        const res = await fetch(`${apiBase}/api/v1/chat/${serviceCode}/history?visitor_id=${encodeURIComponent(visitorId)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data && data.messages && data.messages.length > 0) {
          data.messages.forEach((msg) => {
            const sourcesList = (msg.sources || []).map((s) => (typeof s === "string" ? s : (s.source || ""))).filter(Boolean);
            appendMessage(msg.content, msg.role === "user", sourcesList);
          });
        }
      } catch (e) {
        // Silently skip if history unavailable
      }
    }

    // Dynamic customization loader from Server
    async function loadWidgetConfig() {
      try {
        const res = await fetch(`${apiBase}/api/v1/chat/${serviceCode}/config`);
        if (!res.ok) return;
        const data = await res.json();
        const cfg = data.widget_config || {};

        // 1. Primary color
        if (cfg.primary_color) {
          container.style.setProperty("--ai-primary", cfg.primary_color);
          container.style.setProperty("--ai-primary-hover", cfg.primary_color);
        }

        // 2. Position (right vs left)
        if (cfg.position === "left") {
          container.classList.add("pos-left");
          win.classList.add("pos-left");
        }

        // 3. Agent Name
        if (cfg.agent_name) {
          const nameEl = document.getElementById("ai-widget-name");
          if (nameEl) nameEl.textContent = cfg.agent_name;
        }

        // 4. Subtitle / Status
        if (cfg.subtitle) {
          const subEl = document.getElementById("ai-widget-status");
          if (subEl) subEl.textContent = cfg.subtitle;
        }

        // 5. Avatar
        const avatarEl = document.getElementById("ai-widget-avatar");
        if (avatarEl) {
          if (cfg.avatar_type === "image" && cfg.avatar_value) {
            avatarEl.innerHTML = `<img src="${cfg.avatar_value}" alt="Avatar"/>`;
          } else {
            avatarEl.textContent = cfg.avatar_value || "🤖";
          }
        }

        // 6. Initial Greeting
        const greetingEl = document.getElementById("ai-widget-initial-greeting");
        if (greetingEl && cfg.greeting) {
          greetingEl.textContent = cfg.greeting;
        }

        // 7. Starter Prompts (Chips)
        const chipsContainer = document.getElementById("ai-widget-starter-chips");
        if (chipsContainer && cfg.starter_prompts && cfg.starter_prompts.length > 0) {
          chipsContainer.innerHTML = "";
          cfg.starter_prompts.forEach((promptText) => {
            if (!promptText || !promptText.trim()) return;
            const chip = document.createElement("button");
            chip.className = "ai-starter-chip";
            chip.type = "button";
            chip.textContent = promptText;
            chip.addEventListener("click", () => {
              input.value = promptText;
              form.dispatchEvent(new Event("submit"));
            });
            chipsContainer.appendChild(chip);
          });
        }
      } catch (e) {
        // Fallback silently to defaults
      }
    }
    loadWidgetConfig();
    loadChatHistory();

    function formatMarkdown(text) {
      return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\n/g, "<br/>")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    }

    function appendMessage(text, isUser, sources = []) {
      const msgEl = document.createElement("div");
      msgEl.className = `ai-msg ${isUser ? "ai-msg-user" : "ai-msg-bot"}`;
      msgEl.innerHTML = formatMarkdown(text);

      if (!isUser && sources && sources.length > 0) {
        const srcEl = document.createElement("div");
        srcEl.className = "ai-msg-sources";
        srcEl.textContent = `📚 Nguồn tham khảo: ${sources.join(", ")}`;
        msgEl.appendChild(srcEl);
      }

      msgs.insertBefore(msgEl, typing);
      msgs.scrollTop = msgs.scrollHeight;
      return msgEl;
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const question = input.value.trim();
      if (!question) return;

      appendMessage(question, true);
      input.value = "";

      // Show typing indicator
      typing.style.display = "flex";
      msgs.scrollTop = msgs.scrollHeight;

      // Create Bot message placeholder
      let botMsgEl = null;
      let botText = "";
      let sourcesList = [];
      let hasReceivedFirstToken = false;

      function renderBotContent() {
        if (!botMsgEl) {
          botMsgEl = document.createElement("div");
          botMsgEl.className = "ai-msg ai-msg-bot";
          msgs.insertBefore(botMsgEl, typing);
        }
        let html = formatMarkdown(botText);
        if (sourcesList && sourcesList.length > 0) {
          const safeSources = sourcesList.map(s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;")).join(", ");
          html += `<div class="ai-msg-sources">📚 Nguồn tham khảo: ${safeSources}</div>`;
        }
        botMsgEl.innerHTML = html;
        msgs.scrollTop = msgs.scrollHeight;
      }

      try {
        const reqHeaders = {
          "Content-Type": "application/json",
        };
        try {
          const jwtToken = localStorage.getItem("ai_agent_jwt_token");
          if (jwtToken) {
            reqHeaders["Authorization"] = `Bearer ${jwtToken}`;
          }
        } catch (_e) {
          // Ignore localStorage access errors in restricted iframes
        }

        const res = await fetch(`${apiBase}/api/v1/chat/${serviceCode}/stream`, {
          method: "POST",
          headers: reqHeaders,
          body: JSON.stringify({ question: question, visitor_id: visitorId }),
        });

        if (!res.ok) {
          typing.style.display = "none";
          const errorData = await res.json().catch(() => ({}));
          const errDetail = errorData.detail || "Không thể kết nối đến máy chủ.";
          appendMessage(`⚠️ Lỗi: ${errDetail}`, false);
          return;
        }

        // Check for streaming body support
        if (!res.body || !res.body.getReader) {
          typing.style.display = "none";
          const text = await res.text();
          appendMessage(text, false);
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop(); // Keep uncompleted line in buffer

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;
            const jsonStr = trimmed.slice(6).trim();
            if (!jsonStr) continue;

            try {
              const event = JSON.parse(jsonStr);
              if (event.type === "sources") {
                sourcesList = event.sources || [];
              } else if (event.type === "token") {
                if (!hasReceivedFirstToken) {
                  hasReceivedFirstToken = true;
                  typing.style.display = "none";
                }
                botText += event.token;
                renderBotContent();
              } else if (event.type === "done") {
                typing.style.display = "none";
                renderBotContent();
              } else if (event.type === "error") {
                typing.style.display = "none";
                botText += `\n⚠️ [Lỗi]: ${event.error}`;
                renderBotContent();
              }
            } catch (err) {
              console.error("SSE parse error:", err);
            }
          }
        }

        typing.style.display = "none";
        if (!botText && !hasReceivedFirstToken) {
          appendMessage("Xin lỗi, hiện tại không nhận được phản hồi từ AI.", false);
        }
      } catch (err) {
        typing.style.display = "none";
        if (botMsgEl && !botText) {
          botMsgEl.remove();
        }
        console.error("AI Widget Connection Error:", err);
        appendMessage(`⚠️ Có sự cố kết nối tới máy chủ AI Agent (${apiBase}). Vui lòng kiểm tra lại kết nối mạng hoặc đảm bảo backend đang chạy!`, false);
      }
    });
  }

  // Safe DOM ready check
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWidget);
  } else {
    initWidget();
  }
})();
