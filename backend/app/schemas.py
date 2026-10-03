import datetime as dt
from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator

from app.models import RoleEnum


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


class PatientData(BaseModel):
    anonimo: bool = False  # NUEVO: si es True no se guardan nombre ni apellido

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

    pain_score: Optional[str] = ""
    pain_location: Optional[str] = ""
    pain_unassessable: bool = False
    mental_status_triage: Optional[str] = ""
    gcs_total: Optional[str] = ""
    weight_kg: Optional[str] = ""
    height_cm: Optional[str] = ""
    chief_complaint_system: Optional[str] = ""
    comorbidities: list[str] = []


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
    is_anonymous: bool = False
    anon_code: Optional[str] = None
    status: str = "en_triaje"


# ──────────────────────────────────────────────────────────
# Flujo triagista -> médico
# ──────────────────────────────────────────────────────────
class TriagistSubmit(BaseModel):
    esi_propuesto: int = Field(ge=1, le=5)
    note: Optional[str] = ""


class DoctorReview(BaseModel):
    agrees: bool
    esi_final: int = Field(ge=1, le=5)
    comment: str = ""  # recomendaciones para el paciente

    @model_validator(mode="after")
    def _coherencia(self):
        if not self.agrees and not self.comment.strip():
            raise ValueError("Si cambiás el nivel ESI, explicá el motivo en el comentario")
        return self


class IdentifyRequest(BaseModel):
    nombre: str
    apellido: str = ""


class CaseSummary(BaseModel):
    classification_id: int
    case_id: int
    display_name: str
    is_anonymous: bool
    esi_model: int
    esi_triagist: Optional[int] = None
    esi_final: Optional[int] = None
    status: str
    doctor_comment: Optional[str] = None
    created_at: dt.datetime
    submitted_at: Optional[dt.datetime] = None


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