from typing import Optional, Literal
from pydantic import BaseModel, Field

from app.models import RoleEnum


# ──────────────────────────────────────────────────────────
# Espejo exacto del JSON pedido en el SYSTEM_PROMPT (app/prompts.py).
# Si el modelo no cumple esta forma, Pydantic lo rechaza y lo tratamos
# como "respuesta no estructurada" (mismo comportamiento que el try/catch del HTML).
# ──────────────────────────────────────────────────────────
class TreatmentItem(BaseModel):
    action: str
    priority: Literal["alta", "media", "baja"] = "media"


class ESIResult(BaseModel):
    esi_level: int = Field(ge=1, le=5)
    esi_label: str
    regla_aplicada: str = ""
    primary_concern: str = ""
    clinical_reasoning: str = ""
    red_flags: list[str] = []
    questions: list[str] = []
    resources: list[str] = []
    treatment: list[TreatmentItem] = []
    confidence: float | None = None


# ──────────────────────────────────────────────────────────
# Datos del paciente (modo formulario estructurado)
# ──────────────────────────────────────────────────────────
class PatientData(BaseModel):
    nombre: Optional[str] = ""
    apellido: Optional[str] = ""
    edad: Optional[str] = ""
    sexo: Optional[str] = ""
    fc: Optional[str] = ""
    pa_s: Optional[str] = ""
    pa_d: Optional[str] = ""
    spo2: Optional[str] = ""
    fr: Optional[str] = ""
    temp: Optional[str] = ""
    motivo: Optional[str] = ""
    sintomas: Optional[str] = ""
    antecedentes: Optional[str] = ""
    medicacion: Optional[str] = ""
    alergias: Optional[str] = ""

    # NUEVO — campos clínicos para el modelo XGBoost
    pain_score: Optional[str] = ""              # 0-10
    pain_location: Optional[str] = ""            # una de las clases de options.pain_location
    pain_unassessable: bool = False               # ej: lactante, paciente inconsciente
    mental_status_triage: Optional[str] = ""      # "Alerta"/"Confundido"/etc (se traduce en model.py)
    gcs_total: Optional[str] = ""                 # 3-15, opcional
    weight_kg: Optional[str] = ""
    height_cm: Optional[str] = ""
    chief_complaint_system: Optional[str] = ""    # categoría del motivo, NO el texto libre
    comorbidities: list[str] = []                 # lista de keys hx_* marcadas (ej: ["hx_hypertension"])

class ClassifyRequest(BaseModel):
    input_mode: Literal["form", "free"] = "form"
    model: str = "gemma3:4b"
    patient_data: Optional[PatientData] = None
    free_text: Optional[str] = None


class ClassifyResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    case_id: int
    classification_id: int
    model_used: str
    result: ESIResult


# ──────────────────────────────────────────────────────────
# Confirmación / ajuste del triagista
# ──────────────────────────────────────────────────────────
class ConfirmRequest(BaseModel):
    type: Literal["ok", "adj"]
    esi_final: int = Field(ge=1, le=5)
    note: Optional[str] = ""


# ──────────────────────────────────────────────────────────
# Auth / usuarios
# ──────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: RoleEnum
    username: str


class UserCreate(BaseModel):
    username: str
    full_name: Optional[str] = None
    password: str
    role: RoleEnum = RoleEnum.triagista


class UserOut(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: RoleEnum
    is_active: bool

    class Config:
        from_attributes = True
