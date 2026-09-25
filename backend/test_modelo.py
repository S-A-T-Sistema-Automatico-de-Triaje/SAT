"""
test_modelos_dataset.py
============================================================

Evaluación comparativa de los modelos del S.A.T.

Evalúa:
    - S.A.T. V1.1
    - S.A.T. V1.2
    - S.A.T. V2 XGBoost

Usa:
    test_clean.csv

El archivo debe contener:
    - patient_id
    - triage_acuity
    - features utilizadas por los modelos

El backend debe estar ejecutándose en:
    http://localhost:8000

Uso:
    python test_modelos_dataset.py

Resultados:
    - Accuracy
    - Precision
    - Recall
    - F1
    - Quadratic Weighted Kappa
    - Matriz de confusión
    - Subtriaje
    - Sobretriaje
    - Tiempo de inferencia
    - Comparación entre modelos
    - CSV con todas las predicciones
"""

import requests
import pandas as pd
import numpy as np

from pathlib import Path
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    cohen_kappa_score,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

BACKEND_URL = "http://localhost:8000"

# Si ejecutás desde backend/
DATASET_PATH = Path("data/train_clean.csv")

RESULTS_PATH = Path("resultados_test_modelos.csv")


MODELOS = {
    "v1.1": "S.A.T. V1.1",
    "V 1.2": "S.A.T. V1.2 KTAS",
    "V 2": "S.A.T. V2 XGBoost",
}


# ============================================================
# COLUMNAS
# ============================================================

# Estas son las columnas que V2 NO utiliza como features.
COLUMNAS_EXCLUIDAS = {
    "patient_id",
    "triage_nurse_id",
    "disposition",
    "ed_los_hours",
    "chief_complaint_raw",
    "triage_acuity",
}


# ============================================================
# BACKEND
# ============================================================

