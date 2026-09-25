from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from datetime import datetime

import joblib
import pandas as pd
import numpy as np

import os
import traceback


# ============================================================
# S.A.T.
# Sistema Automático de Triaje
#
# Soporte:
#   - Múltiples modelos
#   - .pkl
#   - .joblib
#   - CatBoost
#   - XGBoost
#   - Modelos compatibles con sklearn
#   - Modelos guardados directamente
#   - Modelos guardados como bundles/diccionarios
#   - Carga bajo demanda
# ============================================================


app = FastAPI(
    title="S.A.T.",
    description="Sistema Automático de Triaje con múltiples modelos",
    version="1.3.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DIRECTORIOS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

MODEL_DIR = os.path.join(
    BASE_DIR,
    "model"
)

FRONTEND_DIR = os.path.join(
    BASE_DIR,
    "..",
    "frontend"
)

FRONTEND_FILE = os.path.join(
    FRONTEND_DIR,
    "triage_prototipo0.7.html"
)


# ============================================================
# CONFIGURACIÓN DE MODELOS
# ============================================================

MODELOS_DISPONIBLES = {

    # --------------------------------------------------------
    # V1.1
    # --------------------------------------------------------

    "v1.1": {
        "file": "sat_v1_1_sin_scores.pkl",
        "name": "S.A.T. V1.1",
        "version": "1.1.0",
        "algorithm": "CatBoost",
        "target": "triage_acuity",
        "description": "Modelo base S.A.T. V1.1",

        # Modelo guardado directamente
        "format": "direct",

        # CatBoost maneja las categóricas directamente
        "preprocessing": "catboost"
    },

    # --------------------------------------------------------
    # V1.2
    # --------------------------------------------------------

    "V 1.2": {
        "file": "triage_catboost_model.joblib",
        "name": "S.A.T. V1.2 KTAS",
        "version": "1.2.0",
        "algorithm": "CatBoost",
        "target": "triage_acuity",
        "description": (
            "Modelo S.A.T. V1.2 entrenado "
            "con datos de triaje KTAS"
        ),

        # El archivo puede ser un modelo directo
        # o un bundle/diccionario.
        "format": "auto",

        "preprocessing": "catboost"
    },

    # --------------------------------------------------------
    # V2
    # --------------------------------------------------------

    "V 2": {
        "file": "triage_xgb_model.joblib",
        "name": "S.A.T. V2",
        "version": "2.0.0",
        "algorithm": "XGBoost",
        "target": "triage_acuity",
        "description": (
            "Modelo S.A.T. V2 basado en XGBoost "
            "entrenado con datos de triaje KTAS"
        ),

        # Este archivo sabemos que contiene:
        #
        # {
        #     "model": model,
        #     "encoders": encoders,
        #     "feature_order": [...]
        # }
        #
        "format": "bundle",

        # XGBoost fue entrenado con LabelEncoder
        "preprocessing": "label_encoder"
    }
}


# ============================================================
# CLASE PARA MANEJAR UN MODELO
# ============================================================

class ModeloSAT:

    def __init__(
        self,
        model_id: str,
        config: dict
    ):

        self.id = model_id

        self.name = config.get(
            "name",
            model_id
        )

        self.version = config.get(
            "version",
            "unknown"
        )

        self.algorithm = config.get(
            "algorithm",
            "unknown"
        )

        self.target = config.get(
            "target",
            "triage_acuity"
        )

        self.description = config.get(
            "description",
            ""
        )

        self.file = config["file"]

        self.format = config.get(
            "format",
            "auto"
        )

        self.preprocessing = config.get(
            "preprocessing",
            "none"
        )

        self.path = os.path.join(
            MODEL_DIR,
            self.file
        )

        # ----------------------------------------------------
        # Estado
        # ----------------------------------------------------

        self.model = None

        self.encoders = {}

        self.feature_names = []

        self.cat_feature_indices = []

        self.cat_feature_names = []

        self.numeric_feature_names = []

        self.loaded = False

        self.error = None

    # ========================================================
    # CARGAR MODELO
    # ========================================================

    def cargar(self):

        if self.loaded:
            return

        if not os.path.exists(self.path):

            raise RuntimeError(
                f"No se encontró el modelo '{self.id}':\n"
                f"{self.path}"
            )

        extension = os.path.splitext(
            self.path
        )[1].lower()

        if extension not in [
            ".pkl",
            ".joblib"
        ]:

            raise RuntimeError(
                f"Formato de modelo no soportado: "
                f"{extension}\n"
                f"Archivo: {self.path}"
            )

        try:

            print()
            print("=" * 70)
            print(f"[CARGANDO] {self.id}")
            print(f"Archivo: {self.path}")
            print("=" * 70)

            objeto = joblib.load(
                self.path
            )

            print(
                f"[OK] Archivo deserializado: "
                f"{type(objeto)}"
            )

            # ------------------------------------------------
            # Detectar bundle
            # ------------------------------------------------

            if isinstance(objeto, dict):

                print(
                    "[INFO] El archivo contiene "
                    "un diccionario/bundle."
                )

                if "model" not in objeto:

                    raise RuntimeError(
                        f"El bundle del modelo '{self.id}' "
                        "no contiene la clave 'model'."
                    )

                self.model = objeto["model"]

                # Encoders
                self.encoders = objeto.get(
                    "encoders",
                    {}
                )

                # Orden de features
                feature_order = objeto.get(
                    "feature_order"
                )

                if feature_order:

                    self.feature_names = list(
                        feature_order
                    )

                    print(
                        f"[OK] Feature order encontrado: "
                        f"{len(self.feature_names)} features"
                    )

            else:

                # ------------------------------------------------
                # Modelo directo
                # ------------------------------------------------

                print(
                    "[INFO] El archivo contiene "
                    "un modelo directo."
                )

                self.model = objeto

            # ------------------------------------------------
            # Verificar predict
            # ------------------------------------------------

            if not hasattr(
                self.model,
                "predict"
            ):

                raise RuntimeError(
                    f"El objeto cargado para '{self.id}' "
                    "no posee el método predict()."
                )

            # ------------------------------------------------
            # Si todavía no tenemos features,
            # intentar descubrirlas.
            # ------------------------------------------------

            if not self.feature_names:

                self.feature_names = (
                    self.obtener_feature_names()
                )

            # ------------------------------------------------
            # Features categóricas
            # ------------------------------------------------

            self.cat_feature_indices = (
                self.obtener_indices_categoricos()
            )

            self.cat_feature_names = [
                self.feature_names[i]
                for i in self.cat_feature_indices
                if i < len(self.feature_names)
            ]

            # ------------------------------------------------
            # Para XGBoost con LabelEncoder
            # ------------------------------------------------

            if (
                self.preprocessing
                == "label_encoder"
                and self.encoders
            ):

                self.cat_feature_names = [
                    nombre
                    for nombre in self.encoders.keys()
                    if nombre in self.feature_names
                ]

            # ------------------------------------------------
            # Numéricas
            # ------------------------------------------------

            self.numeric_feature_names = [
                feature
                for feature in self.feature_names
                if feature not in self.cat_feature_names
            ]

            self.loaded = True
            self.error = None

            print()
            print(
                f"[OK] Modelo cargado correctamente: "
                f"{self.name}"
            )
            print(
                f"     ID: {self.id}"
            )
            print(
                f"     Algoritmo: {self.algorithm}"
            )
            print(
                f"     Features: "
                f"{len(self.feature_names)}"
            )

            if self.encoders:

                print(
                    f"     Encoders: "
                    f"{len(self.encoders)}"
                )

            print()

        except Exception as e:

            self.loaded = False
            self.error = str(e)

            print()
            print(
                f"[ERROR] No se pudo cargar "
                f"el modelo '{self.id}'"
            )
            print(
                f"        {e}"
            )

            traceback.print_exc()

            raise RuntimeError(
                f"No se pudo cargar el modelo "
                f"'{self.id}': {e}"
            )

    # ========================================================
    # FEATURE NAMES
    # ========================================================

    def obtener_feature_names(self):

        # ----------------------------------------------------
        # CatBoost
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "feature_names_"
        ):

            try:

                nombres = (
                    self.model.feature_names_
                )

                if nombres:

                    return list(nombres)

            except Exception:
                pass

        # ----------------------------------------------------
        # XGBoost
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "feature_names_in_"
        ):

            try:

                nombres = (
                    self.model.feature_names_in_
                )

                if nombres is not None:

                    return list(nombres)

            except Exception:
                pass

        # ----------------------------------------------------
        # Booster de XGBoost
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "get_booster"
        ):

            try:

                booster = (
                    self.model.get_booster()
                )

                nombres = (
                    booster.feature_names
                )

                if nombres:

                    return list(nombres)

            except Exception:
                pass

        # ----------------------------------------------------
        # Algunos wrappers
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "get_feature_names"
        ):

            try:

                nombres = (
                    self.model.get_feature_names()
                )

                if nombres:

                    return list(nombres)

            except Exception:
                pass

        # ----------------------------------------------------
        # sklearn / pipelines
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "feature_names_in_"
        ):

            try:

                nombres = (
                    self.model.feature_names_in_
                )

                if nombres is not None:

                    return list(nombres)

            except Exception:
                pass

        # ----------------------------------------------------
        # Pipeline
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "named_steps"
        ):

            for _, step in reversed(
                list(
                    self.model.named_steps.items()
                )
            ):

                if hasattr(
                    step,
                    "feature_names_in_"
                ):

                    try:

                        nombres = (
                            step.feature_names_in_
                        )

                        if nombres is not None:

                            return list(nombres)

                    except Exception:
                        pass

                if hasattr(
                    step,
                    "feature_names_"
                ):

                    try:

                        nombres = (
                            step.feature_names_
                        )

                        if nombres:

                            return list(nombres)

                    except Exception:
                        pass

        raise RuntimeError(
            f"El modelo '{self.id}' no expone "
            "nombres de features conocidos y "
            "el archivo tampoco contiene "
            "'feature_order'.\n"
            "No se puede determinar automáticamente "
            "la estructura de entrada."
        )

    # ========================================================
    # FEATURES CATEGÓRICAS
    # ========================================================

    def obtener_indices_categoricos(self):

        # ----------------------------------------------------
        # CatBoost
        # ----------------------------------------------------

        if hasattr(
            self.model,
            "get_cat_feature_indices"
        ):

            try:

                return list(
                    self.model.get_cat_feature_indices()
                )

            except Exception:
                pass

        return []

    # ========================================================
    # INFORMACIÓN
    # ========================================================

    def info(self):

        return {
            "id": self.id,

            "name": self.name,

            "version": self.version,

            "algorithm": self.algorithm,

            "target": self.target,

            "description": self.description,

            "model_file": self.file,

            "model_loaded": self.model is not None,

            "preprocessing": self.preprocessing,

            "feature_count": len(
                self.feature_names
            ),

            "features": self.feature_names,

            "categorical_features": (
                self.cat_feature_names
            ),

            "numeric_features": (
                self.numeric_feature_names
            ),

            "encoders": list(
                self.encoders.keys()
            )
        }


