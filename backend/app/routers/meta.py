"""
app/routers/meta.py

Las categorías de pain_location y chief_complaint_system están confirmadas
directamente contra train_clean.csv (el mismo dataset con el que se entrenó
CatBoost) — ya no hace falta leerlas de ningún joblib de XGBoost.
"""
from fastapi import APIRouter, Depends

from app.ml.model import get_comorbidity_columns
from app.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/api/meta", tags=["meta"])

# Confirmadas contra train_clean.csv (df["pain_location"].unique() / df["chief_complaint_system"].unique())
PAIN_LOCATION_OPTIONS = [
    "abdomen", "back", "chest", "extremity", "head", "multiple", "none", "pelvis", "unknown",
]
CHIEF_COMPLAINT_SYSTEM_OPTIONS = [
    "ENT", "cardiovascular", "dermatological", "endocrine", "gastrointestinal",
    "genitourinary", "infectious", "musculoskeletal", "neurological", "ophthalmic",
    "other", "psychiatric", "respiratory", "trauma",
]

COMORBIDITY_LABELS_ES = {
    "hx_hypertension": "Hipertensión",
    "hx_diabetes_type1": "Diabetes tipo 1",
    "hx_diabetes_type2": "Diabetes tipo 2",
    "hx_asthma": "Asma",
    "hx_copd": "EPOC",
    "hx_heart_failure": "Insuficiencia cardíaca",
    "hx_coronary_artery_disease": "Enfermedad coronaria",
    "hx_atrial_fibrillation": "Fibrilación auricular",
    "hx_ckd": "Enfermedad renal crónica",
    "hx_liver_disease": "Enfermedad hepática",
    "hx_malignancy": "Cáncer / neoplasia",
    "hx_obesity": "Obesidad",
    "hx_depression": "Depresión",
    "hx_anxiety": "Ansiedad",
    "hx_dementia": "Demencia",
    "hx_epilepsy": "Epilepsia",
    "hx_hypothyroidism": "Hipotiroidismo",
    "hx_hyperthyroidism": "Hipertiroidismo",
    "hx_hiv": "VIH",
    "hx_coagulopathy": "Coagulopatía",
    "hx_immunosuppressed": "Inmunosuprimido",
    "hx_pregnant": "Embarazo",
    "hx_substance_use_disorder": "Consumo problemático de sustancias",
    "hx_stroke_prior": "ACV previo",
    "hx_peripheral_vascular_disease": "Enfermedad vascular periférica",
}


def _humanize(col: str) -> str:
    if col in COMORBIDITY_LABELS_ES:
        return COMORBIDITY_LABELS_ES[col]
    return col.removeprefix("hx_").replace("_", " ").capitalize()


@router.get("/form-options")
def form_options(_user: User = Depends(get_current_user)):
    return {
        "sex": ["Masculino", "Femenino", "Otro"],  # el mapeo a M/F/Other lo hace el backend
        "mental_status_triage": ["Alerta", "Confundido", "Agitado", "Somnoliento", "No responde"],
        "pain_location": PAIN_LOCATION_OPTIONS,
        "chief_complaint_system": CHIEF_COMPLAINT_SYSTEM_OPTIONS,
        "comorbidities": [
            {"key": col, "label": _humanize(col)} for col in get_comorbidity_columns()
        ],
    }