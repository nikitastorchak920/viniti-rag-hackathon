"use strict";

const domains = {
  solar: {
    title: "Тонкоплёночные солнечные элементы",
    tables: {devices: "Приборы", materials: "Материалы", layers: "Слои", measurements: "Условия измерений"},
    ids: {devices: "device_id", materials: "material_id", layers: "layer_id", measurements: "measurement_id"},
    controls: "Физический контроль",
  },
  rag: {
    title: "RAG и поиск по документам",
    tables: {configurations: "Конфигурации", datasets: "Датасеты", tasks: "Задачи", experiments: "Эксперименты"},
    ids: {configurations: "config_id", datasets: "dataset_id", tasks: "task_id", experiments: "experiment_id"},
    controls: "Контроль шкалы и @k",
  },
};
const solarRules = new Set(["jv_consistency", "voc_limit", "eqe_consistency", "champion_vs_mean",
  "range", "hysteresis_index", "missing_conditions", "comparability", "unit_inconsistency"]);
const pageSize = 25;
const fmt = new Intl.NumberFormat("ru");
const percent = new Intl.NumberFormat("ru", {style: "percent", maximumFractionDigits: 1});
const $ = id => document.getElementById(id);
const grid = $("grid"), dialog = $("detail");
const bundles = new Map(), pending = new Map();
const key = (paper, id) => JSON.stringify([paper, id]);
const normalize = value => String(value ?? "").normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[c]);
const quote = row => row.source_fragment || row.source_quote || "";
const extracted = row => row.extraction_status === "extracted" && !!(row.normalized_value || row.metric_value);
const scope = row => row.exclusion_reason === "Unprocessed: no scope decision" ? "Не обработана"
  : row.in_scope === "true" ? "В области" : row.in_scope === "false" ? "Вне области" : "Не обработана";
const raw = row => row.raw_value ? [row.raw_value, row.raw_unit && !row.raw_value.endsWith(row.raw_unit) ? row.raw_unit : ""]
  .filter(Boolean).join(" ") : "";
const normalized = row => row.normalized_value ? [row.normalized_value, row.normalized_unit].filter(Boolean).join(" ") : "";
const metric = row => row.metric_k && !/@\s*\d/.test(row.metric_name || "")
  ? (row.metric_name || "") + " · k=" + row.metric_k : row.metric_name;
const origin = row => ({primary: "Первичный", cited: "Цитируемый"})[row.result_origin] || "";
const locator = row => [row.source_page && "стр. " + row.source_page, row.source_table,
  row.source_figure, row.source_section && "раздел " + row.source_section].filter(Boolean).join(" · ");
const tableNames = domain => ["publications", ...Object.keys(domains[domain].tables), "results", "issues"];
const ruleCode = (domain, name) => /^RULE_/.test(name || "") ? name
  : domain === "solar" && solarRules.has(name) ? "RULE_" + name.toUpperCase() : "";

let domain = "rag", view = "results", entityTable = "", filter = "all", page = 0, comparing = false;
let manifest = {}, bundle = null, pageRows = [], selected = null;

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  text = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"' && !field) quoted = true;
    else if (char === ",") { row.push(field); field = ""; }
    else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      if (row.length > 1 || field) rows.push(row);
      row = []; field = "";
    } else field += char;
  }
  if (quoted) throw new Error("Незакрытое поле CSV");
  if (row.length || field) { row.push(field); rows.push(row); }
  const columns = rows.shift();
  if (!columns?.includes("publication_id")) throw new Error("Отсутствует заголовок CSV");
  const records = rows.map(cells => Object.fromEntries(columns.map((column, i) => [column, cells[i] ?? ""])));
  records.columns = columns;
  return records;
}

