const STORAGE_KEY = "sonarr-proxy-manager.rules.v2";
const THEME_KEY = "sonarr-proxy-manager.theme";
const LEGACY_STORAGE_KEY = "sonarr-nyaa-proxy-manager.rules.v1";
const LEGACY_THEME_KEY = "sonarr-nyaa-proxy-manager.theme";
const ICONS = {
  lock: "033-lock.png",
  unlock: "034-lock-1.png",
  edit: "020-pen.png",
  delete: "007-trash-1.png",
  moon: "050-dark.png",
  sun: "sun.png",
};
const ruleCatalog = [
  { id: "year-hygiene", type: "title rewrite", name: "Strip release years", description: "Removes bracketed years before classification so release years are not mistaken for episode numbers." },
  { id: "season-classification", type: "season pack", name: "Normalize season packs", description: "Recognizes Season 1, S01, and ordinal seasons, then rewrites accepted packs to a Sonarr-safe Sxx title." },
  { id: "episode-isolation", type: "episode filter", name: "Episode scans stay episodic", description: "Only returns an exact SxxExx release for an episode search. Packs and episode ranges are excluded." },
  { id: "season-isolation", type: "season filter", name: "Season scans stay seasonal", description: "Excludes single episodes and partial ranges from season searches while keeping full packs for the requested season." },
  { id: "series-anchor", type: "series safety", name: "Anchor the series match", description: "Requires meaningful title words to match, reducing substring results for a different show." },
  { id: "query-expansion", type: "search strategy", name: "Expand release queries", description: "Searches padded, unpadded, ordinal, and year-aware season forms to retain additional release-group results." },
  { id: "direct-torrent", type: "delivery", name: "Provide torrent links", description: "Uses Nyaa's torrent download URL for accepted releases." },
  { id: "dual-audio", type: "languages", name: "Annotate Dual Audio", description: "Adds Japanese and English to Dual Audio titles and Torznab metadata so Sonarr sees both languages." },
];

const els = {
  defaultRules: document.querySelector("#defaultRules"),
  customRules: document.querySelector("#customRules"),
  emptyState: document.querySelector("#emptyState"),
  form: document.querySelector("#ruleForm"),
  themeToggle: document.querySelector("#themeToggle"),
  themeLabel: document.querySelector("#themeLabel"),
  themeIcon: document.querySelector("#themeIcon"),
  saveStatus: document.querySelector("#saveStatus"),
  defaultCount: document.querySelector("#defaultCount"),
  customCount: document.querySelector("#customCount"),
  activeCount: document.querySelector("#activeCount"),
  navDefaultCount: document.querySelector("#navDefaultCount"),
  navCustomCount: document.querySelector("#navCustomCount"),
  ruleAction: document.querySelector("#ruleAction"),
  valueField: document.querySelector("#valueField"),
  ruleValue: document.querySelector("#ruleValue"),
};

const defaultSettings = Object.fromEntries(ruleCatalog.map(rule => [rule.id, {
  enabled: true,
  locked: false,
  name: rule.name,
  description: rule.description,
}]));
let customRules = [];
let editingRule = null;
let currentTheme = localStorage.getItem(THEME_KEY) || localStorage.getItem(LEGACY_THEME_KEY) || "dark";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function icon(name, className = "") {
  return `<span class="ui-icon ${className}" style="--icon-url: url('/manager/assets/icons/${ICONS[name]}')" aria-hidden="true"></span>`;
}

function applyConfig(payload) {
  if (payload && typeof payload.defaults === "object" && !Array.isArray(payload.defaults)) {
    for (const rule of ruleCatalog) {
      const incoming = payload.defaults[rule.id];
      if (incoming && typeof incoming === "object") {
        defaultSettings[rule.id] = { ...defaultSettings[rule.id], ...incoming };
      }
    }
  }
  if (Array.isArray(payload?.customRules)) {
    customRules = payload.customRules;
  } else if (Array.isArray(payload)) {
    customRules = payload.map(rule => ({
      id: rule.id || crypto.randomUUID(),
      name: rule.name || "Imported rule",
      match: rule.match || "",
      action: rule.action === "keep" ? "prefer" : rule.action || "exclude",
      scope: "all",
      value: rule.value || "",
      enabled: rule.enabled !== false,
      locked: false,
    }));
  }
}

