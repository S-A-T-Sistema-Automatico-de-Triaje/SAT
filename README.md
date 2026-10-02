# SAT

Sistema de triaje hospitalario asistido por IA, clasificando pacientes según la escala **ESI** (Emergency Severity Index, niveles 1-5). Corre 100% **on-premise**: ningún dato de paciente sale de la red del hospital, la inferencia se hace localmente con un modelo **CatBoost** entrenado específicamente para triaje.

> **Historial de arquitectura:** el sistema arrancó con un LLM vía Ollama, migró a un modelo **XGBoost** propio, y finalmente a **CatBoost** (mejor resultado en la comparación cabeza a cabeza contra XGBoost, mismo split de validación). Ollama ya no es una dependencia del proyecto; XGBoost tampoco.

## Arquitectura

```
SAT/
├── Backend/     → API FastAPI: auth, clasificación (CatBoost), historial, auditoría
├── Frontend/    → Interfaz web (HTML/JS) para Triagista
├── requieremnts.txt
├── Documento/   → Aqui ira La Documentacion del Proyecto
└── README.md
```

```
Backend/app/
├── auth.py, config.py, database.py, models.py, schemas.py, prompts.py, main.py
├── routers/
│   ├── auth.py       → login, alta de usuarios
│   ├── cases.py       → historial, confirmación/ajuste del triagista
│   ├── classify.py    → clasificación ESI
│   └── meta.py         → opciones válidas para el formulario (categorías del modelo)
└── ml/
    ├── model.py         → carga el modelo y arma la fila de features
    ├── narrative.py      → genera señales de alarma / tratamiento sugerido (basado en reglas, sin LLM)
    └── artifacts/
        └── triage_catboost_model.joblib
```

El Frontend nunca corre el modelo directamente: todo pasa por el Backend, que arma la fila de features, ejecuta la clasificación, y persiste cada resultado para trazabilidad.

```
Triagista (navegador, login con JWT)
        │  HTTP + JWT
        ▼
   Backend (FastAPI, :8000)
        │  carga en memoria
        ▼
   Modelo CatBoost (triage_catboost_model.joblib)
```

## Requisitos

- Python 3.11+
- Windows, Linux o macOS — ya **no hace falta GPU** ni Ollama instalado; CatBoost corre en CPU

## Puesta en marcha

Se necesitan **2 procesos corriendo en paralelo** (antes eran 3: Ollama ya no es necesario), cada uno en su propia terminal.

### 1. Backend

```powershell
cd Backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Editar `.env`:

```dotenv
DATABASE_URL=sqlite:///./triageai.db
SECRET_KEY=<generar con: python -c "import secrets; print(secrets.token_hex(32))">
SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD=<cambiar antes del primer uso real>
CATBOOST_MODEL_PATH=app/ml/artifacts/triage_catboost_model.joblib
SITE_ID=SITE-HEL-01   # ajustar al identificador real de esta instalación (ver Modelo de IA)
```

Colocar el modelo entrenado en `Backend/app/ml/artifacts/triage_catboost_model.joblib` (un `.joblib` con las claves `model`, `cat_features` y `feature_order`).

```powershell
uvicorn app.main:app --reload --port 8000
```

La primera vez crea las tablas y siembra un usuario Administrador (usuario/contraseña definidos en `.env`). Documentación interactiva: http://localhost:8000/docs

Detalle completo de la API en [`Backend/README.md`](Backend/README.md).

### 2. Frontend

```powershell
cd Frontend
python -m http.server 8080
```

Abrir **http://localhost:8080/triage_prototipo0.7.html** (no abrir el archivo directamente con `file://` — el CORS del backend solo permite `http://localhost:8080`). Pide login contra el Backend.

## Roles

| Rol | Puede |
|---|---|
| `triagista` | Ingresar el caso, ver la clasificación sugerida por el modelo, confirmar o ajustar el nivel ESI |
| `medico_guardia` | Ver el detalle completo del caso y la historia previa del paciente, confirmar si corresponde la prioridad asignada |
| `jefe_enfermeria` | Ver historial y métricas del turno |
| `administrador` | Gestionar usuarios |
| `auditor_clinico` | Solo lectura, para trazabilidad |

> Los roles están en revisión: se está evaluando simplificar el flujo a solo **Triagista** (sugiere prioridad) y **Médico** (revisa el caso completo, ve si el paciente ya vino antes, y confirma la prioridad).

## Modelo de IA

