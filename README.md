## SAT

Sistema de triaje hospitalario asistido por IA, clasificando pacientes según la escala **ESI** (Emergency Severity Index, niveles 1-5). Corre 100% **on-premise**: ningún dato de paciente sale de la red del hospital, la inferencia se hace localmente con un modelo **CatBoost** entrenado específicamente para triaje.

> **Historial de arquitectura:** el sistema arrancó con un LLM vía Ollama, migró a un modelo **XGBoost** propio, y finalmente a **CatBoost** (mejor resultado en la comparación cabeza a cabeza contra XGBoost, mismo split de validación). Ollama ya no es una dependencia del proyecto; XGBoost tampoco.

## Arquitectura

```
SAT/
├── Backend/     → API FastAPI: auth, clasificación (CatBoost), historial, auditoría
├── Frontend/    → Interfaz web (HTML/JS): login, vista del Triagista y vista del Médico
├── run.py       → Lanzador: levanta Backend + Frontend y abre el navegador
├── requieremnts.txt
├── Documento/   → Aqui ira La Documentacion del Proyecto
└── README.md
```

```
Backend/app/
├── auth.py, config.py, database.py, models.py, schemas.py, prompts.py, main.py
(En main.py → crea los usuarios iniciales: admin, triagista y médico)
├── routers/
│   ├── auth.py       → login, alta de usuarios
│   ├── cases.py       → flujo triagista → médico: enviar, cola, revisión, identificar anónimos, historial
│   ├── classify.py    → clasificación ESI
│   └── meta.py         → opciones válidas para el formulario (categorías del modelo)
└── ml/
    ├── model.py         → carga el modelo y arma la fila de features
    ├── narrative.py      → genera señales de alarma / tratamiento sugerido (basado en reglas, sin LLM)
    └── artifacts/
        └── triage_catboost_model.joblib
```

```
Frontend/
├── index.html      → login; redirige a la pantalla según el rol
├── triage.html     → vista del Triagista (formulario, clasificación, envío al médico, "Mis casos")
├── medico.html     → vista del Médico (cola por gravedad, detalle, revisión y recomendaciones)
├── css/styles.css  → tokens de color, tema claro/oscuro y componentes compartidos
└── js/common.js    → sesión, llamadas a la API y bloques de render compartidos
```

El Frontend nunca corre el modelo directamente: todo pasa por el Backend, que arma la fila de features, ejecuta la clasificación, y persiste cada resultado para trazabilidad.

```
Triagista / Médico (navegador, login con JWT)
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

### Arranque rápido

Desde la raíz del proyecto, una vez hecha la configuración del Backend (paso 1):

```powershell
python run.py              # Backend (:8000) + Frontend (:8080) y abre el navegador
python run.py --reload     # Backend con autorecarga (desarrollo)
python run.py --no-browser # no abre el navegador
```

`Ctrl+C` detiene ambos procesos. Si preferís levantarlos a mano, se necesitan **2 procesos en paralelo** (antes eran 3: Ollama ya no es necesario), cada uno en su terminal, como se detalla abajo.

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

La primera vez crea las tablas y siembra un usuario Administrador (usuario/contraseña definidos en `.env`) **solo si la tabla de usuarios está vacía**. Documentación interactiva: http://localhost:8000/docs

**Usuarios iniciales.** Para crear además un Triagista y un Médico de prueba, corré una vez (con el venv activo, desde `Backend/`):

```powershell
python seed_users.py
```

Crea `admin` (credenciales del `.env`), `triagista1` y `medico1` (contraseña `cambiar123`, **cambiarla antes de un uso real**). Es idempotente: no duplica usuarios existentes. Para dar de alta más usuarios, el Administrador usa `POST /api/auth/users` desde `/docs`.

> **Cambios de esquema:** el proyecto todavía no usa Alembic. Si cambian los modelos, hay que borrar `triageai.db` (se recrea al arrancar) y volver a correr `seed_users.py`, o escribir un `ALTER TABLE`.

Detalle completo de la API en [`Backend/README.md`](Backend/README.md).

### 2. Frontend

```powershell
cd Frontend
python -m http.server 8080
```

Abrir **http://localhost:8080/index.html** (no abrir el archivo directamente con `file://`, y usar `localhost` y no `127.0.0.1` — el CORS del backend solo permite `http://localhost:8080`). Pide login contra el Backend y lleva a cada usuario a su pantalla según el rol.

