"""
app/routers/meta.py

Las categorías de pain_location y chief_complaint_system están confirmadas
directamente contra train_clean.csv (el mismo dataset con el que se entrenó
CatBoost). Para el Frontend se devuelven como {value, label}: value es el
string en inglés que el modelo necesita recibir tal cual, label es la
traducción al español que ve el triagista en el <select>.
"""
import unicodedata

from fastapi import APIRouter, Depends

from app.ml.model import get_comorbidity_columns
from app.security import get_current_user
from app.models import User

router = APIRouter(prefix="/api/meta", tags=["meta"])

# value = lo que espera el modelo (inglés, confirmado contra train_clean.csv)
# label = lo que ve el triagista en el <select>
PAIN_LOCATION_OPTIONS = [
    {"value": "abdomen", "label": "Abdomen"},
    {"value": "back", "label": "Espalda"},
    {"value": "chest", "label": "Tórax / pecho"},
    {"value": "extremity", "label": "Extremidad"},
    {"value": "head", "label": "Cabeza"},
    {"value": "multiple", "label": "Múltiples zonas"},
    {"value": "none", "label": "Sin dolor"},
    {"value": "pelvis", "label": "Pelvis"},
    {"value": "unknown", "label": "Desconocida / no especificada"},
]

CHIEF_COMPLAINT_SYSTEM_OPTIONS = [
    {"value": "ENT", "label": "Otorrinolaringológico (ORL)"},
    {"value": "cardiovascular", "label": "Cardiovascular"},
    {"value": "dermatological", "label": "Dermatológico"},
    {"value": "endocrine", "label": "Endocrino"},
    {"value": "gastrointestinal", "label": "Gastrointestinal"},
    {"value": "genitourinary", "label": "Genitourinario"},
    {"value": "infectious", "label": "Infeccioso"},
    {"value": "musculoskeletal", "label": "Musculoesquelético"},
    {"value": "neurological", "label": "Neurológico"},
    {"value": "ophthalmic", "label": "Oftalmológico"},
    {"value": "other", "label": "Otro / inespecífico"},
    {"value": "psychiatric", "label": "Psiquiátrico"},
    {"value": "respiratory", "label": "Respiratorio"},
    {"value": "trauma", "label": "Traumatológico"},
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


def _sort_key(text: str) -> str:
    """Orden alfabético ignorando tildes (ej: 'Cáncer' debe ir junto a 'Asma', no después de 'Consumo')."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


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
        "comorbidities": sorted(
            ({"key": col, "label": _humanize(col)} for col in get_comorbidity_columns()),
            key=lambda c: _sort_key(c["label"]),
        ),
    }