def comprobar_backend():

    print("=" * 75)
    print("COMPROBANDO BACKEND")
    print("=" * 75)

    try:

        response = requests.get(
            f"{BACKEND_URL}/api/health",
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        print("[OK] Backend conectado")
        print(f"     Versión: {data.get('version')}")
        print()

        return True

    except Exception as e:

        print("[ERROR] No se pudo conectar con el backend")
        print(f"        {e}")
        print()

        return False


# ============================================================
# DATASET
# ============================================================

def cargar_dataset():

    print("=" * 75)
    print("CARGANDO DATASET")
    print("=" * 75)

    if not DATASET_PATH.exists():

        print(f"[ERROR] No existe: {DATASET_PATH}")
        return None

    try:

        df = pd.read_csv(DATASET_PATH)

    except Exception as e:

        print("[ERROR] No se pudo leer el CSV")
        print(f"        {e}")

        return None

    print(f"[OK] Dataset cargado")
    print(f"     Filas:    {len(df)}")
    print(f"     Columnas: {len(df.columns)}")
    print()

    # --------------------------------------------------------
    # Comprobar columnas importantes
    # --------------------------------------------------------

    if "patient_id" not in df.columns:

        print("[ERROR] El dataset no tiene patient_id")
        return None

    if "triage_acuity" not in df.columns:

        print(
            "[ERROR] El dataset no tiene triage_acuity."
        )

        print(
            "No es posible calcular métricas reales "
            "sin la etiqueta."
        )

        return None

    # --------------------------------------------------------
    # Distribución de clases
    # --------------------------------------------------------

    print("Distribución de triage_acuity REAL:")

    distribucion = (
        df["triage_acuity"]
        .value_counts()
        .sort_index()
    )

    for clase, cantidad in distribucion.items():

        porcentaje = cantidad / len(df) * 100

        print(
            f"     ESI {int(clase)}: "
            f"{cantidad:>6} "
            f"({porcentaje:6.2f}%)"
        )

    print()

    return df


# ============================================================
# CONVERSIÓN DE NaN
# ============================================================

def limpiar_valor(valor):

    if pd.isna(valor):
        return None

    # numpy int
    if isinstance(valor, np.integer):
        return int(valor)

    # numpy float
    if isinstance(valor, np.floating):
        return float(valor)

    return valor


# ============================================================
# CREAR PAYLOAD
# ============================================================

def crear_payload(row, model_id):

    payload = {}

    for columna in row.index:

        # No mandar datos que son exclusivamente del dataset
        if columna in {
            "patient_id",
            "triage_acuity",
            "triage_nurse_id",
            "disposition",
            "ed_los_hours",
            "chief_complaint_raw",
        }:
            continue

        valor = limpiar_valor(row[columna])

        if valor is not None:

            payload[columna] = valor

    payload["selected_model"] = model_id

    return payload


# ============================================================
# PREDICCIÓN
# ============================================================

def predecir(model_id, row):

    payload = crear_payload(row, model_id)

    try:

        response = requests.post(
            f"{BACKEND_URL}/predecir",
            json=payload,
            timeout=60
        )

        if not response.ok:

            return {
                "success": False,
                "error": response.text,
            }

        resultado = response.json()

        return resultado

    except Exception as e:

        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# EVALUACIÓN
# ============================================================

def evaluar_modelo(df, model_id, nombre):

    print()
    print("=" * 75)
    print(f"EVALUANDO: {nombre}")
    print("=" * 75)

    reales = []
    predicciones = []

    errores = []

    tiempos = []

    total = len(df)

    for indice, (_, row) in enumerate(df.iterrows(), start=1):

        resultado = predecir(model_id, row)

        if resultado.get("success"):

            real = int(row["triage_acuity"])

            predicho = int(
                resultado["triage_level"]
            )

            reales.append(real)
            predicciones.append(predicho)

            # El backend puede devolver confidence
            # y tiempo no necesariamente.
            if "tiempo" in resultado:

                tiempos.append(
                    float(resultado["tiempo"])
                )

        else:

            errores.append({
                "patient_id": row["patient_id"],
                "error": resultado.get("error"),
            })

        # Progreso

        if indice % 100 == 0 or indice == total:

            porcentaje = indice / total * 100

            print(
                f"\r     Progreso: "
                f"{indice}/{total} "
                f"({porcentaje:6.2f}%)",
                end=""
            )

    print()
    print()

    if not predicciones:

        print("[ERROR] No hubo predicciones válidas.")
        return None

    # ========================================================
    # MÉTRICAS
    # ========================================================

    accuracy = accuracy_score(
        reales,
        predicciones
    )

    precision = precision_score(
        reales,
        predicciones,
        labels=[1, 2, 3, 4, 5],
        average="macro",
        zero_division=0
    )

    recall = recall_score(
        reales,
        predicciones,
        labels=[1, 2, 3, 4, 5],
        average="macro",
        zero_division=0
    )

    f1 = f1_score(
        reales,
        predicciones,
        labels=[1, 2, 3, 4, 5],
        average="macro",
        zero_division=0
    )

    kappa = cohen_kappa_score(
        reales,
        predicciones,
        weights="quadratic"
    )

    # ========================================================
    # MATRIZ DE CONFUSIÓN
    # ========================================================

    cm = confusion_matrix(
        reales,
        predicciones,
        labels=[1, 2, 3, 4, 5]
    )

    # ========================================================
    # SUBTRIAJE / SOBRETRIAJE
    # ========================================================

    subtriaje = 0
    sobretriaje = 0
    exactos = 0

    for real, predicho in zip(
        reales,
        predicciones
    ):

        if predicho < real:

            # Menor número ESI = mayor urgencia.
            #
            # Ejemplo:
            # real 1 → pred 4
            # es subtriaje.

            subtriaje += 1

        elif predicho > real:

            sobretriaje += 1

        else:

            exactos += 1

    total_validos = len(reales)

    # ========================================================
    # RESULTADO
    # ========================================================

    resultado = {
        "model_id": model_id,
        "model_name": nombre,

        "total": total,
        "validos": total_validos,
        "errores": len(errores),

        "accuracy": accuracy,
        "precision_macro": precision,
        "recall_macro": recall,
        "f1_macro": f1,
        "qwk": kappa,

        "exactos": exactos,

        "subtriaje": subtriaje,
        "subtriaje_pct": (
            subtriaje / total_validos * 100
        ),

        "sobretriaje": sobretriaje,
        "sobretriaje_pct": (
            sobretriaje / total_validos * 100
        ),

        "reales": reales,
        "predicciones": predicciones,

        "matriz": cm,

        "errores": errores,

        "tiempo_promedio": (
            sum(tiempos) / len(tiempos)
            if tiempos
            else None
        ),
    }

    # ========================================================
    # IMPRIMIR
    # ========================================================

    print(f"Pacientes evaluados: {total_validos}")
    print(f"Errores API:         {len(errores)}")
    print()

    print("MÉTRICAS")
    print("-" * 50)

    print(
        f"Accuracy:             {accuracy * 100:7.2f}%"
    )

    print(
        f"Precision macro:      {precision * 100:7.2f}%"
    )

    print(
        f"Recall macro:         {recall * 100:7.2f}%"
    )

    print(
        f"F1 macro:             {f1 * 100:7.2f}%"
    )

    print(
        f"QWK:                  {kappa:7.4f}"
    )

    print()

    print("TRIAJE")
    print("-" * 50)

    print(
        f"Predicciones exactas: {exactos:7}"
    )

    print(
        f"Subtriaje:            {subtriaje:7} "
        f"({subtriaje / total_validos * 100:.2f}%)"
    )

    print(
        f"Sobretriaje:          {sobretriaje:7} "
        f"({sobretriaje / total_validos * 100:.2f}%)"
    )

    if tiempos:

        print()

        print(
            f"Tiempo promedio:      "
            f"{resultado['tiempo_promedio']:.4f}s"
        )

    # ========================================================
    # MATRIZ
    # ========================================================

    print()
    print("MATRIZ DE CONFUSIÓN")
    print("(filas = REAL / columnas = PREDICHO)")
    print()

    matriz_df = pd.DataFrame(
        cm,
        index=[
            "REAL ESI 1",
            "REAL ESI 2",
            "REAL ESI 3",
            "REAL ESI 4",
            "REAL ESI 5",
        ],
        columns=[
            "PRED ESI 1",
            "PRED ESI 2",
            "PRED ESI 3",
            "PRED ESI 4",
            "PRED ESI 5",
        ]
    )

    print(matriz_df.to_string())

    # ========================================================
    # REPORTE POR CLASE
    # ========================================================

    print()
    print("REPORTE POR CATEGORÍA ESI")
    print()

    print(
        classification_report(
            reales,
            predicciones,
            labels=[1, 2, 3, 4, 5],
            target_names=[
                "ESI 1",
                "ESI 2",
                "ESI 3",
                "ESI 4",
                "ESI 5",
            ],
            digits=4,
            zero_division=0
        )
    )

    return resultado


# ============================================================
# GUARDAR PREDICCIONES
# ============================================================

def guardar_predicciones(
    df,
    resultados
):

    print("=" * 75)
    print("GUARDANDO RESULTADOS")
    print("=" * 75)

    salida = pd.DataFrame()

    salida["patient_id"] = df["patient_id"]
    salida["triage_real"] = df["triage_acuity"]

    for model_id, resultado in resultados.items():

        nombre_columna = (
            model_id
            .replace(" ", "_")
            .replace(".", "_")
        )

        predicciones = resultado["predicciones"]

        # Puede haber errores de API.
        #
        # Por eso las predicciones válidas se
        # colocan sobre los primeros registros válidos
        # mediante una serie indexada.

        valores = [np.nan] * len(df)

        indice_valido = 0

        for i in range(len(df)):

            if indice_valido >= len(predicciones):
                break

            # Reconstruimos usando el orden de las
            # filas que tuvieron respuesta válida.
            valores[i] = predicciones[indice_valido]
            indice_valido += 1

        salida[
            f"pred_{nombre_columna}"
        ] = valores

    salida.to_csv(
        RESULTS_PATH,
        index=False
    )

    print(
        f"[OK] Resultados guardados en:"
    )

    print(
        f"     {RESULTS_PATH}"
    )

    print()


# ============================================================
# COMPARACIÓN FINAL
# ============================================================

def mostrar_comparacion(resultados):

    print()
    print()
    print("=" * 75)
    print("COMPARACIÓN FINAL")
    print("=" * 75)

    filas = []

    for model_id, resultado in resultados.items():

        filas.append({
            "Modelo": resultado["model_name"],
            "Accuracy": resultado["accuracy"] * 100,
            "F1 Macro": resultado["f1_macro"] * 100,
            "QWK": resultado["qwk"],
            "Subtriaje %": resultado["subtriaje_pct"],
            "Sobretriaje %": resultado["sobretriaje_pct"],
            "Errores API": resultado["errores"],
        })

    tabla = pd.DataFrame(filas)

    print()

    print(
        tabla.to_string(
            index=False,
            formatters={
                "Accuracy": "{:.2f}".format,
                "F1 Macro": "{:.2f}".format,
                "QWK": "{:.4f}".format,
                "Subtriaje %": "{:.2f}".format,
                "Sobretriaje %": "{:.2f}".format,
            }
        )
    )

    # ========================================================
    # RANKING
    # ========================================================

    print()
    print("=" * 75)
    print("RANKING")
    print("=" * 75)

    # Para el ranking general damos prioridad a:
    #
    # 1. QWK
    # 2. F1
    # 3. Accuracy
    #
    # El subtriaje NO se ignora:
    # se muestra aparte porque es especialmente importante
    # en un sistema de triaje.

    ranking = sorted(
        resultados.values(),
        key=lambda r: (
            r["qwk"],
            r["f1_macro"],
            r["accuracy"]
        ),
        reverse=True
    )

    for posicion, resultado in enumerate(
        ranking,
        start=1
    ):

        print(
            f"{posicion}. "
            f"{resultado['model_name']}"
        )

        print(
            f"   QWK:       "
            f"{resultado['qwk']:.4f}"
        )

        print(
            f"   F1 Macro:  "
            f"{resultado['f1_macro'] * 100:.2f}%"
        )

        print(
            f"   Accuracy:  "
            f"{resultado['accuracy'] * 100:.2f}%"
        )

        print(
            f"   Subtriaje: "
            f"{resultado['subtriaje_pct']:.2f}%"
        )

        print()

    print(
        "NOTA: el ranking no implica validación clínica."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("S.A.T. - EVALUACIÓN COMPARATIVA DE MODELOS")
    print("=" * 75)
    print()

    # --------------------------------------------------------
    # Backend
    # --------------------------------------------------------

    if not comprobar_backend():

        return

    # --------------------------------------------------------
    # Dataset
    # --------------------------------------------------------

    df = cargar_dataset()

    if df is None:

        return

    # --------------------------------------------------------
    # Evaluar
    # --------------------------------------------------------

    resultados = {}

    for model_id, nombre in MODELOS.items():

        resultado = evaluar_modelo(
            df,
            model_id,
            nombre
        )

        if resultado is not None:

            resultados[model_id] = resultado

    # --------------------------------------------------------
    # Comprobar resultados
    # --------------------------------------------------------

    if not resultados:

        print(
            "[ERROR] Ningún modelo produjo resultados."
        )

        return

    # --------------------------------------------------------
    # Comparación
    # --------------------------------------------------------

    mostrar_comparacion(
        resultados
    )

    # --------------------------------------------------------
    # Guardar
    # --------------------------------------------------------

    guardar_predicciones(
        df,
        resultados
    )

    # --------------------------------------------------------
    # Fin
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print("EVALUACIÓN FINALIZADA")
    print("=" * 75)
    print()


if __name__ == "__main__":

    main()