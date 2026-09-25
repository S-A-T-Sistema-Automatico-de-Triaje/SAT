"""
test_modelos.py
============================================================
Pruebas comparativas del S.A.T.

Ejecuta varios casos de prueba contra:
    - S.A.T. V1.1
    - S.A.T. V1.2 KTAS
    - S.A.T. V2 XGBoost

Requiere que el backend esté ejecutándose en:
    http://localhost:8000

Uso:
    python test_modelos.py
"""

import requests
import time


BACKEND_URL = "http://localhost:8000"


# ============================================================
# CASOS DE PRUEBA
# ============================================================

CASOS = [

    {
        "nombre": "Paciente estable - dolor leve",
        "descripcion": "Signos vitales normales y dolor leve.",

        "datos": {
            "age": 30,
            "sex": "M",
            "arrival_mode": "walk-in",

            "chief_complaint_system": "musculoskeletal",
            "pain_location": "other",

            "mental_status_triage": "alert",
            "gcs_total": 15,
            "pain_score": 2,

            "heart_rate": 72,
            "respiratory_rate": 16,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "mean_arterial_pressure": 93.3,
            "pulse_pressure": 40,
            "spo2": 99,
            "temperature_c": 36.6,

            "num_prior_ed_visits_12m": 0,
            "num_prior_admissions_12m": 0,
            "num_active_medications": 0,
            "num_comorbidities": 0,

            "weight_kg": 70,
            "height_cm": 175,
            "bmi": 22.9,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 10,
            "arrival_season": "winter",
            "shift": "morning",
        }
    },

    {
        "nombre": "Dolor moderado",
        "descripcion": "Paciente estable con dolor moderado.",

        "datos": {
            "age": 45,
            "sex": "F",
            "arrival_mode": "walk-in",

            "chief_complaint_system": "gastrointestinal",
            "pain_location": "abdomen",

            "mental_status_triage": "alert",
            "gcs_total": 15,
            "pain_score": 6,

            "heart_rate": 92,
            "respiratory_rate": 18,
            "systolic_bp": 128,
            "diastolic_bp": 82,
            "mean_arterial_pressure": 97.3,
            "pulse_pressure": 46,
            "spo2": 98,
            "temperature_c": 37.1,

            "num_prior_ed_visits_12m": 1,
            "num_prior_admissions_12m": 0,
            "num_active_medications": 1,
            "num_comorbidities": 0,

            "weight_kg": 68,
            "height_cm": 165,
            "bmi": 25.0,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 14,
            "arrival_season": "winter",
            "shift": "afternoon",
        }
    },

    {
        "nombre": "Fiebre y taquicardia",
        "descripcion": "Paciente con fiebre, taquicardia y cuadro infeccioso.",

        "datos": {
            "age": 52,
            "sex": "M",
            "arrival_mode": "walk-in",

            "chief_complaint_system": "respiratory",
            "pain_location": "chest",

            "mental_status_triage": "alert",
            "gcs_total": 15,
            "pain_score": 5,

            "heart_rate": 115,
            "respiratory_rate": 24,
            "systolic_bp": 105,
            "diastolic_bp": 68,
            "mean_arterial_pressure": 80.3,
            "pulse_pressure": 37,
            "spo2": 94,
            "temperature_c": 39.0,

            "num_prior_ed_visits_12m": 2,
            "num_prior_admissions_12m": 1,
            "num_active_medications": 2,
            "num_comorbidities": 1,

            "weight_kg": 82,
            "height_cm": 178,
            "bmi": 25.9,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 18,
            "arrival_season": "winter",
            "shift": "evening",
        }
    },

    {
        "nombre": "Hipertensión",
        "descripcion": "Presión arterial elevada.",

        "datos": {
            "age": 65,
            "sex": "M",
            "arrival_mode": "walk-in",

            "chief_complaint_system": "cardiovascular",
            "pain_location": "head",

            "mental_status_triage": "alert",
            "gcs_total": 15,
            "pain_score": 7,

            "heart_rate": 96,
            "respiratory_rate": 20,
            "systolic_bp": 190,
            "diastolic_bp": 110,
            "mean_arterial_pressure": 136.7,
            "pulse_pressure": 80,
            "spo2": 97,
            "temperature_c": 36.8,

            "num_prior_ed_visits_12m": 3,
            "num_prior_admissions_12m": 1,
            "num_active_medications": 4,
            "num_comorbidities": 2,

            "weight_kg": 90,
            "height_cm": 172,
            "bmi": 30.4,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 20,
            "arrival_season": "winter",
            "shift": "night",
        }
    },

    {
        "nombre": "Dificultad respiratoria",
        "descripcion": "Paciente con hipoxemia y frecuencia respiratoria elevada.",

        "datos": {
            "age": 70,
            "sex": "F",
            "arrival_mode": "ambulance",

            "chief_complaint_system": "respiratory",
            "pain_location": "chest",

            "mental_status_triage": "drowsy",
            "gcs_total": 13,
            "pain_score": 4,

            "heart_rate": 125,
            "respiratory_rate": 32,
            "systolic_bp": 95,
            "diastolic_bp": 60,
            "mean_arterial_pressure": 71.7,
            "pulse_pressure": 35,
            "spo2": 84,
            "temperature_c": 37.8,

            "num_prior_ed_visits_12m": 4,
            "num_prior_admissions_12m": 2,
            "num_active_medications": 5,
            "num_comorbidities": 3,

            "weight_kg": 75,
            "height_cm": 160,
            "bmi": 29.3,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 22,
            "arrival_season": "winter",
            "shift": "night",
        }
    },

    {
        "nombre": "Alteración neurológica",
        "descripcion": "Paciente con confusión y disminución del nivel de conciencia.",

        "datos": {
            "age": 78,
            "sex": "M",
            "arrival_mode": "ambulance",

            "chief_complaint_system": "neurological",
            "pain_location": "head",

            "mental_status_triage": "confused",
            "gcs_total": 10,
            "pain_score": 3,

            "heart_rate": 105,
            "respiratory_rate": 22,
            "systolic_bp": 175,
            "diastolic_bp": 95,
            "mean_arterial_pressure": 121.7,
            "pulse_pressure": 80,
            "spo2": 93,
            "temperature_c": 37.0,

            "num_prior_ed_visits_12m": 2,
            "num_prior_admissions_12m": 2,
            "num_active_medications": 6,
            "num_comorbidities": 4,

            "weight_kg": 80,
            "height_cm": 170,
            "bmi": 27.7,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 3,
            "arrival_season": "winter",
            "shift": "night",
        }
    },

    {
        "nombre": "Caso crítico",
        "descripcion": "Compromiso severo de signos vitales y conciencia.",

        "datos": {
            "age": 60,
            "sex": "M",
            "arrival_mode": "ambulance",

            "chief_complaint_system": "cardiovascular",
            "pain_location": "chest",

            "mental_status_triage": "unresponsive",
            "gcs_total": 5,
            "pain_score": 10,

            "heart_rate": 145,
            "respiratory_rate": 35,
            "systolic_bp": 75,
            "diastolic_bp": 45,
            "mean_arterial_pressure": 55.0,
            "pulse_pressure": 30,
            "spo2": 72,
            "temperature_c": 35.9,

            "num_prior_ed_visits_12m": 2,
            "num_prior_admissions_12m": 2,
            "num_active_medications": 5,
            "num_comorbidities": 4,

            "weight_kg": 85,
            "height_cm": 175,
            "bmi": 27.8,

            "arrival_day": 5,
            "arrival_month": 9,
            "arrival_hour": 2,
            "arrival_season": "winter",
            "shift": "night",
        }
    },

]


