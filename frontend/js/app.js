(function () {
  // Two independent orb instances — landing orb (in-flow, unchanged from
  // Phase 2) and the docked chat orb (fixed, right-center). See
  // particle-sphere.js's factory refactor comment for why these are separate
  // instances rather than one canvas moved between layouts.
  const landingSphere = window.createNimbusSphere("sphere", "sphereState");
  const chatSphere = window.createNimbusSphere("sphereChat", "sphereStateChat");

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

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
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

  function activateChatView() {
    if (conversationStarted) return;
    conversationStarted = true;
    landing.classList.add("landing-exit");
    chatSection.hidden = false;
    appRoot.classList.add("chat-active");
    setTimeout(() => { landing.hidden = true; }, 520);
    // hand off orb state from landing to the docked chat orb
    chatSphere.setState(landingSphere.getState());
  }

  function resetToLanding() {
    conversationStarted = false;
    landing.hidden = false;
    landing.classList.remove("landing-exit");
    chatSection.hidden = true;
    appRoot.classList.remove("chat-active");
    messagesEl.innerHTML = "";
    landingSphere.setState("idle");
    chatSphere.setState("idle");
    currentTitle = null;
    currentConversationId = null;
    lastUserText = null;
    hideAttachmentChip();
    closeAttachMenu();
    fetch("/api/attachment", { method: "DELETE" }).catch(() => {});
    renderSidebarActive();
  }

  // ---------- sidebar ----------

  sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
  });

  newChatBtn.addEventListener("click", resetToLanding);

  async function refreshConversationList() {
    try {
      const res = await fetch("/api/conversations");
      const list = await res.json();
      chatList.innerHTML = "";
      if (!list.length) {
        chatList.innerHTML = '<li class="chat-list-empty">No conversations yet</li>';
        return;
      }
      list.forEach((conv) => {
        const li = document.createElement("li");
        li.textContent = conv.title;
        li.dataset.id = conv.id;
        li.addEventListener("click", () => loadConversationIntoView(conv.id));
        chatList.appendChild(li);
      });
      renderSidebarActive();
    } catch (err) {
      // best-effort — sidebar just stays as it was
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
      if (!res.ok) return;
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

  async function sendMessage(text, viaVoice = false) {
    if (!text.trim()) return;
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

  async function streamInto(assistantBubble, userText, viaVoice) {
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          conversation_id: currentConversationId,
          model: currentModelId,
        }),
      });

      if (!res.ok || !res.body) {
        setAssistantContent(assistantBubble, "Something went wrong reaching Nimbus. Try again in a moment.");
        activeSphere().setState("idle");
        return;
      }

      const returnedId = res.headers.get("X-Conversation-Id");
      if (returnedId) currentConversationId = returnedId;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = "";
      let firstChunk = true;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (firstChunk) {
          activeSphere().setState(viaVoice ? "thinking" : "speaking");
          firstChunk = false;
        }
        full += decoder.decode(value, { stream: true });
        setAssistantContent(assistantBubble, full, { pending: true });
        window.scrollTo({ top: document.body.scrollHeight, behavior: "auto" });
      }
      setAssistantContent(assistantBubble, full);
      refreshConversationList();

      if (viaVoice) {
        speak(full, () => {
          if (voiceChatActive) startListening();
        });
      } else {
        activeSphere().setState("idle");
      }
    } catch (err) {
      setAssistantContent(assistantBubble, "Couldn't reach the Nimbus backend — is it running?");
      activeSphere().setState("idle");
    }
  }

  function regenerateInto(group, bubble, precedingUserText) {
    setAssistantContent(bubble, "", { pending: true });
    activeSphere().setState("thinking");
    streamInto(bubble, precedingUserText, false);
  }

  composerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (voiceChatActive) stopVoiceChat();
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
    // The browser can fire onvoiceschanged more than once, which used to
    // silently reset the selection back to the first option every time —
    // that's the "keeps switching back to the default voice" bug. Restore
    // whatever was previously selected if it's still in the list.
    const stillExists = Array.from(voiceSelect.options).some((o) => o.value === previousSelection);
    if (previousSelection && stillExists) {
      voiceSelect.value = previousSelection;
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

  // ---------- voice input (browser STT) ----------

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;
  let listening = false;
  let voiceChatActive = false;

  function showMicError(message) {
    console.error("Nimbus mic error:", message);
    micBtn.title = `Voice input error: ${message}`;
    flashStateMessage(`Mic error: ${message}`);
  }

  function setVoiceChatUI(active) {
    voiceChatActive = active;
    micBtn.classList.toggle("voice-chat-active", active);
    micBtn.title = active ? "Stop voice chat" : "Start voice chat";
    micBtn.setAttribute("aria-label", active ? "Stop voice chat" : "Start voice chat");
  }

  function startListening() {
    if (!recognizer || listening) return;
    try {
      recognizer.start();
    } catch (err) {
      showMicError(err.message || "couldn't start microphone");
      setVoiceChatUI(false);
    }
  }

  function stopVoiceChat() {
    setVoiceChatUI(false);
    if (listening) recognizer.stop();
    window.speechSynthesis.cancel();
    activeSphere().setState("idle");
  }

  if (SpeechRecognition) {
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

    micBtn.addEventListener("click", () => {
      if (voiceChatActive) {
        stopVoiceChat();
        return;
      }
      setVoiceChatUI(true);
      startListening();
    });
  } else {
    micBtn.disabled = true;
    micBtn.title = "Voice input isn't supported in this browser — try Chrome or Edge";
  }

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
      const models = await res.json();
      modelSelect.innerHTML = "";
      models.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.label;
        modelSelect.appendChild(opt);
      });
      if (models.length) {
        currentModelId = models[0].id;
        modelNameEl.textContent = models[0].label.replace(" (recommended)", "");
      }
    } catch (err) {
      // best-effort — chat still works, backend just uses its own default
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
  }

  // ---------- profile modal ----------

  const profileBtn = document.getElementById("profileBtn");
  const profileOverlay = document.getElementById("profileOverlay");
  const profileClose = document.getElementById("profileClose");
  const profileBody = document.getElementById("profileBody");

  function renderProfile() {
    if (!currentUser) {
      profileBody.innerHTML = `
        <p class="ts-muted">You're using Nimbus as a guest — sign in to keep your own conversation history, attachments, and settings.</p>
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
        <div class="profile-avatar">${initial}</div>
        <div>
          <div class="profile-name">${currentUser.display_name || currentUser.username}${currentUser.is_admin ? ' <span class="admin-badge">Admin</span>' : ""}</div>
          <div class="profile-email">${currentUser.email}</div>
        </div>
      </div>
      <p class="ts-muted" style="margin:0;">Member since ${joined}</p>
      <div class="form-divider"></div>
      <button type="button" class="form-submit secondary" id="profileLogoutBtn">Log out</button>
    `;
    document.getElementById("profileLogoutBtn").addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
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
          <input type="text" id="displayNameInput" class="form-input" value="${(currentUser.display_name || "").replace(/"/g, "&quot;")}" />
        </label>
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
      try {
        const res = await fetch("/api/auth/me", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: document.getElementById("displayNameInput").value }),
        });
        if (res.ok) {
          currentUser = { ...currentUser, ...(await res.json()) };
          successEl.textContent = "Saved.";
          setTimeout(() => { successEl.textContent = ""; }, 2000);
        }
      } catch (err) {
        // best-effort
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
                <td>${u.display_name || u.username}${u.is_admin ? ' <span class="admin-badge">Admin</span>' : ""}</td>
                <td>${u.email}</td>
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
        if (!voiceChatActive) {
          setVoiceChatUI(true);
          startListening();
        }
      } else if (action === "coding") {
        fillComposer("Write code for");
      }
    });
  });

  loadCurrentUser();
})();