function saveRules() {
  const payload = { schemaVersion: 2, defaults: defaultSettings, customRules };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  els.saveStatus.textContent = "Saving";
  els.saveStatus.classList.add("is-saving");
  return fetch("/manager/api/rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async response => {
    if (response.status === 401 || response.status === 503) {
      window.location.assign("/manager/login");
      return;
    }
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.error || "Could not save rules");
    }
    els.saveStatus.textContent = "Synced";
    els.saveStatus.classList.remove("is-saving", "is-error");
  }).catch(error => {
    els.saveStatus.textContent = "Not synced";
    els.saveStatus.title = error.message;
    els.saveStatus.classList.remove("is-saving");
    els.saveStatus.classList.add("is-error");
  });
}

async function hydrateRules() {
  try {
    const response = await fetch("/manager/api/rules");
    if (response.status === 401 || response.status === 503) {
      window.location.assign("/manager/login");
      return;
    }
    if (!response.ok) throw new Error("Rules API unavailable");
    const payload = await response.json();
    applyConfig(payload);
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ defaults: defaultSettings, customRules }));
    render();
  } catch {
    try {
      const cached = localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_STORAGE_KEY);
      if (cached) applyConfig(JSON.parse(cached));
    } catch { /* Keep the built-in defaults if the browser cache is invalid. */ }
    els.saveStatus.textContent = "Offline";
    render();
  }
}

function ruleEditor(rule, kind) {
  return `<div class="inline-editor" data-editor="${kind}" data-id="${escapeHtml(rule.id)}">
    <label>Name<input name="name" maxlength="64" value="${escapeHtml(rule.name)}" required /></label>
    <label>Description<textarea name="description" maxlength="240" rows="3" required>${escapeHtml(rule.description || "")}</textarea></label>
    <div class="editor-actions"><button class="button button-primary" type="button" data-action="save-edit">Save changes</button><button class="button button-secondary" type="button" data-action="cancel-edit">Cancel</button></div>
  </div>`;
}

function defaultRuleCard(rule) {
  const settings = defaultSettings[rule.id];
  const locked = settings.locked;
  const editing = editingRule?.kind === "default" && editingRule.id === rule.id;
  return `<article class="rule-card ${settings.enabled ? "is-enabled" : "is-disabled"}" data-kind="default" data-id="${rule.id}">
    <div class="rule-meta"><span class="tag">${escapeHtml(rule.type)}</span><div class="card-actions">
      ${locked ? "" : `<button class="icon-action" type="button" data-action="edit" aria-label="Edit ${escapeHtml(settings.name)}" title="Edit rule">${icon("edit")}</button>`}
      <button class="icon-action lock-action" type="button" data-action="lock" aria-label="${locked ? "Unlock" : "Lock"} ${escapeHtml(settings.name)}" aria-pressed="${locked}" title="${locked ? "Unlock editing" : "Lock editing"}">${icon(locked ? "lock" : "unlock")}</button>
    </div></div>
    <label class="rule-state"><input type="checkbox" data-action="enabled" ${settings.enabled ? "checked" : ""} ${locked ? "disabled" : ""} /><span><i></i>${settings.enabled ? "Active" : "Off"}</span></label>
    <button class="rule-content" type="button" data-action="edit" ${locked ? "disabled" : ""} aria-label="Edit ${escapeHtml(settings.name)}">
      <span class="rule-name">${escapeHtml(settings.name)}</span><span class="rule-description">${escapeHtml(settings.description)}</span>
    </button>
    ${editing ? ruleEditor(settings, "default") : ""}
  </article>`;
}

function scopeLabel(scope) {
  return ({ all: "all searches", episodes: "episode scans", seasons: "season scans" })[scope] || "all searches";
}

function actionLabel(action) {
  return ({ exclude: "exclude", prefer: "prefer", rewrite: "rewrite", annotate: "annotate" })[action] || action;
}

