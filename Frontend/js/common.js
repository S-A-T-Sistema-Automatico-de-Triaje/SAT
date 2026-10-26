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
/** Para fechas lejanas (visitas previas): "hoy", "hace 3 días", "hace 2 meses", "hace 1 año". */
function timeAgoLong(iso) {
  if (!iso) return "";
  const d = Math.floor((Date.now() - parseUTC(iso)) / 86400000);
  if (d < 1) return "hoy";
  if (d < 31) return `hace ${d} día${d !== 1 ? "s" : ""}`;
  if (d < 365) { const m = Math.floor(d / 30); return `hace ${m} mes${m !== 1 ? "es" : ""}`; }
  const y = Math.floor(d / 365); return `hace ${y} año${y !== 1 ? "s" : ""}`;
}
function fmtDate(iso) { return iso ? parseUTC(iso).toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" }) : ""; }
/** "12345678" -> "12.345.678" */
function formatDni(d) { const s = String(d ?? "").replace(/\D/g, ""); return s.replace(/\B(?=(\d{3})+(?!\d))/g, "."); }

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
  const hasName = !!(pd.nombre || pd.apellido);
  const dniLine = pd.dni ? `<div class="ps-dni">DNI <b>${esc(formatDni(pd.dni))}</b></div>` : hasName ? `<div class="ps-dni none">DNI sin registrar</div>` : "";
  const bodyLine = [pd.edad && esc(pd.edad) + " años", pd.sexo && esc(pd.sexo), pd.weight_kg && `${esc(pd.weight_kg)} kg`, pd.height_cm && `${esc(pd.height_cm)} cm`].filter(Boolean).join(" · ") || "Sin datos demográficos";
  return `<div class="patient-summary">
    <div class="ps-header"><div class="ps-avatar">${avatar}</div><div>
      <div class="ps-name">${esc(name)}${anonCode ? `<span class="tag-anon">${esc(anonCode)}</span>` : ""}</div>
      ${dniLine}
      <div class="ps-age">${bodyLine}</div></div></div>
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

// ══ Ficha de paciente (compartida por la vista del triagista y la del médico) ══
// Cada página define openRecord(dni) y openCase(id); acá solo se arma el HTML.
const RECORD_CSS = `
.mono{font-family:var(--mono)}
.btn-sm{padding:6px 12px;font-size:12px}
/* Lista de pacientes */
.pt-row{display:flex;gap:10px;padding:10px 12px;border-radius:8px;border:1px solid var(--border);margin:0 0 6px;cursor:pointer;background:var(--surface2);align-items:flex-start}
.pt-row:hover,.pt-row.active{border-color:var(--blue)}
.pt-name{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pt-sub{font-size:12px;color:var(--muted);margin-top:2px}.pt-dni{font-family:var(--mono);font-size:14px;font-weight:600;color:var(--text)}
.pt-last{font-size:12px;color:var(--dim);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* Ficha */
.pr-head{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin-bottom:12px}
.pr-id{display:flex;align-items:center;gap:14px}.pr-main{min-width:0;flex:1}
.pr-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.pr-avatar{width:52px;height:52px;border-radius:50%;background:var(--surface3);border:1.5px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0}
.pr-name{font-size:25px;font-weight:700;line-height:1.2}
.pr-dni{font-size:19px;margin-top:3px}.pr-dni b{font-family:var(--mono);font-weight:600;letter-spacing:.3px}
.pr-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.pr-chip{font-size:13px;color:var(--muted);background:var(--surface3);border:1px solid var(--border2);border-radius:6px;padding:2px 9px}
.pr-chip b{color:var(--text);font-weight:600}
.pr-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}
.pr-stat{background:var(--surface3);border:1px solid var(--border);border-radius:8px;padding:9px 10px}
.pr-stat b{display:block;font-size:15px;font-family:var(--mono)}.pr-stat span{font-size:10px;color:var(--dim)}
.pr-stat.warn b{color:var(--amber)}
.pr-allergy{display:flex;gap:8px;align-items:flex-start;background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.4);border-radius:9px;padding:10px 14px;margin-bottom:12px;font-size:13px;color:var(--red)}
.pr-allergy b{font-weight:700}
.pr-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.pr-block{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:11px 14px}
.pr-block.wide{grid-column:1/-1}
.pr-lbl{font-size:11px;font-weight:600;color:var(--dim);margin-bottom:5px}
.pr-val{font-size:12px;color:var(--muted);line-height:1.6}.pr-none{font-size:12px;color:var(--dim)}
.pr-title{font-size:13px;font-weight:600;margin:16px 0 8px;display:flex;align-items:center;gap:8px}
.pr-title small{font-weight:400;color:var(--muted);font-size:11px}
.pr-note{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:12px 16px;margin-bottom:12px;font-size:12px;color:var(--muted)}
.pr-note.hist{border-left:3px solid var(--blue)}
.pr-note .row{display:flex;gap:8px;margin-top:8px}.pr-note .row input{flex:1;background:var(--surface3);border:1px solid var(--border);border-radius:7px;padding:7px 10px;font:12px var(--sans);color:var(--text)}
.pr-note .msg{color:var(--red);margin-top:6px;min-height:14px}
.hx-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.hx-top b{font-size:13px;color:var(--text)}.hx-top .btn{margin-left:auto}
/* Visitas */
.vx{background:var(--surface2);border:1px solid var(--border);border-radius:9px;margin-bottom:8px;overflow:hidden}
.vx[open]{border-color:var(--border2)}
.vx>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:10px 12px}
.vx>summary::-webkit-details-marker{display:none}
.vx>summary::after{content:'▾';margin-left:auto;color:var(--dim);font-size:12px;transition:transform .15s}
.vx[open]>summary::after{transform:rotate(180deg)}
.vx-head{flex:1;min-width:0}.vx-date{font-size:12px;font-weight:600}.vx-date small{font-weight:400;color:var(--dim);margin-left:4px}
.vx-motivo{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vx-tag{font-size:10px;font-weight:600;border-radius:5px;padding:1px 7px;border:1px solid var(--border2);color:var(--muted);white-space:nowrap}
.vx-tag.ok{color:var(--green);border-color:rgba(16,185,129,.4)}.vx-tag.adj{color:var(--amber);border-color:rgba(245,158,11,.4)}
.vx-body{padding:4px 14px 14px;border-top:1px solid var(--border)}
.vx-sec{margin-top:10px}.vx-sec .pr-val{color:var(--text)}
.esi-trio{display:flex;gap:14px;margin-top:10px}
.esi-trio div{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--dim)}
.vx-vit{font:12px var(--mono);color:var(--muted)}
.vx-note{border-left:2px solid var(--border2);padding-left:10px;font-size:12px;color:var(--muted);line-height:1.5}
.vx-note b{color:var(--text);font-weight:600}
.pr-flags{display:flex;flex-wrap:wrap;gap:5px}.pr-flags .flag-pill{font-size:11px;padding:2px 9px}
@media(max-width:720px){.pr-stats{grid-template-columns:1fr 1fr}.pr-grid{grid-template-columns:1fr}}
`;
(function injectRecordCss() {
  if (typeof document === "undefined" || !document.head || document.getElementById("record-css")) return;
  const st = document.createElement("style"); st.id = "record-css"; st.textContent = RECORD_CSS; document.head.appendChild(st);
})();

function patientFullName(p) { return [p.nombre, p.apellido].filter(Boolean).join(" ") || "Sin nombre registrado"; }

/** Filas de un listado de pacientes (resultado de /search o /list). Al tocar una se llama a openRecord(dni). */
function patientRows(list, activeDni) {
  return list.map(r => {
    const sub = [`DNI <span class="pt-dni">${esc(formatDni(r.dni))}</span>`, r.edad != null && `${r.edad} años`, r.sexo && esc(r.sexo)].filter(Boolean).join(" · ");
    return `<div class="pt-row ${r.dni === activeDni ? "active" : ""}" onclick="openRecord('${esc(r.dni)}')">
      ${esiBadge(r.last_esi)}
      <div style="min-width:0;flex:1"><div class="pt-name">${esc(patientFullName(r))}</div><div class="pt-sub">${sub}</div>
      <div class="pt-sub">${r.visits} visita${r.visits !== 1 ? "s" : ""} · última ${esc(timeAgoLong(r.last_visit))}</div>
      ${r.last_motivo ? `<div class="pt-last">${esc(r.last_motivo)}</div>` : ""}</div></div>`;
  }).join("");
}

/** Cabecera de la ficha: nombre y DNI grandes, datos básicos y contadores. `actions` = botones opcionales a la derecha. */
function recordHeader(r, actions = "") {
  const p = r.patient, s = r.stats;
  const avatar = p.sexo === "Femenino" ? "👩" : p.sexo === "Masculino" ? "👨" : "🧑";
  const chip = (lbl, val) => val ? `<span class="pr-chip">${lbl} <b>${val}</b></span>` : "";
  return `<div class="pr-head"><div class="pr-id"><div class="pr-avatar">${avatar}</div><div class="pr-main">
      <div class="pr-name">${esc(patientFullName(p))}</div>
      <div class="pr-dni">DNI <b>${esc(formatDni(p.dni))}</b></div>
      <div class="pr-chips">${chip("", p.edad != null ? `${p.edad} años` : "")}${chip("", esc(p.sexo || ""))}${chip("Peso", p.weight_kg ? esc(p.weight_kg) + " kg" : "")}${chip("Altura", p.height_cm ? esc(p.height_cm) + " cm" : "")}</div></div>
      ${actions ? `<div class="pr-actions">${actions}</div>` : ""}</div>
    <div class="pr-stats">
      <div class="pr-stat"><b>${s.total_visits}</b><span>visitas registradas</span></div>
      <div class="pr-stat"><b>${esc(fmtDate(s.first_visit))}</b><span>primera visita</span></div>
      <div class="pr-stat"><b>${esc(fmtDate(s.last_visit))}</b><span>última · ${esc(timeAgoLong(s.last_visit))}</span></div>
      <div class="pr-stat ${s.urgent_visits ? "warn" : ""}"><b>${s.urgent_visits}</b><span>con ESI 1-2</span></div></div></div>`;
}

function allergyBanner(s) {
  if (!s || !s.allergies.length) return "";
  return `<div class="pr-allergy"><span>⚠</span><div><b>Alergias:</b> ${s.allergies.map(esc).join(" · ")}</div></div>`;
}

function clinicalSummary(s) {
  if (!s) return "";
  const none = '<span class="pr-none">sin datos</span>';
  const como = s.comorbidities.length ? `<div class="pill-row">${s.comorbidities.map(c => `<span class="chip-pill">${esc(c.label)}</span>`).join("")}</div>` : none;
  return `<div class="pr-grid">
    <div class="pr-block"><div class="pr-lbl">Comorbilidades (todas las visitas)</div>${como}</div>
    <div class="pr-block"><div class="pr-lbl">Última medicación informada</div><div class="pr-val">${s.medication ? esc(s.medication) : none}</div></div>
    ${s.antecedentes.length ? `<div class="pr-block wide"><div class="pr-lbl">Antecedentes (texto libre)</div><div class="pr-val">${s.antecedentes.map(esc).join("<br>")}</div></div>` : ""}</div>`;
}

/** Una visita previa como informe desplegable. `canOpen(v)` decide si se muestra "Abrir caso completo" (llama a openCase). */
function visitCard(v, open, canOpen) {
  const vt = v.vitals;
  const vit = [vt.fc && `FC ${esc(vt.fc)}`, vt.pa_s && `PA ${esc(vt.pa_s)}${vt.pa_d ? "/" + esc(vt.pa_d) : ""}`, vt.spo2 && `SpO₂ ${esc(vt.spo2)}%`, vt.fr && `FR ${esc(vt.fr)}`, vt.temp && `T ${esc(vt.temp)}°`].filter(Boolean).join("  ·  ");
  const sec = (lbl, html) => html ? `<div class="vx-sec"><div class="pr-lbl">${lbl}</div>${html}</div>` : "";
  const reviewed = v.status === "revisado";
  const tag = reviewed ? (v.doctor_agrees ? '<span class="vx-tag ok">✓ confirmado</span>' : '<span class="vx-tag adj">✎ nivel cambiado</span>') : '<span class="vx-tag">sin revisión médica</span>';
  const doctor = reviewed ? `${v.doctor_agrees ? "Confirmó el nivel" : "Cambió el nivel"} ESI ${v.esi_final}${v.doctor ? " · " + esc(v.doctor) : ""}` : "";
  const openBtn = !canOpen || canOpen(v) ? `<div style="margin-top:12px"><button class="btn btn-sm" onclick="openCase(${v.classification_id})">Abrir caso completo</button></div>` : "";
  return `<details class="vx" ${open ? "open" : ""}>
    <summary>${esiBadge(v.esi_effective)}<div class="vx-head"><div class="vx-date">${esc(fmtDate(v.date))}<small>${esc(timeAgoLong(v.date))}</small></div>
      <div class="vx-motivo">${esc(v.motivo || "Sin motivo registrado")}</div></div>${tag}</summary>
    <div class="vx-body">
      <div class="esi-trio"><div>Modelo ${esiBadge(v.esi_model)}</div><div>Triagista ${esiBadge(v.esi_triagist)}</div><div>Médico ${esiBadge(v.esi_final)}</div></div>
      ${sec("Motivo de consulta", v.motivo && `<div class="pr-val">${esc(v.motivo)}</div>`)}
      ${sec("Síntomas", v.sintomas && `<div class="pr-val">${esc(v.sintomas)}</div>`)}
      ${sec("Signos vitales", vit && `<div class="vx-vit">${vit}</div>`)}
      ${sec("Preocupación principal (modelo)", v.primary_concern && `<div class="pr-val">${esc(v.primary_concern)}</div>`)}
      ${sec("Señales de alarma", v.red_flags.length && `<div class="pr-flags">${v.red_flags.map(f => `<span class="flag-pill">⚠ ${esc(f)}</span>`).join("")}</div>`)}
      ${sec(`Nota del triagista${v.triagist ? " · " + esc(v.triagist) : ""}`, v.triagist_note && `<div class="vx-note">${esc(v.triagist_note)}</div>`)}
      ${sec("Revisión médica", reviewed && `<div class="vx-note"><b>${doctor}</b>${v.doctor_comment ? `<br>${esc(v.doctor_comment)}` : "<br>Sin recomendaciones."}</div>`)}
      ${openBtn}</div></details>`;
}

/** Ficha completa (vista por DNI). */
function renderPatientRecord(r, { actions = "", canOpen } = {}) {
  return `${recordHeader(r, actions)}${allergyBanner(r.summary)}${clinicalSummary(r.summary)}
    <div class="pr-title">Informe de visitas <small>${r.visits.length} registrada${r.visits.length !== 1 ? "s" : ""} · de la más reciente a la más antigua</small></div>
    ${r.visits.map((v, i) => visitCard(v, i === 0, canOpen)).join("")}`;
}

/** Panel de historial dentro de un caso: las visitas ANTERIORES de este paciente. El botón llama a openRecord(dni). */
function historyPanel(visits, summary, dni, canOpen) {
  if (!visits.length) return `<div class="pr-note hist">Primera visita registrada para el DNI <b class="mono">${esc(formatDni(dni))}</b>.</div>`;
  const n = visits.length, last = visits[0];
  return `<div class="pr-note hist">
    <div class="hx-top"><b>Paciente con ${n} visita${n !== 1 ? "s" : ""} previa${n !== 1 ? "s" : ""}</b><span>última ${esc(timeAgoLong(last.date))} · ESI ${last.esi_effective}</span>
      <button class="btn btn-sm" onclick="openRecord('${esc(dni)}')">Ver ficha completa</button></div>
    ${allergyBanner(summary).replace('class="pr-allergy"', 'class="pr-allergy" style="margin:8px 0"')}
    ${clinicalSummary(summary)}
    <div class="pr-title" style="margin-top:6px">Informe de visitas anteriores</div>
    ${visits.map(v => visitCard(v, false, canOpen)).join("")}</div>`;
}
