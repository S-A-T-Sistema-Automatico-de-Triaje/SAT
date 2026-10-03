/* TriageAI — utilidades compartidas. Cargar ANTES del script de cada página. */
const BACKEND_URL = "http://localhost:8000";
const ESI_LABELS = {
  1: "Resucitación inmediata", 2: "Emergente — atención < 15 min",
  3: "Urgente — atención < 30 min", 4: "Semi-urgente — atención < 60 min", 5: "No urgente",
};

// ── Sesión ───────────────────────────────────────────────
const getToken = () => localStorage.getItem("triage_token");
function getUser() { try { return JSON.parse(localStorage.getItem("triage_user") || "null"); } catch { return null; } }
const homeFor = role => role === "medico_guardia" ? "medico.html" : "triage.html";

/** Llamar al inicio de cada página. El backend igual valida el rol; esto solo evita ver la pantalla equivocada. */
function requireRole(...roles) {
  const u = getUser();
  if (!getToken() || !u || (roles.length && !roles.includes(u.role) && u.role !== "administrador")) {
    location.href = "index.html"; return null;
  }
  const n = document.getElementById("user-name"), a = document.getElementById("user-avatar");
  if (n) n.textContent = u.username;
  if (a) a.textContent = u.username.slice(0, 2).toUpperCase();
  return u;
}

function doLogout() {
  localStorage.removeItem("triage_token"); localStorage.removeItem("triage_user");
  location.href = "index.html";
}

async function doLogin(username, password) {
  const d = await api("/api/auth/login", { method: "POST", form: new URLSearchParams({ username, password }) });
  localStorage.setItem("triage_token", d.access_token);
  localStorage.setItem("triage_user", JSON.stringify({ username: d.username, role: d.role }));
  location.href = homeFor(d.role);
}

/** fetch con token, manejo de 401 y mensajes de error legibles. */
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {}, t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const r = await fetch(BACKEND_URL + path, { method, headers, body: payload });
  if (r.status === 401 && path !== "/api/auth/login") { doLogout(); throw new Error("La sesión expiró"); }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    const msg = Array.isArray(d.detail) ? d.detail.map(x => x.msg).join("; ") : d.detail;
    throw new Error(msg || `Error ${r.status}`);
  }
  return r.json();
}

// ── UI ───────────────────────────────────────────────────
function esc(s) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

function setStatus(type, msg) {
  const d = document.getElementById("sdot"), t = document.getElementById("stext");
  if (d) d.className = `sdot sdot-${type === "warn" ? "wait" : type}`;
  if (t) t.textContent = msg;
}

function applyTheme(light) {
  document.documentElement.classList.toggle("theme-light", light);
  const i = document.getElementById("theme-icon"); if (i) i.textContent = light ? "☀️" : "🌙";
  localStorage.setItem("triage_theme", light ? "light" : "dark");
}
function toggleTheme() { applyTheme(!document.documentElement.classList.contains("theme-light")); }
document.addEventListener("DOMContentLoaded", () => applyTheme(localStorage.getItem("triage_theme") === "light"));

/** El backend guarda UTC sin sufijo "Z"; sin esto el navegador lo toma como hora local. */
function parseUTC(iso) { return new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z"); }
function timeAgo(iso) {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - parseUTC(iso)) / 60000));
  return m < 1 ? "recién" : m < 60 ? `hace ${m} min` : `hace ${Math.floor(m / 60)} h ${m % 60} min`;
}

// ── Bloques de render compartidos ────────────────────────
const esiBadge = (n, cls = "") => n ? `<span class="badge e-${n} ${cls}">${n}</span>` : `<span class="badge badge-na ${cls}">–</span>`;