function customRuleEditor(rule) {
  return `<div class="inline-editor custom-editor" data-editor="custom" data-id="${escapeHtml(rule.id)}">
    <label>Name<input name="name" maxlength="64" value="${escapeHtml(rule.name)}" required /></label>
    <label>Title contains<input name="match" maxlength="120" value="${escapeHtml(rule.match)}" required /></label>
    <label>Scope<select name="scope"><option value="all" ${rule.scope === "all" ? "selected" : ""}>Episodes and seasons</option><option value="episodes" ${rule.scope === "episodes" ? "selected" : ""}>Single episodes only</option><option value="seasons" ${rule.scope === "seasons" ? "selected" : ""}>Season packs only</option></select></label>
    <label>Action<select name="action"><option value="prefer" ${rule.action === "prefer" ? "selected" : ""}>Prefer matching results</option><option value="exclude" ${rule.action === "exclude" ? "selected" : ""}>Exclude matching results</option><option value="rewrite" ${rule.action === "rewrite" ? "selected" : ""}>Replace matching text</option><option value="annotate" ${rule.action === "annotate" ? "selected" : ""}>Add a title label</option></select></label>
    <label class="editor-value">Replacement or label<input name="value" maxlength="120" value="${escapeHtml(rule.value || "")}" /></label>
    <div class="editor-actions"><button class="button button-primary" type="button" data-action="save-edit">Save changes</button><button class="button button-secondary" type="button" data-action="cancel-edit">Cancel</button></div>
  </div>`;
}

function customRuleCard(rule) {
  const locked = rule.locked === true;
  const editing = editingRule?.kind === "custom" && editingRule.id === rule.id;
  return `<article class="custom-rule ${rule.enabled ? "is-enabled" : "is-disabled"}" data-kind="custom" data-id="${escapeHtml(rule.id)}">
    <label class="rule-state"><input type="checkbox" data-action="enabled" ${rule.enabled ? "checked" : ""} ${locked ? "disabled" : ""} /><span><i></i>${rule.enabled ? "Active" : "Off"}</span></label>
    <button class="rule-content" type="button" data-action="edit" ${locked ? "disabled" : ""} aria-label="Edit ${escapeHtml(rule.name)}">
      <span class="rule-name">${escapeHtml(rule.name)}</span><span class="rule-description">${escapeHtml(rule.action)} · ${escapeHtml(scopeLabel(rule.scope))} · contains “${escapeHtml(rule.match)}”</span>
    </button>
    <div class="custom-actions">
      ${locked ? "" : `<button class="icon-action" type="button" data-action="edit" aria-label="Edit ${escapeHtml(rule.name)}" title="Edit rule">${icon("edit")}</button>`}
      <button class="icon-action lock-action" type="button" data-action="lock" aria-label="${locked ? "Unlock" : "Lock"} ${escapeHtml(rule.name)}" aria-pressed="${locked}" title="${locked ? "Unlock editing" : "Lock editing"}">${icon(locked ? "lock" : "unlock")}</button>
      <button class="icon-action" type="button" data-action="delete" aria-label="Remove ${escapeHtml(rule.name)}" title="Remove rule" ${locked ? "disabled" : ""}>${icon("delete")}</button>
    </div>
    ${editing ? customRuleEditor(rule) : ""}
  </article>`;
}

function render() {
  els.defaultRules.innerHTML = ruleCatalog.map(defaultRuleCard).join("");
  els.customRules.innerHTML = customRules.map(customRuleCard).join("");
  els.emptyState.hidden = customRules.length > 0;
  els.defaultCount.textContent = ruleCatalog.length;
  els.customCount.textContent = customRules.length;
  els.activeCount.textContent = [...Object.values(defaultSettings), ...customRules].filter(rule => rule.enabled).length;
  els.navDefaultCount.textContent = ruleCatalog.length;
  els.navCustomCount.textContent = customRules.length;
}

function setTheme(theme) {
  currentTheme = theme;
  document.documentElement.dataset.theme = theme;
  els.themeLabel.textContent = theme === "dark" ? "Light" : "Dark";
  els.themeIcon.style.setProperty("--icon-url", `url('/manager/assets/icons/${theme === "dark" ? ICONS.sun : ICONS.moon}')`);
  els.themeToggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
  localStorage.setItem(THEME_KEY, theme);
}

