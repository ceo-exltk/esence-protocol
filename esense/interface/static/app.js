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
  let obStep = 0;                  // onboarding current step index
  const obAnswers = {};            // { identity, style, topics, requests, limits, notes }
  const threads = {};              // thread_id → { msg, el: bubble, group: groupEl, direction, peerDid }
  const nodeGroups = {};           // peerDid → { el, tids: [], did, direction }
  let currentThreadPeer = null;    // DID of peer whose thread panel is open
  const activeStreams = {};        // stream_id → { tid, contentEl, text }
  let _wsErrNotified = false;      // anti-spam para errores de WS
  let currentTheme = "dark";       // dark | light

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const statusDot          = $("status-dot");
  const statusText         = $("status-text");
  const budgetText         = $("budget-text");
  const peersText          = $("peers-text");
  const profileLink        = $("profile-link");
  const avatarInitials     = $("avatar-initials");
  const moodDot            = $("mood-dot");
  const notifBadge         = $("notif-badge");
  const btnNotif           = $("btn-notif");
  const btnTheme           = $("btn-theme");
  const btnSettings        = $("btn-settings");
  const settingsDrawer     = $("settings-drawer");
  const btnCloseSettings   = $("btn-close-settings");
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
  const threadPanel        = $("thread-panel");
  const threadMessages     = $("thread-messages");
  const threadPanelName    = $("thread-panel-name");
  const threadPanelDid     = $("thread-panel-did");
  const threadReplyText    = $("thread-reply-text");
  const btnThreadClose     = $("btn-thread-close");
  const btnThreadReply     = $("btn-thread-reply");

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);
    setStatus("connecting");

    ws.onopen = () => {
      setStatus("online");
      _wsErrNotified = false;
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
    ws.onerror = () => {
      setStatus("offline");
      if (!_wsErrNotified) { notify("Conexión perdida con el nodo", "error"); _wsErrNotified = true; }
    };
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
          sendBrowserNotif(
            `Mensaje de ${shortenDid(data.from_did)}`,
            (data.content || "").slice(0, 80),
            () => { if (!currentReviewThreadId) showReview(data); }
          );
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
        // Fallback (non-streaming) — used if streaming fails
        upsertCard({
          from_did: "tu agente",
          content: data.content,
          timestamp: new Date().toISOString(),
          type: "self_reply",
          status: "answered",
          thread_id: "self-" + Date.now(),
        }, "self");
        break;

      case "agent_reply_start": {
        const tid = "stream-" + data.stream_id;
        upsertCard({
          from_did: "tu agente",
          content: "",
          timestamp: new Date().toISOString(),
          type: "self_reply",
          status: "answered",
          thread_id: tid,
        }, "self");
        const t = threads[tid];
        if (t) {
          const contentEl = t.el.querySelector(".msg-content");
          // Add a blinking cursor
          const cursor = document.createElement("span");
          cursor.className = "stream-cursor";
          contentEl.appendChild(cursor);
          activeStreams[data.stream_id] = { tid, contentEl, text: "" };
        }
        break;
      }

      case "agent_reply_chunk": {
        const stream = activeStreams[data.stream_id];
        if (stream) {
          stream.text += data.chunk;
          // Update text node before the cursor
          const cursor = stream.contentEl.querySelector(".stream-cursor");
          if (cursor) {
            cursor.before(document.createTextNode(data.chunk));
          } else {
            stream.contentEl.textContent = stream.text;
          }
        }
        break;
      }

      case "agent_reply_done": {
        const stream = activeStreams[data.stream_id];
        if (stream) {
          stream.contentEl.textContent = data.content || stream.text;
          delete activeStreams[data.stream_id];
        }
        break;
      }

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
        // Refresh thread panel pending banner if it's open for this peer
        if (currentThreadPeer) {
          const t = threads[data.thread_id];
          if (t?.peerDid === currentThreadPeer) {
            renderPendingBanner(currentThreadPeer);
            updateApproveAllBtn(currentThreadPeer);
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

      case "onboarding_complete":
        hideOnboarding();
        notify("Esencia guardada ✦ Tu agente ya sabe quién sos", "success");
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
      const parts = state.did.split(":");
      const nodeName = parts[parts.length - 1] || "node";
      if (profileLink) {
        profileLink.textContent = `@${nodeName}`;
        profileLink.title = `Ver perfil público · ${state.did}`;
        profileLink.href = `/@${nodeName}`;
      }
      const name = state.node_name || nodeName || "N";
      if (avatarInitials) avatarInitials.textContent = name[0].toUpperCase();
    }

    if (state.budget && budgetText) {
      const used = state.budget.used_tokens || 0;
      const lim  = state.budget.monthly_limit_tokens || 500_000;
      budgetText.textContent = `${Math.round(used / lim * 100)}% budget`;
    }

    if (typeof state.peer_count === "number" && peersText)
      peersText.textContent = `${state.peer_count} peer${state.peer_count !== 1 ? "s" : ""}`;

    if (typeof state.maturity === "number") {
      const pct = Math.round(state.maturity * 100);
      if (maturityFill) maturityFill.style.width = `${pct}%`;
      if (maturityScore) maturityScore.textContent = `${state.maturity_label || ""} · ${pct}%`;
    }

    if (state.corrections_count !== undefined && maturityCorrections)
      maturityCorrections.textContent = `${state.corrections_count} correcciones`;
    if (state.patterns_count !== undefined && maturityPatterns)
      maturityPatterns.textContent = `${state.patterns_count} patrones`;

    if (state.mood) setMoodUI(state.mood);
    if (typeof state.auto_approve === "boolean") setAutoApproveUI(state.auto_approve);
    if (state.onboarding_complete === false) showOnboarding();
  }

  // ------------------------------------------------------------------
  // Mood dropdown
  // ------------------------------------------------------------------

  function setMoodUI(mood) {
    currentMood = mood;
    if (moodDot) {
      moodDot.className = `mood-dot ${mood}`;
      moodDot.title = { available: "Disponible", moderate: "Moderado", absent: "Ausente", dnd: "No molestar" }[mood] || mood;
    }
    document.querySelectorAll(".mood-btn, .mood-btn-simple").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mood === mood);
    });
  }

  // Toggle dropdown on avatar click (legacy — avatar-btn no longer exists in new layout)
  if (avatarBtn && moodDropdown) {
    avatarBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      moodDropdown.classList.toggle("hidden");
      avatarBtn.setAttribute("aria-expanded", String(!moodDropdown.classList.contains("hidden")));
    });

    // Close dropdown on outside click
    document.addEventListener("click", (e) => {
      if (!moodDropdown.contains(e.target) && e.target !== avatarBtn) {
        moodDropdown.classList.add("hidden");
        avatarBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Mood button clicks (handles both old .mood-btn and new .mood-btn-simple)
  document.querySelectorAll(".mood-btn, .mood-btn-simple").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mood = btn.dataset.mood;
      if (mood === currentMood) { moodDropdown?.classList.add("hidden"); return; }
      sendWS("set_mood", { mood });
      setMoodUI(mood);
      moodDropdown?.classList.add("hidden");
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
    updateFaviconBadge(pendingCount);
    document.title = pendingCount > 0 ? `(${pendingCount}) Esense Node` : "Esense Node";
  }

  btnNotif?.addEventListener("click", () => sendWS("get_pending"));

  // Settings drawer
  function openSettings() {
    settingsDrawer?.classList.remove("hidden");
    btnSettings?.setAttribute("aria-expanded", "true");
  }
  function closeSettings() {
    settingsDrawer?.classList.add("hidden");
    btnSettings?.setAttribute("aria-expanded", "false");
  }
  btnSettings?.addEventListener("click", () => {
    if (settingsDrawer?.classList.contains("hidden")) openSettings();
    else closeSettings();
  });
  btnCloseSettings?.addEventListener("click", closeSettings);
  document.addEventListener("click", (e) => {
    if (settingsDrawer && !settingsDrawer.contains(e.target) && btnSettings && !btnSettings.contains(e.target)) {
      closeSettings();
    }
  });

  // Theme toggle
  function initTheme() {
    const saved = localStorage.getItem("theme") || "dark";
    currentTheme = saved;
    document.documentElement.setAttribute("data-theme", saved);
    console.log("[Theme] Initialized with:", saved);
  }
  function toggleTheme() {
    currentTheme = currentTheme === "dark" ? "light" : "dark";
    console.log("[Theme] Toggled to:", currentTheme);
    document.documentElement.setAttribute("data-theme", currentTheme);
    localStorage.setItem("theme", currentTheme);
  }
  if (btnTheme) {
    btnTheme.addEventListener("click", toggleTheme);
    console.log("[Theme] Listener attached to btnTheme");
  } else {
    console.warn("[Theme] btnTheme not found!");
  }

  // ------------------------------------------------------------------
  // Feed — grouped by sender
  // ------------------------------------------------------------------

  function showFeed() {
    feedEmpty.style.display = "none";
    messagesEl.style.display = "block";
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
    // Peer key: for inbound = sender, for outbound = recipient, for self-chat = "self"
    const peerDid = direction === "inbound" ? fromDid
                  : direction === "outbound" ? (msg.to_did || fromDid)
                  : "self";

    let groupEl;
    if (nodeGroups[peerDid]) {
      groupEl = nodeGroups[peerDid].el;
      nodeGroups[peerDid].tids.push(tid);
      messagesEl.prepend(groupEl); // move to top (most recent)
    } else {
      groupEl = buildGroupEl(msg, direction, peerDid);
      nodeGroups[peerDid] = { el: groupEl, did: peerDid, tids: [tid], direction };
      messagesEl.prepend(groupEl);
    }

    const bubble = buildBubble(msg, direction, tid);
    groupEl.querySelector(".msg-group-body").appendChild(bubble);

    // Update group count + time in header
    const ng = nodeGroups[peerDid];
    const countEl = groupEl.querySelector(".msg-group-count");
    if (countEl) { countEl.textContent = ng.tids.length; countEl.classList.remove("hidden"); }
    const timeEl = groupEl.querySelector(".msg-group-last-time");
    if (timeEl && msg.timestamp) timeEl.textContent = fmtTime(msg.timestamp);

    threads[tid] = { msg, el: bubble, group: groupEl, direction, peerDid };

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
          // Remove tid from nodeGroups
          const ng = nodeGroups[t.peerDid];
          if (ng) ng.tids = ng.tids.filter((x) => x !== threadId);
          delete threads[threadId];
          // Si el grupo quedó vacío, quitarlo también
          if (!groupBody.querySelector(".msg-bubble")) {
            t.group.remove();
            delete nodeGroups[t.peerDid];
          } else {
            // Update count badge
            const countEl = t.group.querySelector(".msg-group-count");
            if (countEl && ng) countEl.textContent = ng.tids.length;
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

  function buildGroupEl(msg, direction, peerDid) {
    const el = document.createElement("div");
    el.className = `msg-group ${direction}`;

    const fromDid = msg.from_did || "unknown";
    const label = peerDid === "self"   ? "tu agente"
                : direction === "outbound" ? "vos → " + shortenDid(msg.to_did || "")
                : shortenDid(fromDid);
    const ini    = label[0].toUpperCase();
    const avCls  = peerDid === "self"      ? "self-av"
                 : direction === "outbound" ? "outbound-av" : "";
    const fromCls = peerDid === "self"      ? "self-lbl"
                  : direction === "outbound" ? "outbound-lbl" : "";

    el.innerHTML = `
      <div class="msg-group-header" title="Abrir conversación">
        <div class="msg-avatar ${avCls}">${esc(ini)}</div>
        <div class="msg-group-meta">
          <span class="msg-from ${fromCls}" title="${esc(fromDid)}">${esc(label)}</span>
          <span class="msg-group-last-time"></span>
        </div>
        <span class="msg-group-count hidden">0</span>
        <button class="msg-collapse-btn" title="Colapsar">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="18 15 12 9 6 15"/>
          </svg>
        </button>
      </div>
      <div class="msg-group-body"></div>
    `;

    // Collapse button (stop propagation so it doesn't open thread panel)
    el.querySelector(".msg-collapse-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      el.classList.toggle("collapsed");
    });

    // Click on header → open thread panel (only for inbound peer conversations)
    const header = el.querySelector(".msg-group-header");
    if (direction === "inbound" && peerDid !== "self") {
      header.style.cursor = "pointer";
      header.addEventListener("click", () => openThreadPanel(peerDid));
    }

    return el;
  }

  function buildBubble(msg, direction, tid) {
    const el = document.createElement("div");
    el.className = "msg-bubble";
    el.dataset.threadId = tid;

    const time      = msg.timestamp ? fmtTime(msg.timestamp) : "";
    const isPending = msg.status === "pending_human_review";
    const contentHtml = direction === "self" ? renderMarkdown(msg.content || "") : esc(msg.content || "");

    el.innerHTML = `
      <div class="msg-content">${contentHtml}</div>
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
      reviewCard?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
  }

  // ------------------------------------------------------------------
  // Review card
  // ------------------------------------------------------------------

  function showReview(msg) {
    currentReviewThreadId = msg.thread_id;
    pendingApprovalState = null;

    if (reviewFrom) reviewFrom.textContent = shortenDid(msg.from_did || "desconocido");
    if (reviewFrom) reviewFrom.title = msg.from_did || "";
    if (reviewContent) reviewContent.textContent = msg.content || "";

    if (learningFeedback) { learningFeedback.classList.add("hidden"); learningFeedback.innerHTML = ""; }
    if (sendConfirmation) { sendConfirmation.classList.add("hidden"); sendConfirmation.innerHTML = ""; }
    if (btnApprove) btnApprove.disabled = false;
    if (btnReject) btnReject.disabled = false;
    if (diffIndicator) diffIndicator.classList.add("hidden");

    // Textarea vacía para respuesta opcional del usuario
    if (proposalEdit) { proposalEdit.value = ""; proposalEdit.classList.remove("edited"); }
    if (reviewLoading) reviewLoading.classList.add("hidden");
    if (reviewProposal) reviewProposal.classList.remove("hidden");

    if (reviewCard) { reviewCard.classList.remove("hidden"); reviewCard.scrollIntoView?.({ behavior: "smooth", block: "nearest" }); }
  }

  function hideReview() {
    if (reviewCard) reviewCard.classList.add("hidden");
    currentReviewThreadId = null;
  }

  proposalEdit?.addEventListener("input", () => {
    const hasContent = proposalEdit.value.trim() !== "";
    proposalEdit.classList.toggle("edited", hasContent);
    diffIndicator?.classList.toggle("hidden", !hasContent);
  });

  // ------------------------------------------------------------------
  // Approve / Reject
  // ------------------------------------------------------------------

  btnApprove?.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    const manualReply = proposalEdit?.value.trim() || null;
    const wasEdited   = !!manualReply;
    const recipientDid = threads[currentReviewThreadId]?.msg?.from_did || "";

    // Guardar estado para cuando llegue el "approved" del servidor
    pendingApprovalState = { wasEdited, recipientDid };

    // Mostrar estado de procesamiento
    if (reviewLoadingText) reviewLoadingText.textContent = wasEdited ? "Enviando…" : "Generando respuesta…";
    reviewLoading?.classList.remove("hidden");
    reviewProposal?.classList.add("hidden");
    if (btnApprove) btnApprove.disabled = true;
    if (btnReject) btnReject.disabled = true;

    sendWS("approve", { thread_id: currentReviewThreadId, edited_reply: manualReply });
  });

  btnReject?.addEventListener("click", () => {
    if (!currentReviewThreadId) return;
    if (!confirm("¿Rechazar este mensaje? No se puede deshacer.")) return;
    sendWS("reject", { thread_id: currentReviewThreadId });
    notify("Mensaje rechazado");
  });

  btnReviewClose?.addEventListener("click", hideReview);

  const btnCancelGeneration = $("btn-cancel-generation");
  btnCancelGeneration?.addEventListener("click", () => {
    reviewLoading.classList.add("hidden");
    reviewProposal.classList.remove("hidden");
    btnApprove.disabled = false; btnReject.disabled = false;
    notify("Generación cancelada — podés rechazar manualmente", "info");
  });

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
  // Send message panel (legacy — no longer exists in new layout)
  // ------------------------------------------------------------------

  const btnSendMsg = document.getElementById('btn-send-msg');
  if (btnSendMsg) {
    btnSendMsg.onclick = async () => {
      const to_did = document.getElementById('send-to-did')?.value.trim();
      const content = document.getElementById('send-content')?.value.trim();
      const statusEl = document.getElementById('send-status');
      if (!to_did || !content) return;
      if (statusEl) statusEl.textContent = 'Enviando…';
      if (statusEl) statusEl.className = 'send-status sending';
      try {
        const resp = await fetch('/api/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({to_did, content}),
        });
        const data = await resp.json();
        if (data.status === 'sent') {
          notify('Mensaje enviado ✓', 'success');
          const sendContentEl = document.getElementById('send-content');
          if (sendContentEl) sendContentEl.value = '';
          if (statusEl) statusEl.textContent = '';
          if (statusEl) statusEl.className = 'send-status';
        } else {
          if (statusEl) statusEl.textContent = 'Error al enviar';
          if (statusEl) statusEl.className = 'send-status error';
          notify('Error al enviar', 'error');
        }
      } catch (err) {
        if (statusEl) statusEl.textContent = 'Error de red';
        if (statusEl) statusEl.className = 'send-status error';
        notify('Error de red', 'error');
      }
    };
  }

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
      if (!list) return; // Legacy element no longer in new layout
      if (badge) badge.textContent = peers.length;
      list.innerHTML = '';
      if (!peers.length) {
        list.innerHTML = '<li class="peer-empty">Sin peers — agregá el primero abajo.</li>';
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
          try {
            const resp = await fetch(`/api/peers/${encodeURIComponent(did)}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ alias: newAlias }),
            });
            if (resp.ok) { notify("Alias guardado", "success"); loadPeers(); }
            else { notify("Error guardando alias", "error"); }
          } catch (e) { notify("Error guardando alias", "error"); }
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
      notify("No se pudo cargar peers", "error");
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
  // Onboarding wizard
  // ------------------------------------------------------------------

  const OB_STEPS = [
    {
      key: "identity", required: true, type: "text",
      num: "01", question: "¿Quién sos?",
      hint: "Tu agente va a representarte. Contale brevemente a qué te dedicás y cuál es tu rol.",
      placeholder: "Soy desarrollador de software, fundador de Esense Protocol…",
    },
    {
      key: "style", required: true, type: "choice",
      num: "02", question: "¿Cómo comunicás?",
      hint: "Elegí el estilo que mejor te describe. Tu agente va a usarlo por defecto.",
      choices: [
        { icon: "⚡", label: "Directo y conciso",   desc: "Al punto, sin rodeos",           value: "Directo y conciso — va al punto sin rodeos." },
        { icon: "◎", label: "Detallado y analítico", desc: "Contexto y porqués",            value: "Detallado y analítico — explica el contexto y los porqués." },
        { icon: "✦", label: "Cálido y cercano",     desc: "Conexión humana primero",        value: "Cálido y cercano — prioriza la conexión humana." },
        { icon: "//", label: "Técnico y preciso",   desc: "Exactitud sobre todo",           value: "Técnico y preciso — la exactitud es lo más importante." },
      ],
    },
    {
      key: "topics", required: true, type: "text",
      num: "03", question: "¿Sobre qué sos experto?",
      hint: "Temas en los que tu agente puede responder con autoridad.",
      placeholder: "tecnología, startups, diseño de producto, filosofía…",
    },
    {
      key: "requests", required: false, type: "text",
      num: "04", question: "¿Cómo respondés ante pedidos?",
      hint: "Cuando alguien te pide algo, ¿qué evaluás antes de decir que sí?",
      placeholder: "Me fijo si es urgente, si puedo ayudar de verdad, si se alinea con mis prioridades…",
    },
    {
      key: "limits", required: false, type: "text",
      num: "05", question: "¿Qué no querés responder?",
      hint: "Tu agente va a rechazar o ignorar estos mensajes automáticamente.",
      placeholder: "spam, pedidos de gente que no conozco, propaganda política…",
    },
    {
      key: "notes", required: false, type: "text",
      num: "06", question: "¿Algo más que deba saber?",
      hint: "Cualquier cosa que ayude a tu agente a representarte mejor.",
      placeholder: "Prefiero responder tarde pero bien. No me gustan los saludos formales…",
    },
  ];

  const obOverlay  = document.getElementById("onboarding-overlay");
  const obBody     = document.getElementById("onboarding-body");
  const obBar      = document.getElementById("onboarding-bar");
  const obStepNum  = document.getElementById("onboarding-step-num");
  const btnObNext  = document.getElementById("btn-ob-next");
  const btnObSkip  = document.getElementById("btn-ob-skip");
  const btnObLater = document.getElementById("btn-ob-later");

  function showOnboarding() {
    obStep = 0;
    obOverlay.classList.remove("hidden");
    trapFocus(obOverlay);
    renderObStep();
  }

  function hideOnboarding() {
    releaseFocusTrap();
    obOverlay.classList.add("hidden");
  }

  function renderObStep() {
    const step = OB_STEPS[obStep];
    const total = OB_STEPS.length;
    const pct = Math.round(((obStep + 1) / total) * 100);
    obBar.style.width = `${pct}%`;
    obStepNum.textContent = `${obStep + 1} / ${total}`;
    btnObSkip.style.display = step.required ? "none" : "";
    btnObNext.textContent = obStep === total - 1 ? "Empezar →" : "Siguiente →";
    const btnObPrev = $("btn-ob-prev");
    if (btnObPrev) btnObPrev.style.display = obStep > 0 ? "" : "none";

    if (step.type === "text") {
      obBody.innerHTML = `
        <div class="ob-step">
          <div class="ob-num">${esc(step.num)}</div>
          <h2 class="ob-question">${esc(step.question)}</h2>
          <p class="ob-hint">${esc(step.hint)}</p>
          <textarea class="ob-textarea" id="ob-input" rows="4"
            placeholder="${esc(step.placeholder || "")}"
          >${esc(obAnswers[step.key] || "")}</textarea>
        </div>
      `;
      setTimeout(() => document.getElementById("ob-input")?.focus(), 50);
    } else if (step.type === "choice") {
      const choicesHtml = step.choices.map((c) => `
        <button class="ob-choice ${obAnswers[step.key] === c.value ? "selected" : ""}"
                data-value="${esc(c.value)}">
          <span class="ob-choice-icon">${esc(c.icon)}</span>
          <div class="ob-choice-text">
            <strong>${esc(c.label)}</strong>
            <span>${esc(c.desc)}</span>
          </div>
        </button>
      `).join("");
      obBody.innerHTML = `
        <div class="ob-step">
          <div class="ob-num">${esc(step.num)}</div>
          <h2 class="ob-question">${esc(step.question)}</h2>
          <p class="ob-hint">${esc(step.hint)}</p>
          <div class="ob-choices">${choicesHtml}</div>
        </div>
      `;
      obBody.querySelectorAll(".ob-choice").forEach((btn) => {
        btn.addEventListener("click", () => {
          obBody.querySelectorAll(".ob-choice").forEach((b) => b.classList.remove("selected"));
          btn.classList.add("selected");
          obAnswers[step.key] = btn.dataset.value;
        });
      });
    }
  }

  function obAdvance() {
    const step = OB_STEPS[obStep];
    // Leer valor del input si es text
    if (step.type === "text") {
      const val = document.getElementById("ob-input")?.value.trim() || "";
      if (step.required && !val) {
        document.getElementById("ob-input")?.classList.add("ob-required-shake");
        let errorMsg = obBody.querySelector(".ob-error-msg");
        if (!errorMsg) {
          errorMsg = document.createElement("p");
          errorMsg.className = "ob-error-msg";
          errorMsg.textContent = "Este campo es requerido para continuar.";
          errorMsg.style.color = "var(--red)"; errorMsg.style.fontSize = "12px"; errorMsg.style.marginTop = "8px";
          document.getElementById("ob-input")?.parentNode.appendChild(errorMsg);
          setTimeout(() => errorMsg.remove(), 3000);
        }
        setTimeout(() => document.getElementById("ob-input")?.classList.remove("ob-required-shake"), 600);
        return;
      }
      obAnswers[step.key] = val;
    } else if (step.type === "choice" && step.required && !obAnswers[step.key]) {
      obBody.querySelector(".ob-choices")?.classList.add("ob-required-shake");
      setTimeout(() => obBody.querySelector(".ob-choices")?.classList.remove("ob-required-shake"), 600);
      return;
    }

    if (obStep < OB_STEPS.length - 1) {
      obStep++;
      renderObStep();
    } else {
      submitOnboarding();
    }
  }

  async function submitOnboarding() {
    btnObNext.disabled = true;
    btnObNext.textContent = "Guardando…";
    try {
      const resp = await fetch("/api/onboarding/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: obAnswers }),
      });
      if (resp.ok) {
        obBar.style.width = "100%";
        hideOnboarding();
        notify("Esencia guardada ✦ Tu agente ya sabe quién sos", "success");
      } else {
        notify("Error guardando la esencia", "error");
        btnObNext.disabled = false;
        btnObNext.textContent = "Empezar →";
      }
    } catch {
      notify("Error de red", "error");
      btnObNext.disabled = false;
      btnObNext.textContent = "Empezar →";
    }
  }

  btnObNext?.addEventListener("click", obAdvance);
  btnObSkip?.addEventListener("click", () => {
    obAnswers[OB_STEPS[obStep].key] = "";
    if (obStep < OB_STEPS.length - 1) { obStep++; renderObStep(); }
    else submitOnboarding();
  });
  const btnObPrev = $("btn-ob-prev");
  btnObPrev?.addEventListener("click", () => {
    if (obStep > 0) { obStep--; renderObStep(); }
  });
  btnObLater?.addEventListener("click", async () => {
    // Marcar como completo sin guardar nada — el usuario configurará después
    await fetch("/api/onboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: {} }),
    });
    hideOnboarding();
  });

  // ------------------------------------------------------------------
  // Thread detail panel
  // ------------------------------------------------------------------

  // Returns list of pending thread_ids for a given peerDid
  function getPendingTids(peerDid) {
    const ng = nodeGroups[peerDid];
    return (ng?.tids || []).filter((tid) => {
      const t = threads[tid];
      return t?.msg?.status === "pending_human_review";
    });
  }

  // Renders the pending-messages banner inside the thread panel
  function renderPendingBanner(peerDid) {
    const existing = threadPanel.querySelector(".thread-pending-banner");
    if (existing) existing.remove();

    const pendingTids = getPendingTids(peerDid);
    if (!pendingTids.length) return;

    const banner = document.createElement("div");
    banner.className = "thread-pending-banner";
    banner.innerHTML = `
      <span class="thread-pending-badge">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        ${pendingTids.length} mensaje${pendingTids.length !== 1 ? "s" : ""} pendiente${pendingTids.length !== 1 ? "s" : ""}
      </span>
      <span class="thread-pending-hint">Escribí tu respuesta abajo y aprobá todo de una vez</span>
    `;
    // Insert after header
    threadPanel.querySelector(".thread-panel-header").after(banner);
  }

  async function openThreadPanel(peerDid) {
    currentThreadPeer = peerDid;
    const label = shortenDid(peerDid);
    threadPanelName.textContent = label;
    threadPanelDid.textContent  = peerDid;
    threadMessages.innerHTML = '<div class="thread-loading">Cargando…</div>';
    threadPanel.classList.remove("hidden");
    renderPendingBanner(peerDid);
    updateApproveAllBtn(peerDid);

    // Collect all thread_ids for this peer
    const ng = nodeGroups[peerDid];
    const tids = ng?.tids || [];

    // Fetch full thread data for each thread_id in parallel
    const results = await Promise.allSettled(
      tids.map(tid => fetch(`/api/threads/${encodeURIComponent(tid)}`).then(r => r.ok ? r.json() : null))
    );
    const allMsgs = results.flatMap(r =>
      r.status === "fulfilled" && r.value ? (r.value.messages || []) : []
    );

    // Sort by timestamp
    allMsgs.sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));

    if (!allMsgs.length) {
      threadMessages.innerHTML = '<div class="thread-empty">Sin mensajes</div>';
      return;
    }

    threadMessages.innerHTML = "";
    allMsgs.forEach((m) => {
      const isOwn = m.from_did === nodeState.did || m.direction === "outbound";
      const isPending = m.status === "pending_human_review";
      const row = document.createElement("div");
      row.className = `thread-msg-row ${isOwn ? "mine" : "theirs"}${isPending ? " pending" : ""}`;
      const contentHtml = m.direction === "self" ? renderMarkdown(m.content || "") : esc(m.content || "");
      row.innerHTML = `
        <div class="thread-msg-bubble">${contentHtml}</div>
        <div style="display:flex;gap:6px;align-items:center;">
          <span class="thread-msg-time">${m.timestamp ? fmtTime(m.timestamp) : ""}</span>
          ${m.status ? `<span class="thread-msg-status">${statusLabel(m.status)}</span>` : ""}
        </div>
      `;
      threadMessages.appendChild(row);
    });

    threadMessages.scrollTop = threadMessages.scrollHeight;
    threadReplyText.value = "";
    threadReplyText.focus();
  }

  // Show/hide "Aprobar todo" button depending on pending count
  function updateApproveAllBtn(peerDid) {
    const existing = threadPanel.querySelector(".btn-approve-all");
    const pendingTids = getPendingTids(peerDid || currentThreadPeer);
    if (!existing) return;
    if (pendingTids.length > 0) {
      existing.classList.remove("hidden");
      existing.textContent = `Aprobar ${pendingTids.length > 1 ? `${pendingTids.length} · ` : ""}Enviar`;
    } else {
      existing.classList.add("hidden");
    }
  }

  function closeThreadPanel() {
    threadPanel.classList.add("hidden");
    currentThreadPeer = null;
  }

  btnThreadClose?.addEventListener("click", closeThreadPanel);

  // Approve all pending from this peer with one reply
  async function approveAllPending(content) {
    if (!currentThreadPeer) return;
    const pendingTids = getPendingTids(currentThreadPeer);
    if (!pendingTids.length) return;

    const btn = threadPanel.querySelector(".btn-approve-all");
    if (btn) { btn.disabled = true; btn.textContent = "Enviando…"; }
    btnThreadReply.disabled = true;

    // Approve each pending thread with the same reply (or null for LLM if empty)
    const editedReply = content || null;
    let successCount = 0;
    for (const tid of pendingTids) {
      try {
        await new Promise((resolve) => {
          sendWS("approve", { thread_id: tid, edited_reply: editedReply });
          // Give a short gap between approvals
          setTimeout(resolve, 150);
        });
        successCount++;
      } catch (_) {}
    }

    // Add own message to thread view
    if (content) {
      const row = document.createElement("div");
      row.className = "thread-msg-row mine";
      row.innerHTML = `
        <div class="thread-msg-bubble">${esc(content)}</div>
        <span class="thread-msg-time">${fmtTime(new Date().toISOString())}</span>
      `;
      threadMessages.appendChild(row);
      threadMessages.scrollTop = threadMessages.scrollHeight;
    }

    threadReplyText.value = "";
    notify(`${successCount} mensaje${successCount !== 1 ? "s" : ""} aprobado${successCount !== 1 ? "s" : ""} ✓`, "success");
    if (btn) { btn.disabled = false; btn.classList.add("hidden"); }
    btnThreadReply.disabled = false;
    // Remove pending banner
    threadPanel.querySelector(".thread-pending-banner")?.remove();
  }

  btnThreadReply?.addEventListener("click", async () => {
    const content = threadReplyText.value.trim();
    if (!content || !currentThreadPeer) return;

    // If there are pending messages, use "approve all" flow
    const pendingTids = getPendingTids(currentThreadPeer);
    if (pendingTids.length > 0) {
      await approveAllPending(content);
      return;
    }

    // No pending — just send a new message
    const toDid = currentThreadPeer;
    btnThreadReply.disabled = true;
    try {
      const resp = await fetch("/api/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_did: toDid, content }),
      });
      const data = await resp.json();
      if (data.status === "sent") {
        const row = document.createElement("div");
        row.className = "thread-msg-row mine";
        row.innerHTML = `
          <div class="thread-msg-bubble">${esc(content)}</div>
          <span class="thread-msg-time">${fmtTime(new Date().toISOString())}</span>
        `;
        threadMessages.appendChild(row);
        threadMessages.scrollTop = threadMessages.scrollHeight;
        threadReplyText.value = "";
        notify(`Enviado a ${shortenDid(toDid)} ✓`, "success");
      } else {
        notify("Error al enviar", "error");
      }
    } catch {
      notify("Error de red", "error");
    }
    btnThreadReply.disabled = false;
  });

  threadReplyText?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); btnThreadReply?.click(); }
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
    statusText.textContent = { online: "conectado", offline: "desconectado", connecting: "conectando…" }[state] || state;
  }

  // ------------------------------------------------------------------
  // Toasts
  // ------------------------------------------------------------------

  function notify(msg, type = "") {
    const container = $("toast-container");
    if (!container) return;
    const el = document.createElement("div");
    el.className = `toast${type ? " " + type : ""}`;
    el.textContent = msg;
    container.appendChild(el);
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
      thread_reply: "respuesta",
      peer_intro: "nuevo contacto",
      capacity_status: "estado de red",
      self_reply: "agente",
      chat: "chat",
    }[t] || t;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function renderMarkdown(text) {
    if (!text) return "";
    let s = esc(text);
    s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/_([^_\n]+)_/g, "<em>$1</em>");
    s = s.replace(/\n\n+/g, "<br><br>");
    s = s.replace(/\n/g, "<br>");
    s = s.replace(/(https:\/\/[^\s<"]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    return s;
  }

  // ------------------------------------------------------------------
  // Focus trap utilities
  // ------------------------------------------------------------------

  const FOCUSABLE = 'button:not([disabled]),[href],input,textarea,[tabindex]:not([tabindex="-1"])';
  let _trapEl = null, _trapHandler = null;

  function trapFocus(el) {
    _trapEl = el;
    const nodes = () => [...el.querySelectorAll(FOCUSABLE)];
    _trapHandler = (e) => {
      if (e.key !== "Tab") return;
      const all = nodes(); const first = all[0]; const last = all[all.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    el.addEventListener("keydown", _trapHandler);
    setTimeout(() => nodes()[0]?.focus(), 50);
  }

  function releaseFocusTrap() {
    if (_trapEl) { _trapEl.removeEventListener("keydown", _trapHandler); _trapEl = null; }
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
      notify("No se pudo cargar contexto", "error");
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
  // Browser notifications + favicon badge
  // ------------------------------------------------------------------

  // Request notification permission once the user interacts
  function requestNotifPermission() {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }
  document.addEventListener("click", requestNotifPermission, { once: true });

  function sendBrowserNotif(title, body, onClick) {
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    if (!document.hidden) return; // solo si la pestaña está en background
    const n = new Notification(title, {
      body,
      icon: "/static/favicon.svg",
      badge: "/static/favicon.svg",
      tag: "esense-msg",       // agrupa notificaciones del mismo origen
      renotify: true,
    });
    n.onclick = () => { window.focus(); n.close(); if (onClick) onClick(); };
  }

  // Favicon badge — SVG con número superpuesto
  function updateFaviconBadge(count) {
    const canvas = document.createElement("canvas");
    canvas.width = 32; canvas.height = 32;
    const ctx = canvas.getContext("2d");

    // Base icon: circle
    ctx.beginPath();
    ctx.arc(16, 16, 14, 0, 2 * Math.PI);
    ctx.fillStyle = "#141414";
    ctx.fill();
    ctx.strokeStyle = "#7c6af7";
    ctx.lineWidth = 2;
    ctx.stroke();

    // "e" letter
    ctx.fillStyle = "#7c6af7";
    ctx.font = "bold 16px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("e", 16, 17);

    if (count > 0) {
      // Red badge
      const r = 9;
      const bx = 24, by = 8;
      ctx.beginPath();
      ctx.arc(bx, by, r, 0, 2 * Math.PI);
      ctx.fillStyle = "#ff5252";
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.font = "bold 10px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(count > 9 ? "9+" : String(count), bx, by);
    }

    let link = document.querySelector("link[rel~='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = canvas.toDataURL();
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  initTheme();
  connect();
  setInterval(() => sendWS("get_state"), 30000);
  updateFaviconBadge(0);

})();
