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
  let lastUserText = null; // for regenerate

  // ---------- tiny markdown renderer ----------
  // Supports: ```code fences``` (+ hljs highlighting), `inline code`,
  // **bold**, *italic*, ![images](url), tables, and - / 1. lists.
  // Hand-rolled instead of a library — Gemini's output only ever needs this
  // subset, and escaping HTML first keeps it safe even though the content is
  // model-generated, not directly user-controllable.

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
    lastUserText = null;
    hideAttachmentChip();
    closeAttachMenu();
    fetch("/api/attachment", { method: "DELETE" }).catch(() => {});
  }

  // ---------- sidebar ----------

  sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
  });

  newChatBtn.addEventListener("click", resetToLanding);

  function addSidebarEntry(title) {
    const empty = chatList.querySelector(".chat-list-empty");
    if (empty) empty.remove();
    const li = document.createElement("li");
    li.textContent = title;
    chatList.prepend(li);
  }

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
    messagesEl.scrollIntoView && bubble.scrollIntoView({ block: "end", behavior: "smooth" });
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
      addSidebarEntry(currentTitle);
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
        body: JSON.stringify({ message: userText }),
      });

      if (!res.ok || !res.body) {
        setAssistantContent(assistantBubble, "Something went wrong reaching Nimbus. Try again in a moment.");
        activeSphere().setState("idle");
        return;
      }

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
      await fetch("/api/attachment", { method: "DELETE" });
    } catch (err) {
      // best-effort — hide the chip either way, it's just UI state
    }
    hideAttachmentChip();
  });

  // ---------- voice selector ("other audio options") ----------

  const voiceSelect = document.getElementById("voiceSelect");
  let availableVoices = [];

  function loadVoices() {
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
})();