function showForm() {
  els.form.hidden = false;
  document.querySelector("#ruleName").focus();
  els.form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideForm() { els.form.hidden = true; els.form.reset(); updateValueRequirement(); }

function updateValueRequirement() {
  const needsValue = ["rewrite", "annotate"].includes(els.ruleAction.value);
  els.ruleValue.required = needsValue;
  els.ruleValue.disabled = !needsValue;
  els.valueField.classList.toggle("is-muted", !needsValue);
}

function findRule(kind, id) {
  return kind === "default" ? defaultSettings[id] : customRules.find(rule => rule.id === id);
}

function handleRuleClick(event, container) {
  const article = event.target.closest("article[data-kind][data-id]");
  if (!article || !container.contains(article)) return;
  const { kind, id } = article.dataset;
  const rule = findRule(kind, id);
  const actionButton = event.target.closest("[data-action]");
  const action = actionButton?.dataset.action;

  if (action === "lock") {
    rule.locked = !rule.locked;
    if (rule.locked && editingRule?.kind === kind && editingRule.id === id) editingRule = null;
  } else if (action === "enabled") {
    rule.enabled = actionButton.checked;
  } else if (action === "edit") {
    if (rule.locked) return;
    editingRule = editingRule?.kind === kind && editingRule.id === id ? null : { kind, id };
  } else if (action === "delete" && kind === "custom" && !rule.locked) {
    customRules = customRules.filter(item => item.id !== id);
    if (editingRule?.id === id) editingRule = null;
  } else if (action === "cancel-edit") {
    editingRule = null;
  } else if (action === "save-edit") {
    const editor = actionButton.closest(".inline-editor");
    const read = name => editor.querySelector(`[name="${name}"]`)?.value?.trim() ?? "";
    if (kind === "default") {
      rule.name = read("name").slice(0, 64);
      rule.description = read("description").slice(0, 240);
    } else {
      Object.assign(rule, {
        name: read("name").slice(0, 64),
        match: read("match").slice(0, 120),
        scope: read("scope"),
        action: read("action"),
        value: read("value").slice(0, 120),
      });
    }
    if (!rule.name || (kind === "custom" && (!rule.match || (["rewrite", "annotate"].includes(rule.action) && !rule.value)))) {
      els.saveStatus.textContent = "Check rule fields";
      els.saveStatus.classList.add("is-error");
      return;
    }
    editingRule = null;
  } else if (!actionButton && event.target.closest(".rule-content")) {
    if (rule.locked) return;
    editingRule = { kind, id };
  }
  render();
  if (["lock", "enabled", "delete", "save-edit"].includes(action)) saveRules();
  else if (action === "edit" || action === "cancel-edit") return;
}

document.querySelector("#openRuleForm").addEventListener("click", showForm);
document.querySelector("#emptyAddRule").addEventListener("click", showForm);
document.querySelector("#closeRuleForm").addEventListener("click", hideForm);
els.ruleAction.addEventListener("change", updateValueRequirement);
els.form.addEventListener("submit", event => {
  event.preventDefault();
  const formData = new FormData(els.form);
  customRules.unshift({
    id: crypto.randomUUID(),
    name: String(formData.get("name")).trim(),
    match: String(formData.get("match")).trim(),
    scope: String(formData.get("scope")),
    action: String(formData.get("action")),
    value: String(formData.get("value") || "").trim(),
    enabled: true,
    locked: false,
  });
  editingRule = null;
  saveRules(); render(); hideForm();
});
els.defaultRules.addEventListener("click", event => handleRuleClick(event, els.defaultRules));
els.customRules.addEventListener("click", event => handleRuleClick(event, els.customRules));
els.themeToggle.addEventListener("click", () => setTheme(currentTheme === "dark" ? "light" : "dark"));

document.querySelector("#logoutButton").addEventListener("click", async () => {
  try { await fetch("/manager/api/logout", { method: "POST" }); } catch { /* Leave the UI even if the network is unavailable. */ }
  window.location.assign("/manager/login");
});

document.querySelector("#exportRules").addEventListener("click", () => {
  const payload = { schemaVersion: 2, exportedAt: new Date().toISOString(), defaults: defaultSettings, customRules };
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  link.download = "sonarr-proxy-manager-rules.json";
  link.click();
  URL.revokeObjectURL(link.href);
});

setTheme(currentTheme);
updateValueRequirement();
try {
  const cached = localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_STORAGE_KEY);
  if (cached) applyConfig(JSON.parse(cached));
} catch { /* Server configuration remains authoritative. */ }
render();
hydrateRules();