function comparisonKey(item) {
  const row = item.row, protocol = item.related.experiments?.evaluation_protocol;
  if (!extracted(row) || row.duplicate_of || !item.related.datasets || !item.related.tasks || !row.metric_name || !protocol || !row.metric_unit) return "";
  if (row.result_origin === "cited" && (!row.cited_publication_id || row.cited_publication_id === "unspecified")) return "";
  return JSON.stringify([row.publication_id, row.dataset_id, row.task_id, row.metric_name, row.metric_k,
    row.metric_variant, protocol, row.metric_unit, row.aggregation, row.metric_direction, row.result_origin, row.cited_publication_id]);
}

function baselineDelta(row) {
  if (!row.baseline_value?.trim() || !row.metric_value?.trim()) return null;
  if (!["higher_is_better", "lower_is_better"].includes(row.metric_direction)) return null;
  const value = Number(row.metric_value), baseline = Number(row.baseline_value);
  return Number.isFinite(value) && Number.isFinite(baseline)
    ? (row.metric_direction === "lower_is_better" ? baseline - value : value - baseline) : null;
}

function addTo(index, id, row) {
  const group = index.get(id);
  if (group) group.push(row);
  else index.set(id, [row]);
}

function evidenceIndex(report, table) {
  const checks = report?.quote_checks?.[table];
  return new Map((Array.isArray(checks) ? checks : []).filter(check => Array.isArray(check) && check.length === 5)
    .map(([paper,id,sourcePage,fragment,matched]) => [key(paper,id), {sourcePage, fragment, matched}]));
}

function verifiedState(row, checks, id) {
  const fragment = quote(row).trim();
  if (!fragment) return null;
  const check = checks.get(key(row.publication_id, id));
  if (check && String(check.sourcePage ?? "") === (row.source_page || "").trim() && check.fragment === fragment
      && typeof check.matched === "boolean") return check.matched;
  if (row.quote_verified === "true") return true;
  if (row.quote_verified === "false") return false;
  return null;
}

function quoteSummary(report, data, id) {
  if (report?.domain && report.domain !== id) return null;
  if (!Object.entries(data).every(([table, rows]) => report?.rows?.[table] === rows.length)) return null;
  const {requested, matched} = report?.quotes || {};
  if (!Number.isSafeInteger(requested) || !Number.isSafeInteger(matched)
      || requested <= 0 || matched < 0 || matched > requested) return null;
  return {requested, matched};
}

function deltaDisplay(delta) {
  if (delta === null) return "—";
  const formatted = new Intl.NumberFormat("ru", {maximumSignificantDigits: 7, signDisplay: "exceptZero"});
  return formatted.format(delta);
}

function comparisonRows(rows) {
  const selector = $("compare-group"), previous = selector.value;
  const groups = new Map();
  for (const item of rows) if (item.comparison) addTo(groups, item.comparison, item);
  for (const [id, items] of groups) {
    if (items.length === 1 && baselineDelta(items[0].row) === null) groups.delete(id);
  }
  selector.replaceChildren(...[...groups].map(([id, items]) => {
    const {row, related} = items[0];
    const label = [row.publication_id, related.datasets.dataset_name, related.tasks.task_type || row.task_id,
      row.metric_name, row.metric_variant, row.metric_k && `k=${row.metric_k}`, row.metric_unit,
      related.experiments.evaluation_protocol].filter(Boolean).join(" · ");
    return new Option(`${label} (${items.length})`, id);
  }));
  if (groups.has(previous)) selector.value = previous;
  if (!groups.size) selector.add(new Option("Нет сопоставимых результатов", ""));
  return groups.get(selector.value) || [];
}

