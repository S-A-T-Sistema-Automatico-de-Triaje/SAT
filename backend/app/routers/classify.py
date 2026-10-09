import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Case, Classification, ClassificationStatus, RoleEnum, User
from app.schemas import ClassifyRequest, ClassifyResponse, ESIResult
from app.prompts import build_prompt_from_form  # solo registro/trazabilidad
from app.ml.model import classify_features
from app.ml.narrative import build_narrative
from app.security import require_roles

router = APIRouter(prefix="/api", tags=["classify"])

MODEL_NAME = "triageai-catboost-v1"


def _next_anon_code(db: Session) -> str:
    """ANON-AAAAMMDD-NNNN, secuencia diaria. Suficiente para una sola instancia del backend."""
    prefix = f"ANON-{dt.date.today():%Y%m%d}-"
    n = db.query(Case).filter(Case.anon_code.like(f"{prefix}%")).count()
    return f"{prefix}{n + 1:04d}"


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    payload: ClassifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(RoleEnum.triagista)),
):
    if payload.input_mode == "free":
        raise HTTPException(
            400,
            "El modo de texto libre no está soportado por el modelo. Usá el formulario estructurado.",
        )

    if not payload.patient_data or not payload.patient_data.motivo:
        raise HTTPException(400, "Falta el motivo de consulta")

    pd = payload.patient_data

    # Anónimo: se borra cualquier nombre ANTES de armar el prompt y el snapshot
    anon_code = None
    if pd.anonimo:
        pd.nombre = pd.apellido = ""
        anon_code = _next_anon_code(db)
        label = anon_code
    else:
        full_name = f"{pd.nombre} {pd.apellido}".strip()
        label = full_name or pd.motivo[:45]

    prompt_record = build_prompt_from_form(pd)

    case = Case(
        label=label,
        input_mode=payload.input_mode,
        patient_data=pd.model_dump(),
        free_text=None,
        prompt_sent=prompt_record,
        is_anonymous=pd.anonimo,
        anon_code=anon_code,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    try:
        prediction = classify_features(pd)
    except FileNotFoundError as e:
        raise HTTPException(500, f"Modelo no disponible: {e}")
    except Exception as e:
        raise HTTPException(500, f"Error al clasificar con el modelo: {e}")

    narrative = build_narrative(pd, prediction["esi_level"])

    result = ESIResult(
        esi_level=prediction["esi_level"],
        esi_label=prediction["esi_label"],
        confidence=prediction["confidence"],
        **narrative,
    )

    classification = Classification(
        case_id=case.id,
        model_used=MODEL_NAME,
        esi_level=result.esi_level,
        result_json=result.model_dump(),
        status=ClassificationStatus.en_triaje,
        created_by_user_id=user.id,
    )
    db.add(classification)
    db.commit()
    db.refresh(classification)

    return ClassifyResponse(
        case_id=case.id,
        classification_id=classification.id,
        model_used=MODEL_NAME,
        result=result,
        is_anonymous=case.is_anonymous,
        anon_code=case.anon_code,
        status=classification.status.value,
    )
