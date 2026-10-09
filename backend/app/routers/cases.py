import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Classification, ClassificationStatus, RoleEnum, User
from app.schemas import CaseSummary, DoctorReview, IdentifyRequest, TriagistSubmit
from app.security import  get_current_user, require_roles

router = APIRouter(prefix="/api/cases", tags=["cases"])

# Roles de solo lectura amplia (el médico revisa; estos supervisan)
READ_ALL = (RoleEnum.medico_guardia, RoleEnum.administrador, RoleEnum.auditor_clinico, RoleEnum.jefe_enfermeria)


def _summary(c: Classification) -> CaseSummary:
    final = c.doctor_esi if c.doctor_esi is not None else None
    return CaseSummary(
        classification_id=c.id,
        case_id=c.case_id,
        display_name=c.case.label or c.case.anon_code or f"Caso {c.case_id}",
        is_anonymous=c.case.is_anonymous,
        esi_model=c.esi_level,
        esi_triagist=c.triagist_esi,
        esi_final=final,
        status=c.status.value,
        doctor_comment=c.doctor_comment,
        created_at=c.created_at,
        submitted_at=c.submitted_at,
    )


def _get_or_404(db: Session, classification_id: int) -> Classification:
    c = (
        db.query(Classification)
        .options(joinedload(Classification.case), joinedload(Classification.doctor_user), joinedload(Classification.created_by_user))
        .filter(Classification.id == classification_id)
        .first()
    )
    if not c:
        raise HTTPException(404, "Clasificación no encontrada")
    return c


# ⚠️ /queue y /mine van ANTES de /{classification_id}, si no FastAPI las toma como un id.

@router.get("/queue", response_model=list[CaseSummary])
def doctor_queue(
    include_reviewed: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(RoleEnum.medico_guardia, RoleEnum.administrador)),
):
    """Cola del médico: pendientes primero, más grave arriba y luego más antiguo."""
    statuses = [ClassificationStatus.pendiente_medico]
    if include_reviewed:
        statuses.append(ClassificationStatus.revisado)
    # Nivel de prioridad = el del triagista; si no hay, el del modelo
    prioridad = func.coalesce(Classification.triagist_esi, Classification.esi_level)
    rows = (
        db.query(Classification)
        .options(joinedload(Classification.case))
        .filter(Classification.status.in_(statuses))
        .order_by(
            (Classification.status == ClassificationStatus.revisado),  # pendientes primero
            prioridad.asc(),
            Classification.submitted_at.asc(),
        )
        .limit(limit)
        .all()
    )
    return [_summary(c) for c in rows]


