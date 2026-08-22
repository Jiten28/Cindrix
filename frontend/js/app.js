(function () {
  // ---------- theme (light/dark) ----------
  // The actual data-theme attribute is already set (or left absent for the
  // dark default) by the inline script in index.html's <head>, before this
  // file ever loads, so there's no flash-of-wrong-theme here. This just
  // wires the toggle button and keeps everything else in sync when it's
  // pressed. See style.css's :root / [data-theme="light"] blocks for the
  // actual color values (Design.md never documented light-mode hex values
  // — checked docs + git history — so these are a new but Ember-Violet-
  // consistent choice, not a rediscovery of an old one).
  const THEME_KEY = "cindrix-theme";
  const themeToggleBtn = document.getElementById("themeToggleBtn");

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function updateThemeToggleUI(theme) {
    if (!themeToggleBtn) return;
    const next = theme === "light" ? "dark" : "light";
    const key = next === "light" ? "topbar.switchToLight" : "topbar.switchToDark";
    const fallback = next === "light" ? "Switch to light theme" : "Switch to dark theme";
    const label = window.CindrixI18n ? window.CindrixI18n.t(key, fallback) : fallback;
    themeToggleBtn.textContent = theme === "light" ? "☀️" : "🌙";
    themeToggleBtn.setAttribute("aria-label", label);
    themeToggleBtn.title = label;
    // Keep the i18n data attributes pointed at the *next* state's key too,
    // so a language switch (i18n.js's applyTranslations) re-labels this
    // button correctly without needing to know about theme state itself.
    themeToggleBtn.setAttribute("data-i18n-aria-label", key);
    themeToggleBtn.setAttribute("data-i18n-title", key);
  }

  function setTheme(theme, persist) {
    document.documentElement.setAttribute("data-theme", theme);
    if (persist) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (err) { /* private mode etc. */ }
    }
    updateThemeToggleUI(theme);
    // Lets particle-sphere.js / starfield.js re-read the (now-changed)
    // --accent/--text/--star-rgb custom properties instead of staying
    // pinned to whatever they cached at creation time — see those files'
    // "cindrix:themechange" listeners.
    window.dispatchEvent(new CustomEvent("cindrix:themechange", { detail: { theme } }));
  }

  updateThemeToggleUI(currentTheme());
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => {
      setTheme(currentTheme() === "light" ? "dark" : "light", true);
    });
  }

  // Two independent orb instances — landing orb (in-flow, unchanged from
  // Phase 2) and the docked chat orb (fixed, right-center). See
  // particle-sphere.js's factory refactor comment for why these are separate
  // instances rather than one canvas moved between layouts.
  const landingSphere = window.createCindrixSphere("sphere", "sphereState");
  const chatSphere = window.createCindrixSphere("sphereChat", "sphereStateChat");
  // Chat orb isn't shown until a conversation starts — no sense ticking its
  // 220-particle transform every frame before then. See activateChatView()/
  // resetToLanding() for where this flips as the view changes.
  chatSphere.setPaused(true);

  let conversationStarted = false;
  function activeSphere() {
    return conversationStarted ? chatSphere : landingSphere;
  }
  function activeStateLabelEl() {
    return document.getElementById(conversationStarted ? "sphereStateChat" : "sphereState");
  }

  // A plain "click" listener on the overlay closes it even when the click
  // was actually the *end* of a text-selection drag that started inside the
  // modal card and drifted onto the backdrop before mouseup — the click
  // event's target is wherever the mouse released, not where it started.
  // This tracks mousedown and click separately and only closes when BOTH
  // happened directly on the backdrop, so selecting text never closes it.
  function wireOverlayClose(overlay) {
    let mousedownOnBackdrop = false;
    overlay.addEventListener("mousedown", (e) => {
      mousedownOnBackdrop = e.target === overlay;
    });
    overlay.addEventListener("click", (e) => {
      if (mousedownOnBackdrop && e.target === overlay) {
        overlay.hidden = true;
      }
      mousedownOnBackdrop = false;
    });
  }

  const landing = document.getElementById("landing");
  const chatSection = document.getElementById("chat");
  const messagesEl = document.getElementById("messages");
  const composerForm = document.getElementById("composerForm");
  const composerInput = document.getElementById("composerInput");
  const micBtn = document.getElementById("micBtn");
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const sidebarBackdrop = document.getElementById("sidebarBackdrop");
  const newChatBtn = document.getElementById("newChatBtn");
  const chatList = document.getElementById("chatList");
  const appRoot = document.querySelector(".app");

  let currentTitle = null;
  let currentConversationId = null;
  let currentModelId = null;
  let currentUser = null; // null = guest (not logged in)
  let lastUserText = null; // for regenerate

  // ---------- tiny markdown renderer ----------
  // Supports: ```code fences``` (+ hljs highlighting), `inline code`,
  // **bold**, *italic*, ![images](url), tables, headings, horizontal rules,
  // and - / 1. lists. Hand-rolled instead of a library — Gemini's output
  // only ever needs this subset, and escaping HTML first keeps it safe even
  // though the content is model-generated, not directly user-controllable.

  // Also used for every user-controlled value this file interpolates into
  // innerHTML (display names, emails, attribute values) — quotes included,
  // so it's safe inside an attribute as well as in text.
  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderMarkdown(raw) {
    const escaped = escapeHtml(raw);
    const blocks = escaped.split(/```(\w*)\n?([\s\S]*?)```/g);
    // split() with capture groups interleaves: [text, lang, code, text, lang, code, ...]
    let html = "";
    for (let i = 0; i < blocks.length; i += 3) {
      const text = blocks[i] || "";
      html += formatBlockText(text);
      if (blocks[i + 2] !== undefined) {
        const code = blocks[i + 2];
        const lang = blocks[i + 1] || "";
        const langClass = lang ? ` class="language-${lang}"` : "";
        html += `<pre><code${langClass}>${code}</code></pre>`;
      }
    }
    return html;
  }

  function formatInline(text) {
    return text
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">')
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  function isTableRow(line) {
    const t = line.trim();
    return t.startsWith("|") && t.endsWith("|") && t.length > 1;
  }
  function isSeparatorRow(line) {
    const t = line.trim();
    return /^\|?[\s:|-]+\|[\s:|-]*\|?$/.test(t) && t.includes("-");
  }
  function splitRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  }

  function formatBlockText(text) {
    const lines = text.split("\n");
    let html = "";
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];

      // table: header row + separator row + body rows
      if (isTableRow(line) && lines[i + 1] !== undefined && isSeparatorRow(lines[i + 1])) {
        const header = splitRow(line);
        i += 2;
        const rows = [];
        while (i < lines.length && isTableRow(lines[i])) {
          rows.push(splitRow(lines[i]));
          i++;
        }
        html += "<table><thead><tr>" +
          header.map((c) => `<th>${formatInline(c)}</th>`).join("") +
          "</tr></thead><tbody>" +
          rows.map((r) => "<tr>" + r.map((c) => `<td>${formatInline(c)}</td>`).join("") + "</tr>").join("") +
          "</tbody></table>";
        continue;
      }

      // heading
      const headingMatch = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        html += `<h${level}>${formatInline(headingMatch[2])}</h${level}>`;
        i++;
        continue;
      }

      // horizontal rule (--- or *** or ___ alone on a line)
      if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
        html += "<hr>";
        i++;
        continue;
      }

      // unordered list
      if (/^\s*[-*]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
          i++;
        }
        html += "<ul>" + items.map((it) => `<li>${formatInline(it)}</li>`).join("") + "</ul>";
        continue;
      }

      // ordered list
      if (/^\s*\d+\.\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
          i++;
        }
        html += "<ol>" + items.map((it) => `<li>${formatInline(it)}</li>`).join("") + "</ol>";
        continue;
      }

      // plain line
      html += formatInline(line);
      if (i < lines.length - 1) html += "<br>";
      i++;
    }
    return html;
  }

  function highlightCodeBlocks(container) {
    if (window.hljs) {
      container.querySelectorAll("pre code").forEach((block) => {
        window.hljs.highlightElement(block);
      });
    }
  }

  // ---------- view transitions ----------

  let landingHideTimer = null;

  function activateChatView() {
    if (conversationStarted) return;
    conversationStarted = true;
    landing.classList.add("landing-exit");
    chatSection.hidden = false;
    appRoot.classList.add("chat-active");
    landingHideTimer = setTimeout(() => {
      landingHideTimer = null;
      landing.hidden = true;
      // Only one orb is ever visible at a time (landing vs. docked chat) —
      // pausing the hidden one's per-particle tick (220 points, every
      // frame) is a real, previously-unused saving, especially on mobile
      // GPUs. Paused after the crossfade finishes, not immediately, so the
      // outgoing orb doesn't visibly freeze mid-transition.
      landingSphere.setPaused(true);
    }, 520);
    // hand off orb state from landing to the docked chat orb
    chatSphere.setState(landingSphere.getState());
    chatSphere.setPaused(false);
  }

  function resetToLanding() {
    conversationStarted = false;
    // The crossfade's pending "hide the landing section" timer would
    // otherwise still fire after we've just shown it again, blanking both
    // sections at once.
    if (landingHideTimer) {
      clearTimeout(landingHideTimer);
      landingHideTimer = null;
    }
    landing.hidden = false;
    landing.classList.remove("landing-exit");
    chatSection.hidden = true;
    appRoot.classList.remove("chat-active");
    messagesEl.innerHTML = "";
    landingSphere.setState("idle");
    chatSphere.setState("idle");
    landingSphere.setPaused(false);
    chatSphere.setPaused(true);
    currentTitle = null;
    currentConversationId = null;
    lastUserText = null;
    hideAttachmentChip();
    closeAttachMenu();
    fetch("/api/attachment", { method: "DELETE" }).catch(() => {});
    renderSidebarActive();
  }

  // ---------- sidebar ----------
  // Below 860px the sidebar switches to an overlay drawer (see the
  // matching CSS media query) — closed by default there, with a tap-to-
  // close backdrop and auto-close after picking something inside it.
  // Desktop keeps the plain collapse/expand toggle it already had.

  const MOBILE_BREAKPOINT = 860;
  function isMobileViewport() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  function openSidebarDrawer() {
    sidebar.classList.remove("collapsed");
    if (isMobileViewport()) sidebarBackdrop.hidden = false;
  }

  function closeSidebarDrawer() {
    sidebar.classList.add("collapsed");
    sidebarBackdrop.hidden = true;
  }

  sidebarToggle.addEventListener("click", () => {
    if (sidebar.classList.contains("collapsed")) {
      openSidebarDrawer();
    } else {
      closeSidebarDrawer();
    }
  });

  sidebarBackdrop.addEventListener("click", closeSidebarDrawer);

  // Delegated so every current and future nav item (new chat, a
  // conversation in the list, Explore items, the footer buttons) gets
  // this without a separate listener each — only acts on mobile, and
  // never on the toggle button itself (it already manages its own state).
  sidebar.addEventListener("click", (e) => {
    if (!isMobileViewport()) return;
    if (sidebarToggle.contains(e.target)) return;
    if (e.target.closest('button, li[data-action], .chat-list li:not(.chat-list-empty)')) {
      closeSidebarDrawer();
    }
  });

  function applyResponsiveSidebarDefault() {
    if (isMobileViewport()) {
      closeSidebarDrawer();
    } else {
      sidebar.classList.remove("collapsed");
      sidebarBackdrop.hidden = true;
    }
  }
  applyResponsiveSidebarDefault();

  // Only react to genuinely crossing the breakpoint (rotating a phone/
  // tablet, resizing across it) — not every resize tick within the same
  // side of it, which would otherwise stomp on a desktop user's manual
  // collapse/expand choice every time their window resizes slightly.
  let wasMobileViewport = isMobileViewport();
  window.addEventListener("resize", () => {
    const nowMobile = isMobileViewport();
    if (nowMobile !== wasMobileViewport) {
      wasMobileViewport = nowMobile;
      applyResponsiveSidebarDefault();
    }
  });

  newChatBtn.addEventListener("click", resetToLanding);

  async function refreshConversationList() {
    try {
      const res = await fetch("/api/conversations");
      const list = res.ok ? await res.json() : null;
      // Guard the shape before clearing — a non-array body (error payload)
      // used to fall through and render "No conversations yet".
      if (!Array.isArray(list)) {
        chatList.innerHTML = '<li class="chat-list-empty">Couldn\'t load conversations.</li>';
        return;
      }
      chatList.innerHTML = "";
      if (!list.length) {
        chatList.innerHTML = `<li class="chat-list-empty" data-i18n="chatList.empty">${window.CindrixI18n.t("chatList.empty", "No conversations yet")}</li>`;
        return;
      }
      list.forEach((conv) => {
        const li = document.createElement("li");
        li.dataset.id = conv.id;

        const label = document.createElement("span");
        label.className = "chat-list-title";
        label.textContent = conv.title;
        li.appendChild(label);

        const del = document.createElement("button");
        del.type = "button";
        del.className = "chat-list-delete";
        del.textContent = "×";
        del.title = "Delete conversation";
        del.setAttribute("aria-label", `Delete conversation: ${conv.title}`);
        del.addEventListener("click", (e) => {
          // Without this the row's own click handler also fires and opens the
          // conversation the user is trying to delete.
          e.stopPropagation();
          deleteConversation(conv.id, conv.title);
        });
        li.appendChild(del);

        li.addEventListener("click", () => loadConversationIntoView(conv.id));
        chatList.appendChild(li);
      });
      renderSidebarActive();
    } catch (err) {
      chatList.innerHTML = '<li class="chat-list-empty">Couldn\'t load conversations.</li>';
    }
  }

  async function deleteConversation(convId, title) {
    if (!window.confirm(`Delete "${title}"? This can't be undone.`)) return;
    try {
      const res = await fetch(`/api/conversations/${convId}`, { method: "DELETE" });
      if (!res.ok) {
        flashStateMessage("Couldn't delete that conversation", 2500);
        return;
      }
      // Deleting the conversation on screen would otherwise leave the view
      // showing messages that no longer exist server-side.
      if (convId === currentConversationId) resetToLanding();
      refreshConversationList();
    } catch (err) {
      flashStateMessage("Couldn't reach the server", 2500);
    }
  }

  function renderSidebarActive() {
    chatList.querySelectorAll("li[data-id]").forEach((li) => {
      li.classList.toggle("active", li.dataset.id === currentConversationId);
    });
  }

  async function loadConversationIntoView(convId) {
    if (convId === currentConversationId) return;
    try {
      const res = await fetch(`/api/conversations/${convId}`);
      if (!res.ok) {
        flashStateMessage("Couldn't load that conversation", 2500);
        return;
      }
      const conv = await res.json();

      messagesEl.innerHTML = "";
      currentConversationId = conv.id;
      currentTitle = conv.title;
      activateChatView();
      renderSidebarActive();

      let precedingUser = null;
      conv.messages.forEach((m) => {
        if (m.role === "user") {
          const { bubble } = buildMessageGroup("user");
          bubble.textContent = m.content;
          bubble.dataset.raw = m.content;
          precedingUser = m.content;
        } else {
          const { group, bubble } = buildMessageGroup("assistant");
          if (precedingUser) group.dataset.precedingUser = precedingUser;
          setAssistantContent(bubble, m.content);
        }
      });
      window.scrollTo({ top: document.body.scrollHeight });

      // Each conversation has its own attachment now — show whatever this
      // one has (or hide the chip if it has none), rather than leaving
      // whatever chip state was showing from wherever the user was before.
      try {
        const attRes = await fetch(`/api/attachment?conversation_id=${convId}`);
        const att = await attRes.json();
        if (att.active) {
          showAttachmentChip(att.kind, att.filename);
        } else {
          hideAttachmentChip();
        }
      } catch (err) {
        hideAttachmentChip();
      }
    } catch (err) {
      flashStateMessage("Couldn't load that conversation", 2500);
    }
  }

  refreshConversationList();

  // ---------- quick-action prompts (landing chips + attach menu items) ----------

  function fillComposer(promptLabel) {
    composerInput.value = promptLabel + ": ";
    composerInput.focus();
  }

  document.querySelectorAll(".chip[data-prompt]").forEach((chip) => {
    chip.addEventListener("click", () => fillComposer(chip.dataset.prompt));
  });

  // ---------- messages ----------

  function buildMessageGroup(role) {
    const group = document.createElement("div");
    group.className = `msg-group ${role}`;

    const bubble = document.createElement("div");
    bubble.className = `msg msg-${role}`;
    group.appendChild(bubble);

    const actions = document.createElement("div");
    actions.className = "msg-actions";

    if (role === "assistant") {
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "msg-action-btn";
      copyBtn.title = "Copy response";
      copyBtn.textContent = "⧉";
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(bubble.dataset.raw || "").then(() => {
          copyBtn.classList.add("copied");
          copyBtn.textContent = "✓";
          setTimeout(() => {
            copyBtn.classList.remove("copied");
            copyBtn.textContent = "⧉";
          }, 1400);
        });
      });
      actions.appendChild(copyBtn);

      const regenBtn = document.createElement("button");
      regenBtn.type = "button";
      regenBtn.className = "msg-action-btn";
      regenBtn.title = "Regenerate response";
      regenBtn.textContent = "↻";
      regenBtn.addEventListener("click", () => {
        const precedingUser = group.dataset.precedingUser;
        if (precedingUser) regenerateInto(group, bubble, precedingUser);
      });
      actions.appendChild(regenBtn);
    } else {
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "msg-action-btn";
      editBtn.title = "Edit message";
      editBtn.textContent = "✎";
      editBtn.addEventListener("click", () => {
        // Simplification: edit refills the composer rather than truncating
        // and replaying conversation history (the backend has no message
        // IDs to support true branching yet — see docs/Memory.md).
        composerInput.value = bubble.dataset.raw || bubble.textContent;
        composerInput.focus();
      });
      actions.appendChild(editBtn);
    }

    group.appendChild(actions);
    messagesEl.appendChild(group);
    bubble.scrollIntoView && bubble.scrollIntoView({ block: "end", behavior: "smooth" });
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    return { group, bubble };
  }

  function setAssistantContent(bubble, rawText, { pending } = {}) {
    bubble.dataset.raw = rawText;
    bubble.classList.toggle("pending", !!pending);
    if (pending && !rawText) {
      bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
    } else {
      bubble.innerHTML = renderMarkdown(rawText);
      highlightCodeBlocks(bubble);
    }
  }

  // ---------- send flow ----------
  // viaVoice controls whether the reply gets spoken: true only when this
  // turn came from the mic, never for typed messages.

  const composerSendBtn = composerForm.querySelector(".composer-send");
  // One generation at a time: currentConversationId is only learned from the
  // response's X-Conversation-Id header, so a second send started before the
  // first one's headers arrive would post conversation_id: null again and the
  // backend would create a second conversation.
  let generationInFlight = false;

  function setGenerating(active) {
    generationInFlight = active;
    if (composerSendBtn) composerSendBtn.disabled = active;
  }

  async function sendMessage(text, viaVoice = false) {
    if (!text.trim()) return;
    if (generationInFlight) {
      flashStateMessage("Still answering — one moment", 2000);
      return;
    }
    closeAttachMenu();

    activateChatView();
    if (!currentTitle) {
      currentTitle = text.length > 34 ? text.slice(0, 34) + "…" : text;
    }
    lastUserText = text;

    const { bubble: userBubble } = buildMessageGroup("user");
    userBubble.textContent = text;
    userBubble.dataset.raw = text;
    composerInput.value = "";

    const { group: assistantGroup, bubble: assistantBubble } = buildMessageGroup("assistant");
    assistantGroup.dataset.precedingUser = text;
    setAssistantContent(assistantBubble, "", { pending: true });
    activeSphere().setState("thinking");

    await streamInto(assistantBubble, text, viaVoice);
  }

  async function streamInto(assistantBubble, userText, viaVoice, regenerate = false) {
    setGenerating(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          conversation_id: currentConversationId,
          model: currentModelId,
          // Tells the backend this turn is already in history: re-answer it
          // instead of appending the same user message a second time.
          regenerate,
        }),
      });

      if (!res.ok || !res.body) {
        setAssistantContent(assistantBubble, "Something went wrong reaching Cindrix. Try again in a moment.");
        activeSphere().setState("idle");
        // Otherwise the mic button keeps showing an active voice session that
        // has no loop left to continue it.
        if (voiceChatActive) setVoiceChatUI(false);
        return;
      }

      const returnedId = res.headers.get("X-Conversation-Id");
      if (returnedId) currentConversationId = returnedId;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Stay in "thinking" for the whole generation, regardless of
        // voice vs. typed input — "speaking" only starts once actual TTS
        // audio plays, via speak() below, after the full reply is in.
        full += decoder.decode(value, { stream: true });
        setAssistantContent(assistantBubble, full, { pending: true });
        window.scrollTo({ top: document.body.scrollHeight, behavior: "auto" });
      }
      setAssistantContent(assistantBubble, full);
      refreshConversationList();

      if (viaVoice) {
        speak(full, () => {
          if (voiceChatActive) window.CindrixVoice.startListening();
        });
      } else {
        activeSphere().setState("idle");
      }
    } catch (err) {
      setAssistantContent(assistantBubble, "Couldn't reach the Cindrix backend — is it running?");
      activeSphere().setState("idle");
      if (voiceChatActive) setVoiceChatUI(false);
    } finally {
      setGenerating(false);
    }
  }

  function regenerateInto(group, bubble, precedingUserText) {
    if (generationInFlight) {
      flashStateMessage("Still answering — one moment", 2000);
      return;
    }
    setAssistantContent(bubble, "", { pending: true });
    activeSphere().setState("thinking");
    streamInto(bubble, precedingUserText, false, true);
  }

  composerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (voiceChatActive) window.CindrixVoice.stopVoiceChat();
    sendMessage(composerInput.value, false);
  });

  // ---------- attach button + menu (Phase 2b: quick actions move here once
  // the conversation has started; before that, the landing chips already
  // show them, so the button just opens the file picker directly) ----------

  const attachBtn = document.getElementById("attachBtn");
  const fileInput = document.getElementById("fileInput");
  const attachMenu = document.getElementById("attachMenu");
  const attachmentChip = document.getElementById("attachmentChip");
  const attachmentChipLabel = document.getElementById("attachmentChipLabel");
  const attachmentChipRemove = document.getElementById("attachmentChipRemove");

  function openAttachMenu() { attachMenu.hidden = false; }
  function closeAttachMenu() { attachMenu.hidden = true; }
  function toggleAttachMenu() { attachMenu.hidden = !attachMenu.hidden; }

  attachMenu.querySelectorAll(".attach-menu-item[data-prompt]").forEach((item) => {
    item.addEventListener("click", () => {
      fillComposer(item.dataset.prompt);
      closeAttachMenu();
    });
  });

  document.getElementById("attachMenuUpload").addEventListener("click", () => {
    closeAttachMenu();
    fileInput.click();
  });

  attachBtn.addEventListener("click", () => {
    if (!conversationStarted) {
      fileInput.click();
      return;
    }
    toggleAttachMenu();
  });

  document.addEventListener("click", (e) => {
    if (!attachMenu.hidden && !attachMenu.contains(e.target) && e.target !== attachBtn) {
      closeAttachMenu();
    }
  });

  function flashStateMessage(text, ms = 2500) {
    const label = activeStateLabelEl();
    if (!label) return;
    label.textContent = text;
    setTimeout(() => {
      label.textContent = "";
    }, ms);
  }

  function showAttachmentChip(kind, filename) {
    const icon = kind === "image" ? "🖼️" : "📄";
    attachmentChipLabel.textContent = `${icon} ${filename}`;
    attachmentChip.hidden = false;
  }

  function hideAttachmentChip() {
    attachmentChip.hidden = true;
    attachmentChipLabel.textContent = "";
  }

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    fileInput.value = "";
    if (!file) return;

    activeSphere().setState("thinking");
    flashStateMessage(`Reading ${file.name}…`, 60000);

    const formData = new FormData();
    formData.append("file", file);
    if (currentConversationId) formData.append("conversation_id", currentConversationId);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();

      if (!res.ok) {
        flashStateMessage(data.error || "Upload failed", 3000);
        activeSphere().setState("idle");
        return;
      }

      showAttachmentChip(data.kind, data.filename);
      const label = activeStateLabelEl();
      if (label) label.textContent = "";
      activeSphere().setState("idle");
    } catch (err) {
      flashStateMessage("Couldn't reach the server to upload that file", 3000);
      activeSphere().setState("idle");
    }
  });

  attachmentChipRemove.addEventListener("click", async () => {
    try {
      await fetch("/api/attachment", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: currentConversationId }),
      });
    } catch (err) {
      // best-effort — hide the chip either way, it's just UI state
    }
    hideAttachmentChip();
  });

  // ---------- voice selector ("other audio options") ----------

  const voiceSelect = document.getElementById("voiceSelect");
  let availableVoices = [];

  // Microsoft's Edge-only "Natural"/"Online" neural voices sound far better
  // than the default robotic ones and are exposed via getVoices() only in
  // Edge (not reliably in Chrome/Firefox). Preferred when present; if none
  // are found (e.g. testing in Chrome/Safari/Firefox), this just falls back
  // to whatever the browser offers — never hard-requires Edge.
  function pickPreferredVoiceName(voices) {
    const pageLang = (document.documentElement.lang || navigator.language || "en").slice(0, 2);
    const neural = voices.filter((v) => /natural|online/i.test(v.name));
    const neuralInLang = neural.filter((v) => v.lang.startsWith(pageLang));
    const pick = neuralInLang[0] || neural[0];
    return pick ? pick.name : null;
  }

  let userPickedVoice = false;
  voiceSelect.addEventListener("change", () => {
    userPickedVoice = true;
    persistDefaultVoice(voiceSelect.value);
  });

  function persistDefaultVoice(voiceName) {
    // Only logged-in users have a stored profile to save this to; guests keep
    // their choice for the session only. Best-effort — a failed save just
    // means the preference won't survive to the next session.
    if (!currentUser || !voiceName) return;
    currentUser.default_voice = voiceName;
    fetch("/api/auth/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ default_voice: voiceName }),
    }).catch(() => {});
  }

  function loadVoices() {
    const previousSelection = voiceSelect.value;
    availableVoices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    if (!availableVoices.length) return;
    voiceSelect.innerHTML = "";
    const english = availableVoices.filter((v) => v.lang.startsWith("en"));
    (english.length ? english : availableVoices).forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.name} (${v.lang})`;
      voiceSelect.appendChild(opt);
    });

    const isAvailable = (name) => !!name && Array.from(voiceSelect.options).some((o) => o.value === name);
    const savedDefault = currentUser && currentUser.default_voice;

    if (!userPickedVoice && isAvailable(savedDefault)) {
      // A logged-in user's saved default wins over both the restore-previous
      // logic and the neural-voice heuristic — but only until they override it
      // this session (userPickedVoice), so a manual change is never undone.
      voiceSelect.value = savedDefault;
    } else if (isAvailable(previousSelection)) {
      // The browser can fire onvoiceschanged more than once, which used to
      // silently reset the selection back to the first option every time —
      // that's the "keeps switching back to the default voice" bug. Restore
      // whatever was previously selected if it's still in the list.
      voiceSelect.value = previousSelection;
    } else if (!userPickedVoice) {
      // No saved default and nothing to restore — default to a Natural/Online
      // neural voice if one exists, otherwise leave the browser's own default.
      const preferred = pickPreferredVoiceName(availableVoices);
      if (preferred) voiceSelect.value = preferred;
    }
  }
  if ("speechSynthesis" in window) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }

  // ---------- voice output (browser TTS) ----------

  function speak(text, onDone) {
    if (!("speechSynthesis" in window) || !text) {
      activeSphere().setState("idle");
      if (onDone) onDone();
      return;
    }
    activeSphere().setState("speaking");
    const utter = new SpeechSynthesisUtterance(stripMarkdownForSpeech(text));
    const chosenVoice = availableVoices.find((v) => v.name === voiceSelect.value);
    if (chosenVoice) utter.voice = chosenVoice;
    const finish = () => {
      activeSphere().setState("idle");
      if (onDone) onDone();
    };
    utter.onend = finish;
    utter.onerror = finish;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  }

  function stripMarkdownForSpeech(text) {
    return text
      .replace(/```[\s\S]*?```/g, " code block omitted ")
      .replace(/!\[[^\]]*\]\([^)]+\)/g, " image omitted ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1");
  }

  // ---------- voice input (browser STT, or Sarvam server-side STT) ----------
  // STT_PROVIDER (fetched below) decides which of the two implementations
  // this section wires up. Both funnel into the exact same downstream call
  // — sendMessage(transcript, true) — so everything past "we have a final
  // transcript" (RAG routing, streaming, TTS, sphere states) is identical
  // regardless of provider. See docs/Architecture.md's STT Provider section.

  let sttProvider = "webspeech"; // overwritten once /api/config resolves; see below
  // Resolves once /api/config has landed and a provider has been wired up.
  // Every "start voice chat" gesture awaits this rather than firing at a no-op
  // stub, so a click that races the fetch still does the right thing.
  let voiceProviderReady = null;
  // null until a provider decides; false means this browser can't do voice at
  // all, and nothing may enter the active voice-chat UI state.
  let voiceSupported = null;
  // Safe no-op default in case anything reaches for this before a provider has
  // initialized — overwritten by whichever real provider initializes below.
  window.CindrixVoice = { startListening() {}, stopVoiceChat() { setVoiceChatUI(false); } };

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;
  let listening = false;
  let voiceChatActive = false;

  function showMicError(message) {
    console.error("Cindrix mic error:", message);
    micBtn.title = `Voice input error: ${message}`;
    flashStateMessage(`Mic error: ${message}`);
  }

  function voiceNotSupportedMessage() {
    return window.CindrixI18n.t(
      "composer.voiceNotSupported",
      "Voice input isn't supported in this browser — try Chrome or Edge"
    );
  }

  function markVoiceUnsupported() {
    voiceSupported = false;
    micBtn.disabled = true;
    micBtn.title = voiceNotSupportedMessage();
    micBtn.setAttribute("data-i18n-title", "composer.voiceNotSupported");
    micBtn.setAttribute("data-i18n-aria-label", "composer.voiceNotSupported");
    micBtn.setAttribute("aria-label", voiceNotSupportedMessage());
  }

  function setVoiceChatUI(active) {
    voiceChatActive = active;
    micBtn.classList.toggle("voice-chat-active", active);
    const key = active ? "composer.stopVoiceChat" : "composer.startVoiceChat";
    const fallback = active ? "Stop voice chat" : "Start voice chat";
    const label = window.CindrixI18n.t(key, fallback);
    micBtn.title = label;
    micBtn.setAttribute("aria-label", label);
    // Keep the i18n data attributes pointed at the *current* state's key, so
    // switching language mid-session (i18n.js's applyTranslations) doesn't
    // relabel a running voice chat as "Start voice chat".
    micBtn.setAttribute("data-i18n-title", key);
    micBtn.setAttribute("data-i18n-aria-label", key);
  }

  // Single entry point for every start/stop voice-chat gesture (the mic button
  // and the sidebar's Explore > Voice item). Registered immediately, so an
  // early click waits for /api/config instead of hitting the no-op stub, and
  // never enters the active voice-chat UI state when voice can't start at all.
  let voiceRequestPending = false;
  async function requestVoiceChatToggle() {
    if (voiceRequestPending) return;
    voiceRequestPending = true;
    try {
      if (voiceProviderReady) await voiceProviderReady;
      if (voiceChatActive) {
        window.CindrixVoice.stopVoiceChat();
        return;
      }
      if (!voiceSupported) {
        flashStateMessage(voiceNotSupportedMessage(), 3500);
        return;
      }
      setVoiceChatUI(true);
      window.CindrixVoice.startListening();
    } finally {
      voiceRequestPending = false;
    }
  }

  micBtn.addEventListener("click", requestVoiceChatToggle);

  // ===== Provider A: Web Speech API (browser-native, dev/fallback) =====

  function startListeningWebSpeech() {
    if (!recognizer || listening) return;
    try {
      recognizer.start();
    } catch (err) {
      showMicError(err.message || "couldn't start microphone");
      setVoiceChatUI(false);
    }
  }

  function stopVoiceChatWebSpeech() {
    setVoiceChatUI(false);
    if (listening) recognizer.stop();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    activeSphere().setState("idle");
  }

  function setupWebSpeechProvider() {
    if (!SpeechRecognition) {
      markVoiceUnsupported();
      return;
    }
    recognizer = new SpeechRecognition();
    recognizer.continuous = false;
    recognizer.interimResults = false;
    recognizer.lang = "en-US";

    recognizer.onstart = () => {
      listening = true;
      micBtn.classList.add("listening");
      activeSphere().setState("listening");
    };

    recognizer.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      composerInput.value = transcript;
      sendMessage(transcript, true);
    };

    recognizer.onerror = (event) => {
      listening = false;
      micBtn.classList.remove("listening");
      activeSphere().setState("idle");
      showMicError(event.error || "unknown");
      setVoiceChatUI(false);
    };

    recognizer.onend = () => {
      listening = false;
      micBtn.classList.remove("listening");
      if (activeSphere().getState() === "listening") activeSphere().setState("idle");
    };

    // No mic-button listener here — requestVoiceChatToggle() above owns that
    // gesture for both providers, so it works before this setup has run.
    voiceSupported = true;
    window.CindrixVoice = { startListening: startListeningWebSpeech, stopVoiceChat: stopVoiceChatWebSpeech };
  }

  // ===== Provider B: Sarvam (server-side, the real STT provider) =====
  // No SpeechRecognition API involved at all — records raw audio via
  // MediaRecorder, detects when the user has stopped talking with a small
  // Web Audio volume analyser (WebSpeech gets this "for free" from the
  // browser; recording raw audio doesn't, so it's built here), then POSTs
  // the clip to /api/stt. SARVAM_API_KEY never touches the browser — only
  // the backend (app/ai/stt.py) holds it.

  function setupSarvamProvider() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      markVoiceUnsupported();
      return;
    }

    const SILENCE_RMS_THRESHOLD = 0.02; // 0-1 scale; below this counts as silence
    const SILENCE_STOP_MS = 1200; // auto-stop this long after speech ends
    const MAX_RECORDING_MS = 20000; // safety cap regardless of silence detection
    const MAX_SILENT_ATTEMPTS = 3; // give up (instead of re-recording forever)

    let mediaStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let audioCtx = null;
    let analyser = null;
    let silenceTimer = null;
    let maxDurationTimer = null;
    let hasHeardSpeech = false;
    let sarvamListening = false;
    let silentAttempts = 0;

    function teardownAudioGraph() {
      if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
      if (maxDurationTimer) { clearTimeout(maxDurationTimer); maxDurationTimer = null; }
      if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null; }
      analyser = null;
      if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
    }

    function monitorSilence() {
      if (!analyser) return;
      const data = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(data);
      let sumSquares = 0;
      for (let i = 0; i < data.length; i++) {
        const norm = (data[i] - 128) / 128;
        sumSquares += norm * norm;
      }
      const rms = Math.sqrt(sumSquares / data.length);

      if (rms > SILENCE_RMS_THRESHOLD) {
        hasHeardSpeech = true;
        if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
      } else if (hasHeardSpeech && !silenceTimer) {
        silenceTimer = setTimeout(() => stopSarvamRecording(), SILENCE_STOP_MS);
      }
      if (mediaRecorder && mediaRecorder.state === "recording") {
        requestAnimationFrame(monitorSilence);
      }
    }

    async function startSarvamRecording() {
      if (sarvamListening) return;
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        showMicError(err.message || "microphone permission denied");
        setVoiceChatUI(false);
        return;
      }

      audioChunks = [];
      hasHeardSpeech = false;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      mediaRecorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream);
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
      mediaRecorder.onstop = handleSarvamRecordingStopped;

      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(mediaStream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      sarvamListening = true;
      micBtn.classList.add("listening");
      activeSphere().setState("listening");
      mediaRecorder.start();
      requestAnimationFrame(monitorSilence);
      maxDurationTimer = setTimeout(() => stopSarvamRecording(), MAX_RECORDING_MS);
    }

    function stopSarvamRecording() {
      if (!sarvamListening || !mediaRecorder) return;
      sarvamListening = false;
      micBtn.classList.remove("listening");
      if (mediaRecorder.state === "recording") mediaRecorder.stop();
    }

    // Nothing usable came back from a recording — retry, but only so many
    // times in a row, otherwise a muted/too-quiet mic re-records forever with
    // no message and no way for the user to notice.
    function handleEmptyCapture() {
      activeSphere().setState("idle");
      silentAttempts++;
      if (silentAttempts >= MAX_SILENT_ATTEMPTS) {
        silentAttempts = 0;
        setVoiceChatUI(false);
        flashStateMessage("Didn't hear anything — voice chat stopped", 3500);
        return;
      }
      if (voiceChatActive) startSarvamRecording();
    }

    async function handleSarvamRecordingStopped() {
      teardownAudioGraph();
      if (!voiceChatActive) return; // user cancelled via stopVoiceChatSarvam
      if (!hasHeardSpeech || !audioChunks.length) {
        // Nothing usable was recorded — go back to idle rather than
        // sending an empty/near-silent clip to the STT API.
        handleEmptyCapture();
        return;
      }
      silentAttempts = 0;

      activeSphere().setState("thinking"); // transcribing, not generating yet
      const blob = new Blob(audioChunks, { type: audioChunks[0].type || "audio/webm" });
      const formData = new FormData();
      formData.append("audio", blob, "voice-input.webm");

      try {
        const res = await fetch("/api/stt", { method: "POST", body: formData });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          showMicError(data.error || `transcription failed (${res.status})`);
          activeSphere().setState("idle");
          setVoiceChatUI(false);
          return;
        }
        if (!data.transcript) {
          // Transcribed successfully but got nothing (e.g. silence Sarvam
          // itself couldn't parse) — same graceful non-dead-end handling
          // as WebSpeech's "no-speech" error, not a hard failure.
          handleEmptyCapture();
          return;
        }
        composerInput.value = data.transcript;
        sendMessage(data.transcript, true);
      } catch (err) {
        showMicError("couldn't reach the transcription service");
        activeSphere().setState("idle");
        setVoiceChatUI(false);
      }
    }

    function stopVoiceChatSarvam() {
      setVoiceChatUI(false);
      silentAttempts = 0;
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      if (sarvamListening) stopSarvamRecording();
      else teardownAudioGraph();
      activeSphere().setState("idle");
    }

    // No mic-button listener here — requestVoiceChatToggle() owns that gesture
    // for both providers, so it works before this setup has run.
    voiceSupported = true;
    window.CindrixVoice = { startListening: startSarvamRecording, stopVoiceChat: stopVoiceChatSarvam };
  }

  // Resolve which provider to wire up. Falls back to Web Speech if
  // /api/config can't be reached at all, e.g. backend not running yet during
  // frontend-only dev.
  voiceProviderReady = fetch("/api/config")
    .then((res) => res.json())
    .then((data) => { sttProvider = data.sttProvider || "webspeech"; })
    .catch(() => { sttProvider = "webspeech"; })
    .finally(() => {
      if (sttProvider === "sarvam") setupSarvamProvider();
      else setupWebSpeechProvider();
    });

  // ---------- export ----------

  const exportBtn = document.getElementById("exportBtn");
  const exportMenu = document.getElementById("exportMenu");

  exportBtn.addEventListener("click", () => {
    if (!currentConversationId) {
      flashStateMessage("Nothing to export yet", 2000);
      return;
    }
    exportMenu.hidden = !exportMenu.hidden;
  });

  exportMenu.querySelectorAll(".attach-menu-item[data-format]").forEach((item) => {
    item.addEventListener("click", () => {
      if (!currentConversationId) return;
      const a = document.createElement("a");
      a.href = `/api/conversations/${currentConversationId}/export?format=${item.dataset.format}`;
      a.click();
      exportMenu.hidden = true;
    });
  });

  document.addEventListener("click", (e) => {
    if (!exportMenu.hidden && !exportMenu.contains(e.target) && e.target !== exportBtn) {
      exportMenu.hidden = true;
    }
  });

  // ---------- analytics dashboard ----------

  const analyticsBtn = document.getElementById("analyticsBtn");
  const analyticsOverlay = document.getElementById("analyticsOverlay");
  const analyticsClose = document.getElementById("analyticsClose");
  const analyticsBody = document.getElementById("analyticsBody");

  function renderAnalytics(data) {
    const toolEntries = Object.entries(data.tool_usage || {});
    const maxToolCount = Math.max(1, ...toolEntries.map(([, c]) => c));

    const days = data.daily_message_counts || [];
    const maxDay = Math.max(1, ...days.map((d) => d.count));

    analyticsBody.innerHTML = `
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-value">${data.total_messages}</div>
          <div class="stat-label">Total messages</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.average_latency_ms}ms</div>
          <div class="stat-label">Average latency</div>
        </div>
      </div>

      <div>
        <p class="ts-muted" style="margin:0 0 8px;">Tool usage</p>
        ${
          toolEntries.length
            ? toolEntries
                .map(
                  ([tool, count]) => `
          <div class="bar-row">
            <span class="bar-label">${tool.replace(/_/g, " ")}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${(count / maxToolCount) * 100}%"></span></span>
            <span class="bar-count">${count}</span>
          </div>`
                )
                .join("")
            : '<p class="ts-muted">No messages yet.</p>'
        }
      </div>

      <div>
        <p class="ts-muted" style="margin:0 0 8px;">Messages per day (last ${days.length || 0})</p>
        ${
          days.length
            ? `<div class="daily-chart">${days
                .map((d) => `<div class="daily-bar" style="height:${(d.count / maxDay) * 100}%" title="${d.date}: ${d.count}"></div>`)
                .join("")}</div>`
            : '<p class="ts-muted">No data yet.</p>'
        }
      </div>
    `;
  }

  analyticsBtn.addEventListener("click", async () => {
    analyticsOverlay.hidden = false;
    analyticsBody.innerHTML = '<p class="ts-muted">Loading…</p>';
    try {
      const res = await fetch("/api/analytics/summary");
      if (!res.ok) {
        analyticsBody.innerHTML = '<p class="ts-muted">Couldn\'t load analytics.</p>';
        return;
      }
      const data = await res.json();
      renderAnalytics(data);
    } catch (err) {
      analyticsBody.innerHTML = '<p class="ts-muted">Couldn\'t load analytics.</p>';
    }
  });

  analyticsClose.addEventListener("click", () => { analyticsOverlay.hidden = true; });
  wireOverlayClose(analyticsOverlay);

  // ---------- model selector ----------

  const modelSelect = document.getElementById("modelSelect");
  const modelNameEl = document.getElementById("modelName");

  async function loadModels() {
    try {
      const res = await fetch("/api/models");
      const models = res.ok ? await res.json() : null;
      // Check the shape before clearing the <select> — a non-array body would
      // otherwise leave the dropdown permanently empty.
      if (!Array.isArray(models) || !models.length) {
        flashStateMessage("Couldn't load the model list — using the server default", 3000);
        return;
      }
      modelSelect.innerHTML = "";
      models.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.label;
        modelSelect.appendChild(opt);
      });
      currentModelId = models[0].id;
      modelNameEl.textContent = models[0].label.replace(" (recommended)", "");
    } catch (err) {
      flashStateMessage("Couldn't load the model list — using the server default", 3000);
    }
  }

  modelSelect.addEventListener("change", () => {
    currentModelId = modelSelect.value;
    const label = modelSelect.options[modelSelect.selectedIndex].textContent;
    modelNameEl.textContent = label.replace(" (recommended)", "");
  });

  loadModels();

  // ---------- auth (login / signup) ----------

  const authOverlay = document.getElementById("authOverlay");
  const authClose = document.getElementById("authClose");
  const authTitle = document.getElementById("authTitle");
  const loginForm = document.getElementById("loginForm");
  const signupForm = document.getElementById("signupForm");
  const loginError = document.getElementById("loginError");
  const signupError = document.getElementById("signupError");

  function openAuthModal(tab = "login") {
    authOverlay.hidden = false;
    setAuthTab(tab);
  }

  function setAuthTab(tab) {
    document.querySelectorAll(".auth-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === tab);
    });
    loginForm.hidden = tab !== "login";
    signupForm.hidden = tab !== "signup";
    authTitle.textContent = tab === "login" ? "Sign in" : "Create account";
    loginError.textContent = "";
    signupError.textContent = "";
  }

  document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => setAuthTab(tab.dataset.tab));
  });

  authClose.addEventListener("click", () => { authOverlay.hidden = true; });
  wireOverlayClose(authOverlay);

  async function afterAuthChange() {
    await loadCurrentUser();
    resetToLanding();
    await refreshConversationList();
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.textContent = "";
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          identifier: document.getElementById("loginIdentifier").value,
          password: document.getElementById("loginPassword").value,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        loginError.textContent = data.error || "Couldn't sign in.";
        return;
      }
      authOverlay.hidden = true;
      loginForm.reset();
      await afterAuthChange();
    } catch (err) {
      loginError.textContent = "Couldn't reach the server.";
    }
  });

  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    signupError.textContent = "";
    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("signupUsername").value,
          email: document.getElementById("signupEmail").value,
          password: document.getElementById("signupPassword").value,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        signupError.textContent = data.error || "Couldn't create account.";
        return;
      }
      authOverlay.hidden = true;
      signupForm.reset();
      await afterAuthChange();
    } catch (err) {
      signupError.textContent = "Couldn't reach the server.";
    }
  });

  async function loadCurrentUser() {
    try {
      const res = await fetch("/api/auth/me");
      const data = await res.json();
      currentUser = data.loggedIn ? data : null;
    } catch (err) {
      currentUser = null;
    }
    document.getElementById("adminBtn").hidden = !(currentUser && currentUser.is_admin);
    // The profile may carry a saved default voice. Voices often finish loading
    // before auth resolves, so re-apply the selection now that currentUser is
    // known — loadVoices() gives the saved default precedence when present.
    if ("speechSynthesis" in window) loadVoices();
  }

  // ---------- profile modal ----------

  const profileBtn = document.getElementById("profileBtn");
  const profileOverlay = document.getElementById("profileOverlay");
  const profileClose = document.getElementById("profileClose");
  const profileBody = document.getElementById("profileBody");

  function renderProfile() {
    if (!currentUser) {
      profileBody.innerHTML = `
        <p class="ts-muted">You're using Cindrix as a guest — sign in to keep your own conversation history, attachments, and settings.</p>
        <button type="button" class="form-submit" id="profileSignInBtn">Sign in / Create account</button>
      `;
      document.getElementById("profileSignInBtn").addEventListener("click", () => {
        profileOverlay.hidden = true;
        openAuthModal("login");
      });
      return;
    }
    const initial = (currentUser.display_name || currentUser.username || "?")[0].toUpperCase();
    const joined = new Date(currentUser.created_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
    profileBody.innerHTML = `
      <div class="profile-row">
        <div class="profile-avatar">${escapeHtml(initial)}</div>
        <div>
          <div class="profile-name">${escapeHtml(currentUser.display_name || currentUser.username)}${currentUser.is_admin ? ' <span class="admin-badge">Admin</span>' : ""}</div>
          <div class="profile-email">${escapeHtml(currentUser.email)}</div>
        </div>
      </div>
      <p class="ts-muted" style="margin:0;">Member since ${joined}</p>
      <div class="form-divider"></div>
      <button type="button" class="form-submit secondary" id="profileLogoutBtn">Log out</button>
      <p class="form-error" id="profileError"></p>
    `;
    document.getElementById("profileLogoutBtn").addEventListener("click", async () => {
      const errorEl = document.getElementById("profileError");
      errorEl.textContent = "";
      try {
        const res = await fetch("/api/auth/logout", { method: "POST" });
        if (!res.ok) {
          errorEl.textContent = "Couldn't log out. Try again.";
          return;
        }
      } catch (err) {
        errorEl.textContent = "Couldn't reach the server to log out.";
        return;
      }
      profileOverlay.hidden = true;
      await afterAuthChange();
    });
  }

  profileBtn.addEventListener("click", () => {
    renderProfile();
    profileOverlay.hidden = false;
  });
  profileClose.addEventListener("click", () => { profileOverlay.hidden = true; });
  wireOverlayClose(profileOverlay);

  // ---------- settings modal ----------

  const settingsBtn = document.getElementById("settingsBtn");
  const settingsOverlay = document.getElementById("settingsOverlay");
  const settingsClose = document.getElementById("settingsClose");
  const settingsBody = document.getElementById("settingsBody");

  function renderSettings() {
    if (!currentUser) {
      settingsBody.innerHTML = `
        <p class="ts-muted">Settings are tied to an account — sign in first.</p>
        <button type="button" class="form-submit" id="settingsSignInBtn">Sign in / Create account</button>
      `;
      document.getElementById("settingsSignInBtn").addEventListener("click", () => {
        settingsOverlay.hidden = true;
        openAuthModal("login");
      });
      return;
    }

    settingsBody.innerHTML = `
      <form class="form" id="profileForm">
        <label class="form-label">Display name
          <input type="text" id="displayNameInput" class="form-input" value="${escapeHtml(currentUser.display_name || "")}" />
        </label>
        <p class="form-error" id="profileFormError"></p>
        <p class="form-success" id="profileFormSuccess"></p>
        <button type="submit" class="form-submit">Save changes</button>
      </form>

      <div class="form-divider"></div>

      <form class="form" id="passwordForm">
        <label class="form-label">Current password
          <div class="password-field">
            <input type="password" id="currentPasswordInput" class="form-input" autocomplete="current-password" required />
            <button type="button" class="password-toggle" data-target="currentPasswordInput" aria-label="Show password">👁</button>
          </div>
        </label>
        <label class="form-label">New password
          <div class="password-field">
            <input type="password" id="newPasswordInput" class="form-input" autocomplete="new-password" required minlength="8" />
            <button type="button" class="password-toggle" data-target="newPasswordInput" aria-label="Show password">👁</button>
          </div>
        </label>
        <ul class="password-requirements" id="newPasswordReqs">
          <li data-rule="length">At least 8 characters</li>
          <li data-rule="lower">One lowercase letter</li>
          <li data-rule="upper">One uppercase letter</li>
          <li data-rule="digit">One number</li>
          <li data-rule="special">One special character</li>
        </ul>
        <p class="form-error" id="passwordFormError"></p>
        <p class="form-success" id="passwordFormSuccess"></p>
        <button type="submit" class="form-submit secondary">Change password</button>
      </form>
    `;

    document.getElementById("profileForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const successEl = document.getElementById("profileFormSuccess");
      const errorEl = document.getElementById("profileFormError");
      errorEl.textContent = "";
      try {
        const res = await fetch("/api/auth/me", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: document.getElementById("displayNameInput").value }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          errorEl.textContent = data.error || "Couldn't save changes.";
          return;
        }
        currentUser = { ...currentUser, ...data };
        successEl.textContent = "Saved.";
        setTimeout(() => { successEl.textContent = ""; }, 2000);
      } catch (err) {
        errorEl.textContent = "Couldn't reach the server.";
      }
    });

    document.getElementById("passwordForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorEl = document.getElementById("passwordFormError");
      const successEl = document.getElementById("passwordFormSuccess");
      errorEl.textContent = "";
      try {
        const res = await fetch("/api/auth/change-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_password: document.getElementById("currentPasswordInput").value,
            new_password: document.getElementById("newPasswordInput").value,
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          errorEl.textContent = data.error || "Couldn't change password.";
          return;
        }
        successEl.textContent = "Password changed.";
        document.getElementById("passwordForm").reset();
        setTimeout(() => { successEl.textContent = ""; }, 2000);
      } catch (err) {
        errorEl.textContent = "Couldn't reach the server.";
      }
    });
  }

  settingsBtn.addEventListener("click", () => {
    renderSettings();
    settingsOverlay.hidden = false;
  });
  settingsClose.addEventListener("click", () => { settingsOverlay.hidden = true; });
  wireOverlayClose(settingsOverlay);

  // ---------- admin panel ----------

  const adminBtn = document.getElementById("adminBtn");
  const adminOverlay = document.getElementById("adminOverlay");
  const adminClose = document.getElementById("adminClose");
  const adminBody = document.getElementById("adminBody");

  adminBtn.addEventListener("click", async () => {
    adminOverlay.hidden = false;
    adminBody.innerHTML = '<p class="ts-muted">Loading…</p>';
    try {
      const res = await fetch("/api/admin/users");
      if (!res.ok) {
        adminBody.innerHTML = '<p class="ts-muted">Admin access required.</p>';
        return;
      }
      const users = await res.json();
      adminBody.innerHTML = `
        <table class="admin-table">
          <thead><tr><th>User</th><th>Email</th><th>Conversations</th><th>Messages</th></tr></thead>
          <tbody>
            ${users.map((u) => `
              <tr>
                <td>${escapeHtml(u.display_name || u.username)}${u.is_admin ? ' <span class="admin-badge">Admin</span>' : ""}</td>
                <td>${escapeHtml(u.email)}</td>
                <td>${u.conversation_count}</td>
                <td>${u.message_count}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    } catch (err) {
      adminBody.innerHTML = '<p class="ts-muted">Couldn\'t load admin data.</p>';
    }
  });
  adminClose.addEventListener("click", () => { adminOverlay.hidden = true; });
  wireOverlayClose(adminOverlay);

  // ---------- initial load ----------

  // ---------- password show/hide toggle + live requirements checklist ----------
  // Delegated on document (not the individual buttons) because the Settings
  // modal's password fields are created dynamically via innerHTML — a
  // direct listener wouldn't exist yet at page-load time.

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".password-toggle");
    if (!btn) return;
    const input = document.getElementById(btn.dataset.target);
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    btn.textContent = showing ? "👁" : "🙈";
    btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  });

  const PASSWORD_RULES = {
    length: (p) => p.length >= 8,
    lower: (p) => /[a-z]/.test(p),
    upper: (p) => /[A-Z]/.test(p),
    digit: (p) => /\d/.test(p),
    special: (p) => /[^a-zA-Z0-9]/.test(p),
  };

  function updatePasswordChecklist(password, listEl) {
    if (!listEl) return;
    listEl.querySelectorAll("li[data-rule]").forEach((li) => {
      const rule = PASSWORD_RULES[li.dataset.rule];
      li.classList.toggle("met", rule ? rule(password) : false);
    });
  }

  document.addEventListener("input", (e) => {
    if (e.target.id === "signupPassword") {
      updatePasswordChecklist(e.target.value, document.getElementById("signupPasswordReqs"));
    }
    if (e.target.id === "newPasswordInput") {
      updatePasswordChecklist(e.target.value, document.getElementById("newPasswordReqs"));
    }
  });

  // ---------- sidebar Explore shortcuts ----------
  // These used to be static leftover items from the original landing-page
  // mockup with no behavior behind them. Wired to the real feature each one
  // names, now that those features exist.

  document.querySelectorAll(".explore-list li[data-action]").forEach((item) => {
    item.addEventListener("click", () => {
      const action = item.dataset.action;
      if (action === "upload") {
        fileInput.click();
      } else if (action === "voice") {
        if (!voiceChatActive) requestVoiceChatToggle();
      } else if (action === "coding") {
        fillComposer("Write code for");
      }
    });
  });

  loadCurrentUser();
})();