function prepare(data, report, id, label) {
  const schema = domains[id], publications = new Map(data.publications.map(row => [row.publication_id, row]));
  const indices = Object.fromEntries(Object.entries(schema.ids).map(([table, field]) => [
    table, new Map(data[table].filter(row => row[field]).map(row => [key(row.publication_id, row[field]), row])),
  ]));
  const resolve = (table, paper, ref) => indices[table]?.get(key(paper, ref));
  const resultsById = new Map(), resultsByPaper = new Map(), resultsByEntity = new Map();
  const issuesByPaper = new Map(), issuesByResult = new Map();
  const issueChecks = evidenceIndex(report, "issues"), resultChecks = evidenceIndex(report, "results");
  const issues = data.issues.map(row => {
    const ids = [...new Set((row.record_ids || "").split(/[;,]/).map(id => id.trim()).filter(Boolean))];
    const item = {row, ids, paper: publications.get(row.publication_id),
      rule: ruleCode(id, row.check_name), verified: verifiedState(row, issueChecks, row.issue_id)};
    addTo(issuesByPaper, row.publication_id, item);
    for (const ref of ids) addTo(issuesByResult, key(row.publication_id, ref), item);
    return item;
  });
  const results = data.results.map(row => {
    const paper = publications.get(row.publication_id);
    const related = Object.fromEntries(Object.entries(schema.ids).map(([table, field]) => [
      table, resolve(table, row.publication_id, row[field]),
    ]));
    if (id === "solar" && !row.material_id) {
      related.materials = resolve("materials", row.publication_id, related.devices?.absorber_material_id);
    }
    const item = {row, paper, related, links: issuesByResult.get(key(row.publication_id, row.result_id)) || [],
      verified: verifiedState(row, resultChecks, row.result_id),
      search: normalize([paper?.title, paper?.authors, origin(row), locator(row), metric(row), ...Object.values(row),
        ...Object.values(related).flatMap(entity => Object.values(entity || {}))].join(" "))};
    if (id === "rag") item.comparison = comparisonKey(item);
    resultsById.set(key(row.publication_id, row.result_id), item);
    addTo(resultsByPaper, row.publication_id, item);
    for (const [table, entity] of Object.entries(related)) {
      if (entity) addTo(resultsByEntity, key(table, key(row.publication_id, entity[schema.ids[table]])), item);
    }
    return item;
  });
  for (const item of issues) {
    item.results = item.ids.map(ref => resultsById.get(key(item.row.publication_id, ref))).filter(Boolean);
    item.search = normalize([item.paper?.title, item.rule, ...Object.values(item.row), ...item.results.map(r => r.search)].join(" "));
  }
  function summary(row, relatedResults, links) {
    return {row, paper: publications.get(row.publication_id), results: relatedResults, links,
      verified: relatedResults.some(item => item.verified === true) ? true : null,
      search: normalize([publications.get(row.publication_id)?.title, ...Object.values(row),
        ...relatedResults.map(item => item.search)].join(" "))};
  }
  const items = {results, issues, publications: data.publications.map(row => summary(row,
    resultsByPaper.get(row.publication_id) || [], issuesByPaper.get(row.publication_id) || []))};
  items.provenance = results.filter(({row}) => quote(row) || locator(row) || row.result_origin);
  for (const [table, field] of Object.entries(schema.ids)) {
    items[table] = data[table].map(row => {
      const direct = resultsByEntity.get(key(table, key(row.publication_id, row[field]))) || [];
      const throughDevice = table === "layers"
        ? resultsByEntity.get(key("devices", key(row.publication_id, row.device_id))) || [] : [];
      const relatedResults = direct.length ? direct : throughDevice;
      const item = summary(row, relatedResults, [...new Set(relatedResults.flatMap(result => result.links))]);
      if (table === "layers") item.related = {devices: resolve("devices", row.publication_id, row.device_id)};
      return item;
    });
  }
  const evidence = [...results, ...issues].filter(item => quote(item.row).trim());
  return {id, label, items, evidence: evidence.length, checked: evidence.filter(item => item.verified !== null).length,
    verified: evidence.filter(item => item.verified === true).length, rules: issues.filter(item => item.rule).length,
    quoteSummary: quoteSummary(report, data, id), published: data.publications.filter(row => scope(row) !== "Не обработана").length,
    extracted: data.results.filter(extracted).length, resultsById};
}

