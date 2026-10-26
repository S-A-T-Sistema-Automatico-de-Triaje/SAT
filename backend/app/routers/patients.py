"""
app/routers/patients.py

Pacientes reincidentes, vinculados por DNI.

Triagista:
- GET   /api/patients/lookup?dni=...                      autocompletado al escribir el DNI
- PATCH /api/patients/by-case/{classification_id}/dni     cargar el DNI a un caso ya existente

Triagista y médico:
- GET   /api/patients/search?q=...                        buscador por DNI (o por nombre, entre pacientes con DNI)
- GET   /api/patients/list                                listado de todos los pacientes con DNI
- GET   /api/patients/record/{dni}                        ficha completa + informe de todas las visitas

Médico:
- GET   /api/patients/reviewed                            pacientes con al menos un caso revisado (+ casos revisados sin DNI)
- GET   /api/patients/by-case/{classification_id}/history historial del paciente del caso que está revisando

Solo se vincula por DNI exacto (normalizado a dígitos). La búsqueda por nombre solo ayuda a
encontrar el DNI: nunca fusiona historias, porque los homónimos son frecuentes y mezclar
historias clínicas es un riesgo clínico real. Los casos anónimos nunca tienen DNI guardado.
"""
import datetime as dt
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.security import require_roles
from app.database import get_db
from app.models import Case, Classification, ClassificationStatus, RoleEnum, User
from app.routers.meta import _humanize

router = APIRouter(prefix="/api/patients", tags=["patients"])
audit = logging.getLogger("triageai.audit")  # accesos a datos de pacientes (quién, qué)

DOCTORS = (RoleEnum.medico_guardia, RoleEnum.administrador)
TRIAGE_AND_DOCTORS = (RoleEnum.triagista, *DOCTORS)  # el triagista también consulta pacientes (ficha, buscador, listado)


# ──────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────
def normalize_dni(raw: str | None) -> str | None:
    """'12.345.678' -> '12345678'. Devuelve None si no quedan dígitos."""
    digits = re.sub(r"\D", "", raw or "")
    return digits or None


def _valid_dni(dni: str | None) -> bool:
    return bool(dni) and 6 <= len(dni) <= 10


def _mask(dni: str) -> str:
    return f"***{dni[-3:]}"  # el DNI nunca va completo a los logs


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _latest(cases: list[Case], key: str):
    """Valor no vacío más reciente de patient_data[key] (cases viene ordenado desc)."""
    for c in cases:
        v = (c.patient_data or {}).get(key)
        if v not in (None, ""):
            return v
    return None


def _effective_esi(c: Classification) -> int:
    """Nivel que vale: el del médico; si no revisó, el del triagista; si no, el del modelo."""
    return c.doctor_esi or c.triagist_esi or c.esi_level


def _adjusted_age(cases: list[Case]) -> int | None:
    """La edad se guardó en la fecha de la visita: se ajusta por los años transcurridos."""
    edad = _int(_latest(cases, "edad"))
    if edad is None:
        return None
    return edad + int((dt.datetime.utcnow() - cases[0].created_at).days / 365.25)


def _patient_header(dni: str, cases: list[Case]) -> dict:
    return {
        "dni": dni,
        "nombre": _latest(cases, "nombre"),
        "apellido": _latest(cases, "apellido"),
        "edad": _adjusted_age(cases),
        "sexo": _latest(cases, "sexo"),
        "weight_kg": _latest(cases, "weight_kg"),
        "height_cm": _latest(cases, "height_cm"),
    }