# ============================================================
# REGISTRO DE MODELOS
#
# IMPORTANTE:
#
# Acá NO cargamos los modelos.
#
# Solamente registramos su configuración.
# ============================================================

MODELOS = {}

for model_id, config in (
    MODELOS_DISPONIBLES.items()
):

    MODELOS[model_id] = ModeloSAT(
        model_id,
        config
    )


# ============================================================
# MODELO POR DEFECTO
# ============================================================

MODELO_DEFAULT = "v1.1"


if MODELO_DEFAULT not in MODELOS:

    raise RuntimeError(
        f"El modelo por defecto '{MODELO_DEFAULT}' "
        "no existe en MODELOS_DISPONIBLES."
    )


# ============================================================
# OBTENER MODELO
#
# Carga bajo demanda.
# ============================================================

def obtener_modelo(
    model_id: Optional[str]
) -> ModeloSAT:

    if model_id is None:

        model_id = MODELO_DEFAULT

    if model_id not in MODELOS:

        disponibles = list(
            MODELOS.keys()
        )

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Modelo no disponible",
                "requested_model": model_id,
                "available_models": disponibles
            }
        )

    modelo_sat = MODELOS[model_id]

    # --------------------------------------------------------
    # Cargar solamente cuando se necesita
    # --------------------------------------------------------

    if not modelo_sat.loaded:

        try:

            modelo_sat.cargar()

        except Exception as e:

            raise HTTPException(
                status_code=500,
                detail={
                    "error": "No se pudo cargar el modelo",
                    "model_id": model_id,
                    "message": str(e)
                }
            )

    return modelo_sat