async function readBundle(id, read, label, hasValidation) {
  const tables = tableNames(id);
  const entries = await Promise.all(tables.map(async table => [table, parseCsv(await read(table + ".csv"))]));
  const data = Object.fromEntries(entries);
  for (const [table, idField] of Object.entries({...domains[id].ids, results: "result_id", issues: "issue_id"})) {
    if (!data[table].columns.includes(idField)) throw new Error(table + ".csv: отсутствует поле " + idField);
  }
  let report = null, notice = "";
  if (hasValidation) {
    try { report = JSON.parse(await read("validation.json")); }
    catch { notice = "Не удалось прочитать validation.json. Цитаты доступны без отметок отчёта."; }
  }
  return {...prepare(data, report, id, label), notice};
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("HTTP " + response.status + " · " + path);
  return response.text();
}

function loadDomain(id) {
  if (!pending.has(id)) {
    const load = readBundle(id, name => fetchText("data/" + id + "/" + name), manifest[id].label || "Пакет CSV", manifest[id].validation)
      .then(result => {
        if (!bundles.has(id)) bundles.set(id, result);
        return bundles.get(id);
      }).finally(() => pending.delete(id));
    pending.set(id, load);
  }
  return pending.get(id);
}

function showNotice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

function pressed(selector, attribute, value) {
  for (const button of document.querySelectorAll(selector)) button.setAttribute("aria-pressed", String(button.dataset[attribute] === value));
}

function showBundle(next, message) {
  bundle = next;
  if (next) showNotice(next.notice);
  $("bundle").textContent = next?.label || message;
  const number = value => next ? fmt.format(value) : "—";
  $("paper-count").textContent = number(next?.published);
  $("paper-note").textContent = next ? "из " + number(next.items.publications.length) + " в пакете" : "";
  $("result-count").textContent = number(next?.extracted);
  $("result-note").textContent = next ? "из " + number(next.items.results.length) + " строк в пакете" : "";
  const summary = next?.quoteSummary;
  const total = next?.checked ? next.evidence : summary?.requested;
  const matched = next?.checked ? next.verified : summary?.matched;
  $("quote-count").textContent = total ? percent.format(matched / total) : "—";
  $("quote-note").textContent = total ? number(matched) + " из " + number(total) + " подтверждены"
    + (!next.checked ? " · сводный отчёт" : "")
    : next?.evidence ? "Нет отчёта по этим цитатам" : next ? "В пакете нет цитат для проверки" : "";
  $("issue-count").textContent = number(next?.rules);
  $("issue-note").textContent = next ? "всего замечаний: " + number(next.items.issues.length) : "";
  $("paper").replaceChildren(new Option("Все статьи", ""), ...(next?.items.publications || [])
    .map(({row}) => new Option(row.publication_id, row.publication_id)));
  $("rule").replaceChildren(new Option("Все правила", ""), ...[...new Set((next?.items.issues || [])
    .map(item => item.rule || item.row.check_name).filter(Boolean))].sort().map(name => new Option(name, name)));
  render();
}

async function switchDomain(id, {reset = true} = {}) {
  domain = id;
  if (reset) {
    if (dialog.open) dialog.close();
    view = "results"; entityTable = ""; filter = "all"; page = 0; comparing = false; selected = null;
    $("q").value = "";
    pressed("[data-filter]", "filter", filter);
  }
  pressed("[data-domain]", "domain", id);
  $("domain-title").textContent = domains[id].title;
  showNotice();
  if (bundles.has(id)) return showBundle(bundles.get(id));
  if (!manifest[id]?.available) return showBundle(null, "Выберите папку с семью CSV этой области");
  showBundle(null, "Загрузка пакета…");
  try {
    const next = await loadDomain(id);
    if (domain === id) showBundle(next);
  } catch (error) {
    if (domain === id && !bundles.has(id)) {
      showBundle(null, "Пакет не загрузился");
      showNotice(error.message);
    }
  }
}