- **Modelo actual: CatBoost** (`CatBoostClassifier`, `loss_function="MultiClass"`), entrenado sobre el mismo dataset sintético estilo NHAMCS/KTAS que el XGBoost anterior (69 features), prediciendo `esi_level` (1-5) directamente. Elegido por mejor quadratic weighted kappa contra XGBoost en el mismo split de validación.
- El `.joblib` contiene tres claves: `model` (el clasificador), `cat_features` (lista de nombres de las 13 columnas categóricas) y `feature_order` (el orden exacto de columnas que espera el modelo). A diferencia de la versión XGBoost, **no hay `encoders`** — CatBoost maneja las categóricas de forma nativa, recibiendo el texto crudo (`"M"`, `"cardiovascular"`, etc.) en vez de un código numérico.
- **El texto libre (motivo de consulta en lenguaje natural) no se usa como feature** — el modelo solo consume datos estructurados (vitales, dolor, estado neurológico, antropometría, comorbilidades, categoría del motivo). Por eso el modo "texto libre" del Frontend está deshabilitado.
- Valores categóricos confirmados contra el dataset de entrenamiento (`train_clean.csv`):
  - `site_id`: `SITE-HEL-01`, `SITE-HEL-02`, `SITE-OUL-01`, `SITE-TMP-01`, `SITE-TUR-01` (con el prefijo `SITE-`)
  - `age_group`: `pediatric` (1-15), `young_adult` (16-39), `middle_aged` (40-64), `elderly` (65+)
  - `pain_location` (9): abdomen, back, chest, extremity, head, multiple, none, pelvis, unknown
  - `chief_complaint_system` (14): ENT, cardiovascular, dermatological, endocrine, gastrointestinal, genitourinary, infectious, musculoskeletal, neurological, ophthalmic, other, psychiatric, respiratory, trauma
  - El dataset de entrenamiento no tiene nulos en las columnas categóricas (sintético, completo).
- `/api/meta/form-options` expone las categorías válidas (dolor, estado mental, categoría del motivo, comorbilidades) para que el formulario nunca mande un valor fuera de catálogo. `pain_location` y `chief_complaint_system` quedan en inglés (tal cual el dataset) hasta que se agregue una traducción.
- Campos que **todavía no se capturan** (quedan con valor "desconocido" por ahora, pendientes de un futuro módulo de admisión): modo de llegada, idioma, tipo de cobertura, origen del traslado, visitas/internaciones previas, medicación activa.

## Estado del proyecto

- [x] Backend funcional: auth por rol, clasificación vía CatBoost local, confirmación del triagista, historial persistente
- [x] Frontend migrado para hablar con el Backend (login JWT real, formulario ampliado con campos clínicos para el modelo)
- [x] Migración de Ollama a XGBoost, y luego de XGBoost a CatBoost: sin dependencia de LLM ni GPU para clasificar
- [x] `age_group`, `site_id` y las categorías de dolor/motivo confirmadas contra el dataset real de entrenamiento
- [ ] Traducción al español de las categorías de `pain_location` y `chief_complaint_system` (hoy se muestran en inglés, tal cual las conoce el modelo)
- [ ] Simplificar roles a Triagista / Médico, con historial de paciente reincidente
- [ ] Panel de administración de usuarios en el Frontend (hoy se gestiona por `/docs`)
- [ ] Confirmar el supuesto de "aire ambiente" usado en el cálculo de `news2_score` contra el pipeline de entrenamiento
- [ ] Historial de sesión persistente entre recargas de página (hoy se resetea al refrescar el navegador; los casos sí quedan guardados en la base, pero el Frontend no los vuelve a traer)
- [ ] Capturar los campos administrativos hoy diferidos (modo de llegada, cobertura, visitas previas) cuando exista el módulo de admisión
- [ ] Incorporar señal del texto libre del motivo de consulta al modelo (vectorización) para mejorar el accuracy
- [ ] Migraciones de base de datos con Alembic

## Seguridad y privacidad

- Toda la inferencia y persistencia ocurre en la red local del hospital — ya no hay ninguna llamada a un servicio de IA externo ni a un proceso separado, el modelo se carga en memoria del propio proceso del Backend.
- Autenticación JWT con expiración de 8 horas por turno.
- `SECRET_KEY` debe generarse de forma única por instalación (`python -c "import secrets; print(secrets.token_hex(32))"`) y nunca commitearse — vive solo en `.env`, que está en `.gitignore`.