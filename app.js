const STORAGE_KEY = "sonarr-nyaa-proxy-manager.rules.v1";
const THEME_KEY = "sonarr-nyaa-proxy-manager.theme";

const defaultRules = [
  { id: "year-hygiene", type: "title rewrite", name: "Strip release years", description: "Removes bracketed years before classification so 2021, 2023, and 2024 never become episode-like tokens." },
  { id: "season-classification", type: "season pack", name: "Normalize season packs", description: "Recognizes Season 1, S01, and ordinal seasons, then rewrites accepted packs to a Sonarr-safe Sxx title." },
  { id: "episode-isolation", type: "episode filter", name: "Episode scans stay episodic", description: "Only returns an exact SxxExx release for an episode search. Packs and episode ranges are excluded." },
  { id: "season-isolation", type: "season filter", name: "Season scans stay seasonal", description: "Excludes single episodes and partial ranges from season searches while keeping full packs for the requested season." },
  { id: "series-anchor", type: "series safety", name: "Anchor the series match", description: "Requires meaningful title words to match, reducing substring results for a different show." },
  { id: "query-expansion", type: "search strategy", name: "Expand release queries", description: "Searches padded, unpadded, ordinal, and year-aware season forms to retain EMBER, Judas, Anime Time, and DB results." },
  { id: "direct-torrent", type: "delivery", name: "Provide torrent links", description: "Prefers a magnet link when Nyaa provides an info hash and falls back to its torrent download URL otherwise." },
  { id: "dual-audio", type: "languages", name: "Annotate Dual Audio", description: "Adds Japanese and English to Dual Audio titles and Torznab metadata so Sonarr sees both languages." },
];

let customRules = loadRules();
let currentTheme = localStorage.getItem(THEME_KEY) || "dark";

const els = {
  defaultRules: document.querySelector("#defaultRules"),
  customRules: document.querySelector("#customRules"),
  emptyState: document.querySelector("#emptyState"),
  form: document.querySelector("#ruleForm"),
  themeToggle: document.querySelector("#themeToggle"),
  themeLabel: document.querySelector("#themeLabel"),
  defaultCount: document.querySelector("#defaultCount"),
  customCount: document.querySelector("#customCount"),
  activeCount: document.querySelector("#activeCount"),
  navDefaultCount: document.querySelector("#navDefaultCount"),
  navCustomCount: document.querySelector("#navCustomCount"),
};

function loadRules() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch { return []; }
}

function saveRules() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(customRules));
  fetch("/manager/api/rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customRules }),
  }).catch(() => undefined);
}

async function hydrateRules() {
  try {
    const response = await fetch("/manager/api/rules");
    if (!response.ok) return;
    const payload = await response.json();
    if (Array.isArray(payload.customRules)) {
      customRules = payload.customRules;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(customRules));
      render();
    }
  } catch { /* Direct file use keeps the local-first fallback. */ }
}

function ruleCard(rule) {
  return `<article class="rule-card"><div class="rule-meta"><span class="tag">${rule.type}</span><span class="locked">LOCKED</span></div><h3>${rule.name}</h3><p>${rule.description}</p></article>`;
}

function customRuleCard(rule) {
  const state = rule.enabled ? "is-on" : "";
  return `<article class="custom-rule" data-id="${rule.id}">
    <button class="toggle ${state}" type="button" aria-label="${rule.enabled ? "Disable" : "Enable"} ${rule.name}" data-action="toggle"><i></i></button>
    <div><h3>${escapeHtml(rule.name)}</h3><p>${escapeHtml(rule.type)} · ${escapeHtml(rule.action)} · ${escapeHtml(rule.match)}</p></div>
    <span class="tag">custom</span>
    <button class="delete-rule" type="button" data-action="delete">Remove</button>
  </article>`;
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function render() {
  els.defaultRules.innerHTML = defaultRules.map(ruleCard).join("");
  els.customRules.innerHTML = customRules.map(customRuleCard).join("");
  els.emptyState.hidden = customRules.length > 0;
  const activeCustom = customRules.filter(rule => rule.enabled).length;
  els.defaultCount.textContent = defaultRules.length;
  els.customCount.textContent = customRules.length;
  els.activeCount.textContent = defaultRules.length + activeCustom;
  els.navDefaultCount.textContent = defaultRules.length;
  els.navCustomCount.textContent = customRules.length;
}

function setTheme(theme) {
  currentTheme = theme;
  document.documentElement.dataset.theme = theme;
  els.themeLabel.textContent = theme === "dark" ? "Light" : "Dark";
  els.themeToggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
  localStorage.setItem(THEME_KEY, theme);
}

function showForm() {
  els.form.hidden = false;
  document.querySelector("#ruleName").focus();
  els.form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideForm() { els.form.hidden = true; els.form.reset(); }

document.querySelector("#openRuleForm").addEventListener("click", showForm);
document.querySelector("#emptyAddRule").addEventListener("click", showForm);
document.querySelector("#closeRuleForm").addEventListener("click", hideForm);

els.form.addEventListener("submit", event => {
  event.preventDefault();
  const formData = new FormData(els.form);
  customRules.unshift({
    id: crypto.randomUUID(),
    name: formData.get("name").trim(),
    type: formData.get("type"),
    match: formData.get("match").trim(),
    action: formData.get("action"),
    enabled: true,
  });
  saveRules(); render(); hideForm();
});

els.customRules.addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest("[data-id]");
  const id = card.dataset.id;
  if (button.dataset.action === "toggle") {
    customRules = customRules.map(rule => rule.id === id ? { ...rule, enabled: !rule.enabled } : rule);
  } else if (button.dataset.action === "delete") {
    customRules = customRules.filter(rule => rule.id !== id);
  }
  saveRules(); render();
});

els.themeToggle.addEventListener("click", () => setTheme(currentTheme === "dark" ? "light" : "dark"));

document.querySelector("#exportRules").addEventListener("click", () => {
  const payload = { schemaVersion: 1, exportedAt: new Date().toISOString(), defaults: defaultRules, customRules };
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  link.download = "sonarr-nyaa-proxy-rules.json";
  link.click();
  URL.revokeObjectURL(link.href);
});

setTheme(currentTheme);
render();
hydrateRules();