function tabs() {
  const [systems, catalog, parts, conditions] = Object.keys(domains[domain].tables);
  const names = domains[domain].tables;
  return [
    ["publications", "Публикации", ["publications"]],
    ["systems", names[systems], [systems, catalog]],
    ["parts", names[parts], [parts]],
    ["conditions", names[conditions], [conditions]],
    ["results", "Результаты метрик", ["results"]],
    ["provenance", "Происхождение и цитаты", ["provenance"]],
    ["issues", "Замечания RULE_*", ["issues"]],
  ];
}

function countedButton(attribute, id, label, count, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute(attribute, id);
  button.setAttribute("aria-pressed", String(active));
  button.append(document.createTextNode(label));
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = bundle ? fmt.format(count) : "—";
  button.append(badge);
  return button;
}

const field = name => ({row}) => row[name];
const joined = (entity, name) => ({related}) => related?.[entity]?.[name];
const displayName = row => [row?.device_label || row?.device_id, row?.device_role].filter(Boolean).join(" · ");
function materialLabel(row) {
  const gap = row?.bandgap_value && "Eg " + [row.bandgap_value, row.bandgap_unit].filter(Boolean).join(" ");
  return [row?.formula_normalized || row?.material_name_raw, gap].filter(Boolean).join(" · ");
}

const entityColumns = {
  configurations: [["ID", field("config_id")], ["Вариант метода", field("rag_variant")],
    ["Генератор", field("generator_model")], ["Поиск", field("retrieval_method")], ["top_k", field("top_k")]],
  datasets: [["ID", field("dataset_id")], ["Датасет", field("dataset_name")],
    ["Версия", field("dataset_version")], ["Язык", field("language")], ["Подвыборка", field("data_split")]],
  tasks: [["ID", field("task_id")], ["Задача", field("task_type")], ["Примечание", field("note")]],
  experiments: [["ID", field("experiment_id")], ["Протокол оценки", field("evaluation_protocol")],
    ["Baseline", field("baseline_name")], ["Оборудование", field("hardware")], ["Задержка, мс", field("latency_ms")]],
  devices: [["ID", field("device_id")], ["Прибор / роль", ({row}) => displayName(row)],
    ["Архитектура", field("architecture")], ["Подложка", field("substrate_type")], ["Тип", field("device_type")]],
  materials: [["ID", field("material_id")], ["Материал / Eg", ({row}) => materialLabel(row)],
    ["Класс", field("material_class")], ["Размерность", field("dimensionality")], ["Метод Eg", field("bandgap_method")]],
  layers: [["ID", field("layer_id")], ["Прибор", item => displayName(item.related?.devices) || item.row.device_id],
    ["Порядок", field("layer_order")], ["Функция", field("layer_function")], ["Материал", field("layer_material")],
    ["Толщина", ({row}) => [row.layer_thickness, row.thickness_unit].filter(Boolean).join(" ")]],
  measurements: [["ID", field("measurement_id")], ["Тип измерения", field("measurement_type")],
    ["Развёртка", field("scan_direction")], ["Спектр", field("spectrum")], ["Интенсивность", field("light_intensity")],
    ["Условия стресса", field("stress_conditions")]],
};