# ──────────────────────────────────────────────────────────
# Autocompletado (triagista)
# ──────────────────────────────────────────────────────────
@router.get("/lookup")
def lookup_by_dni(
    dni: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.triagista, RoleEnum.medico_guardia, RoleEnum.administrador)),
):
    n = normalize_dni(dni)
    if not _valid_dni(n):
        raise HTTPException(400, "DNI inválido")
    audit.info("lookup dni=%s user=%s", _mask(n), user.username)

    cases = (
        db.query(Case)
        .filter(Case.dni == n, Case.is_anonymous == False)  # noqa: E712
        .order_by(Case.created_at.desc())
        .all()
    )
    if not cases:
        return {"found": False}

    h = _patient_header(n, cases)
    return {
        "found": True,
        "visits": len(cases),
        "last_visit": cases[0].created_at,
        "patient": {k: h[k] for k in ("nombre", "apellido", "edad", "sexo", "weight_kg", "height_cm")},
    }


# ──────────────────────────────────────────────────────────
# Ficha e informe (médico)
# ──────────────────────────────────────────────────────────
def _rows_for_dni(db: Session, dni: str) -> list[Classification]:
    return (
        db.query(Classification)
        .join(Case, Classification.case_id == Case.id)
        .options(joinedload(Classification.case), joinedload(Classification.doctor_user), joinedload(Classification.created_by_user))
        .filter(Case.dni == dni)
        .order_by(Classification.created_at.desc())
        .all()
    )


def build_record(rows: list[Classification], dni: str, exclude_classification_id: int | None = None) -> dict:
    """Ficha del paciente: cabecera, resumen clínico acumulado, estadísticas e informe de visitas.
    `rows` viene ordenado de más reciente a más antiguo."""
    cases = [c.case for c in rows]

    comorb: dict[str, dt.datetime] = {}
    alergias: list[str] = []
    antecedentes: list[str] = []
    medicacion = None
    seen_a, seen_t = set(), set()
    for c in rows:  # más reciente primero
        p = c.case.patient_data or {}
        for k in p.get("comorbidities") or []:
            comorb.setdefault(k, c.created_at)
        al = (p.get("alergias") or "").strip()
        if al and al.lower() not in seen_a:
            seen_a.add(al.lower()); alergias.append(al)
        an = (p.get("antecedentes") or "").strip()
        if an and an.lower() not in seen_t:
            seen_t.add(an.lower()); antecedentes.append(an)
        if medicacion is None and (p.get("medicacion") or "").strip():
            medicacion = p["medicacion"].strip()

    visits = []
    for c in rows:
        if c.id == exclude_classification_id:
            continue
        p = c.case.patient_data or {}
        res = c.result_json or {}
        visits.append({
            "classification_id": c.id,
            "date": c.created_at,
            "status": c.status.value,
            "motivo": p.get("motivo") or "",
            "sintomas": p.get("sintomas") or "",
            "vitals": {k: p.get(k) or "" for k in ("fc", "pa_s", "pa_d", "spo2", "fr", "temp")},
            "primary_concern": res.get("primary_concern") or "",
            "red_flags": res.get("red_flags") or [],
            "esi_model": c.esi_level,
            "esi_triagist": c.triagist_esi,
            "esi_final": c.doctor_esi,
            "esi_effective": _effective_esi(c),
            "triagist": c.created_by_user.username if c.created_by_user else None,
            "triagist_note": c.triagist_note or "",
            "doctor_agrees": c.doctor_agrees,
            "doctor_comment": c.doctor_comment or "",
            "doctor": c.doctor_user.username if c.doctor_user else None,
        })

    return {
        "patient": _patient_header(dni, cases),
        "stats": {
            "total_visits": len(rows),
            "first_visit": rows[-1].created_at,
            "last_visit": rows[0].created_at,
            "urgent_visits": sum(1 for c in rows if _effective_esi(c) <= 2),
        },
        "total_visits": len(rows),
        "summary": {
            "comorbidities": [{"key": k, "label": _humanize(k)} for k in comorb],
            "allergies": alergias,
            "medication": medicacion,
            "antecedentes": antecedentes,
        },
        "visits": visits,
    }


