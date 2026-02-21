/* ============================================================
   Esence Node UI — app.js
   ============================================================ */

(function () {
  "use strict";

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let ws = null;
  let wsReconnectTimer = null;
  let currentReviewThreadId = null;
  let originalProposal = "";        // para detectar ediciones
  let pendingCount = 0;
  let currentMood = "moderate";
  let nodeState = {};
  const threads = {};               // thread_id → { msg, el, direction }

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const statusDot         = $("status-dot");
  const statusText        = $("status-text");
  const budgetText        = $("budget-text");
  const peersText         = $("peers-text");
  const didText           = $("did-text");
  const avatarInitials    = $("avatar-initials");
  const moodDot           = $("mood-dot");
  const notifBadge        = $("notif-badge");
  const btnNotif          = $("btn-notif");
  const feedEmpty         = $("feed-empty");
  const messagesEl        = $("messages");
  const reviewCard        = $("review-card");
  const reviewFrom        = $("review-from");
  const reviewContent     = $("review-content");
  const reviewProposal    = $("review-proposal");
  const reviewLoading     = $("review-loading");
  const proposalEdit      = $("proposal-edit");
  const diffIndicator     = $("diff-indicator");
  const btnApprove        = $("btn-approve");
  const btnReject         = $("btn-reject");
  const btnReviewClose    = $("btn-review-close");
  const learningFeedback  = $("learning-feedback");
  const inputText         = $("input-text");
  const btnSend           = $("btn-send");
  const charCount         = $("char-count");
  const maturityFill      = $("maturity-fill");
  const maturityScore     = $("maturity-score");
  const maturityCorrections = $("maturity-corrections");
  const maturityPatterns  = $("maturity-patterns");

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);
    setStatus("connecting");

    ws.onopen = () => {
      setStatus("online");
      clearTimeout(wsReconnectTimer);
      sendWS("get_state");
      sendWS("get_pending");
    };

    ws.onmessage = (e) => {
      try { handleServerEvent(...Object.values(JSON.parse(e.data))); }
      catch (err) { console.error("WS parse:", err); }
    };

    ws.onclose = () => { setStatus("offline"); wsReconnectTimer = setTimeout(connect, 3000); };
    ws.onerror = () => setStatus("offline");
  }

  function sendWS(type, data = {}) {
    if (ws && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ type, ...data }));
  }

  // ------------------------------------------------------------------
  // Server events
  // ------------------------------------------------------------------

  function handleServerEvent(type, data) {
    switch (type) {

      case "node_state":
        applyState(data);
        break;

      case "inbound_message":
        upsertCard(data, "inbound");
        if (data.status === "pending_human_review") {
          setPending(pendingCount + 1);
          if (!currentReviewThreadId) showReview(data);
          notify("Mensaje de " + shortenDid(data.from_did), "warning");
        }
        break;

      case "review_ready":
        // Engine generó propuesta — actualizar card y review si corresponde
        upsertCard(data.message, "inbound");
        updateReplyBtn(data.thread_id, data.proposed_reply);
        if (!currentReviewThreadId || currentReviewThreadId === data.thread_id) {
          showReview({ ...data.message, proposed_reply: data.proposed_reply });
        }
        break;

      case "auto_approved":
        updateStatus(data.thread_id, "auto_approved");
        notify("Auto-aprobado · " + shortenDid(data.from_did || ""), "info");
        break;

      case "agent_reply":
        upsertCard({
          from_did: "tu agente",
          content: data.content,
          timestamp: new Date().toISOString(),
          type: "self_reply",
          status: "answered",
          thread_id: "self-" + Date.now(),
        }, "self");
        break;

      case "pending_messages":
        if (data.messages?.length) {
          data.messages.forEach((m) => upsertCard(m, "inbound"));
          setPending(data.messages.length);
          if (!currentReviewThreadId) showReview(data.messages[0]);
        }
        break;

      case "approved":
        updateStatus(data.thread_id, "approved");
        if (currentReviewThreadId === data.thread_id) hideReview();
        setPending(Math.max(0, pendingCount - 1));
        sendWS("get_pending");   // cargar próximo pendiente si hay
        break;

      case "rejected":
        updateStatus(data.thread_id, "rejected");
        if (currentReviewThreadId === data.thread_id) hideReview();
        setPending(Math.max(0, pendingCount - 1));
        sendWS("get_pending");
        break;

      case "mood_changed":
        setMoodUI(data.mood);
        break;

      case "correction_logged":
        sendWS("get_state");
        break;

      case "patterns_updated":
        const n = data.new_patterns;
        notify(`${n} nuevo${n > 1 ? "s" : ""} patrón${n > 1 ? "es" : ""} extraído${n > 1 ? "s" : ""}`, "success");
        sendWS("get_state");
        break;

      case "error":
        console.error("Server:", data);
        break;
    }
  }

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------

  function applyState(state) {
    if (!state) return;
    nodeState = state;

    if (state.did) {
      didText.textContent = shortenDid(state.did);
      didText.title = state.did;
      const name = state.node_name || "N";
      avatarInitials.textContent = name[0].toUpperCase();
    }

    if (state.budget) {
      const used = state.budget.used_tokens || 0;
      const lim  = state.budget.monthly_limit_tokens || 500_000;
      budgetText.textContent = `${Math.round(used / lim * 100)}% budget`;
    }

    if (typeof state.peer_count === "number")
      peersText.textContent = `${state.peer_count} peer${state.peer_count !== 1 ? "s" : ""}`;

    if (typeof state.maturity === "number") {
      const pct = Math.round(state.maturity * 100);
      maturityFill.style.width = `${pct}%`;
      maturityScore.textContent = `${state.maturity_label || ""} · ${pct}%`;
    }

    if (state.corrections_count !== undefined)
      maturityCorrections.textContent = `${state.corrections_count} correcciones`;
    if (state.patterns_count !== undefined)
      maturityPatterns.textContent = `${state.patterns_count} patrones`;

    if (state.mood) setMoodUI(state.mood);
  }

  // ------------------------------------------------------------------
  // Mood
  // ------------------------------------------------------------------

  function setMoodUI(mood) {
    currentMood = mood;

    // Dot en avatar
    moodDot.className = `mood-dot ${mood}`;
    moodDot.title = { available: "Disponible", moderate: "Moderado", absent: "Ausente", dnd: "No molestar" }[mood] || mood;

    // Botones del selector
    document.querySelectorAll(".mood-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mood === mood);
    });
  }

  document.querySelectorAll(".mood-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mood = btn.dataset.mood;
      if (mood === currentMood) return;
      sendWS("set_mood", { mood });
      setMoodUI(mood); // optimistic update
      const labels = { available: "● Disponible", moderate: "◑ Moderado", absent: "○ Ausente", dnd: "⊗ No molestar" };
      notify(`Modo: ${labels[mood] || mood}`);
    });
  });

  // ------------------------------------------------------------------
  // Pending count + bell
  // ------------------------------------------------------------------

  function setPending(n) {
    pendingCount = Math.max(0, n);
    if (pendingCount > 0) {
      notifBadge.textContent = pendingCount > 9 ? "9+" : String(pendingCount);
      notifBadge.classList.remove("hidden");
      btnNotif.style.color = "var(--amber)";
    } else {
      notifBadge.classList.add("hidden");
      btnNotif.style.color = "";
    }
  }

  btnNotif.addEventListener("click", () => sendWS("get_pending"));

  // ------------------------------------------------------------------
  // Feed
  // ------------------------------------------------------------------

  function showFeed() {
    feedEmpty.style.display = "none";
    messagesEl.style.display = "block";
  }

  function upsertCard(msg, direction) {
    if (!msg) return;
    const tid = msg.thread_id || ("anon-" + Date.now());
    showFeed();

    if (threads[tid]) {
      // Actualizar status
      if (msg.status) updateStatus(tid, msg.status);
      // Actualizar proposed_reply si llegó
      if (msg.proposed_reply) updateReplyBtn(tid, msg.proposed_reply);
      return;
    }

    const card = buildCard(msg, direction, tid);
    threads[tid] = { msg, el: card, direction };
    messagesEl.prepend(card);
  }

  function buildCard(msg, direction, tid) {
    const el = document.createElement("div");
    el.className = `message-card ${direction}`;
    el.dataset.threadId = tid;

    const time  = msg.timestamp ? fmtTime(msg.timestamp) : "";
    const from  = msg.from_did || "desconocido";
    const label = direction === "self" ? "tu agente"
                : direction === "outbound" ? "vos"
                : shortenDid(from);
    const ini   = label[0].toUpperCase();
    const avCls = direction === "self" ? "self-av"
                : direction === "outbound" ? "outbound-av" : "";
    const fromCls = direction === "self" ? "self-lbl"
                  : direction === "outbound" ? "outbound-lbl" : "";
    const isPending = msg.status === "pending_human_review";

    el.innerHTML = `
      <div class="msg-header">
        <div class="msg-from-block">
          <div class="msg-avatar ${avCls}">${esc(ini)}</div>
          <span class="msg-from ${fromCls}" title="${esc(from)}">${esc(label)}</span>
        </div>
        <div class="msg-meta">
          <span class="msg-type">${esc(typeLabel(msg.type || ""))}</span>
          <span class="msg-time">${time}</span>
        </div>
      </div>
      <div class="msg-content">${esc(msg.content || "")}</div>
      <div class="msg-footer">
        <span class="msg-status ${msg.status || ""}">${statusLabel(msg.status)}</span>
        ${direction === "inbound" ? `
        <div class="msg-actions">
          <button class="msg-action-btn reply-btn ${isPending ? "pending-action" : ""}"
                  data-tid="${esc(tid)}"
                  data-proposed="${esc(msg.proposed_reply || "")}">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>
            </svg>
            ${isPending ? "Revisar" : "Ver"}
          </button>
        </div>` : ""}
      </div>
    `;

    const replyBtn = el.querySelector(".reply-btn");
    if (replyBtn) {
      replyBtn.addEventListener("click", () => {
        const proposed = replyBtn.dataset.proposed || "";
        showReview({ ...msg, thread_id: tid, proposed_reply: proposed });
        reviewCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }

    return el;
  }

  function updateStatus(tid, status) {
    const t = threads[tid];
    if (!t) return;
    const el = t.el.querySelector(".msg-status");
    if (el) { el.className = `msg-status ${status}`; el.textContent = statusLabel(status); }
    // Cambiar botón reply si ya no está pendiente
    const replyBtn = t.el.querySelector(".reply-btn");
    if (replyBtn && status !== "pending_human_review") {
      replyBtn.classList.remove("pending-action");
      replyBtn.innerHTML = `
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>
        </svg>
        Ver
      `;
    }
  }

  function updateReplyBtn(tid, proposed) {
    const t = threads[tid];
    if (!t) return;
    const btn = t.el.querySelector(".reply-btn");
    if (!btn) return;
    btn.dataset.proposed = proposed;
    btn.classList.remove("pending-action");
    btn.innerHTML = `
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>
      </svg>
      Revisar
    `;
    btn.onclick = () => {
      showReview({ ...t.msg, thread_id: tid, proposed_reply: proposed });
      reviewCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
  }

  // ------------------------------------------------------------------
  // Review card
  // ------------------------------------------------------------------

  function showReview(msg) {
    currentReviewThreadId = msg.thread_id;
    originalProposal = msg.proposed_reply || "";

    reviewFrom.textContent = shortenDid(msg.from_did || "desconocido");
    reviewFrom.title = msg.from_did || "";
    reviewContent.textContent = msg.content || "";

    // Reset learning feedback
    learningFeedback.classList.add("hidden");
    learningFeedback.innerHTML = "";
    btnApprove.disabled = false;
    btnReject.disabled = false;
    diffIndicator.classList.add("hidden");

    if (msg.proposed_reply) {
      proposalEdit.value = msg.proposed_reply;
      proposalEdit.classList.remove("edited");
      reviewLoading.classList.add("hidden");
      reviewProposal.classList.remove("hidden");
    } else {
      reviewProposal.classList.add("hidden");
      reviewLoading.classList.remove("hidden");
    }

    reviewCard.classList.remove("hidden");
  }

  function hideReview() {
    reviewCard.classList.add("hidden");
    currentReviewThreadId = null;
    originalProposal = "";
  }

  // Detectar ediciones en la propuesta → mostrar diff indicator
  proposalEdit.addEventListener("input", () => {
    const edited = proposalEdit.value !== originalProposal && proposalEdit.value.trim() !== "";
    proposalEdit.classList.toggle("edited", edited);
    diffIndicator.classList.toggle("hidden", !edited);
  });

  // ------------------------------------------------------------------
  // Approve / Reject
  // ------------------------------------------------------------------

  btnApprove.addEventListener("click", () => {
    if (!currentReviewThreadId) return;

    const edited = proposalEdit.value.trim();
    const wasEdited = edited !== originalProposal && edited !== "";
    const editedReply = edited || null;

    sendWS("approve", { thread_id: currentReviewThreadId, edited_reply: editedReply });

    btnApprove.disabled = true;
    btnReject.disabled = true;

    // Mostrar learning feedback inmediatamente
    showLearningFeedback(wasEdited, nodeState.corrections_count || 0);
  });

  btnReject.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    sendWS("reject", { thread_id: currentReviewThreadId });
    notify("Mensaje rechazado");
  });

  btnReviewClose.addEventListener("click", hideReview);

  function showLearningFeedback(wasEdited, prevCorrections) {
    const next = prevCorrections + 1;
    const toNext = 5 - (next % 5);

    let html = "";
    if (wasEdited) {
      html = `
        <strong>✦ Señal de aprendizaje registrada</strong>
        <span>El agente tomó nota de tu corrección.</span>
      `;
    } else {
      html = `
        <strong>✓ Aprobación registrada</strong>
        <span>El agente confirmó este patrón.</span>
      `;
    }

    if (toNext < 5) {
      html += `<span style="color:var(--text-muted);">${toNext} corrección${toNext !== 1 ? "es" : ""} más para extraer nuevos patrones.</span>`;
    } else {
      html += `<span style="color:var(--green);">Extrayendo nuevos patrones de razonamiento…</span>`;
    }

    learningFeedback.innerHTML = html;
    learningFeedback.classList.remove("hidden");

    // Auto-ocultar review después de 2.5s
    setTimeout(() => {
      hideReview();
    }, 2500);
  }

  // ------------------------------------------------------------------
  // Chat input
  // ------------------------------------------------------------------

  btnSend.addEventListener("click", sendChat);

  inputText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });

  inputText.addEventListener("input", () => {
    charCount.textContent = `${inputText.value.length} / 2000`;
  });

  function sendChat() {
    const content = inputText.value.trim();
    if (!content) return;
    upsertCard({
      from_did: "vos",
      content,
      timestamp: new Date().toISOString(),
      type: "chat",
      status: "sent",
      thread_id: "chat-" + Date.now(),
    }, "outbound");
    sendWS("chat", { content });
    inputText.value = "";
    charCount.textContent = "0 / 2000";
  }

  // ------------------------------------------------------------------
  // Status
  // ------------------------------------------------------------------

  function setStatus(state) {
    statusDot.className = `status-dot ${state}`;
    statusText.textContent = { online: "online", offline: "offline", connecting: "conectando…" }[state] || state;
  }

  // ------------------------------------------------------------------
  // Toasts
  // ------------------------------------------------------------------

  function notify(msg, type = "") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity 0.3s";
      setTimeout(() => el.remove(), 300);
    }, 3000);
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function shortenDid(did) {
    if (!did) return "—";
    if (did.startsWith("did:wba:")) {
      const p = did.split(":");
      if (p.length >= 4) return `${p[2]}/${p[3]}`;
    }
    return did.length <= 28 ? did : did.slice(0, 16) + "…" + did.slice(-8);
  }

  function fmtTime(iso) {
    try { return new Date(iso).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" }); }
    catch { return ""; }
  }

  function statusLabel(s) {
    return {
      pending_human_review: "⏳ pendiente",
      auto_approved: "✦ auto-aprobado",
      approved: "✓ aprobado",
      sent: "↑ enviado",
      answered: "✓ respondido",
      rejected: "✗ rechazado",
    }[s] || s || "";
  }

  function typeLabel(t) {
    return {
      thread_message: "mensaje",
      thread_reply: "reply",
      peer_intro: "peer intro",
      capacity_status: "capacidad",
      self_reply: "agente",
      chat: "chat",
    }[t] || t;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  connect();
  setInterval(() => sendWS("get_state"), 30000);

})();