function vitalClass(val, type) {
  const n = +val; if (!val) return "";
  const r = {
    fc:   n > 150 || n < 40 ? 2 : n > 100 || n < 50 ? 1 : 0,
    pa_s: n < 90 ? 2 : n < 100 ? 1 : 0,
    spo2: n < 90 ? 2 : n < 94 ? 1 : 0,
    temp: n > 39 ? 2 : n > 37.5 ? 1 : 0,
  }[type] || 0;
  return ["", "ps-vital-warn", "ps-vital-crit"][r];
}

function renderPatientSummary(pd, anonCode) {
  pd = pd || {};
  const name = [pd.nombre, pd.apellido].filter(Boolean).join(" ") || (anonCode ? "Paciente anónimo" : "Paciente sin nombre");
  const avatar = pd.sexo === "Femenino" ? "👩" : pd.sexo === "Masculino" ? "👨" : "🧑";
  const v = (val, lbl, type, shown) => val ? `<div class="ps-vital ${vitalClass(val, type)}"><div class="ps-vital-val">${esc(shown ?? val)}</div><div class="ps-vital-lbl">${lbl}</div></div>` : "";
  const hasVitals = pd.fc || pd.pa_s || pd.spo2 || pd.fr || pd.temp;
  const sec = (lbl, val) => val ? `<div class="ps-section"><div class="ps-sec-label">${lbl}</div><div class="ps-sec-val">${esc(val)}</div></div>` : "";
  const como = (pd.comorbidities || []).map(k => `<span class="chip-pill">${esc(k.replace(/^hx_/, "").replace(/_/g, " "))}</span>`).join("");
  return `<div class="patient-summary">
    <div class="ps-header"><div class="ps-avatar">${avatar}</div><div>
      <div class="ps-name">${esc(name)}${anonCode ? `<span class="tag-anon">${esc(anonCode)}</span>` : ""}</div>
      <div class="ps-age">${[pd.edad && pd.edad + " años", pd.sexo].filter(Boolean).join(", ") || "Sin datos demográficos"}</div></div></div>
    ${hasVitals ? `<div class="ps-grid">
      ${v(pd.fc, "FC (bpm)", "fc")}${v(pd.pa_s, "PA (mmHg)", "pa_s", pd.pa_d ? `${pd.pa_s}/${pd.pa_d}` : pd.pa_s)}
      ${v(pd.spo2, "SpO₂ (%)", "spo2")}${v(pd.fr, "FR (rpm)", "fr")}${v(pd.temp, "Temp (°C)", "temp")}</div>` : ""}
    ${sec("Motivo", pd.motivo)}${sec("Síntomas", pd.sintomas)}${sec("Antecedentes", pd.antecedentes)}
    ${sec("Medicación", pd.medicacion)}${sec("Alergias", pd.alergias)}
    ${como ? `<div class="ps-section"><div class="ps-sec-label">Comorbilidades</div><div class="pill-row">${como}</div></div>` : ""}
  </div>`;
}

function renderESICard(esi, rule = "") {
  return `<div class="esi-card e-${esi}"><div class="esi-header"><div class="esi-num">${esi}</div>
    <div><div class="esi-level-title">ESI ${esi} — ${ESI_LABELS[esi] || ""}</div><div class="esi-rule">${esc(rule)}</div></div></div></div>`;
}

/** Preocupación principal, razonamiento y señales de alarma a partir de result_json. */
function renderSections(r) {
  r = r || {};
  const flags = r.red_flags || [];
  return `<div class="sections">
    ${r.primary_concern ? `<div class="rs"><div class="rs-title">Preocupación principal</div><p>${esc(r.primary_concern)}</p></div>` : ""}
    ${r.clinical_reasoning ? `<div class="rs"><div class="rs-title">Razonamiento</div><p>${esc(r.clinical_reasoning)}</p></div>` : ""}
    ${flags.length ? `<div class="rs"><div class="rs-title">Señales de alarma</div><div class="pill-row">${flags.map(f => `<span class="flag-pill">⚠ ${esc(f)}</span>`).join("")}</div></div>` : ""}
  </div>`;
}