# ============================================================
# MODELOS
# ============================================================

MODELOS = [
    ("v1.1", "S.A.T. V1.1"),
    ("V 1.2", "S.A.T. V1.2 KTAS"),
    ("V 2", "S.A.T. V2 XGBoost"),
]


# ============================================================
# FUNCIONES
# ============================================================

def comprobar_backend():
    print("=" * 70)
    print("COMPROBANDO BACKEND")
    print("=" * 70)

    try:
        response = requests.get(
            f"{BACKEND_URL}/api/health",
            timeout=5
        )

        response.raise_for_status()

        data = response.json()

        print("[OK] Backend conectado")
        print(f"     Versión: {data.get('version')}")
        print()

        return True

    except Exception as e:
        print("[ERROR] No se pudo conectar al backend")
        print(f"        {e}")
        print()
        print("Asegurate de tener FastAPI ejecutándose.")
        return False


def ejecutar_modelo(model_id, datos):

    payload = datos.copy()
    payload["selected_model"] = model_id

    inicio = time.perf_counter()

    try:

        response = requests.post(
            f"{BACKEND_URL}/predecir",
            json=payload,
            timeout=30
        )

        tiempo = time.perf_counter() - inicio

        if not response.ok:
            return {
                "success": False,
                "error": response.text,
                "tiempo": tiempo
            }

        resultado = response.json()

        resultado["tiempo"] = tiempo

        return resultado

    except Exception as e:

        tiempo = time.perf_counter() - inicio

        return {
            "success": False,
            "error": str(e),
            "tiempo": tiempo
        }