@router.get("/mine", response_model=list[CaseSummary])
def my_cases(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.triagista)),
):
    """Casos cargados por este triagista, con su estado y el veredicto del médico.
    Reemplaza al historial de sesión que se perdía al recargar."""
    rows = (
        db.query(Classification)
        .options(joinedload(Classification.case))
        .filter(Classification.created_by_user_id == user.id)
        .order_by(Classification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_summary(c) for c in rows]


@router.get("", response_model=list[CaseSummary])
def list_all_cases(
    limit: int = 50,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(RoleEnum.administrador, RoleEnum.auditor_clinico, RoleEnum.jefe_enfermeria)),
):
    rows = (
        db.query(Classification)
        .options(joinedload(Classification.case))
        .order_by(Classification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_summary(c) for c in rows]


@router.get("/{classification_id}")
def get_case_detail(
    classification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = _get_or_404(db, classification_id)

    # El triagista solo ve lo que cargó él
    if user.role == RoleEnum.triagista and c.created_by_user_id != user.id:
        raise HTTPException(403, "Este caso lo cargó otro triagista")
    if user.role not in READ_ALL and user.role != RoleEnum.triagista:
        raise HTTPException(403, "No autorizado")

    return {
        "classification_id": c.id,
        "status": c.status.value,
        "case": {
            "id": c.case.id,
            "label": c.case.label,
            "is_anonymous": c.case.is_anonymous,
            "anon_code": c.case.anon_code,
            "patient_data": c.case.patient_data,
        },
        "model": {"name": c.model_used, "esi": c.esi_level, "result": c.result_json},
        "triagist": {
            "username": c.created_by_user.username if c.created_by_user else None,
            "esi": c.triagist_esi,
            "note": c.triagist_note,
            "submitted_at": c.submitted_at,
        },
        "doctor": {
            "username": c.doctor_user.username if c.doctor_user else None,
            "agrees": c.doctor_agrees,
            "esi": c.doctor_esi,
            "comment": c.doctor_comment,
            "reviewed_at": c.reviewed_at,
        },
        "created_at": c.created_at,
    }


@router.post("/{classification_id}/submit")
def submit_to_doctor(
    classification_id: int,
    payload: TriagistSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.triagista)),
):
    """El triagista propone su ESI (con nota opcional) y manda el caso al médico."""
    c = _get_or_404(db, classification_id)
    if c.created_by_user_id != user.id:
        raise HTTPException(403, "Solo podés enviar casos que cargaste vos")
    if c.status == ClassificationStatus.revisado:
        raise HTTPException(409, "Este caso ya fue revisado por un médico")

    c.triagist_esi = payload.esi_propuesto
    c.triagist_note = payload.note or ""
    c.submitted_at = dt.datetime.utcnow()
    c.status = ClassificationStatus.pendiente_medico
    db.commit()
    return {"ok": True, "classification_id": c.id, "status": c.status.value}


@router.post("/{classification_id}/review")
def doctor_review(
    classification_id: int,
    payload: DoctorReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.medico_guardia)),
):
    """El médico confirma o cambia el ESI y deja recomendaciones para el paciente."""
    c = _get_or_404(db, classification_id)
    if c.status == ClassificationStatus.revisado:
        raise HTTPException(409, "Este caso ya fue revisado")
    if c.status != ClassificationStatus.pendiente_medico:
        raise HTTPException(409, "El triagista todavía no envió este caso")

    # Coherencia: si dice que está de acuerdo, el ESI final es el del triagista
    esi_final = c.triagist_esi if payload.agrees and c.triagist_esi else payload.esi_final

    c.doctor_agrees = payload.agrees
    c.doctor_esi = esi_final
    c.doctor_comment = payload.comment
    c.doctor_user_id = user.id
    c.reviewed_at = dt.datetime.utcnow()
    c.status = ClassificationStatus.revisado
    db.commit()
    return {"ok": True, "classification_id": c.id, "esi_final": c.doctor_esi, "status": c.status.value}


@router.patch("/{classification_id}/identify")
def identify_patient(
    classification_id: int,
    payload: IdentifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.triagista, RoleEnum.medico_guardia)),
):
    """Completa nombre/apellido de un caso anónimo cuando el paciente se identifica.
    Se conserva anon_code para poder rastrear el caso original."""
    c = _get_or_404(db, classification_id)
    if user.role == RoleEnum.triagista and c.created_by_user_id != user.id:
        raise HTTPException(403, "Solo podés identificar casos que cargaste vos")
    if not c.case.is_anonymous:
        raise HTTPException(409, "El caso ya está identificado")

    nombre, apellido = payload.nombre.strip(), payload.apellido.strip()
    if not nombre:
        raise HTTPException(400, "Falta el nombre")

    # Reasignar el dict completo: SQLAlchemy no detecta mutaciones in-place en JSON
    pdata = dict(c.case.patient_data or {})
    pdata.update({"nombre": nombre, "apellido": apellido, "anonimo": False})
    c.case.patient_data = pdata
    c.case.label = f"{nombre} {apellido}".strip()
    c.case.is_anonymous = False
    db.commit()
    return {"ok": True, "label": c.case.label, "anon_code": c.case.anon_code}
