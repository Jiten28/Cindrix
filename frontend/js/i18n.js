(function () {
  // Real client-side i18n via i18next (loaded from CDN in index.html — no
  // bundler in this project, so a plain UMD build fits with the least
  // friction; see docs/Architecture.md). Translation files live in
  // frontend/i18n/*.json and are fetched at startup, not hardcoded here.
  //
  // Scope: UI chrome only (sidebar, chips, composer placeholder, nav/topbar
  // controls) — never the AI's own responses, and never voice recognition
  // language (recognizer.lang in app.js stays "en-US" on purpose; that's a
  // separate, deliberately out-of-scope concern per the task brief).

  const SUPPORTED_LANGS = [
    { code: "en", label: "English" },
    { code: "es", label: "Español" },
    { code: "fr", label: "Français" },
    { code: "hi", label: "हिन्दी" },
  ];
  const STORAGE_KEY = "cindrix-lang";

  function detectInitialLang() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && SUPPORTED_LANGS.some((l) => l.code === saved)) return saved;
    } catch (err) {
      // localStorage unavailable (private mode etc.) — fall through
    }
    const browserLang = (navigator.language || "en").slice(0, 2);
    return SUPPORTED_LANGS.some((l) => l.code === browserLang) ? browserLang : "en";
  }

  async function loadResources() {
    const resources = {};
    await Promise.all(
      SUPPORTED_LANGS.map(async ({ code }) => {
        const res = await fetch(`i18n/${code}.json`);
        resources[code] = { translation: await res.json() };
      })
    );
    return resources;
  }

  function applyTranslations() {
    // Call window.i18next.t(...) directly rather than detaching it into a
    // local `t` reference — don't rely on it being safe to call unbound.
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = window.i18next.t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = window.i18next.t(el.getAttribute("data-i18n-placeholder"));
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      el.setAttribute("aria-label", window.i18next.t(el.getAttribute("data-i18n-aria-label")));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = window.i18next.t(el.getAttribute("data-i18n-title"));
    });
    document.documentElement.lang = window.i18next.language;
  }

  function populateLanguageSwitcher() {
    const select = document.getElementById("langSelect");
    if (!select) return;
    select.innerHTML = "";
    SUPPORTED_LANGS.forEach(({ code, label }) => {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = label;
      select.appendChild(opt);
    });
    select.value = window.i18next.language;
    select.addEventListener("change", () => {
      window.CindrixI18n.changeLanguage(select.value);
    });
  }

  async function changeLanguage(lang) {
    await window.i18next.changeLanguage(lang);
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (err) {
      // best-effort persistence only
    }
    applyTranslations();
  }

  // t() with a plain-English fallback, for the handful of places app.js
  // needs a translated string for content it creates dynamically (after
  // this module has finished initializing, in practice, but the fallback
  // keeps things sane even if called before init resolves).
  function t(key, fallback) {
    return window.i18next && window.i18next.isInitialized ? window.i18next.t(key) : fallback;
  }

  window.CindrixI18n = {
    t,
    apply: applyTranslations,
    changeLanguage,
    ready: (async function init() {
      const resources = await loadResources();
      await window.i18next.init({
        lng: detectInitialLang(),
        fallbackLng: "en",
        resources,
        interpolation: { escapeValue: false },
      });
      applyTranslations();
      populateLanguageSwitcher();
    })(),
  };
})();