def imprimir_resultado(modelo, resultado):

    if not resultado.get("success"):

        print(
            f"  {modelo:<20} ERROR "
            f"({resultado.get('tiempo', 0):.2f}s)"
        )

        print(f"      {resultado.get('error')}")

        return

    nivel = resultado.get("triage_level", "?")
    confianza = resultado.get("confidence", "?")
    tiempo = resultado.get("tiempo", 0)

    print(
        f"  {modelo:<20} "
        f"ESI {nivel}   "
        f"Confianza: {confianza}%   "
        f"Tiempo: {tiempo:.2f}s"
    )


# ============================================================
# EJECUCIÓN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("S.A.T. - TEST COMPARATIVO DE MODELOS")
    print("=" * 70)
    print()

    if not comprobar_backend():
        return

    total_pruebas = 0
    errores = 0

    for numero, caso in enumerate(CASOS, start=1):

        print()
        print("=" * 70)
        print(f"CASO {numero}: {caso['nombre']}")
        print("=" * 70)

        print(caso["descripcion"])
        print()

        resultados = {}

        for model_id, nombre in MODELOS:

            resultado = ejecutar_modelo(
                model_id,
                caso["datos"]
            )

            resultados[model_id] = resultado

            imprimir_resultado(
                nombre,
                resultado
            )

            total_pruebas += 1

            if not resultado.get("success"):
                errores += 1

        # ----------------------------------------------------
        # Comparación
        # ----------------------------------------------------

        niveles = []

        for model_id, _ in MODELOS:

            resultado = resultados[model_id]

            if resultado.get("success"):
                niveles.append(
                    resultado.get("triage_level")
                )

        if niveles:

            if len(set(niveles)) == 1:

                print()
                print(
                    f"  [COINCIDENCIA] Los 3 modelos "
                    f"predijeron ESI {niveles[0]}"
                )

            else:

                print()
                print(
                    "  [DIFERENCIA] Los modelos "
                    "no coinciden:"
                )

                for model_id, nombre in MODELOS:

                    resultado = resultados[model_id]

                    if resultado.get("success"):

                        print(
                            f"      {nombre}: "
                            f"ESI {resultado.get('triage_level')}"
                        )


    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)

    print(f"Casos evaluados:       {len(CASOS)}")
    print(f"Pruebas ejecutadas:    {total_pruebas}")
    print(f"Errores:               {errores}")
    print()

    print("Pruebas completadas.")


if __name__ == "__main__":
    main()