# ============================================================
# FRONTEND
# ============================================================

if os.path.isdir(
    FRONTEND_DIR
):

    app.mount(
        "/static",
        StaticFiles(
            directory=FRONTEND_DIR
        ),
        name="static"
    )


@app.get("/")
async def read_index():

    if not os.path.exists(
        FRONTEND_FILE
    ):

        raise HTTPException(
            status_code=404,
            detail="No se encontró el frontend."
        )

    return FileResponse(
        FRONTEND_FILE
    )


# ============================================================
# DATOS DEL PACIENTE
# ============================================================

class DatosPacienteTriage(
    BaseModel
):

    model_config = ConfigDict(
        extra="allow"
    )

    # --------------------------------------------------------
    # Datos generales
    # --------------------------------------------------------

    age: Optional[float] = None
    sex: Optional[Any] = None

    # --------------------------------------------------------
    # Llegada
    # --------------------------------------------------------

    arrival_mode: Optional[Any] = None
    arrival_day: Optional[Any] = None
    arrival_season: Optional[Any] = None
    arrival_hour: Optional[float] = None
    arrival_month: Optional[float] = None
    shift: Optional[Any] = None

    # --------------------------------------------------------
    # Datos demográficos / administrativos
    # --------------------------------------------------------

    language: Optional[Any] = None
    insurance_type: Optional[Any] = None
    transport_origin: Optional[Any] = None

    # --------------------------------------------------------
    # Consulta
    # --------------------------------------------------------

    chief_complaint_system: Optional[Any] = None
    chief_complaint: Optional[str] = None
    chief_complaint_text: Optional[str] = None
    pain_location: Optional[Any] = None

    # --------------------------------------------------------
    # Estado clínico
    # --------------------------------------------------------

    mental_status_triage: Optional[Any] = None

    # --------------------------------------------------------
    # Dolor
    # --------------------------------------------------------

    pain_score: Optional[float] = None

    # --------------------------------------------------------
    # Signos vitales
    # --------------------------------------------------------

    heart_rate: Optional[float] = None

    respiratory_rate: Optional[float] = None
    resp_rate: Optional[float] = None

    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None

    sys_bp: Optional[float] = None
    dias_bp: Optional[float] = None

    spo2: Optional[float] = None
    oxygen_saturation: Optional[float] = None

    temperature: Optional[float] = None
    temp: Optional[float] = None

    # --------------------------------------------------------
    # Antropometría
    # --------------------------------------------------------

    weight: Optional[float] = None
    height: Optional[float] = None
    bmi: Optional[float] = None

    # --------------------------------------------------------
    # Antecedentes
    # --------------------------------------------------------

    history_count: Optional[float] = None
    chronic_conditions_count: Optional[float] = None

    # --------------------------------------------------------
    # Otros
    # --------------------------------------------------------

    previous_ed_visits: Optional[float] = None
    previous_hospitalizations: Optional[float] = None
    medications_count: Optional[float] = None

    # --------------------------------------------------------
    # Modelo
    # --------------------------------------------------------

    selected_model: Optional[str] = MODELO_DEFAULT


