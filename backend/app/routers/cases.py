import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Classification, Case, User
from app.schemas import ConfirmRequest
from app.auth import get_current_user

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("")
def list_cases(limit: int = 50, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Historial de sesión, equivalente a sessionData en el HTML pero persistente entre sesiones."""
    classifications = (
        db.query(Classification)
        .options(joinedload(Classification.case))
        .order_by(Classification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "classification_id": c.id,
            "case_id": c.case_id,
            "label": c.case.label,
            "esi_level": c.esi_level,
            "model_used": c.model_used,
            "confirmed": c.confirmed,
            "confirmation_type": c.confirmation_type,
            "esi_final": c.esi_final,
            "created_at": c.created_at,
        }
        for c in classifications
    ]


@router.get("/{classification_id}")
def get_case_detail(classification_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    c = db.query(Classification).options(joinedload(Classification.case)).filter(Classification.id == classification_id).first()
    if not c:
        raise HTTPException(404, "Clasificación no encontrada")
    return {
        "classification_id": c.id,
        "case": {
            "id": c.case.id,
            "label": c.case.label,
            "input_mode": c.case.input_mode,
            "patient_data": c.case.patient_data,
            "free_text": c.case.free_text,
        },
        "model_used": c.model_used,
        "result": c.result_json,
        "confirmed": c.confirmed,
        "confirmation_type": c.confirmation_type,
        "esi_final": c.esi_final,
        "adjustment_note": c.adjustment_note,
    }


@router.post("/{classification_id}/confirm")
def confirm_case(
    classification_id: int,
    payload: ConfirmRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Equivalente a saveConf() en el HTML: el triagista confirma o ajusta el ESI sugerido."""
    c = db.query(Classification).filter(Classification.id == classification_id).first()
    if not c:
        raise HTTPException(404, "Clasificación no encontrada")

    c.confirmed = True
    c.confirmation_type = payload.type
    c.esi_final = payload.esi_final
    c.adjustment_note = payload.note or ""
    c.confirmed_at = dt.datetime.utcnow()
    db.commit()

    return {"ok": True, "classification_id": c.id, "esi_final": c.esi_final, "type": c.confirmation_type}
