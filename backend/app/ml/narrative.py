"""
app/ml/narrative.py

XGBoost no redacta 'clinical_reasoning', 'red_flags', 'questions', etc.
Esta función arma esos campos con reglas simples (mismos umbrales que ya
tenías en el SYSTEM_PROMPT / checkVitals() del frontend original), para no
perder esa info en la UI sin depender de un LLM.

Opcional: si más adelante querés explicaciones más finas, reemplazar el
cuerpo de red_flags/clinical_reasoning por una llamada a SHAP
(shap.TreeExplainer(model).shap_values(row)) para decir *qué feature*
empujó la predicción, no solo repetir el umbral que se cruzó.
"""
from app.schemas import PatientData


def _f(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_narrative(pd: PatientData, esi_level: int) -> dict:
    fc, pa_s, spo2, temp = _f(pd.fc), _f(pd.pa_s), _f(pd.spo2), _f(pd.temp)

    red_flags = []
    if pa_s is not None and pa_s < 90:
        red_flags.append(f"PA sistólica baja ({pa_s} mmHg)")
    if spo2 is not None and spo2 < 94:
        red_flags.append(f"SpO₂ baja ({spo2}%)")
    if fc is not None and (fc > 150 or fc < 40):
        red_flags.append(f"Frecuencia cardíaca crítica ({fc} bpm)")
    if temp is not None and temp > 39:
        red_flags.append(f"Fiebre alta ({temp}°C)")

    treatment_by_level = {
        1: [{"action": "Reanimación inmediata / activar código de emergencia", "priority": "alta"}],
        2: [{"action": "Evaluación médica inmediata, monitoreo continuo", "priority": "alta"}],
        3: [{"action": "Evaluación médica dentro de 30 min, monitoreo de signos vitales", "priority": "media"}],
        4: [{"action": "Evaluación médica dentro de 60 min", "priority": "media"}],
        5: [{"action": "Puede esperar en sala, reevaluar si empeora", "priority": "baja"}],
    }

    return {
        "regla_aplicada": "Clasificación por modelo XGBoost (no basada en reglas de prompt)",
        "primary_concern": pd.motivo or "",
        "clinical_reasoning": (
            f"Nivel ESI {esi_level} asignado por el modelo según signos vitales y datos ingresados."
        ),
        "red_flags": red_flags,
        "questions": [],  # sin LLM no hay generación dinámica de preguntas; dejar vacío o fijo por nivel
        "resources": [],
        "treatment": treatment_by_level.get(esi_level, []),
    }
