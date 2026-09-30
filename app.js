const SCHEMA_VERSION = 4;
const STORAGE_KEY = "sonarr-proxy-manager.rules.v4";
const THEME_KEY = "sonarr-proxy-manager.theme";
const ruleCatalog = [
  { id: "year-hygiene", type: "Title rewrite", name: "Strip release years", description: "Removes bracketed years before classification so release years are not mistaken for episode numbers." },
  { id: "season-classification", type: "Season pack", name: "Normalize season packs", description: "Recognizes Season 1, S01, and ordinal seasons, then rewrites accepted packs to a Sonarr-safe Sxx title." },
  { id: "episode-isolation", type: "Episode filter", name: "Episode scans stay episodic", description: "Only returns the exact requested SxxExx release for an episode search. Packs and episode ranges are excluded." },
  { id: "season-isolation", type: "Season filter", name: "Season scans stay seasonal", description: "Excludes single episodes and partial ranges from season searches while keeping full packs for the requested season." },
  { id: "series-anchor", type: "Series safety", name: "Anchor the series match", description: "Requires meaningful title words to match, reducing substring results for a different show." },
  { id: "query-expansion", type: "Search strategy", name: "Expand release queries", description: "Searches padded, unpadded, ordinal, and year-aware season forms to retain additional release-group results." },
  { id: "direct-torrent", type: "Delivery", name: "Provide torrent links", description: "Uses the upstream indexer's download link for accepted releases." },
  { id: "dual-audio", type: "Languages", name: "Annotate Dual Audio", description: "Adds Japanese and English to Dual Audio titles and Torznab metadata so Sonarr sees both languages." },
];
const byId = id => document.getElementById(id);
const siteSelectRoots = [];
let indexerCatalog = [{ id: "nyaa", name: "Nyaa" }];
let feeds = [];
let sources = [];
let settings = null;
let currentPage = "rules";
let integrationBusy = false;
let editingFeedId = null;
function rulesEndpoint() { return `/manager/api/rules${byId("ruleProfile").value ? `?feed=${encodeURIComponent(byId("ruleProfile").value)}` : ""}`; }
const els = Object.fromEntries([
  "defaultRules", "customRules", "defaultSection", "customSection", "emptyState", "noResults",
  "ruleDialog", "ruleForm", "ruleName", "ruleDescription", "descriptionField", "customFields",
  "ruleMatch", "ruleScope", "ruleIndexer", "ruleAction", "ruleValue", "valueField", "valueLabel", "editorError",
  "themeToggle", "themeIcon", "themeLabel", "saveStatus", "feedback", "ruleSearch", "stateFilter",
].map(id => [id, byId(id)]));

function readStorage(key) { try { return localStorage.getItem(key); } catch { return null; } }
function writeStorage(key, value) { try { localStorage.setItem(key, value); } catch { /* Server saves remain available without browser storage. */ } }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function icon(name) { return `<span class="ui-icon icon-${name}" aria-hidden="true"></span>`; }
function syncSiteSelect(root) {
  if (!root) return;
  const select = root.querySelector("select");
  const trigger = root.querySelector(".site-select-trigger");
  const selected = root.querySelector(`[data-value="${CSS.escape(select.value)}"]`);
  if (!trigger) return;
  trigger.disabled = select.disabled;
  trigger.querySelector(".site-select-value").textContent = selected?.textContent || select.value;
  trigger.setAttribute("aria-label", `${root.dataset.selectLabel}, ${selected?.textContent || select.value}`);
  root.querySelectorAll(".site-option").forEach(option => option.setAttribute("aria-selected", String(option === selected)));
}
function refreshSiteSelect(root) {
  const select = root?.querySelector("select");
  const menu = root?.querySelector(".site-select-menu");
  if (!select || !menu) return;
  menu.replaceChildren();
  [...select.options].forEach(option => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "site-option";
    item.setAttribute("role", "option");
    item.dataset.value = option.value;
    item.innerHTML = '<span class="site-option-check" aria-hidden="true"></span><span class="site-option-label"></span>';
    item.querySelector(".site-option-label").textContent = option.textContent;
    menu.append(item);
  });
  syncSiteSelect(root);
}
function syncSiteSelects() { siteSelectRoots.forEach(syncSiteSelect); }
function setSiteOptionFocus(root, index) {
  const options = [...root.querySelectorAll(".site-option")];
  const target = options[Math.max(0, Math.min(index, options.length - 1))];
  target?.focus();
}
function positionSiteMenu(root) {
  const trigger = root.querySelector(".site-select-trigger");
  const menu = root.querySelector(".site-select-menu");
  const bounds = trigger.getBoundingClientRect();
  menu.style.setProperty("--select-min-width", `${bounds.width}px`);
  const menuBounds = menu.getBoundingClientRect();
  const left = Math.max(12, Math.min(bounds.right - menuBounds.width, window.innerWidth - menuBounds.width - 12));
  const below = window.innerHeight - bounds.bottom;
  const top = below < Math.min(menuBounds.height, 260) + 8 && bounds.top > below
    ? Math.max(12, bounds.top - menuBounds.height - 6)
    : Math.min(bounds.bottom + 6, window.innerHeight - menuBounds.height - 12);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}