function columns(table) {
  const citation = ["Статус", item => statusBadge(item), "badge-cell"];
  if (table === "results") {
    const context = domain === "solar" ? [
      ["Прибор / роль", item => displayName(item.related?.devices) || item.row.device_id],
      ["Архитектура", joined("devices", "architecture")],
      ["Материал / Eg", item => materialLabel(item.related?.materials)],
      ["Развёртка", joined("measurements", "scan_direction")],
    ] : [
      ["Датасет", joined("datasets", "dataset_name")], ["Вариант метода", joined("configurations", "rag_variant")],
      ["Генератор", joined("configurations", "generator_model")],
    ];
    return [["Статья", field("publication_id")], ...context, ["Метрика", ({row}) => metric(row)],
      ["Raw", ({row}) => raw(row)], ["Normalized", ({row}) => normalized(row)],
      comparing ? ["Δ к baseline", ({row}) => deltaDisplay(baselineDelta(row))] : citation];
  }
  if (table === "provenance") return [
    ["Статья", field("publication_id")], ["Метрика", ({row}) => metric(row)], ["Происхождение", ({row}) => origin(row)],
    ["Источник", ({row}) => locator(row)], ["Дословная цитата", ({row}) => quote(row)], citation,
  ];
  if (table === "issues") return [
    ["Статья", field("publication_id")], ["Код правила", item => item.rule || item.row.check_name],
    ["Замечание", field("description")], ["Связанные записи", field("record_ids")], ["Источник", ({row}) => locator(row)],
  ];
  if (table === "publications") return [
    ["ID", field("publication_id")], ["Публикация", field("title")],
    ["Год", field("year")], ["Статус", ({row}) => scope(row)], ["Результаты", item => fmt.format(item.results.length)],
  ];
  return [["Статья", field("publication_id")], ...entityColumns[table], citation];
}

function statusBadge(item, quoteOnly = false) {
  if (!quoteOnly && (item.rule || item.links?.some(issue => issue.rule))) return '<span class="state issue">Есть замечания</span>';
  if (item.verified === true) return '<span class="state verified">Подтверждено</span>';
  if (item.verified === false) return '<span class="state issue">Цитата на проверке</span>';
  return '<span class="state">Нет подтверждения</span>';
}

function render() {
  const layout = tabs();
  const current = layout.find(tab => tab[0] === view);
  const available = current[2], table = available.includes(entityTable) ? entityTable : available[0];
  const items = name => bundle?.items[name] || [];
  $("tabs").replaceChildren(...layout.map(([id, label, tables]) =>
    countedButton("data-tab", id, label, tables.reduce((n, name) => n + items(name).length, 0), id === view)));
  $("subnav").hidden = available.length === 1;
  $("subnav").replaceChildren(...(available.length > 1 ? available : []).map(name =>
    countedButton("data-entity", name, domains[domain].tables[name], items(name).length, name === table)));
  $("rule").hidden = view !== "issues";
  $("comparison").hidden = domain !== "rag" || view !== "results";
  $("compare").setAttribute("aria-pressed", String(comparing));
  $("compare-group").hidden = $("compare-note").hidden = !comparing;

  const search = normalize($("q").value).split(" ").filter(Boolean);
  const paper = $("paper").value, rule = $("rule").value;
  let rows = items(table).filter(item => (!paper || item.row.publication_id === paper)
    && (view !== "issues" || !rule || (item.rule || item.row.check_name) === rule)
    && (filter !== "verified" || item.verified === true)
    && (filter !== "issues" || item.rule || item.links?.some(issue => issue.rule))
    && search.every(term => item.search.includes(term)));
  if (comparing) rows = comparisonRows(rows);
  page = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
  const start = page * pageSize;
  pageRows = rows.slice(start, start + pageSize);
  const cols = columns(table);
  grid.classList.toggle("wide", table === "results");
  grid.tHead.innerHTML = "<tr>" + cols.map(([label]) => '<th scope="col">' + escapeHtml(label) + "</th>").join("") + "</tr>";
  grid.tBodies[0].innerHTML = pageRows.map((item, i) => '<tr data-row="' + i
    + '" data-selected="' + (item === selected) + '">' + cols.map(([, value, type], j) => {
      const result = value(item);
      if (type === "badge-cell") return "<td>" + result + "</td>";
      const text = escapeHtml(result || "—");
      return j === 0 ? '<td><button class="row-button" type="button">' + text + "</button></td>"
        : '<td><span class="cell-label">' + text + "</span></td>";
    }).join("") + "</tr>").join("");
  $("empty").hidden = rows.length > 0;
  $("empty").textContent = bundle ? "По текущим условиям записей нет." : "Подключите пакет CSV для этой области.";
  $("range").textContent = rows.length ? fmt.format(start + 1) + "–" + fmt.format(start + pageRows.length) + " из " + fmt.format(rows.length) : "0 записей";
  $("prev").disabled = page === 0;
  $("next").disabled = start + pageRows.length >= rows.length;
}

