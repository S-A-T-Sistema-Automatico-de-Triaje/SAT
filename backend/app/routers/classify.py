from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Case, Classification, User
from app.schemas import ClassifyRequest, ClassifyResponse, ESIResult
from app.prompts import build_prompt_from_form  # se mantiene solo como registro/trazabilidad
from app.ml.model import classify_features
from app.ml.narrative import build_narrative
from app.auth import get_current_user

router = APIRouter(prefix="/api", tags=["classify"])

MODEL_NAME = "triageai-catboost-v1" 


@router.post("/classify", response_model=ClassifyResponse)
async def classify(payload: ClassifyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # El modo "free" sigue sin soportarse: XGBoost necesita los campos estructurados
    # (vitales, dolor, GCS, comorbilidades, etc.), no texto libre.
    if payload.input_mode == "free":
        raise HTTPException(
            400,
            "El modo de texto libre no está soportado por el modelo XGBoost. Usá el formulario estructurado.",
        )

    if not payload.patient_data or not payload.patient_data.motivo:
        raise HTTPException(400, "Falta el motivo de consulta")

    pd = payload.patient_data
    full_name = f"{pd.nombre} {pd.apellido}".strip()
    label = full_name or pd.motivo[:45]


    # 1. Guardar el caso ANTES de clasificar (igual que con Ollama: queda
    #    registrado aunque la inferencia falle)
    case = Case(
    label=label,
    input_mode=payload.input_mode,
    patient_data=pd.model_dump(),
    free_text=None,
    prompt_sent=None,
)
    db.add(case)
    db.commit()
    db.refresh(case)

    # 2. Clasificar con XGBoost (reemplaza el bloque httpx.post a Ollama + _extract_json)
    try:
        prediction = classify_features(pd)
    except FileNotFoundError as e:
        raise HTTPException(500, f"Modelo XGBoost no disponible: {e}")
    except Exception as e:
        raise HTTPException(500, f"Error al clasificar con el modelo: {e}")

    narrative = build_narrative(pd, prediction["esi_level"])

    result = ESIResult(
        esi_level=prediction["esi_level"],
        esi_label=prediction["esi_label"],
        confidence=prediction["confidence"],
        **narrative,
    )

    # 3. Persistir la clasificación, ligada al caso y al usuario que la generó
    classification = Classification(
        case_id=case.id,
        model_used=MODEL_NAME,
        esi_level=result.esi_level,
        result_json=result.model_dump(),
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
    )
