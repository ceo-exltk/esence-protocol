/* ============================================================
   Esence Node UI — app.js
   WebSocket nativo, sin frameworks
   ============================================================ */

(function () {
  "use strict";

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let ws = null;
  let wsReconnectTimer = null;
  let currentReviewThreadId = null;
  let nodeState = {};

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const statusDot = $("status-dot");
  const statusText = $("status-text");
  const budgetText = $("budget-text");
  const peersText = $("peers-text");
  const didText = $("did-text");
  const feedEmpty = $("feed-empty");
  const messagesEl = $("messages");
  const reviewCard = $("review-card");
  const reviewFrom = $("review-from");
  const reviewContent = $("review-content");
  const reviewProposal = $("review-proposal");
  const proposalText = $("proposal-text");
  const btnApprove = $("btn-approve");
  const btnReject = $("btn-reject");
  const inputText = $("input-text");
  const btnSend = $("btn-send");
  const charCount = $("char-count");
  const maturityFill = $("maturity-fill");
  const maturityScore = $("maturity-score");

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    setStatus("connecting");

    ws.onopen = () => {
      setStatus("online");
      clearTimeout(wsReconnectTimer);
      ws.send(JSON.stringify({ type: "get_state" }));
      ws.send(JSON.stringify({ type: "get_pending" }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleServerEvent(msg.type, msg.data);
      } catch (e) {
        console.error("WS parse error:", e);
      }
    };

    ws.onclose = () => {
      setStatus("offline");
      wsReconnectTimer = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      setStatus("offline");
    };
  }

  function sendWS(type, data = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, ...data }));
    }
  }

  // ------------------------------------------------------------------
  // Event handlers from server
  // ------------------------------------------------------------------

  function handleServerEvent(type, data) {
    switch (type) {
      case "node_state":
        applyState(data);
        break;
      case "inbound_message":
        addMessageCard(data, "inbound");
        showFeed();
        if (data.status === "pending_human_review") {
          showReviewCard(data);
          notify("Nuevo mensaje pendiente de revisión");
        }
        break;
      case "agent_reply":
        addMessageCard(
          {
            from_did: "tu agente",
            content: data.content,
            timestamp: new Date().toISOString(),
            type: "self_reply",
            status: "answered",
          },
          "self"
        );
        showFeed();
        break;
      case "pending_messages":
        if (data.messages && data.messages.length > 0) {
          data.messages.forEach((m) => {
            addMessageCard(m, "inbound");
          });
          showFeed();
          showReviewCard(data.messages[0]);
        }
        break;
      case "approved":
        updateCardStatus(data.thread_id, "approved");
        hideReviewCard();
        notify("Mensaje aprobado");
        break;
      case "rejected":
        updateCardStatus(data.thread_id, "rejected");
        hideReviewCard();
        notify("Mensaje rechazado");
        break;
      case "error":
        console.error("Server error:", data);
        break;
    }
  }

  // ------------------------------------------------------------------
  // State management
  // ------------------------------------------------------------------

  function applyState(state) {
    nodeState = state || {};

    // DID
    if (state.did) {
      didText.textContent = shortenDid(state.did);
      didText.title = state.did;
    }

    // Budget
    if (state.budget) {
      const used = state.budget.used_tokens || 0;
      const limit = state.budget.monthly_limit_tokens || 500000;
      const pct = Math.round((used / limit) * 100);
      budgetText.textContent = `${pct}% budget`;
    }

    // Peers
    if (typeof state.peer_count === "number") {
      peersText.textContent = `${state.peer_count} peer${state.peer_count !== 1 ? "s" : ""}`;
    }

    // Maturity
    if (typeof state.maturity === "number") {
      const pct = Math.round(state.maturity * 100);
      maturityFill.style.width = `${pct}%`;
      maturityScore.textContent = `${state.maturity_label || ""} (${pct}%)`;
    }
  }

  // ------------------------------------------------------------------
  // Feed
  // ------------------------------------------------------------------

  function showFeed() {
    feedEmpty.style.display = "none";
    messagesEl.style.display = "block";
  }

  function addMessageCard(msg, direction = "inbound") {
    const el = document.createElement("div");
    el.className = `message-card ${direction}`;
    el.dataset.threadId = msg.thread_id || "";

    const time = msg.timestamp
      ? formatTime(msg.timestamp)
      : "";

    const fromLabel =
      direction === "self"
        ? "tu agente"
        : shortenDid(msg.from_did || "desconocido");

    el.innerHTML = `
      <div class="msg-header">
        <span class="msg-from ${direction === "self" ? "self" : ""}">${escHtml(fromLabel)}</span>
        <div style="display:flex;gap:6px;align-items:center">
          <span class="msg-type">${escHtml(msg.type || "")}</span>
          <span class="msg-time">${time}</span>
        </div>
      </div>
      <div class="msg-content">${escHtml(msg.content || "")}</div>
      <span class="msg-status ${msg.status || ""}">${msg.status || ""}</span>
    `;

    messagesEl.prepend(el);
  }

  function updateCardStatus(threadId, status) {
    const cards = messagesEl.querySelectorAll(`[data-thread-id="${threadId}"]`);
    cards.forEach((card) => {
      const statusEl = card.querySelector(".msg-status");
      if (statusEl) {
        statusEl.className = `msg-status ${status}`;
        statusEl.textContent = status;
      }
    });
  }

  // ------------------------------------------------------------------
  // Review card
  // ------------------------------------------------------------------

  function showReviewCard(msg) {
    currentReviewThreadId = msg.thread_id;
    reviewFrom.textContent = shortenDid(msg.from_did || "desconocido");
    reviewFrom.title = msg.from_did || "";
    reviewContent.textContent = msg.content || "";

    if (msg.proposed_reply) {
      proposalText.textContent = msg.proposed_reply;
      reviewProposal.classList.remove("hidden");
    } else {
      reviewProposal.classList.add("hidden");
    }

    reviewCard.classList.remove("hidden");
  }

  function hideReviewCard() {
    reviewCard.classList.add("hidden");
    currentReviewThreadId = null;
  }

  // ------------------------------------------------------------------
  // Buttons
  // ------------------------------------------------------------------

  btnApprove.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    sendWS("approve", { thread_id: currentReviewThreadId });
  });

  btnReject.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    sendWS("reject", { thread_id: currentReviewThreadId });
  });

  btnSend.addEventListener("click", sendChat);

  inputText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      sendChat();
    }
  });

  inputText.addEventListener("input", () => {
    const len = inputText.value.length;
    charCount.textContent = `${len} / 2000`;
  });

  function sendChat() {
    const content = inputText.value.trim();
    if (!content) return;

    // Mostrar en feed
    addMessageCard(
      {
        from_did: "vos",
        content,
        timestamp: new Date().toISOString(),
        type: "chat",
        status: "sent",
      },
      "outbound"
    );
    showFeed();

    sendWS("chat", { content });
    inputText.value = "";
    charCount.textContent = "0 / 2000";
  }

  // ------------------------------------------------------------------
  // Status
  // ------------------------------------------------------------------

  function setStatus(state) {
    statusDot.className = `status-dot ${state}`;
    const labels = {
      online: "online",
      offline: "offline",
      connecting: "conectando...",
    };
    statusText.textContent = labels[state] || state;
  }

  // ------------------------------------------------------------------
  // Notifications
  // ------------------------------------------------------------------

  function notify(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function shortenDid(did) {
    if (!did) return "—";
    if (did.length <= 32) return did;
    return did.slice(0, 20) + "…" + did.slice(-10);
  }

  function formatTime(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString("es-AR", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  connect();

  // Refrescar estado cada 30s
  setInterval(() => {
    sendWS("get_state");
  }, 30000);
})();