function facts(title, entries) {
  const rows = entries.filter(([, value]) => value !== "" && value != null);
  return rows.length ? '<section class="drawer-section"><h3>' + escapeHtml(title) + "</h3><dl>"
    + rows.map(([name, value]) => "<dt>" + escapeHtml(name) + "</dt><dd>" + escapeHtml(value) + "</dd>").join("")
    + "</dl></section>" : "";
}

function highlighted(fragment, value) {
  if (!value) return escapeHtml(fragment);
  const escaped = value.replace(/[.*+?^{}$()|[\]\\]/g, "\\$&");
  const match = new RegExp("(?<![\\w.,+−-])" + escaped + "(?![\\w.,])", "u").exec(fragment);
  if (!match) return escapeHtml(fragment);
  return escapeHtml(fragment.slice(0, match.index)) + "<mark>" + escapeHtml(match[0]) + "</mark>"
    + escapeHtml(fragment.slice(match.index + match[0].length));
}

function sourceSection(item) {
  const row = item.row, fragment = quote(row);
  return '<section class="drawer-section"><h3>Источник в PDF</h3><p class="muted">'
    + escapeHtml(locator(row) || "Локатор не указан") + "</p>" + statusBadge(item, true)
    + (fragment ? "<blockquote>" + highlighted(fragment, row.raw_value) + "</blockquote>" : '<p class="muted">Цитата не указана</p>')
    + "</section>";
}

function checksSection(item, resultView) {
  const findings = resultView ? item.links || [] : [item];
  const rows = findings.map(issue => "<li><strong>" + escapeHtml(issue.rule || issue.row.check_name || issue.row.issue_id)
    + "</strong>" + (issue.rule && issue.row.check_name !== issue.rule ? " · " + escapeHtml(issue.row.check_name) : "")
    + "<br>" + escapeHtml(issue.row.description) + "</li>");
  return '<section class="drawer-section"><h3>' + domains[domain].controls + "</h3>"
    + (rows.length ? '<ul class="issue-list">' + rows.join("") + "</ul>" : '<p class="muted">Связанных замечаний нет.</p>')
    + "</section>";
}

function openDetail(item, resultView = view === "results" || view === "provenance") {
  const row = item.row, paper = item.paper;
  if (!dialog.open) {
    selected = item;
    const opening = grid.tBodies[0].querySelector('tr[data-row="' + pageRows.indexOf(item) + '"]');
    grid.tBodies[0].querySelector("[data-selected=true]")?.setAttribute("data-selected", "false");
    opening?.setAttribute("data-selected", "true");
  }
  $("detail-title").textContent = resultView ? "Путь одного числа" : view === "issues" ? "Замечание" : "Карточка записи";
  $("detail-kicker").textContent = [row.publication_id, row.result_id || row.issue_id, resultView && metric(row)].filter(Boolean).join(" · ");
  const names = domains[domain].tables;
  const metadata = resultView ? facts("Значение метрики", [
    ["Метрика", metric(row)], ["Raw · исходное", raw(row) || "—"], ["Normalized · нормализованное", normalized(row) || "—"],
    ["Происхождение", origin(row)], ["Цитируемая работа", row.cited_publication_id],
    ["Статус извлечения", row.extraction_status], ["Baseline", row.baseline_value],
  ]) : "";
  const related = Object.entries(item.related || {}).map(([table, entity]) => facts(names[table], Object.entries(entity || {}))).join("");
  const linked = (item.results || []).slice(0, 12);
  const navigation = linked.length && !resultView ? '<section><h3>Связанные результаты</h3><div class="subnav">'
    + linked.map(({row}) => '<button type="button" class="pill" data-jump="' + escapeHtml(row.result_id) + '">'
      + escapeHtml([row.result_id, metric(row), raw(row)].filter(Boolean).join(" · ")) + "</button>").join("")
    + "</div></section>" : "";
  $("detail-body").innerHTML = facts("Статья", [["ID", row.publication_id], ["Название", paper?.title],
    ["Год", paper?.year], ["DOI", paper?.DOI || paper?.doi]]) + related + metadata
    + (resultView || view === "issues" ? sourceSection(item) + checksSection(item, resultView) : "")
    + facts("Поля записи", Object.entries(row)) + navigation;
  if (!dialog.open) dialog.showModal();
}

