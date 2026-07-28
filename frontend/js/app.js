(function () {
  const sphere = window.NimbusSphere;

  // ---------- tiny markdown renderer (escape first, then format) ----------
  // Supports: ```code fences```, `inline code`, **bold**, *italic*, line breaks.
  // Deliberately hand-rolled instead of pulling in a library — Gemini's output
  // only ever uses this small subset, and escaping HTML first keeps it safe
  // even though the content is model-generated, not directly user-controlled.

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
      html += formatInline(text);
      if (blocks[i + 2] !== undefined) {
        const code = blocks[i + 2];
        html += `<pre><code>${code}</code></pre>`;
      }
    }
    return html;
  }

  function formatInline(text) {
    return text
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/\n/g, "<br>");
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

  let conversationStarted = false;
  let currentTitle = null;

  // ---------- view transitions ----------

  function activateChatView() {
    if (conversationStarted) return;
    conversationStarted = true;
    landing.hidden = true;
    chatSection.hidden = false;
    appRoot.classList.add("chat-active");
  }

  function resetToLanding() {
    conversationStarted = false;
    landing.hidden = false;
    chatSection.hidden = true;
    appRoot.classList.remove("chat-active");
    messagesEl.innerHTML = "";
    sphere.setState("idle");
    currentTitle = null;
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

  // ---------- suggestion chips ----------

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      composerInput.value = chip.textContent + ": ";
      composerInput.focus();
    });
  });

  // ---------- messages ----------

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = `msg msg-${role}`;
    if (role === "assistant") {
      el.innerHTML = renderMarkdown(text);
    } else {
      el.textContent = text;
    }
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  // ---------- send flow ----------
  // viaVoice controls whether the reply gets spoken: true only when this
  // turn came from the mic, never for typed messages — per your rule that
  // text in should mean text out, voice in should mean voice out.

  async function sendMessage(text, viaVoice = false) {
    if (!text.trim()) return;

    activateChatView();
    if (!currentTitle) {
      currentTitle = text.length > 34 ? text.slice(0, 34) + "…" : text;
      addSidebarEntry(currentTitle);
    }

    appendMessage("user", text);
    composerInput.value = "";

    const assistantEl = appendMessage("assistant", "");
    assistantEl.classList.add("pending");
    sphere.setState("thinking");

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      if (!res.ok || !res.body) {
        assistantEl.textContent = "Something went wrong reaching Nimbus. Try again in a moment.";
        assistantEl.classList.remove("pending");
        sphere.setState("idle");
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
          sphere.setState(viaVoice ? "thinking" : "speaking");
          assistantEl.classList.remove("pending");
          firstChunk = false;
        }
        full += decoder.decode(value, { stream: true });
        assistantEl.innerHTML = renderMarkdown(full);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }

      if (viaVoice) {
        // hold "thinking" through the (silent) stream, switch to "speaking"
        // only once actual audio starts, then loop back to listening.
        speak(full, () => {
          if (voiceChatActive) startListening();
        });
      } else {
        sphere.setState("idle");
      }
    } catch (err) {
      assistantEl.textContent = "Couldn't reach the Nimbus backend — is it running?";
      assistantEl.classList.remove("pending");
      sphere.setState("idle");
    }
  }

  composerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    // Typing manually always breaks out of an active voice-chat loop —
    // once you're driving by text, replies go back to text-only.
    if (voiceChatActive) stopVoiceChat();
    sendMessage(composerInput.value, false);
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
      sphere.setState("idle");
      if (onDone) onDone();
      return;
    }
    sphere.setState("speaking");
    const utter = new SpeechSynthesisUtterance(stripMarkdownForSpeech(text));
    const chosenVoice = availableVoices.find((v) => v.name === voiceSelect.value);
    if (chosenVoice) utter.voice = chosenVoice;
    const finish = () => {
      sphere.setState("idle");
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
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1");
  }

  // ---------- voice input (browser STT) ----------


  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;
  let listening = false;
  const sphereStateLabel = document.getElementById("sphereState");

  function showMicError(message) {
    console.error("Nimbus mic error:", message);
    micBtn.title = `Voice input error: ${message}`;
    if (sphereStateLabel) {
      const prev = sphere.getState();
      sphereStateLabel.textContent = `Mic error: ${message}`;
      setTimeout(() => {
        sphereStateLabel.textContent = prev.charAt(0).toUpperCase() + prev.slice(1);
      }, 2500);
    }
  }

  let voiceChatActive = false;

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
    sphere.setState("idle");
  }

  if (SpeechRecognition) {
    recognizer = new SpeechRecognition();
    recognizer.continuous = false;
    recognizer.interimResults = false;
    recognizer.lang = "en-US";

    recognizer.onstart = () => {
      listening = true;
      micBtn.classList.add("listening");
      sphere.setState("listening");
    };

    recognizer.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      composerInput.value = transcript;
      sendMessage(transcript, true); // true = spoken reply, then loop back to listening
    };

    recognizer.onerror = (event) => {
      listening = false;
      micBtn.classList.remove("listening");
      sphere.setState("idle");
      // Common causes: "not-allowed" (mic permission denied — check the
      // browser's site settings / the permission prompt), "no-speech"
      // (nothing heard before the timeout), "audio-capture" (no mic found).
      // Any error stops the loop rather than silently retrying forever —
      // click the mic again to restart it.
      showMicError(event.error || "unknown");
      setVoiceChatUI(false);
    };

    recognizer.onend = () => {
      listening = false;
      micBtn.classList.remove("listening");
      if (sphere.getState() === "listening") sphere.setState("idle");
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

  // ---------- attach button (file upload — Phase 2) ----------

  const attachBtn = document.getElementById("attachBtn");
  attachBtn.addEventListener("click", () => {
    const label = document.getElementById("sphereState");
    if (!label) return;
    const prev = sphere.getState();
    label.textContent = "File upload arrives in Phase 2";
    setTimeout(() => {
      label.textContent = prev.charAt(0).toUpperCase() + prev.slice(1);
    }, 2500);
  });
})();