function closeSiteMenu(root, restoreFocus = false) {
  const trigger = root.querySelector(".site-select-trigger");
  const menu = root.querySelector(".site-select-menu");
  if (menu.hidden) return;
  menu.hidden = true;
  trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) trigger.focus();
}
function openSiteMenu(root, offset = 0, edge = null) {
  if (root.querySelector("select").disabled) return;
  const menu = root.querySelector(".site-select-menu");
  const options = [...menu.querySelectorAll(".site-option")];
  const selectedIndex = options.findIndex(option => option.getAttribute("aria-selected") === "true");
  menu.hidden = false;
  root.querySelector(".site-select-trigger").setAttribute("aria-expanded", "true");
  positionSiteMenu(root);
  setSiteOptionFocus(root, edge === "first" ? 0 : edge === "last" ? options.length - 1 : Math.max(0, selectedIndex) + offset);
}
function enhanceSiteSelects() {
  document.querySelectorAll(".site-select[data-select-label]").forEach((root, index) => {
    const select = root.querySelector("select");
    const menu = document.createElement("div");
    const trigger = document.createElement("button");
    menu.id = `${select.id}Options`;
    menu.className = "site-select-menu";
    menu.setAttribute("role", "listbox");
    menu.setAttribute("aria-label", root.dataset.selectLabel);
    menu.hidden = true;
    trigger.type = "button";
    trigger.className = "site-select-trigger";
    trigger.setAttribute("aria-label", root.dataset.selectLabel);
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-controls", menu.id);
    trigger.setAttribute("aria-expanded", "false");
    trigger.innerHTML = `<span class="site-select-value"></span><span class="ui-icon icon-chevron" aria-hidden="true"></span>`;
    [...select.options].forEach(option => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "site-option";
      item.setAttribute("role", "option");
      item.dataset.value = option.value;
      item.innerHTML = '<span class="site-option-check" aria-hidden="true"></span><span class="site-option-label"></span>';
      item.querySelector(".site-option-label").textContent = option.textContent;
      menu.append(item);
    });
    select.classList.add("site-select-native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
    root.insertBefore(trigger, select);
    root.append(menu);
    siteSelectRoots.push(root);
    trigger.addEventListener("click", () => menu.hidden ? openSiteMenu(root) : closeSiteMenu(root));
    trigger.addEventListener("keydown", event => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        openSiteMenu(root, event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        openSiteMenu(root, 0, event.key === "Home" ? "first" : "last");
      } else if (event.key === "Escape" && !menu.hidden) {
        event.preventDefault();
        closeSiteMenu(root, true);
      }
    });
    menu.addEventListener("click", event => {
      const option = event.target.closest(".site-option");
      if (!option) return;
      select.value = option.dataset.value;
      syncSiteSelect(root);
      closeSiteMenu(root, true);
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    menu.addEventListener("keydown", event => {
      const options = [...menu.querySelectorAll(".site-option")];
      const activeIndex = options.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        setSiteOptionFocus(root, activeIndex + (event.key === "ArrowDown" ? 1 : -1));
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        setSiteOptionFocus(root, event.key === "Home" ? 0 : options.length - 1);
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeSiteMenu(root, true);
      } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        const query = `${root.dataset.typeahead || ""}${event.key}`.toLowerCase();
        root.dataset.typeahead = query;
        clearTimeout(root.typeaheadTimer);
        root.typeaheadTimer = setTimeout(() => { delete root.dataset.typeahead; }, 700);
        const matchIndex = options.findIndex(option => option.textContent.toLowerCase().startsWith(query));
        if (matchIndex >= 0) setSiteOptionFocus(root, matchIndex);
      }
    });
    syncSiteSelect(root);
  });
  document.addEventListener("pointerdown", event => {
    siteSelectRoots.forEach(root => { if (!root.contains(event.target)) closeSiteMenu(root); });
  });
  document.addEventListener("focusin", event => {
    siteSelectRoots.forEach(root => { if (!root.contains(event.target)) closeSiteMenu(root); });
  });
  window.addEventListener("resize", () => siteSelectRoots.forEach(root => { if (!root.querySelector(".site-select-menu").hidden) positionSiteMenu(root); }));
  window.addEventListener("scroll", () => siteSelectRoots.forEach(root => { if (!root.querySelector(".site-select-menu").hidden) positionSiteMenu(root); }), true);
}
function initialConfig() {
  return {
    schemaVersion: SCHEMA_VERSION,
    defaults: Object.fromEntries(ruleCatalog.map(rule => [rule.id, { enabled: true, locked: true, name: rule.name, description: rule.description }])),
    customRules: [],
  };
}
function indexerName(id) {
  if (!id || id === "all") return "All indexers";
  return indexerCatalog.find(indexer => indexer.id === id)?.name || `Unavailable (${id})`;
}
function setIndexerOptions(selectedId = "all") {
  const select = els.ruleIndexer;
  if (!select) return;
  const feed = feeds.find(value => value.id === byId("ruleProfile").value);
  const available = feed ? indexerCatalog.filter(indexer => feed.sourceIds.includes(indexer.id)) : indexerCatalog.filter(indexer => !sources.length || sources.some(source => source.id === indexer.id && source.origin !== "Prowlarr"));
  const options = [{ id: "all", name: "All indexers in this profile" }, ...available];
  if (selectedId !== "all" && !options.some(indexer => indexer.id === selectedId)) {
    options.push({ id: selectedId, name: `Unavailable (${selectedId})` });
  }
  select.replaceChildren(...options.map(indexer => new Option(indexer.name, indexer.id)));
  select.value = selectedId;
  refreshSiteSelect(select.closest(".site-select"));
}
function normalizeConfig(payload) {
  const normalized = initialConfig();
  if (payload && typeof payload.defaults === "object" && !Array.isArray(payload.defaults)) {
    for (const rule of ruleCatalog) {
      const incoming = payload.defaults[rule.id];
      if (incoming && typeof incoming === "object") normalized.defaults[rule.id] = { ...normalized.defaults[rule.id], ...incoming };
      if (Number(payload.schemaVersion) < 3) normalized.defaults[rule.id].locked = true;
    }
  }
  if (Array.isArray(payload?.customRules)) normalized.customRules = payload.customRules;
  return normalized;
}