$("detail-body").addEventListener("click", event => {
  const ref = event.target.closest("[data-jump]")?.dataset.jump;
  if (!ref) return;
  const paper = selected?.row.publication_id;
  const result = bundle?.resultsById.get(key(paper, ref));
  if (result) openDetail(result, true);
});
grid.tBodies[0].addEventListener("click", event => {
  const row = event.target.closest("[data-row]");
  if (row) openDetail(pageRows[Number(row.dataset.row)]);
});
dialog.addEventListener("click", event => {
  if (event.target === dialog && event.clientX < dialog.getBoundingClientRect().left) dialog.close();
});
for (const button of document.querySelectorAll("[data-domain]")) {
  button.addEventListener("click", () => switchDomain(button.dataset.domain));
}
$("tabs").addEventListener("click", event => {
  const button = event.target.closest("[data-tab]");
  if (!button) return;
  view = button.dataset.tab; entityTable = ""; page = 0; comparing = false; selected = null;
  render();
  $("tabs").querySelector('[data-tab="' + view + '"]')?.focus();
});
$("subnav").addEventListener("click", event => {
  const button = event.target.closest("[data-entity]");
  if (!button) return;
  entityTable = button.dataset.entity; page = 0; selected = null;
  render();
  $("subnav").querySelector('[data-entity="' + entityTable + '"]')?.focus();
});
for (const button of document.querySelectorAll("[data-filter]")) {
  button.addEventListener("click", () => {
    filter = button.dataset.filter; page = 0;
    pressed("[data-filter]", "filter", filter);
    render();
  });
}
for (const id of ["q", "paper", "rule", "compare-group"]) {
  $(id).addEventListener("input", () => { page = 0; render(); });
}
$("compare").addEventListener("click", () => { comparing = !comparing; page = 0; render(); });
$("prev").addEventListener("click", () => { page--; render(); });
$("next").addEventListener("click", () => { page++; render(); });
$("folder").addEventListener("click", () => $("files").click());
$("files").addEventListener("change", async () => {
  const files = new Map([...$("files").files].filter(file => file.webkitRelativePath.split("/").length <= 2)
    .map(file => [file.name, file]));
  $("files").value = "";
  if (!files.size) return;
  const id = [domain, ...Object.keys(domains).filter(other => other !== domain)]
    .find(candidate => tableNames(candidate).every(table => files.has(table + ".csv")));
  if (!id) return showNotice("В папке должны быть семь CSV одной предметной области.");
  const label = files.values().next().value.webkitRelativePath.split("/")[0];
  try {
    bundles.set(id, await readBundle(id, name => files.get(name).text(), label, files.has("validation.json")));
    await switchDomain(id);
  } catch (error) {
    showNotice(error.message);
  }
});

async function start() {
  if (location.protocol !== "file:") {
    try {
      manifest = JSON.parse(await fetchText("api/domains.json"));
    } catch (error) {
      await switchDomain(domain);
      showNotice("Сервер пакетов недоступен. " + error.message);
      return;
    }
  }
  await switchDomain(manifest.rag?.available ? "rag" : manifest.solar?.available ? "solar" : domain);
  // Prepare the second domain in the background so later switches use indexed data.
  for (const other of Object.keys(domains)) {
    if (other !== domain && manifest[other]?.available && !bundles.has(other)) loadDomain(other).catch(() => {});
  }
}

render();
start();