# ============================================================
# CONVERSIÓN DE DATOS
# ============================================================

def model_to_dict(
    datos: DatosPacienteTriage
) -> dict:

    if hasattr(
        datos,
        "model_dump"
    ):

        return datos.model_dump()

    return datos.dict()


# ============================================================
# NORMALIZACIÓN DE ALIAS
# ============================================================

def normalizar_aliases(
    data: dict
) -> dict:

    aliases = {

        "temp": "temperature",

        "resp_rate": "respiratory_rate",

        "sys_bp": "systolic_bp",

        "dias_bp": "diastolic_bp",

        "oxygen_saturation": "spo2",

        "chief_complaint_text":
            "chief_complaint"
    }

    resultado = dict(data)

    for origen, destino in aliases.items():

        if origen in resultado:

            if (
                destino not in resultado
                or resultado[destino] is None
            ):

                resultado[destino] = (
                    resultado[origen]
                )

    return resultado


# ============================================================
# HORA ACTUAL
# ============================================================

def hora_actual() -> int:

    return datetime.now().hour


# ============================================================
# DÍA ACTUAL
# ============================================================

def dia_actual() -> int:

    return datetime.now().day


# ============================================================
# VALORES POR DEFECTO
# ============================================================

def valor_default(
    feature: str,
    es_categorica: bool
):

    if es_categorica:

        return "Unknown"

    defaults = {

        "age": 30.0,

        "arrival_hour":
            hora_actual(),

        "arrival_month":
            datetime.now().month,

        "arrival_day":
            dia_actual(),

        "pain_score":
            0.0,

        "heart_rate":
            80.0,

        "respiratory_rate":
            16.0,

        "systolic_bp":
            120.0,

        "diastolic_bp":
            80.0,

        "spo2":
            98.0,

        "temperature":
            36.7,

        "weight":
            70.0,

        "height":
            170.0,

        "bmi":
            24.2,

        "history_count":
            0.0,

        "chronic_conditions_count":
            0.0,

        "previous_ed_visits":
            0.0,

        "previous_hospitalizations":
            0.0,

        "medications_count":
            0.0,
    }

    return defaults.get(
        feature,
        0.0
    )