let config = initialConfig();
let lastSaved = structuredClone(config);
let canSave = false;
let isSaving = false;
let currentView = "all";
let editingRule = null;
let currentTheme = readStorage(THEME_KEY) || readStorage("sonarr-nyaa-proxy-manager.theme") || "dark";

function setStatus(message, state = "") {
  els.saveStatus.textContent = message;
  els.saveStatus.classList.toggle("is-saving", state === "saving");
  els.saveStatus.classList.toggle("is-error", state === "error");
}
function showError(message) { els.feedback.textContent = message; els.feedback.hidden = !message; }

async function hydrateRules() {
  canSave = false;
  setStatus("Loading rules");
  render();
  try {
    const indexersResponse = await fetch("/manager/api/indexers");
    if (indexersResponse.status === 401 || indexersResponse.status === 503) { window.location.assign("/manager/login"); return; }
    if (!indexersResponse.ok) throw new Error("Could not load configured indexers.");
    const configuredIndexers = await indexersResponse.json();
    if (!Array.isArray(configuredIndexers) || configuredIndexers.some(indexer => typeof indexer.id !== "string" || typeof indexer.name !== "string")) {
      throw new Error("The configured indexer list is invalid.");
    }
    indexerCatalog = configuredIndexers;
    setIndexerOptions(els.ruleIndexer.value || "all");
    const response = await fetch(rulesEndpoint());
    if (response.status === 401 || response.status === 503) { window.location.assign("/manager/login"); return; }
    if (!response.ok) throw new Error("Could not load rules. Reload the page to try again.");
    config = normalizeConfig(await response.json());
    lastSaved = structuredClone(config);
    writeStorage(STORAGE_KEY, JSON.stringify(config));
    canSave = true;
    setStatus("All changes saved");
  } catch (error) {
    setStatus("Offline", "error");
    showError(error.message || "Could not load rules. Reload the page to try again.");
  }
  render();
}

async function saveChanges(change) {
  if (!canSave || isSaving) return false;
  const candidate = structuredClone(config);
  change(candidate);
  config = candidate;
  isSaving = true;
  setStatus("Saving...", "saving");
  showError("");
  render();
  try {
    const response = await fetch(rulesEndpoint(), {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(candidate),
    });
    if (response.status === 401 || response.status === 503) { window.location.assign("/manager/login"); return false; }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Could not save changes. Please try again.");
    config = normalizeConfig(payload);
    lastSaved = structuredClone(config);
    writeStorage(STORAGE_KEY, JSON.stringify(config));
    setStatus("All changes saved");
    return true;
  } catch (error) {
    config = structuredClone(lastSaved);
    setStatus("Changes not saved", "error");
    showError(error.message);
    if (els.ruleDialog.open) { els.editorError.textContent = error.message; els.editorError.hidden = false; }
    return false;
  } finally {
    isSaving = false;
    render();
  }
}

