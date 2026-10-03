import enum
import datetime as dt

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Text, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.database import Base


class RoleEnum(str, enum.Enum):
    """Roles de TriageAI. En uso: triagista, medico_guardia y administrador.
    El resto queda declarado para no romper usuarios existentes."""
    triagista = "triagista"
    medico_guardia = "medico_guardia"
    jefe_enfermeria = "jefe_enfermeria"
    administrador = "administrador"
    auditor_clinico = "auditor_clinico"


class ClassificationStatus(str, enum.Enum):
    en_triaje = "en_triaje"                # el modelo clasificó; el triagista todavía no lo envió
    pendiente_medico = "pendiente_medico"  # enviado, esperando revisión médica
    revisado = "revisado"                  # el médico ya dio su veredicto


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.triagista)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    classifications = relationship(
        "Classification",
        foreign_keys="Classification.created_by_user_id",
        back_populates="created_by_user",
    )


class Case(Base):
    """Un caso clínico (los datos del paciente que se ingresaron para clasificar)."""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(150), nullable=True)  # nombre, código anónimo o resumen corto
    input_mode = Column(String(10), default="form")
    patient_data = Column(JSON, nullable=True)
    free_text = Column(String, nullable=True)
    prompt_sent = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # -- Anonimato --
    is_anonymous = Column(Boolean, default=False, nullable=False)
    anon_code = Column(String(32), nullable=True, index=True)  # ej. ANON-20261002-0007 (se conserva al identificar)

    classifications = relationship("Classification", back_populates="case")


class Classification(Base):
    """Cada llamada al modelo genera una clasificación, ligada a un caso.
    Guarda los tres niveles ESI: modelo, triagista y médico."""
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)

    # -- 1. Modelo --
    model_used = Column(String(100), nullable=False)
    esi_level = Column(Integer, nullable=False)
    result_json = Column(JSON, nullable=False)

    status = Column(
        SAEnum(ClassificationStatus),
        nullable=False,
        default=ClassificationStatus.en_triaje,
        index=True,
    )

    # -- 2. Triagista (quien cargó el caso es created_by_user_id) --
    triagist_esi = Column(Integer, nullable=True)
    triagist_note = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)

    # -- 3. Médico --
    doctor_agrees = Column(Boolean, nullable=True)
    doctor_esi = Column(Integer, nullable=True)
    doctor_comment = Column(Text, nullable=True)  # recomendaciones para el paciente
    doctor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    case = relationship("Case", back_populates="classifications")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="classifications")
    doctor_user = relationship("User", foreign_keys=[doctor_user_id])