## Roles

El flujo de trabajo se centra en dos roles: **Triagista** y **Médico**.

| Rol | Puede |
|---|---|
| `triagista` | Cargar el caso (con nombre o anónimo), ver la clasificación del modelo, proponer su nivel ESI con una nota y enviarlo al médico; ver el estado y el veredicto de sus casos; identificar casos anónimos |
| `medico` | Ver la cola de casos pendientes (más graves primero), revisar los tres niveles ESI (modelo, triagista, propio), confirmar o cambiar el nivel y dejar recomendaciones para el paciente |
| `administrador` | Gestionar usuarios y ver el historial completo |
Roles a Implementar a futuro:
| `jefe_enfermeria` | Ver el historial completo (sin pantalla propia todavía) |
| `auditor_clinico` | Solo lectura, para trazabilidad (sin pantalla propia todavía) |

## Flujo de trabajo

```
Triagista                      Modelo CatBoost                Médico
─────────                      ───────────────                ──────
Carga datos (con nombre
o anónimo)              ──►    Sugiere ESI + confianza
Propone su ESI + nota   ──►    estado: pendiente_medico  ──►  Ve la cola, abre el caso
                                                              ¿Coincide el ESI? Sí / No
Ve el veredicto         ◄──    estado: revisado          ◄──  Deja recomendaciones
```

- Cada caso guarda **tres niveles ESI**: el del modelo, el del triagista y el final del médico. Sirve para medir cuánto acierta el modelo y cuánto se corrige.
- Estados de una clasificación: `en_triaje` (el modelo clasificó, aún sin enviar), `pendiente_medico` y `revisado`.
- **Casos anónimos:** si no se completan nombre ni apellido, el caso se registra como anónimo con un código `ANON-AAAAMMDD-NNNN`. No se guarda ningún nombre, y puede identificarse después sin perder el código original.
- Si el médico cambia el nivel ESI, debe explicar el motivo en el comentario.

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

- [x] Backend funcional: auth por rol, clasificación vía CatBoost local, flujo triagista → médico, historial persistente
- [x] Frontend migrado para hablar con el Backend (login JWT real, formulario ampliado con campos clínicos para el modelo)
- [x] Frontend separado por rol: login, vista del Triagista y vista del Médico
- [x] Casos anónimos automáticos (sin nombre) con identificación posterior
- [x] Lanzador `run.py` y script de usuarios iniciales `seed_users.py`
- [x] Migración de Ollama a XGBoost, y luego de XGBoost a CatBoost: sin dependencia de LLM ni GPU para clasificar
- [x] `age_group`, `site_id` y las categorías de dolor/motivo confirmadas contra el dataset real de entrenamiento
- [x] Traducción al español de las categorías de `pain_location` y `chief_complaint_system`
- [x] Simplificar roles a Triagista / Médico
- [ ] Historial de paciente reincidente (buscar visitas previas por nombre/DNI)
- [ ] "Tomar caso" en la vista del Médico, para evitar que dos médicos revisen el mismo paciente
- [ ] Actualizar `Backend/README.md` con los endpoints nuevos (`/submit`, `/review`, `/queue`, `/mine`, `/identify`)
- [ ] Alojar localmente las fuentes (hoy se cargan desde Google Fonts, y sin internet caen a la fuente del sistema)
- [ ] Panel de administración de usuarios en el Frontend (hoy se gestiona por `/docs`)
- [ ] Confirmar el supuesto de "aire ambiente" usado en el cálculo de `news2_score` contra el pipeline de entrenamiento
- [ ] Capturar los campos administrativos hoy diferidos (modo de llegada, cobertura, visitas previas) cuando exista el módulo de admisión
- [ ] Incorporar señal del texto libre del motivo de consulta al modelo (vectorización) para mejorar el accuracy
- [ ] Migraciones de base de datos con Alembic

## Seguridad y privacidad

- Toda la inferencia y persistencia ocurre en la red local del hospital — ya no hay ninguna llamada a un servicio de IA externo ni a un proceso separado, el modelo se carga en memoria del propio proceso del Backend.
- Autenticación JWT con expiración de 8 horas por turno.
- `SECRET_KEY` debe generarse de forma única por instalación (`python -c "import secrets; print(secrets.token_hex(32))"`) y nunca commitearse — vive solo en `.env`, que está en `.gitignore`.