function findRule(kind, id, source = config) { return kind === "default" ? source.defaults[id] : source.customRules.find(rule => rule.id === id); }
function scopeLabel(scope) { return ({ all: "Episodes and seasons", episodes: "Episode searches", seasons: "Season searches" })[scope] || "Episodes and seasons"; }
function actionLabel(action) { return ({ exclude: "Exclude", prefer: "Prefer", rewrite: "Rewrite", annotate: "Annotate" })[action] || action; }

function ruleRow(rule, kind, number, type) {
  const locked = rule.locked === true;
  const blocked = !canSave || isSaving;
  const disabled = blocked || locked;
  const description = kind === "default" ? rule.description : `Title contains "${rule.match}". ${scopeLabel(rule.scope)}. ${indexerName(rule.indexer)}${rule.value ? ` / ${rule.value}` : ""}.`;
  return `<article class="rule-row ${kind === "custom" ? "custom-row" : ""} ${rule.enabled ? "" : "is-disabled"}" data-kind="${kind}" data-id="${escapeHtml(rule.id)}">
    <div class="rule-title"><span class="rule-number" aria-hidden="true">${number}</span><div class="rule-copy"><button class="rule-name" type="button" data-action="edit" ${disabled ? "disabled" : ""} aria-label="Edit ${escapeHtml(rule.name)}">${escapeHtml(rule.name)}</button><p class="rule-description">${escapeHtml(description)}</p></div></div>
    <span class="behavior-tag">${escapeHtml(type)}</span>
    <label class="rule-state"><input type="checkbox" data-action="enabled" aria-label="Enable ${escapeHtml(rule.name)}" ${rule.enabled ? "checked" : ""} ${disabled ? "disabled" : ""} /><span class="switch-track" aria-hidden="true"></span><span class="switch-label" aria-hidden="true">${rule.enabled ? "On" : "Off"}</span></label>
    <div class="access-actions"><button class="icon-button" type="button" data-action="edit" aria-label="Edit ${escapeHtml(rule.name)}" title="${locked ? "Unlock this rule to edit" : "Edit rule"}" ${disabled ? "disabled" : ""}>${icon("edit")}</button><button class="lock-button" type="button" data-action="lock" aria-label="${locked ? "Unlock" : "Lock"} ${escapeHtml(rule.name)}" aria-pressed="${locked}" title="${locked ? "Unlock editing" : "Lock editing"}" ${blocked ? "disabled" : ""}>${icon(locked ? "lock" : "unlock")}${kind === "default" ? `<span>${locked ? "Locked" : "Unlocked"}</span>` : ""}</button>${kind === "custom" ? `<button class="icon-button" type="button" data-action="delete" aria-label="Remove ${escapeHtml(rule.name)}" title="Remove rule" ${disabled ? "disabled" : ""}>${icon("delete")}</button>` : ""}</div>
  </article>`;
}

function matchesFilters(rule) {
  const query = els.ruleSearch.value.trim().toLowerCase();
  const state = els.stateFilter.value;
  if (query && ![rule.name, rule.description, rule.type, rule.match, rule.action, rule.scope, rule.indexer, indexerName(rule.indexer), rule.value].filter(Boolean).join(" ").toLowerCase().includes(query)) return false;
  if (state === "enabled" && !rule.enabled) return false;
  if (state === "disabled" && rule.enabled) return false;
  if (state === "locked" && !rule.locked) return false;
  if (state === "unlocked" && rule.locked) return false;
  return true;
}