# ============================================================
# ALIASES ESPECÍFICOS DE FEATURES
# ============================================================

ALIAS_MAP = {

    "temperature": [
        "temperature",
        "temp"
    ],

    "respiratory_rate": [
        "respiratory_rate",
        "resp_rate"
    ],

    "systolic_bp": [
        "systolic_bp",
        "sys_bp"
    ],

    "diastolic_bp": [
        "diastolic_bp",
        "dias_bp"
    ],

    "spo2": [
        "spo2",
        "oxygen_saturation"
    ],

    "chief_complaint": [
        "chief_complaint",
        "chief_complaint_text"
    ]
}


# ============================================================
# CONSTRUIR DATAFRAME BASE
# ============================================================

def construir_dataframe_base(
    datos: DatosPacienteTriage,
    modelo_sat: ModeloSAT
) -> pd.DataFrame:

    data = model_to_dict(
        datos
    )

    # --------------------------------------------------------
    # Quitar selector
    # --------------------------------------------------------

    data.pop(
        "selected_model",
        None
    )

    # --------------------------------------------------------
    # Normalizar aliases
    # --------------------------------------------------------

    data = normalizar_aliases(
        data
    )

    fila = {}

    # --------------------------------------------------------
    # Construir exactamente el orden del modelo
    # --------------------------------------------------------

    for feature in (
        modelo_sat.feature_names
    ):

        es_categorica = (
            feature
            in modelo_sat.cat_feature_names
        )

        valor = None

        # ----------------------------------------------------
        # Coincidencia directa
        # ----------------------------------------------------

        if feature in data:

            valor = data[feature]

        # ----------------------------------------------------
        # Alias
        # ----------------------------------------------------

        if valor is None:

            posibles = ALIAS_MAP.get(
                feature,
                []
            )

            for nombre in posibles:

                if (
                    nombre in data
                    and data[nombre] is not None
                ):

                    valor = data[nombre]

                    break

        # ----------------------------------------------------
        # Default
        # ----------------------------------------------------

        if valor is None:

            valor = valor_default(
                feature,
                es_categorica
            )

        # ----------------------------------------------------
        # CatBoost
        # ----------------------------------------------------

        if (
            modelo_sat.preprocessing
            == "catboost"
        ):

            if es_categorica:

                valor = str(
                    valor
                )

            else:

                try:

                    valor = float(
                        valor
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    valor = valor_default(
                        feature,
                        False
                    )

        # ----------------------------------------------------
        # XGBoost / LabelEncoder
        # ----------------------------------------------------

        elif (
            modelo_sat.preprocessing
            == "label_encoder"
        ):

            encoder = (
                modelo_sat.encoders.get(
                    feature
                )
            )

            if encoder is not None:

                valor = str(
                    valor
                )

                if valor in encoder.classes_:

                    valor = encoder.transform(
                        [valor]
                    )[0]

                else:

                    # ------------------------------------------------
                    # Categoría desconocida
                    # ------------------------------------------------

                    valor = -1

            else:

                try:

                    valor = float(
                        valor
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    valor = 0.0

        # ----------------------------------------------------
        # Genérico
        # ----------------------------------------------------

        else:

            if es_categorica:

                valor = str(
                    valor
                )

            else:

                try:

                    valor = float(
                        valor
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    valor = 0.0

        fila[feature] = valor

    # --------------------------------------------------------
    # DataFrame
    # --------------------------------------------------------

    return pd.DataFrame(
        [fila],
        columns=modelo_sat.feature_names
    )


# ============================================================
# PREDICCIÓN
# ============================================================

@app.post("/predecir")
async def predecir_triage(
    datos: DatosPacienteTriage
):

    try:

        # ----------------------------------------------------
        # Seleccionar y cargar modelo
        # ----------------------------------------------------

        modelo_sat = obtener_modelo(
            datos.selected_model
        )

        print()
        print("=" * 70)
        print("NUEVA PREDICCIÓN")
        print("=" * 70)
        print()

        print(
            f"Modelo: "
            f"{modelo_sat.name}"
        )

        print(
            f"ID: "
            f"{modelo_sat.id}"
        )

        print(
            f"Algoritmo: "
            f"{modelo_sat.algorithm}"
        )

        print(
            f"Preprocesamiento: "
            f"{modelo_sat.preprocessing}"
        )

        print()

        # ----------------------------------------------------
        # Construir entrada
        # ----------------------------------------------------

        df_paciente = construir_dataframe_base(
            datos,
            modelo_sat
        )

        print(
            "Datos utilizados:"
        )

        for columna in (
            df_paciente.columns
        ):

            print(
                f"  {columna}: "
                f"{df_paciente.iloc[0][columna]}"
            )

        print()

        # ----------------------------------------------------
        # Predicción
        # ----------------------------------------------------

        if not hasattr(
            modelo_sat.model,
            "predict"
        ):

            raise RuntimeError(
                f"El modelo '{modelo_sat.id}' "
                "no posee el método predict()."
            )

        prediccion = (
            modelo_sat.model.predict(
                df_paciente
            )
        )

        print(
            "PREDICCIÓN RAW:"
        )

        print(
            prediccion
        )

        print(
            "TYPE:",
            type(prediccion)
        )

        # ----------------------------------------------------
        # Extraer predicción
        # ----------------------------------------------------

        pred_array = np.asarray(
            prediccion
        ).reshape(-1)

        if len(pred_array) == 0:

            raise RuntimeError(
                "El modelo no devolvió "
                "ninguna predicción."
            )

        pred_raw = pred_array[0]

        print(
            "PRED_RAW:",
            pred_raw
        )

        print(
            "PRED_RAW TYPE:",
            type(pred_raw)
        )

        # ----------------------------------------------------
        # Convertir a nivel
        # ----------------------------------------------------

        try:

            nivel = int(
                float(pred_raw)
            )

        except (
            ValueError,
            TypeError
        ):

            raise RuntimeError(
                "La predicción del modelo "
                "no es numérica: "
                f"{pred_raw!r}"
            )

        # ----------------------------------------------------
        # XGBoost fue entrenado con:
        #
        # y = triage_acuity - 1
        #
        # Por eso devuelve 0-4.
        #
        # CatBoost V1.1/V1.2 normalmente devuelve 1-5.
        # ----------------------------------------------------

        if (
            modelo_sat.algorithm.upper()
            == "XGBOOST"
        ):

            nivel += 1

        # ----------------------------------------------------
        # Asegurar ESI 1-5
        # ----------------------------------------------------

        nivel = max(
            1,
            min(
                5,
                nivel
            )
        )

        # ----------------------------------------------------
        # Probabilidades
        # ----------------------------------------------------

        confianza = None
        probabilidades = None
        clases = None

        if hasattr(
            modelo_sat.model,
            "predict_proba"
        ):

            try:

                proba = (
                    modelo_sat.model
                    .predict_proba(
                        df_paciente
                    )[0]
                )

                probabilidades = [
                    float(x)
                    for x in proba
                ]

                confianza = float(
                    np.max(proba) * 100
                )

                if hasattr(
                    modelo_sat.model,
                    "classes_"
                ):

                    clases_raw = (
                        modelo_sat.model.classes_
                    )

                    clases = []

                    for clase in clases_raw:

                        try:

                            clase_int = int(
                                clase
                            )

                            # XGBoost: 0-4
                            if (
                                modelo_sat.algorithm.upper()
                                == "XGBOOST"
                            ):

                                clase_int += 1

                            clases.append(
                                str(clase_int)
                            )

                        except (
                            ValueError,
                            TypeError
                        ):

                            clases.append(
                                str(clase)
                            )

            except Exception as e:

                print(
                    "No se pudieron obtener "
                    f"probabilidades: {e}"
                )

        # ----------------------------------------------------
        # Justificación
        # ----------------------------------------------------

        if confianza is not None:

            justificacion = (
                f"Modelo "
                f"{modelo_sat.name} / "
                f"{modelo_sat.algorithm}: "
                f"ESI {nivel}. "
                f"Confianza estimada del modelo: "
                f"{confianza:.1f}%."
            )

        else:

            justificacion = (
                f"Modelo "
                f"{modelo_sat.name} / "
                f"{modelo_sat.algorithm}: "
                f"ESI {nivel}."
            )

        # ----------------------------------------------------
        # Log
        # ----------------------------------------------------

        print(
            f"RESULTADO: ESI {nivel}"
        )

        if confianza is not None:

            print(
                f"CONFIANZA: "
                f"{confianza:.2f}%"
            )

        print("=" * 70)
        print()

        # ----------------------------------------------------
        # Respuesta
        # ----------------------------------------------------

        return {

            "success": True,

            "model": modelo_sat.name,

            "model_id": modelo_sat.id,

            "model_version":
                modelo_sat.version,

            "model_type":
                modelo_sat.algorithm,

            "model_file":
                modelo_sat.file,

            "triage_level":
                nivel,

            "triage_acuity":
                nivel,

            "confidence":
                (
                    round(
                        confianza,
                        2
                    )
                    if confianza is not None
                    else None
                ),

            "probabilities":
                probabilidades,

            "classes":
                clases,

            "justification":
                justificacion
        }

    except HTTPException:

        raise

    except Exception as e:

        print()
        print("=" * 70)
        print("ERROR EN PREDICCIÓN")
        print("=" * 70)

        traceback.print_exc()

        print("=" * 70)
        print()

        raise HTTPException(
            status_code=500,
            detail={
                "error":
                    "Error durante "
                    "la predicción",

                "message":
                    str(e)
            }
        )


# ============================================================
# LISTAR MODELOS
# ============================================================

@app.get("/api/models")
async def listar_modelos():

    modelos = []

    for modelo_sat in MODELOS.values():

        modelos.append({

            "id":
                modelo_sat.id,

            "name":
                modelo_sat.name,

            "version":
                modelo_sat.version,

            "algorithm":
                modelo_sat.algorithm,

            "target":
                modelo_sat.target,

            "description":
                modelo_sat.description,

            "file":
                modelo_sat.file,

            "model_loaded":
                modelo_sat.loaded,

            "feature_count":
                len(
                    modelo_sat.feature_names
                ),

            "preprocessing":
                modelo_sat.preprocessing,

            "error":
                modelo_sat.error
        })

    return {

        "success": True,

        "default_model":
            MODELO_DEFAULT,

        "models":
            modelos,

        "count":
            len(modelos)
    }


# ============================================================
# INFORMACIÓN DEL MODELO
# ============================================================

@app.get("/api/model-info")
async def model_info(
    model: Optional[str] = None
):

    modelo_sat = obtener_modelo(
        model
    )

    return modelo_sat.info()


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
async def health():

    return {

        "status":
            "ok",

        "system":
            "S.A.T.",

        "version":
            "1.3.0",

        "models_registered":
            len(MODELOS),

        "models_loaded":
            sum(
                1
                for modelo in MODELOS.values()
                if modelo.loaded
            ),

        "default_model":
            MODELO_DEFAULT,

        "models": {

            model_id: {

                "name":
                    modelo_sat.name,

                "algorithm":
                    modelo_sat.algorithm,

                "loaded":
                    modelo_sat.loaded,

                "error":
                    modelo_sat.error

            }

            for model_id, modelo_sat
            in MODELOS.items()
        }
    }


# ============================================================
# ROOT INFO
# ============================================================

@app.get("/api")
async def api_info():

    return {

        "name":
            "S.A.T.",

        "version":
            "1.3.0",

        "description":
            "Sistema Automático de "
            "Triaje con múltiples modelos",

        "endpoint_prediction":
            "/predecir",

        "endpoint_models":
            "/api/models",

        "endpoint_model_info":
            "/api/model-info",

        "endpoint_health":
            "/api/health",

        "default_model":
            MODELO_DEFAULT,

        "available_models":
            list(MODELOS.keys())
    }


# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )