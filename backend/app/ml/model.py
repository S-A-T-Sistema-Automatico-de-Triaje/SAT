"""
app/ml/model.py

Carga triage_catboost_model.joblib (dict con 'model', 'cat_features', 'feature_order')
una sola vez, y arma la fila de features dinámicamente a partir de PatientData.

Diferencia clave vs. la versión XGBoost: CatBoost maneja las columnas categóricas
de forma NATIVA — se les pasa el string crudo (ej. "M", "cardiovascular"), no un
código numérico de un LabelEncoder. No hay fallback a -1 para valores no vistos:
CatBoost los absorbe solo, tratándolos como una categoría más en tiempo de inferencia.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool  # noqa: F401 (CatBoostClassifier necesario para des-picklear)

from app.config import settings
from app.schemas import PatientData

ESI_LABELS = {
    1: "Resucitación inmediata",
    2: "Emergente — atención < 15 min",
    3: "Urgente — atención < 30 min",
    4: "Semi-urgente — atención < 60 min",
    5: "No urgente",
}

# Campos "administrativos" que todavía no se capturan en el sistema (grupo ⑤).
# Con CatBoost, un valor no visto en entrenamiento no rompe nada: se pasa tal cual
# y el modelo lo trata como categoría desconocida.
DEFERRED_CATEGORICAL_VALUE = "unknown"

# Traducción español (formulario) -> inglés (mismas etiquetas usadas en entrenamiento).
# ⚠️ Asume que el dataset de CatBoost usa las mismas categorías en inglés que el de
# XGBoost (mismo dataset base). Si entrenaste con otras etiquetas, ajustar acá.
SEX_ES_TO_EN = {"Masculino": "M", "Femenino": "F", "Otro": "Other"}
MENTAL_STATUS_ES_TO_EN = {
    "Alerta": "alert",
    "Confundido": "confused",
    "Agitado": "agitated",
    "Somnoliento": "drowsy",
    "No responde": "unresponsive",
}

SEASON_BY_MONTH = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}
SHIFT_BY_HOUR = [
    (range(6, 14), "morning"),
    (range(14, 22), "afternoon"),
    (range(22, 24), "evening"),
    (range(0, 6), "night"),
]


@lru_cache(maxsize=1)
def get_bundle() -> dict:
    path = Path(settings.catboost_model_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el modelo CatBoost en {path}")
    bundle = joblib.load(path)
    for key in ("model", "cat_features", "feature_order"):
        if key not in bundle:
            raise ValueError(f"El joblib no tiene la clave esperada '{key}'")
    return bundle


def get_categorical_columns() -> list[str]:
    """
    Nombres de las columnas categóricas, a partir de bundle['cat_features'].
    Si vino como índices (int) en vez de nombres, se resuelve contra feature_order.
    """
    bundle = get_bundle()
    cat_features = bundle["cat_features"]
    feature_order = bundle["feature_order"]
    if cat_features and isinstance(cat_features[0], int):
        return [feature_order[i] for i in cat_features]
    return list(cat_features)


def get_comorbidity_columns() -> list[str]:
    bundle = get_bundle()
    return [c for c in bundle["feature_order"] if c.startswith("hx_")]


def _missing_flag_columns() -> list[str]:
    bundle = get_bundle()
    return [c for c in bundle["feature_order"] if c.endswith("_missing")]


def _to_float(value, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _age_group(age: float | None) -> str:
    """Bins confirmados contra train_clean.csv: pediatric 1-15, young_adult 16-39,
    middle_aged 40-64, elderly 65+."""
    if age is None:
        return DEFERRED_CATEGORICAL_VALUE
    if age <= 15:
        return "pediatric"
    if age <= 39:
        return "young_adult"
    if age <= 64:
        return "middle_aged"
    return "elderly"


def _news2_score(rr, spo2, systolic_bp, hr, temp, alert: bool) -> float:
    """NEWS2 estándar, asumiendo aire ambiente (sin dato de O2 suplementario)."""
    score = 0
    if rr is not None:
        if rr <= 8 or rr >= 25: score += 3
        elif rr >= 21: score += 2
        elif rr <= 11: score += 1
    if spo2 is not None:
        if spo2 <= 91: score += 3
        elif spo2 <= 93: score += 2
        elif spo2 <= 95: score += 1
    if systolic_bp is not None:
        if systolic_bp <= 90 or systolic_bp >= 220: score += 3
        elif systolic_bp <= 100: score += 2
        elif systolic_bp <= 110: score += 1
    if hr is not None:
        if hr <= 40 or hr >= 131: score += 3
        elif hr >= 111: score += 2
        elif hr >= 91 or hr <= 50: score += 1
    if not alert:
        score += 3
    if temp is not None:
        if temp <= 35.0: score += 3
        elif temp >= 39.1: score += 2
        elif temp <= 36.0 or temp >= 38.1: score += 1
    return float(score)


def build_feature_row(pd_data: PatientData) -> pd.DataFrame:
    bundle = get_bundle()
    feature_order: list[str] = bundle["feature_order"]
    cat_cols = set(get_categorical_columns())
    now = dt.datetime.now()

    age = _to_float(pd_data.edad)
    systolic_bp = _to_float(pd_data.pa_s)
    diastolic_bp = _to_float(pd_data.pa_d)
    heart_rate = _to_float(pd_data.fc)
    respiratory_rate = _to_float(pd_data.fr)
    temperature_c = _to_float(pd_data.temp)
    spo2 = _to_float(pd_data.spo2)
    gcs_total = _to_float(pd_data.gcs_total)
    pain_score = _to_float(pd_data.pain_score)
    weight_kg = _to_float(pd_data.weight_kg)
    height_cm = _to_float(pd_data.height_cm)

    sex_en = SEX_ES_TO_EN.get(pd_data.sexo, pd_data.sexo)
    mental_status_en = MENTAL_STATUS_ES_TO_EN.get(pd_data.mental_status_triage, pd_data.mental_status_triage)
    is_alert = (mental_status_en == "alert") if mental_status_en else True

    mean_arterial_pressure = (
        diastolic_bp + (systolic_bp - diastolic_bp) / 3
        if systolic_bp is not None and diastolic_bp is not None else None
    )
    pulse_pressure = (
        systolic_bp - diastolic_bp if systolic_bp is not None and diastolic_bp is not None else None
    )
    shock_index = (
        heart_rate / systolic_bp if heart_rate is not None and systolic_bp not in (None, 0) else None
    )
    bmi = (
        weight_kg / ((height_cm / 100) ** 2)
        if weight_kg is not None and height_cm not in (None, 0) else None
    )
    news2 = _news2_score(respiratory_rate, spo2, systolic_bp, heart_rate, temperature_c, is_alert)

    comorbidities = set(pd_data.comorbidities or [])

    numeric_values: dict[str, float | None] = {
        "arrival_hour": float(now.hour),
        "arrival_month": float(now.month),
        "age": age,
        "num_prior_ed_visits_12m": 0.0,
        "num_prior_admissions_12m": 0.0,
        "num_active_medications": 0.0,
        "num_comorbidities": float(len(comorbidities)),
        "systolic_bp": systolic_bp,
        "diastolic_bp": diastolic_bp,
        "mean_arterial_pressure": mean_arterial_pressure,
        "pulse_pressure": pulse_pressure,
        "heart_rate": heart_rate,
        "respiratory_rate": respiratory_rate,
        "temperature_c": temperature_c,
        "spo2": spo2,
        "gcs_total": gcs_total,
        "pain_score": pain_score,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "bmi": bmi,
        "shock_index": shock_index,
        "shock_index_recalc": shock_index,
        "news2_score": news2,
        "pain_unassessable": 1.0 if pd_data.pain_unassessable else 0.0,
    }

    categorical_raw_values: dict[str, str] = {
        "site_id": settings.site_id,  # ⚠️ debe incluir el prefijo, ej. "SITE-HEL-01"
        "arrival_mode": DEFERRED_CATEGORICAL_VALUE,
        "arrival_day": now.strftime("%A"),
        "arrival_season": SEASON_BY_MONTH[now.month],
        "shift": next(s for hrs, s in SHIFT_BY_HOUR if now.hour in hrs),
        "age_group": _age_group(age),
        "sex": sex_en or DEFERRED_CATEGORICAL_VALUE,
        "language": DEFERRED_CATEGORICAL_VALUE,
        "insurance_type": DEFERRED_CATEGORICAL_VALUE,
        "transport_origin": DEFERRED_CATEGORICAL_VALUE,
        "pain_location": pd_data.pain_location or DEFERRED_CATEGORICAL_VALUE,
        "mental_status_triage": mental_status_en or DEFERRED_CATEGORICAL_VALUE,
        "chief_complaint_system": pd_data.chief_complaint_system or DEFERRED_CATEGORICAL_VALUE,
    }

    missing_cols = set(_missing_flag_columns())

    row: dict[str, object] = {}
    for col in feature_order:
        if col in cat_cols:
            # CatBoost recibe el string crudo tal cual — sin encoder, sin -1.
            row[col] = str(categorical_raw_values.get(col, DEFERRED_CATEGORICAL_VALUE))
        elif col.startswith("hx_"):
            row[col] = 1.0 if col in comorbidities else 0.0
        elif col in missing_cols:
            base = col[: -len("_missing")]
            was_provided = numeric_values.get(base) is not None
            row[col] = 0.0 if was_provided else 1.0
        elif col in numeric_values:
            # A diferencia de XGBoost, dejamos NaN en vez de 0.0 cuando falta el dato:
            # CatBoost maneja missing values de forma nativa en columnas numéricas.
            val = numeric_values[col]
            row[col] = np.nan if val is None else val
        else:
            row[col] = np.nan

    return pd.DataFrame([row], columns=feature_order)


def classify_features(pd_data: PatientData) -> dict:
    bundle = get_bundle()
    model: CatBoostClassifier = bundle["model"]
    row_df = build_feature_row(pd_data)
    cat_cols = get_categorical_columns()

    pool = Pool(row_df, cat_features=cat_cols)
    proba = model.predict_proba(pool)[0]      # shape (5,), clases 0-indexadas
    esi_level = int(np.argmax(proba)) + 1        # +1 -> ESI 1..5
    confidence = float(np.max(proba))

    return {
        "esi_level": esi_level,
        "esi_label": ESI_LABELS.get(esi_level, ""),
        "confidence": confidence,
        "proba_by_class": {i + 1: float(p) for i, p in enumerate(proba)},
    }