function render() {
  syncSiteSelects();
  const defaults = ruleCatalog.map((rule, index) => ({ ...rule, ...config.defaults[rule.id], number: String(index + 1).padStart(2, "0") }));
  const visibleDefaults = currentView === "custom" ? [] : defaults.filter(matchesFilters);
  const visibleCustom = currentView === "default" ? [] : config.customRules.filter(matchesFilters);
  const emptyCustom = currentView !== "default" && config.customRules.length === 0 && !els.ruleSearch.value.trim() && els.stateFilter.value === "all";
  const visibleCount = visibleDefaults.length + visibleCustom.length;
  const totalCount = (currentView === "custom" ? 0 : defaults.length) + (currentView === "default" ? 0 : config.customRules.length);
  const allRules = [...defaults, ...config.customRules];
  els.defaultRules.innerHTML = visibleDefaults.map(rule => ruleRow(rule, "default", rule.number, rule.type)).join("");
  els.customRules.innerHTML = visibleCustom.map((rule, index) => ruleRow(rule, "custom", `C${String(index + 1).padStart(2, "0")}`, actionLabel(rule.action))).join("");
  els.defaultSection.hidden = visibleDefaults.length === 0;
  els.customSection.hidden = visibleCustom.length === 0 && !emptyCustom;
  els.emptyState.hidden = !emptyCustom;
  els.noResults.hidden = visibleCount > 0 || emptyCustom;
  byId("defaultCount").textContent = visibleDefaults.length;
  byId("customGroupCount").textContent = visibleCustom.length;
  byId("navAllCount").textContent = allRules.length;
  byId("navDefaultCount").textContent = defaults.length;
  byId("navCustomCount").textContent = config.customRules.length;
  byId("customCount").textContent = config.customRules.length;
  byId("activeCount").textContent = allRules.filter(rule => rule.enabled).length;
  byId("lockedCount").textContent = allRules.filter(rule => rule.locked).length;
  byId("resultCount").textContent = `${visibleCount} of ${totalCount} ${totalCount === 1 ? "rule" : "rules"}`;
  byId("pageTitle").textContent = ({ all: "Rule library", default: "Built-in rules", custom: "Custom rules" })[currentView];
  document.querySelectorAll("[data-view]").forEach(button => {
    const selected = currentPage === "rules" && button.dataset.view === currentView;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  for (const id of ["openRuleForm", "emptyAddRule", "saveRuleButton"]) byId(id).disabled = !canSave || isSaving;
  for (const id of ["closeRuleForm", "cancelRuleForm"]) byId(id).disabled = isSaving;
  els.ruleName.disabled = isSaving;
  els.ruleDescription.disabled = isSaving || editingRule?.kind !== "default";
  els.customFields.disabled = isSaving || editingRule?.kind === "default";
  updateValueRequirement();
  byId("saveRuleButton").textContent = isSaving ? "Saving..." : "Save rule";
  byId("ruleProfile").disabled = isSaving || !canSave;
  syncSiteSelect(byId("ruleProfile").closest(".site-select"));
}

function setTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = currentTheme;
  document.querySelector('meta[name="theme-color"]').content = currentTheme === "dark" ? "#171818" : "#f5f3ef";
  els.themeLabel.textContent = currentTheme === "dark" ? "Light" : "Dark";
  els.themeIcon.style.setProperty("--icon-url", `url('/manager/assets/icons/${currentTheme === "dark" ? "sun.png" : "050-dark.png"}')`);
  els.themeToggle.setAttribute("aria-label", `Switch to ${currentTheme === "dark" ? "light" : "dark"} mode`);
  writeStorage(THEME_KEY, currentTheme);
}

function updateValueRequirement() {
  const needsValue = ["rewrite", "annotate"].includes(els.ruleAction.value) && editingRule?.kind !== "default";
  els.ruleValue.required = needsValue;
  els.ruleValue.disabled = !needsValue || isSaving;
  els.valueField.hidden = !needsValue;
  els.valueLabel.textContent = els.ruleAction.value === "annotate" ? "Title label" : "Replacement text";
}

function openEditor(kind = "custom", id = null) {
  if (!canSave || isSaving) return;
  const rule = id ? findRule(kind, id) : null;
  if (id && (!rule || rule.locked)) return;
  editingRule = { kind, id };
  const builtin = kind === "default";
  els.ruleForm.reset();
  els.editorError.hidden = true;
  byId("editorTitle").textContent = id ? "Edit rule" : "Add a rule";
  byId("editorKind").textContent = builtin ? "Built-in rule" : "Custom rule";
  byId("editorIntro").textContent = builtin ? "Update this rule's name and description. Its behavior is controlled by the enabled switch in the library." : "Choose a title match and how the proxy should handle it.";
  els.descriptionField.hidden = !builtin;
  els.ruleDescription.disabled = !builtin;
  els.customFields.hidden = builtin;
  els.customFields.disabled = builtin;
  els.ruleName.value = rule?.name || "";
  els.ruleDescription.value = rule?.description || "";
  els.ruleMatch.value = rule?.match || "";
  els.ruleScope.value = rule?.scope || "all";
  setIndexerOptions(rule?.indexer || "all");
  els.ruleAction.value = rule?.action || "prefer";
  els.ruleValue.value = rule?.value || "";
  syncSiteSelects();
  updateValueRequirement();
  els.ruleDialog.showModal();
  els.ruleName.focus();
}

function closeEditor() { if (!isSaving) els.ruleDialog.close(); }
function focusRule(kind, id, action) { document.querySelector(`article[data-kind="${kind}"][data-id="${CSS.escape(id)}"] [data-action="${action}"]`)?.focus({ preventScroll: true }); }

async function handleRuleClick(event) {
  const button = event.target.closest("button[data-action]");
  const article = button?.closest("article[data-kind][data-id]");
  if (!article || !canSave || isSaving || button.disabled) return;
  const { kind, id } = article.dataset;
  const rule = findRule(kind, id);
  if (!rule) return;
  if (button.dataset.action === "edit") { openEditor(kind, id); return; }
  if (button.dataset.action === "lock") {
    await saveChanges(candidate => { findRule(kind, id, candidate).locked = !rule.locked; });
    focusRule(kind, id, "lock");
  } else if (button.dataset.action === "delete" && kind === "custom" && !rule.locked) {
    await saveChanges(candidate => { candidate.customRules = candidate.customRules.filter(item => item.id !== id); });
    byId("openRuleForm").focus({ preventScroll: true });
  }
}

async function handleRuleChange(event) {
  const input = event.target.closest('input[data-action="enabled"]');
  const article = input?.closest("article[data-kind][data-id]");
  if (!article || !canSave || isSaving || input.disabled) return;
  const { kind, id } = article.dataset;
  const rule = findRule(kind, id);
  if (!rule || rule.locked) return;
  const enabled = input.checked;
  await saveChanges(candidate => { findRule(kind, id, candidate).enabled = enabled; });
  focusRule(kind, id, "enabled");
}

for (const container of [els.defaultRules, els.customRules]) {
  container.addEventListener("click", handleRuleClick);
  container.addEventListener("change", handleRuleChange);
}
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => { currentView = button.dataset.view; showPage("rules"); render(); }));
els.ruleSearch.addEventListener("input", render);
els.stateFilter.addEventListener("change", render);
byId("clearFilters").addEventListener("click", () => { els.ruleSearch.value = ""; els.stateFilter.value = "all"; render(); els.ruleSearch.focus(); });
for (const id of ["openRuleForm", "emptyAddRule"]) byId(id).addEventListener("click", () => openEditor());
for (const id of ["closeRuleForm", "cancelRuleForm"]) byId(id).addEventListener("click", closeEditor);
els.ruleAction.addEventListener("change", updateValueRequirement);
els.ruleDialog.addEventListener("cancel", event => { if (isSaving) event.preventDefault(); });
els.ruleDialog.addEventListener("click", event => {
  const bounds = els.ruleDialog.getBoundingClientRect();
  if (event.target === els.ruleDialog && (event.clientX < bounds.left || event.clientX > bounds.right)) closeEditor();
});
els.ruleForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!editingRule || isSaving || !canSave || !els.ruleForm.reportValidity()) return;
  const { kind, id } = editingRule;
  const name = els.ruleName.value.trim();
  const match = els.ruleMatch.value.trim();
  const value = els.ruleValue.disabled ? "" : els.ruleValue.value.trim();
  if (!name || (kind === "custom" && (!match || (els.ruleValue.required && !value)))) {
    els.editorError.textContent = "Enter a name and all required matching fields.";
    els.editorError.hidden = false;
    return;
  }
  const updates = kind === "default" ? { name, description: els.ruleDescription.value.trim() } : { name, match, scope: els.ruleScope.value, indexer: els.ruleIndexer.value, action: els.ruleAction.value, value };
  const savedId = id || crypto.randomUUID();
  const saved = await saveChanges(candidate => {
    if (id) Object.assign(findRule(kind, id, candidate), updates);
    else candidate.customRules.unshift({ id: savedId, ...updates, enabled: true, locked: false });
  });
  if (saved) {
    if (!id) { currentView = "custom"; els.ruleSearch.value = ""; els.stateFilter.value = "all"; render(); }
    els.ruleDialog.close();
    focusRule(kind, savedId, "edit");
  }
});
els.themeToggle.addEventListener("click", () => setTheme(currentTheme === "dark" ? "light" : "dark"));
byId("logoutButton").addEventListener("click", async () => {
  try { await fetch("/manager/api/logout", { method: "POST" }); } catch { /* Return to sign-in even when the network is unavailable. */ }
  window.location.assign("/manager/login");
});
byId("exportRules").addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify({ ...config, exportedAt: new Date().toISOString() }, null, 2)], { type: "application/json" }));
  link.download = "sonarr-proxy-manager-rules.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
});

