/* ============================================================
   Esense Node UI — app.js
   ============================================================ */

(function () {
  "use strict";

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let ws = null;
  let wsReconnectTimer = null;
  let currentReviewThreadId = null;
  let pendingCount = 0;
  let currentMood = "moderate";
  let autoApprove = false;
  let nodeState = {};
  let peerMap = {};                // did → peer object (con display_name, alias)
  let pendingApprovalState = null; // { wasEdited, recipientDid } — set on approve click
  const threads = {};              // thread_id → { msg, el: bubble, group: groupEl, direction }
  let lastGroupKey = null;
  let lastGroupEl = null;

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const statusDot          = $("status-dot");
  const statusText         = $("status-text");
  const budgetText         = $("budget-text");
  const peersText          = $("peers-text");
  const didText            = $("did-text");
  const avatarInitials     = $("avatar-initials");
  const moodDot            = $("mood-dot");
  const notifBadge         = $("notif-badge");
  const btnNotif           = $("btn-notif");
  const avatarBtn          = $("avatar-btn");
  const moodDropdown       = $("mood-dropdown");
  const feedEmpty          = $("feed-empty");
  const messagesEl         = $("messages");
  const reviewCard         = $("review-card");
  const reviewFrom         = $("review-from");
  const reviewContent      = $("review-content");
  const reviewProposal     = $("review-proposal");
  const reviewLoading      = $("review-loading");
  const proposalEdit       = $("proposal-edit");
  const diffIndicator      = $("diff-indicator");
  const btnApprove         = $("btn-approve");
  const btnReject          = $("btn-reject");
  const btnReviewClose     = $("btn-review-close");
  const learningFeedback   = $("learning-feedback");
  const sendConfirmation   = $("send-confirmation");
  const reviewLoadingText  = $("review-loading-text");
  const btnAutoApprove     = $("btn-auto-approve");
  const inputText          = $("input-text");
  const btnSend            = $("btn-send");
  const charCount          = $("char-count");
  const maturityFill       = $("maturity-fill");
  const maturityScore      = $("maturity-score");
  const maturityCorrections = $("maturity-corrections");
  const maturityPatterns   = $("maturity-patterns");

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
      loadPeers();
      loadContext();
      loadAutoApprove();
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
        loadPeers();
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
        // Ya no se usa (LLM corre post-aprobación), ignorar silenciosamente
        break;

      case "auto_approved":
        removeThinkingBubble(data.thread_id);
        updateStatus(data.thread_id, "auto_approved");
        notify("Auto-aprobado · " + shortenDid(data.from_did || ""), "info");
        break;

      case "auto_approve_changed":
        setAutoApproveUI(data.enabled);
        break;

      case "agent_error":
        removeThinkingBubble(data.thread_id);
        reviewLoading.classList.add("hidden");
        btnApprove.disabled = false;
        btnReject.disabled = false;
        notify("Error generando respuesta", "error");
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
        removeThinkingBubble(data.thread_id);
        updateStatus(data.thread_id, "approved");
        if (currentReviewThreadId === data.thread_id) {
          reviewLoading.classList.add("hidden");
          if (pendingApprovalState) {
            showLearningFeedback(
              pendingApprovalState.wasEdited,
              nodeState.corrections_count || 0,
              pendingApprovalState.recipientDid,
            );
            pendingApprovalState = null;
          } else {
            hideReview();
          }
        }
        setPending(Math.max(0, pendingCount - 1));
        sendWS("get_pending");
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

      case "thread_history":
        (data.threads || []).forEach((t) => {
          upsertCard({
            thread_id: t.thread_id,
            from_did: t.from_did,
            content: t.last_message,
            timestamp: t.timestamp,
            status: t.status,
          }, "inbound");
        });
        break;

      case "agent_thinking":
        showThinkingBubble(data.thread_id);
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
      // Mostrar solo @node_name en el header, DID completo en tooltip
      const parts = state.did.split(":");
      const nodeName = parts[parts.length - 1] || "node";
      didText.textContent = `@${nodeName}`;
      didText.title = state.did;
      const name = state.node_name || nodeName || "N";
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
    if (typeof state.auto_approve === "boolean") setAutoApproveUI(state.auto_approve);
  }

  // ------------------------------------------------------------------
  // Mood dropdown
  // ------------------------------------------------------------------

  function setMoodUI(mood) {
    currentMood = mood;
    moodDot.className = `mood-dot ${mood}`;
    moodDot.title = { available: "Disponible", moderate: "Moderado", absent: "Ausente", dnd: "No molestar" }[mood] || mood;
    document.querySelectorAll(".mood-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mood === mood);
    });
  }

  // Toggle dropdown on avatar click
  avatarBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    moodDropdown.classList.toggle("hidden");
  });

  // Close dropdown on outside click
  document.addEventListener("click", (e) => {
    if (!moodDropdown.contains(e.target) && e.target !== avatarBtn) {
      moodDropdown.classList.add("hidden");
    }
  });

  // Mood button clicks
  document.querySelectorAll(".mood-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mood = btn.dataset.mood;
      if (mood === currentMood) { moodDropdown.classList.add("hidden"); return; }
      sendWS("set_mood", { mood });
      setMoodUI(mood);
      moodDropdown.classList.add("hidden");
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
  // Feed — grouped by sender
  // ------------------------------------------------------------------

  function showFeed() {
    feedEmpty.style.display = "none";
    messagesEl.style.display = "block";
  }

  function groupKey(direction, fromDid) {
    return `${direction}:${fromDid}`;
  }

  function upsertCard(msg, direction) {
    if (!msg) return;
    const tid = msg.thread_id || ("anon-" + Date.now());
    showFeed();

    // If already exists, just update it
    if (threads[tid]) {
      if (msg.status) updateStatus(tid, msg.status);
      if (msg.proposed_reply) updateReplyBtn(tid, msg.proposed_reply);
      return;
    }

    const fromDid = msg.from_did || "unknown";
    const key = groupKey(direction, fromDid);

    let bubble, groupEl;

    if (lastGroupKey === key && lastGroupEl) {
      // Same sender as the last message — append bubble to existing group
      groupEl = lastGroupEl;
      bubble = buildBubble(msg, direction, tid);
      groupEl.querySelector(".msg-group-body").appendChild(bubble);
    } else {
      // New sender or first message — create new group
      groupEl = buildGroupEl(msg, direction);
      bubble = buildBubble(msg, direction, tid);
      groupEl.querySelector(".msg-group-body").appendChild(bubble);
      messagesEl.prepend(groupEl);
      lastGroupKey = key;
      lastGroupEl = groupEl;
    }

    threads[tid] = { msg, el: bubble, group: groupEl, direction };

    // Wire up review button (ver propuesta del agente)
    const replyBtn = bubble.querySelector(".reply-btn");
    if (replyBtn) {
      replyBtn.addEventListener("click", () => {
        const proposed = replyBtn.dataset.proposed || "";
        showReview({ ...msg, thread_id: tid, proposed_reply: proposed });
        reviewCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }

    // Wire up respond button (abrir panel enviar con DID pre-cargado)
    const respondBtn = bubble.querySelector(".respond-btn");
    if (respondBtn) {
      respondBtn.addEventListener("click", () => {
        const fromDid = respondBtn.dataset.fromDid || "";
        const sendToDid = document.getElementById("send-to-did");
        const sendContent = document.getElementById("send-content");
        const sendPanel = document.getElementById("send-panel");
        if (sendToDid) sendToDid.value = fromDid;
        if (sendContent) sendContent.focus();
        if (sendPanel) sendPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        notify(`Respondiendo a ${shortenDid(fromDid)}`, "info");
      });
    }

    // Wire up delete button
    const deleteBtn = bubble.querySelector(".delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", async () => {
        const threadId = deleteBtn.dataset.tid;
        try {
          await fetch(`/api/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
        } catch (_) { /* si el thread ya no existe, igual borramos de la UI */ }
        // Eliminar burbuja del DOM
        const t = threads[threadId];
        if (t) {
          const groupBody = t.group.querySelector(".msg-group-body");
          t.el.remove();
          delete threads[threadId];
          // Si el grupo quedó vacío, quitarlo también
          if (!groupBody.querySelector(".msg-bubble")) {
            t.group.remove();
            if (lastGroupEl === t.group) { lastGroupKey = null; lastGroupEl = null; }
          }
        }
        // Si el feed quedó vacío, mostrar el empty state
        if (!messagesEl.querySelector(".msg-bubble")) {
          feedEmpty.style.display = "";
          messagesEl.style.display = "none";
        }
        // Si era el mensaje en review, cerrar el card
        if (currentReviewThreadId === threadId) hideReview();
      });
    }
  }

  function buildGroupEl(msg, direction) {
    const el = document.createElement("div");
    el.className = `msg-group ${direction}`;

    const fromDid = msg.from_did || "unknown";
    const label = direction === "self"     ? "tu agente"
                : direction === "outbound" ? "vos"
                : shortenDid(fromDid);
    const ini    = label[0].toUpperCase();
    const avCls  = direction === "self"     ? "self-av"
                 : direction === "outbound" ? "outbound-av" : "";
    const fromCls = direction === "self"     ? "self-lbl"
                  : direction === "outbound" ? "outbound-lbl" : "";

    el.innerHTML = `
      <div class="msg-group-header">
        <div class="msg-avatar ${avCls}">${esc(ini)}</div>
        <span class="msg-from ${fromCls}" title="${esc(fromDid)}">${esc(label)}</span>
        <span class="msg-group-count hidden"></span>
        <button class="msg-collapse-btn" title="Colapsar">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="18 15 12 9 6 15"/>
          </svg>
        </button>
      </div>
      <div class="msg-group-body"></div>
    `;

    el.querySelector(".msg-collapse-btn").addEventListener("click", () => {
      const collapsed = el.classList.toggle("collapsed");
      const body = el.querySelector(".msg-group-body");
      const countEl = el.querySelector(".msg-group-count");
      const n = body.querySelectorAll(".msg-bubble").length;
      countEl.textContent = `${n} msg${n !== 1 ? "s" : ""}`;
      countEl.classList.toggle("hidden", !collapsed);
    });

    return el;
  }

  function buildBubble(msg, direction, tid) {
    const el = document.createElement("div");
    el.className = "msg-bubble";
    el.dataset.threadId = tid;

    const time      = msg.timestamp ? fmtTime(msg.timestamp) : "";
    const isPending = msg.status === "pending_human_review";

    el.innerHTML = `
      <div class="msg-content">${esc(msg.content || "")}</div>
      <div class="msg-footer">
        <div class="msg-meta-row">
          <span class="msg-type">${esc(typeLabel(msg.type || ""))}</span>
          <span class="msg-time">${time}</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span class="msg-status ${msg.status || ""}">${statusLabel(msg.status)}</span>
          <div class="msg-actions">
            ${direction === "inbound" ? `
            <button class="msg-action-btn reply-btn ${isPending ? "pending-action" : ""}"
                    data-tid="${esc(tid)}"
                    data-proposed="${esc(msg.proposed_reply || "")}">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>
              </svg>
              ${isPending ? "Revisar" : "Ver"}
            </button>
            <button class="msg-action-btn respond-btn"
                    data-tid="${esc(tid)}"
                    data-from-did="${esc(msg.from_did || '')}"
                    title="Responder directamente">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Responder
            </button>` : ""}
            <button class="msg-action-btn delete-btn"
                    data-tid="${esc(tid)}"
                    title="Eliminar mensaje">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                <path d="M10 11v6"/><path d="M14 11v6"/>
                <path d="M9 6V4h6v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    `;
    return el;
  }

  function updateStatus(tid, status) {
    const t = threads[tid];
    if (!t) return;
    const el = t.el.querySelector(".msg-status");
    if (el) { el.className = `msg-status ${status}`; el.textContent = statusLabel(status); }
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
    pendingApprovalState = null;

    reviewFrom.textContent = shortenDid(msg.from_did || "desconocido");
    reviewFrom.title = msg.from_did || "";
    reviewContent.textContent = msg.content || "";

    learningFeedback.classList.add("hidden");
    learningFeedback.innerHTML = "";
    sendConfirmation.classList.add("hidden");
    sendConfirmation.innerHTML = "";
    btnApprove.disabled = false;
    btnReject.disabled = false;
    diffIndicator.classList.add("hidden");

    // Textarea vacía para respuesta opcional del usuario
    proposalEdit.value = "";
    proposalEdit.classList.remove("edited");
    reviewLoading.classList.add("hidden");
    reviewProposal.classList.remove("hidden");

    reviewCard.classList.remove("hidden");
  }

  function hideReview() {
    reviewCard.classList.add("hidden");
    currentReviewThreadId = null;
    originalProposal = "";
  }

  proposalEdit.addEventListener("input", () => {
    const hasContent = proposalEdit.value.trim() !== "";
    proposalEdit.classList.toggle("edited", hasContent);
    diffIndicator.classList.toggle("hidden", !hasContent);
  });

  // ------------------------------------------------------------------
  // Approve / Reject
  // ------------------------------------------------------------------

  btnApprove.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    const manualReply = proposalEdit.value.trim() || null;
    const wasEdited   = !!manualReply;
    const recipientDid = threads[currentReviewThreadId]?.msg?.from_did || "";

    // Guardar estado para cuando llegue el "approved" del servidor
    pendingApprovalState = { wasEdited, recipientDid };

    // Mostrar estado de procesamiento
    if (reviewLoadingText) reviewLoadingText.textContent = wasEdited ? "Enviando…" : "Generando respuesta…";
    reviewLoading.classList.remove("hidden");
    reviewProposal.classList.add("hidden");
    btnApprove.disabled = true;
    btnReject.disabled = true;

    sendWS("approve", { thread_id: currentReviewThreadId, edited_reply: manualReply });
  });

  btnReject.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    sendWS("reject", { thread_id: currentReviewThreadId });
    notify("Mensaje rechazado");
  });

  btnReviewClose.addEventListener("click", hideReview);

  function showLearningFeedback(wasEdited, prevCorrections, recipientDid) {
    const next  = prevCorrections + 1;
    const toNext = 5 - (next % 5);

    // Confirmación de envío (persistente)
    const recipient = shortenDid(recipientDid || "");
    sendConfirmation.innerHTML = `
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
      Respuesta enviada a <strong>${esc(recipient)}</strong>
    `;
    sendConfirmation.classList.remove("hidden");

    // Feedback de aprendizaje
    let html = wasEdited
      ? `<strong>✦ Señal de aprendizaje registrada</strong><span>El agente tomó nota de tu corrección.</span>`
      : `<strong>✓ Aprobación registrada</strong><span>El agente confirmó este patrón.</span>`;

    html += toNext < 5
      ? `<span style="color:var(--text-muted);">${toNext} corrección${toNext !== 1 ? "es" : ""} más para extraer nuevos patrones.</span>`
      : `<span style="color:var(--green);">Extrayendo nuevos patrones de razonamiento…</span>`;

    learningFeedback.innerHTML = html;
    learningFeedback.classList.remove("hidden");
    // Ya no se cierra automáticamente — el usuario cierra con el botón ×
  }

  // ------------------------------------------------------------------
  // Send message panel
  // ------------------------------------------------------------------

  document.getElementById('btn-send-msg').onclick = async () => {
    const to_did = document.getElementById('send-to-did').value.trim();
    const content = document.getElementById('send-content').value.trim();
    const statusEl = document.getElementById('send-status');
    if (!to_did || !content) return;
    statusEl.textContent = 'Enviando…';
    statusEl.className = 'send-status sending';
    try {
      const resp = await fetch('/api/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({to_did, content}),
      });
      const data = await resp.json();
      if (data.status === 'sent') {
        notify('Mensaje enviado ✓', 'success');
        document.getElementById('send-content').value = '';
        statusEl.textContent = '';
        statusEl.className = 'send-status';
      } else {
        statusEl.textContent = 'Error al enviar';
        statusEl.className = 'send-status error';
        notify('Error al enviar', 'error');
      }
    } catch (err) {
      statusEl.textContent = 'Error de red';
      statusEl.className = 'send-status error';
      notify('Error de red', 'error');
    }
  };

  // ------------------------------------------------------------------
  // Peers panel
  // ------------------------------------------------------------------

  async function loadPeers() {
    try {
      const resp = await fetch('/api/peers');
      if (!resp.ok) return;
      const peers = await resp.json();

      // Actualizar peerMap global para que shortenDid resuelva alias
      peerMap = peers.reduce((m, p) => ({ ...m, [p.did]: p }), {});

      const list = document.getElementById('peers-list');
      const badge = document.getElementById('peer-count-badge');
      badge.textContent = peers.length;
      list.innerHTML = '';
      if (!peers.length) {
        list.innerHTML = '<li class="peer-empty">Sin peers conocidos</li>';
        return;
      }
      peers.forEach((peer) => {
        const trust = peer.trust_score != null ? peer.trust_score : 0.5;
        const pct = Math.round(trust * 100);
        const displayName = peer.display_name || shortenDid(peer.did || '');
        const alias = peer.alias || '';
        const li = document.createElement('li');
        li.className = 'peer-item';
        const isBlocked = !!peer.blocked;
        li.className = `peer-item${isBlocked ? " peer-blocked" : ""}`;
        li.innerHTML = `
          <div class="peer-info">
            <div class="peer-name-row">
              <span class="peer-did" title="${esc(peer.did || '')}">${esc(displayName)}</span>
              <input class="peer-alias-input" value="${esc(alias)}" placeholder="alias (ej: @daniel)" title="Alias para mostrar" data-did="${esc(peer.did || '')}"/>
            </div>
            <div class="trust-bar-wrap">
              <div class="trust-bar" style="width:${pct}%"></div>
            </div>
            <span class="peer-trust">${pct}%</span>
          </div>
          <button class="peer-block-btn ${isBlocked ? "blocked" : ""}" data-did="${esc(peer.did || '')}" title="${isBlocked ? "Desbloquear peer" : "Bloquear peer"}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              ${isBlocked
                ? '<circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>'
                : '<path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/>'}
            </svg>
          </button>
          <button class="peer-remove-btn" data-did="${esc(peer.did || '')}" title="Eliminar peer">×</button>
        `;
        // Guardar alias al hacer blur o Enter
        const aliasInput = li.querySelector('.peer-alias-input');
        const saveAlias = async () => {
          const did = aliasInput.dataset.did;
          const newAlias = aliasInput.value.trim();
          await fetch(`/api/peers/${encodeURIComponent(did)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ alias: newAlias }),
          });
          loadPeers();
        };
        aliasInput.addEventListener('blur', saveAlias);
        aliasInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); saveAlias(); } });

        li.querySelector('.peer-block-btn').addEventListener('click', async () => {
          const did = li.querySelector('.peer-block-btn').dataset.did;
          const nowBlocked = !li.querySelector('.peer-block-btn').classList.contains('blocked');
          await fetch(`/api/peers/${encodeURIComponent(did)}/block`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ blocked: nowBlocked }),
          });
          loadPeers();
          notify(nowBlocked ? `${shortenDid(did)} bloqueado` : `${shortenDid(did)} desbloqueado`, nowBlocked ? 'warning' : 'info');
        });

        li.querySelector('.peer-remove-btn').addEventListener('click', async () => {
          const did = li.querySelector('.peer-remove-btn').dataset.did;
          await fetch(`/api/peers/${encodeURIComponent(did)}`, { method: 'DELETE' });
          loadPeers();
          notify('Peer eliminado');
        });
        list.appendChild(li);
      });
    } catch (err) {
      console.error('loadPeers:', err);
    }
  }

  document.getElementById('btn-add-peer').addEventListener('click', async () => {
    const input = document.getElementById('new-peer-did');
    const did = input.value.trim();
    if (!did) return;
    const resp = await fetch('/api/peers', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({did}),
    });
    if (resp.ok) {
      input.value = '';
      loadPeers();
      notify('Peer agregado', 'success');
    } else {
      notify('Error al agregar peer', 'error');
    }
  });

  document.getElementById('new-peer-did').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('btn-add-peer').click();
  });

  // ------------------------------------------------------------------
  // Auto-approve toggle
  // ------------------------------------------------------------------

  async function loadAutoApprove() {
    try {
      const resp = await fetch("/api/auto-approve");
      if (resp.ok) {
        const data = await resp.json();
        setAutoApproveUI(data.auto_approve);
      }
    } catch (err) {
      console.error("loadAutoApprove:", err);
    }
  }

  function setAutoApproveUI(enabled) {
    autoApprove = enabled;
    if (!btnAutoApprove) return;
    btnAutoApprove.classList.toggle("active", enabled);
    btnAutoApprove.title = enabled
      ? "Auto-aprobación: activada — click para desactivar"
      : "Auto-aprobación: desactivada — click para activar";
  }

  btnAutoApprove?.addEventListener("click", async () => {
    const newVal = !autoApprove;
    try {
      await fetch("/api/auto-approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newVal }),
      });
      setAutoApproveUI(newVal);
      notify(newVal ? "Auto-aprobación activada ⚡" : "Auto-aprobación desactivada", newVal ? "success" : "info");
    } catch (err) {
      notify("Error cambiando auto-aprobación", "error");
    }
  });

  // ------------------------------------------------------------------
  // Chat input
  // ------------------------------------------------------------------

  btnSend.addEventListener("click", sendChat);

  inputText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
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
    // Alias configurado en peers tiene prioridad
    const peer = peerMap[did];
    if (peer?.alias) return peer.alias;
    if (peer?.display_name) return peer.display_name;
    // Fallback: extraer @node_name del DID
    if (did.startsWith("did:wba:")) {
      const p = did.split(":");
      if (p.length >= 4) return `@${p[3]}`;
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
  // Typing indicator
  // ------------------------------------------------------------------

  function showThinkingBubble(thread_id) {
    const t = threads[thread_id];
    if (!t) return;
    const el = t.el;
    if (el.querySelector(".thinking-indicator")) return;
    const indicator = document.createElement("div");
    indicator.className = "thinking-indicator";
    indicator.innerHTML = '<span class="spinner"></span> pensando…';
    el.appendChild(indicator);
  }

  function removeThinkingBubble(thread_id) {
    const t = threads[thread_id];
    if (!t) return;
    const indicator = t.el.querySelector(".thinking-indicator");
    if (indicator) indicator.remove();
  }

  // ------------------------------------------------------------------
  // Context editor
  // ------------------------------------------------------------------

  async function loadContext() {
    try {
      const resp = await fetch("/api/context");
      if (!resp.ok) return;
      const data = await resp.json();
      document.getElementById("context-editor").value = data.content || "";
    } catch (err) {
      console.error("loadContext:", err);
    }
  }

  document.getElementById("btn-save-context").onclick = async () => {
    const content = document.getElementById("context-editor").value;
    const statusEl = document.getElementById("context-save-status");
    try {
      const resp = await fetch("/api/context", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (resp.ok) {
        statusEl.textContent = "Guardado ✓";
        notify("Contexto actualizado", "success");
        sendWS("get_state");
      } else {
        statusEl.textContent = "Error al guardar";
      }
    } catch (err) {
      statusEl.textContent = "Error de red";
    }
    setTimeout(() => { statusEl.textContent = ""; }, 3000);
  };

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  connect();
  setInterval(() => sendWS("get_state"), 30000);

})();