@router.get("/record/{dni}")
def patient_record(
    dni: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*TRIAGE_AND_DOCTORS)),
):
    n = normalize_dni(dni)
    if not _valid_dni(n):
        raise HTTPException(400, "DNI inválido")
    rows = _rows_for_dni(db, n)
    if not rows:
        raise HTTPException(404, "No hay visitas registradas con ese DNI")
    audit.info("record dni=%s user=%s", _mask(n), user.username)
    return build_record(rows, n)


@router.get("/by-case/{classification_id}/history")
def history_by_case(
    classification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*DOCTORS)),
):
    c = db.get(Classification, classification_id)
    if not c:
        raise HTTPException(404, "Clasificación no encontrada")
    dni = c.case.dni
    if not dni:
        return {"has_dni": False, "dni": None, "total_visits": 0, "summary": None, "visits": []}
    audit.info("history case=%s dni=%s user=%s", classification_id, _mask(dni), user.username)
    # Sin la visita actual en la lista; las estadísticas sí la cuentan
    return {"has_dni": True, "dni": dni, **build_record(_rows_for_dni(db, dni), dni, exclude_classification_id=c.id)}


# ──────────────────────────────────────────────────────────
# Buscador y listado de pacientes
# ──────────────────────────────────────────────────────────
def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _summaries(db: Session, dnis: list[str]) -> list[dict]:
    """Una fila por paciente (DNI), en el mismo orden que `dnis`: datos básicos, visitas y última visita."""
    if not dnis:
        return []
    # Todas las visitas de esos DNI (no solo las que coincidieron con la búsqueda)
    rows = (
        db.query(Classification)
        .join(Case, Classification.case_id == Case.id)
        .options(joinedload(Classification.case))
        .filter(Case.dni.in_(dnis))
        .order_by(Classification.created_at.desc())
        .all()
    )
    by_dni: dict[str, list[Classification]] = {d: [] for d in dnis}
    for c in rows:
        by_dni[c.case.dni].append(c)

    results = []
    for d in dnis:
        rs = by_dni[d]
        if not rs:
            continue
        h = _patient_header(d, [c.case for c in rs])
        results.append({
            "dni": d,
            "nombre": h["nombre"], "apellido": h["apellido"], "edad": h["edad"], "sexo": h["sexo"],
            "visits": len(rs),
            "last_visit": rs[0].created_at,
            "last_esi": _effective_esi(rs[0]),
            "last_motivo": (rs[0].case.patient_data or {}).get("motivo") or "",
        })
    return results


def _identified_cases(db: Session):
    """Casos con DNI y no anónimos, agrupados por DNI con la fecha de la última visita."""
    return db.query(Case.dni, func.max(Case.created_at).label("last_seen")).filter(
        Case.dni.isnot(None), Case.is_anonymous == False  # noqa: E712
    )


@router.get("/search")
def search_patients(
    q: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*TRIAGE_AND_DOCTORS)),
):
    """Busca por DNI (completo o parcial, desde 3 dígitos) o por nombre/apellido (desde 3 letras).
    Solo devuelve pacientes con DNI registrado, porque el DNI es lo que vincula las visitas."""
    q = (q or "").strip()
    limit = max(1, min(limit, 50))
    q_cases = _identified_cases(db)

    if re.fullmatch(r"[\d.\s]+", q):
        mode, digits = "dni", normalize_dni(q) or ""
        if len(digits) < 3:
            raise HTTPException(400, "Escribí al menos 3 dígitos del DNI")
        q_cases = q_cases.filter(Case.dni.like(f"%{digits}%"))
    else:
        mode = "nombre"
        if len(q) < 3:
            raise HTTPException(400, "Escribí al menos 3 letras del nombre")
        q_cases = q_cases.filter(Case.label.ilike(f"%{_like_escape(q)}%", escape="\\"))

    dnis = [r.dni for r in q_cases.group_by(Case.dni).order_by(desc("last_seen")).limit(limit).all()]
    audit.info("search mode=%s results=%d user=%s", mode, len(dnis), user.username)
    return {"results": _summaries(db, dnis), "truncated": len(dnis) >= limit}


