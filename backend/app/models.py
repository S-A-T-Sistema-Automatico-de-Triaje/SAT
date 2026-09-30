import enum
import datetime as dt

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.database import Base


class RoleEnum(str, enum.Enum):
    """Los 5 roles clínicos definidos en la arquitectura de TriageAI."""
    triagista = "triagista"
    medico_guardia = "medico_guardia"
    jefe_enfermeria = "jefe_enfermeria"
    administrador = "administrador"
    auditor_clinico = "auditor_clinico"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.triagista)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    classifications = relationship("Classification", back_populates="created_by_user")


class Case(Base):
    """Un caso clínico (los datos del paciente que se ingresaron para clasificar)."""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(150), nullable=True)  # nombre o resumen corto para el historial
    input_mode = Column(String(10), default="form")  # "form" | "free"
    patient_data = Column(JSON, nullable=True)  # snapshot del formulario estructurado
    free_text = Column(String, nullable=True)   # si vino de texto libre
    prompt_sent = Column(String, nullable=True)  # prompt exacto enviado al modelo (auditable)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    classifications = relationship("Classification", back_populates="case")


class Classification(Base):
    """Cada llamada al modelo genera una clasificación, ligada a un caso."""
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)

    model_used = Column(String(100), nullable=False)
    esi_level = Column(Integer, nullable=False)
    result_json = Column(JSON, nullable=False)  # respuesta completa validada del modelo

    # -- Confirmación / ajuste del triagista --
    confirmed = Column(Boolean, default=False)
    confirmation_type = Column(String(10), nullable=True)  # "ok" | "adj"
    esi_final = Column(Integer, nullable=True)
    adjustment_note = Column(String, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case", back_populates="classifications")
    created_by_user = relationship("User", back_populates="classifications")