try {
  const cached = readStorage(STORAGE_KEY) || readStorage("sonarr-proxy-manager.rules.v2");
  if (cached) config = normalizeConfig(JSON.parse(cached));
} catch { /* Fetch authoritative settings when a browser cache is invalid. */ }
setTheme(currentTheme);
enhanceSiteSelects();
render();
hydrateRules();
hydrateIntegrations();

async function managerRequest(path, method = "GET", payload) {
  const response = await fetch(`/manager/api/${path}`, {
    method, headers: { "Content-Type": "application/json" },
    ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
  });
  if (response.status === 401 || response.status === 503) {
    window.location.assign("/manager/login");
    throw new Error("Sign in to continue.");
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "The operation could not be completed.");
  return result;
}

function integrationMessage(message, error = false) {
  const feedback = byId("integrationFeedback");
  feedback.textContent = message;
  feedback.hidden = !message;
  feedback.classList.toggle("is-error", error);
}

function showPage(page) {
  currentPage = page;
  byId("ruleWorkspace").hidden = page !== "rules";
  byId("feedsWorkspace").hidden = page !== "feeds";
  byId("settingsWorkspace").hidden = page !== "settings";
  document.querySelectorAll("[data-page]").forEach(button => {
    button.classList.toggle("is-selected", button.dataset.page === page);
    button.setAttribute("aria-pressed", String(button.dataset.page === page));
  });
  render();
}