@router.get("/list")
def list_patients(
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*TRIAGE_AND_DOCTORS)),
):
    """Listado de todos los pacientes con DNI registrado, del que vino más recientemente al más antiguo."""
    limit = max(1, min(limit, 500))
    base = _identified_cases(db).group_by(Case.dni)
    total = base.count()
    dnis = [r.dni for r in base.order_by(desc("last_seen")).limit(limit).all()]
    audit.info("list results=%d total=%d user=%s", len(dnis), total, user.username)
    return {"results": _summaries(db, dnis), "total": total, "truncated": total > len(dnis)}


@router.get("/reviewed")
def reviewed_patients(
    limit: int = 500,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*DOCTORS)),
):
    """Pestaña "Revisados" del médico: pacientes (por DNI) con al menos un caso revisado, y aparte los
    casos revisados que no tienen DNI (anónimos o anteriores a esta función), que no se pueden agrupar."""
    limit = max(1, min(limit, 500))
    done = Classification.status == ClassificationStatus.revisado
    dnis = [r.dni for r in (
        db.query(Case.dni).join(Classification, Classification.case_id == Case.id)
        .filter(done, Case.dni.isnot(None), Case.is_anonymous == False)  # noqa: E712
        .group_by(Case.dni).order_by(desc(func.max(Classification.created_at))).limit(limit).all())]
    no_dni = (
        db.query(Classification).join(Case, Classification.case_id == Case.id)
        .options(joinedload(Classification.case))
        .filter(done, Case.dni.is_(None)).order_by(Classification.created_at.desc()).limit(limit).all())
    audit.info("reviewed patients=%d no_dni=%d user=%s", len(dnis), len(no_dni), user.username)
    return {
        "results": _summaries(db, dnis),
        "no_dni": [{
            "classification_id": c.id, "label": c.case.label, "anonymous": bool(c.case.is_anonymous),
            "esi": _effective_esi(c), "date": c.created_at,
        } for c in no_dni],
    }


# ──────────────────────────────────────────────────────────
# Cargar el DNI a un caso que ya existe (pacientes anteriores a esta función)
# ──────────────────────────────────────────────────────────
class DniUpdate(BaseModel):
    dni: str


@router.patch("/by-case/{classification_id}/dni")
def set_case_dni(
    classification_id: int,
    payload: DniUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.triagista, RoleEnum.medico_guardia, RoleEnum.administrador)),
):
    """Agrega el DNI a un caso ya cargado, para vincularlo con el historial del paciente.
    No toca nada más del caso. Si ya tiene un DNI distinto, solo el administrador puede corregirlo."""
    c = db.get(Classification, classification_id)
    if not c:
        raise HTTPException(404, "Clasificación no encontrada")
    if user.role == RoleEnum.triagista and c.created_by_user_id != user.id:
        raise HTTPException(403, "Solo podés editar casos que cargaste vos")
    if c.case.is_anonymous:
        raise HTTPException(409, "Primero identificá al paciente (nombre) y después cargá su DNI")

    n = normalize_dni(payload.dni)
    if not _valid_dni(n):
        raise HTTPException(400, "El DNI debe tener entre 6 y 10 dígitos")
    if c.case.dni and c.case.dni != n and user.role != RoleEnum.administrador:
        raise HTTPException(409, "Este caso ya tiene otro DNI; solo un administrador puede corregirlo")

    # Reasignar el dict completo: SQLAlchemy no detecta mutaciones in-place en JSON
    pdata = dict(c.case.patient_data or {})
    pdata["dni"] = n
    c.case.patient_data = pdata
    c.case.dni = n
    db.commit()
    audit.info("set_dni case=%s dni=%s user=%s", classification_id, _mask(n), user.username)

    other = db.query(Case).filter(Case.dni == n, Case.id != c.case_id).count()
    return {"ok": True, "dni": n, "previous_visits": other}