function renderIntegrations() {
  if (settings) {
    for (const service of ["prowlarr", "sonarr", "proxy"]) {
      const connection = settings.connections[service];
      byId(`${service}Url`).value = connection.url;
      byId(`${service}Url`).disabled = connection.managed.url;
      byId(`${service}Key`).value = "";
      byId(`${service}Key`).disabled = connection.managed.apiKey;
      byId(`${service}Key`).placeholder = connection.hasApiKey ? "Saved key (leave blank to keep)" : "Enter API key";
      byId(`${service}Origin`).textContent = Object.values(connection.managed).some(Boolean) ? "Environment" : "Local settings";
    }
  }
  const profile = byId("ruleProfile");
  const selected = profile.value;
  profile.replaceChildren(new Option("Legacy combined feed (/api)", ""), ...feeds.map(feed => new Option(feed.name, feed.id)));
  profile.value = feeds.some(feed => feed.id === selected) ? selected : "";
  refreshSiteSelect(profile.closest(".site-select"));
  byId("navFeedCount").textContent = feeds.length;
  byId("feedEmpty").hidden = feeds.length > 0;
  byId("feedList").innerHTML = feeds.map(feed => `<article class="feed-card" data-feed-id="${escapeHtml(feed.id)}">
    <div class="feed-card-heading"><h2>${escapeHtml(feed.name)}</h2><span class="behavior-tag">${({ anime: "Anime only", tv: "TV only", both: "Anime + TV" })[feed.mode]}</span></div>
    <p>${feed.sourceIds.map(id => escapeHtml(indexerName(id))).join(" / ")}</p>
    <p>${feed.enabled ? "Interactive and automatic searches enabled" : "Disabled; sync to disable in Sonarr"}</p>
    <code>${escapeHtml(feed.url || "Set proxy base URL in Settings")}${escapeHtml(feed.apiPath)}</code>
    ${feed.unavailableSources?.length ? `<p class="source-warning">Unavailable sources: ${feed.unavailableSources.map(escapeHtml).join(", ")}. Rediscover Prowlarr.</p>` : ""}
    <div class="panel-actions"><button class="button button-secondary" type="button" data-feed-action="rules">Edit rules</button><button class="button button-secondary" type="button" data-feed-action="edit" ${settings?.feedsManaged ? "disabled" : ""}>Edit feed</button></div>
  </article>`).join("");
  byId("addFeed").disabled = settings?.feedsManaged || integrationBusy;
  byId("syncSonarr").disabled = !feeds.length || integrationBusy;
}

async function hydrateIntegrations() {
  try {
    settings = await managerRequest("settings");
    sources = await managerRequest("sources");
    feeds = await managerRequest("feeds");
    indexerCatalog = sources;
    setIndexerOptions(els.ruleIndexer.value);
    renderIntegrations();
  } catch (error) { integrationMessage(error.message, true); }
}

async function runIntegration(button, operation) {
  if (integrationBusy) return;
  integrationBusy = true;
  button.disabled = true;
  integrationMessage("Working...");
  try { await operation(); }
  catch (error) {
    integrationMessage(error.message, true);
    if (byId("feedDialog").open) { byId("feedError").textContent = error.message; byId("feedError").hidden = false; }
  } finally {
    integrationBusy = false;
    button.disabled = false;
    byId("addFeed").disabled = settings?.feedsManaged;
    byId("syncSonarr").disabled = !feeds.length;
  }
}

document.querySelectorAll("[data-page]").forEach(button => button.addEventListener("click", () => showPage(button.dataset.page)));
byId("ruleProfile").addEventListener("change", () => { if (!isSaving) hydrateRules(); });
byId("settingsForm").addEventListener("submit", event => {
  event.preventDefault();
  if (!settings || !event.currentTarget.reportValidity()) return;
  runIntegration(byId("saveSettings"), async () => {
    const connections = {};
    for (const service of ["prowlarr", "sonarr", "proxy"]) {
      connections[service] = {};
      if (!settings.connections[service].managed.url) connections[service].url = byId(`${service}Url`).value.trim();
      if (!settings.connections[service].managed.apiKey && byId(`${service}Key`).value) connections[service].apiKey = byId(`${service}Key`).value;
    }
    settings = await managerRequest("settings", "PUT", { connections });
    sources = await managerRequest("sources");
    indexerCatalog = sources;
    setIndexerOptions();
    renderIntegrations();
    integrationMessage("Connections saved. Saved API keys remain hidden.");
  });
});
document.querySelectorAll("[data-test-service]").forEach(button => button.addEventListener("click", () => runIntegration(button, async () => {
  const result = await managerRequest("test-connection", "POST", { service: button.dataset.testService });
  integrationMessage(`${button.dataset.testService === "prowlarr" ? "Prowlarr" : "Sonarr"} connected (version ${result.version}).`);
})));
byId("discoverIndexers").addEventListener("click", event => runIntegration(event.currentTarget, async () => {
  sources = await managerRequest("discover", "POST", {});
  indexerCatalog = sources;
  setIndexerOptions();
  feeds = await managerRequest("feeds");
  renderIntegrations();
  integrationMessage(`Discovered ${sources.filter(source => source.origin === "Prowlarr").length} upstream torrent indexers. Proxy feeds were excluded.`);
}));
byId("syncSonarr").addEventListener("click", event => runIntegration(event.currentTarget, async () => {
  const result = await managerRequest("sync-sonarr", "POST", {});
  integrationMessage(`${result.entries.length} feeds synchronized. ${result.message}`);
}));

function openFeedEditor(id = null) {
  if (integrationBusy || settings?.feedsManaged) return;
  const feed = feeds.find(value => value.id === id);
  editingFeedId = feed?.id || null;
  byId("feedForm").reset();
  byId("feedEditorTitle").textContent = feed ? "Edit feed" : "Add feed";
  byId("feedId").value = feed?.id || "";
  byId("feedId").readOnly = Boolean(feed);
  byId("feedName").value = feed?.name || "";
  byId("feedMode").value = feed?.mode || "anime";
  byId("feedEnabled").checked = feed?.enabled !== false;
  const options = [...sources];
  for (const missing of feed?.unavailableSources || []) options.push({ id: missing, name: `Unavailable (${missing})`, origin: "Rediscover Prowlarr" });
  byId("feedSources").innerHTML = options.map(source => `<label><input type="checkbox" name="source" value="${escapeHtml(source.id)}" ${feed?.sourceIds.includes(source.id) ? "checked" : ""} /><span>${escapeHtml(source.name)}<small>${escapeHtml(source.origin)}</small></span></label>`).join("");
  byId("feedError").hidden = true;
  syncSiteSelects();
  byId("feedDialog").showModal();
  byId("feedName").focus();
}
byId("addFeed").addEventListener("click", () => openFeedEditor());
byId("feedList").addEventListener("click", event => {
  const button = event.target.closest("[data-feed-action]");
  const id = button?.closest("[data-feed-id]")?.dataset.feedId;
  if (!id || button.disabled) return;
  if (button.dataset.feedAction === "edit") openFeedEditor(id);
  else if (!isSaving) {
    byId("ruleProfile").value = id;
    currentView = "all";
    els.ruleSearch.value = "";
    els.stateFilter.value = "all";
    showPage("rules");
    hydrateRules();
  }
});
for (const id of ["closeFeed", "cancelFeed"]) byId(id).addEventListener("click", () => { if (!integrationBusy) byId("feedDialog").close(); });
byId("feedDialog").addEventListener("cancel", event => { if (integrationBusy) event.preventDefault(); });
byId("feedForm").addEventListener("submit", event => {
  event.preventDefault();
  if (!event.currentTarget.reportValidity()) return;
  runIntegration(byId("saveFeed"), async () => {
    const sourceIds = [...byId("feedSources").querySelectorAll("input:checked")].map(input => input.value);
    if (!sourceIds.length) throw new Error("Select at least one upstream indexer.");
    const previous = feeds.find(feed => feed.id === editingFeedId);
    const feed = { ...previous, id: byId("feedId").value, name: byId("feedName").value.trim(), mode: byId("feedMode").value, enabled: byId("feedEnabled").checked, sourceIds };
    if (!editingFeedId && feeds.some(value => value.id === feed.id)) throw new Error("Choose a unique feed ID.");
    const candidate = editingFeedId ? feeds.map(value => value.id === editingFeedId ? feed : value) : [...feeds, feed];
    feeds = await managerRequest("feeds", "PUT", candidate);
    renderIntegrations();
    byId("feedDialog").close();
    integrationMessage("Feed saved with its own rule profile. Sync feeds to Sonarr when ready.");
  });
});
