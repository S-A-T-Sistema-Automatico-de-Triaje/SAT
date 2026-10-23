## SAT

Sistema de triaje hospitalario asistido por IA, clasificando pacientes según la escala **ESI** (Emergency Severity Index, niveles 1-5). Corre 100% **on-premise**: ningún dato de paciente sale de la red del hospital, la inferencia se hace localmente con un modelo **CatBoost** entrenado específicamente para triaje.

> **Historial de arquitectura:** el sistema arrancó con un LLM vía Ollama, migró a un modelo **XGBoost** propio, y finalmente a **CatBoost** (mejor resultado en la comparación cabeza a cabeza contra XGBoost, mismo split de validación). Ollama ya no es una dependencia del proyecto; XGBoost tampoco.

## Arquitectura

```
SAT/
├── Backend/     → API FastAPI: auth, clasificación (CatBoost), historial, auditoría
├── Frontend/    → Interfaz web (HTML/JS): login, vista del Triagista y vista del Médico
├── run.py       → Lanzador: levanta Backend + Frontend e imprime el link (no abre el navegador)
├── requieremnts.txt
├── Documento/   → Aqui ira La Documentacion del Proyecto
└── README.md
```

```
Backend/app/
├── security.py (hash, JWT, require_roles; antes auth.py), config.py, database.py, models.py, schemas.py, prompts.py, main.py
(En main.py → crea los usuarios iniciales que falten —admin, triagista y médico— y migra la columna cases.dni)
├── routers/
│   ├── auth.py       → login, alta de usuarios
│   ├── cases.py       → flujo triagista → médico: enviar, cola, revisión, identificar anónimos, historial
│   ├── classify.py    → clasificación ESI (valida y guarda el DNI opcional)
│   ├── patients.py    → pacientes por DNI: autocompletado, ficha, historial, buscador, listados, cargar DNI a casos viejos
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
├── triage.html     → vista del Triagista (formulario, clasificación, envío al médico; barra Inicio / Listado / Buscar)
├── medico.html     → vista del Médico (pestañas Pendientes / Revisados, buscador, ficha del paciente, revisión y recomendaciones)
├── css/styles.css  → tokens de color, tema claro/oscuro y componentes compartidos
└── js/common.js    → sesión, llamadas a la API, formato de DNI/fechas y la ficha de paciente compartida (la usan ambas vistas)
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
python run.py              # Backend (:8000) + Frontend (:8080); al terminar imprime el link para abrirlo a mano
python run.py --reload     # Backend con autorecarga (desarrollo)
```

Al arrancar muestra los mensajes de cada proceso (útil para detectar errores) y al final el link `http://localhost:8080/index.html`: se abre a mano en el navegador, no se abre solo. `Ctrl+C` detiene ambos procesos. Si preferís levantarlos a mano, se necesitan **2 procesos en paralelo** (antes eran 3: Ollama ya no es necesario), cada uno en su terminal, como se detalla abajo.

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

Al arrancar crea las tablas y los usuarios iniciales que falten (ver abajo). Documentación interactiva: http://localhost:8000/docs

**Usuarios iniciales.** `main.py` los crea solos al arrancar si no existen: `admin` (credenciales del `.env`), `triagista1` y `medico1`. Si preferís hacerlo a mano, también sirve (con el venv activo, desde `Backend/`):

```powershell
python seed_users.py
```

Crea `admin` (credenciales del `.env`), `triagista1` y `medico1` (contraseña `cambiar123`, **cambiarla antes de un uso real**). Es idempotente: no duplica usuarios existentes. Para dar de alta más usuarios, el Administrador usa `POST /api/auth/users` desde `/docs`.

> **Cambios de esquema:** el proyecto todavía no usa Alembic. La columna `cases.dni` se agrega sola a bases existentes al arrancar (`_migrate_add_dni` en `main.py`), sin borrar `triageai.db`. Para otros cambios de modelos hay que borrar la base (se recrea al arrancar) o escribir un `ALTER TABLE`.

Los endpoints están documentados abajo, en la sección [API](#api), y de forma interactiva en http://localhost:8000/docs.

### 2. Frontend

```powershell
cd Frontend
python -m http.server 8080
```

Abrir **http://localhost:8080/index.html** (no abrir el archivo directamente con `file://`, y usar `localhost` y no `127.0.0.1` — el CORS del backend solo permite `http://localhost:8080`). Pide login contra el Backend y lleva a cada usuario a su pantalla según el rol.

## API

Todos los endpoints (salvo el login y `/api/health`) requieren `Authorization: Bearer <token>`. Abajo, quién puede usar cada uno. La referencia interactiva con los esquemas completos está en `/docs`.

**General**

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `GET /api/health` | público | Estado del servicio |
| `/api/auth/*` | — | Login y alta de usuarios (`POST /api/auth/users`, solo administrador) |
| `GET /api/meta/form-options` | autenticado | Categorías válidas para el formulario (dolor, estado mental, motivo, comorbilidades) |
| `POST /api/classify` | triagista | Guarda el caso y lo clasifica con CatBoost. Valida el DNI opcional (6-10 dígitos; los anónimos no lo guardan). Devuelve `case_id`, `classification_id` y el resultado |

**Casos** (`/api/cases`)

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `GET /queue?include_reviewed=false&limit=100` | médico, admin | Cola del médico: pendientes primero, más grave arriba y luego más antiguo |
| `GET /mine?limit=50` | triagista | Casos cargados por el triagista, con su estado y el veredicto |
| `GET /` | admin, auditor, jefe de enfermería | Todos los casos, del más reciente al más antiguo |
| `GET /{id}` | triagista (solo los suyos), médico, admin, auditor, jefe | Detalle: datos del paciente, resultado del modelo, nota del triagista y revisión médica |
| `POST /{id}/submit` | triagista (solo los suyos) | Propone su ESI con una nota y envía el caso al médico (`pendiente_medico`) |
| `POST /{id}/review` | médico | Confirma o cambia el ESI y deja recomendaciones (`revisado`). Si cambia el nivel, el comentario es obligatorio |
| `PATCH /{id}/identify` | triagista (solo los suyos), médico | Completa nombre y apellido de un caso anónimo; conserva el `anon_code` |

`{id}` es siempre el `classification_id`. Un caso ya revisado no se puede volver a enviar ni a revisar (409).

**Pacientes por DNI** (`/api/patients`)

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `GET /lookup?dni=` | triagista | Autocompletado al escribir el DNI: datos básicos y cantidad de visitas |
| `GET /record/{dni}` | triagista, médico, admin | Ficha completa: datos, estadísticas, resumen clínico y todas las visitas |
| `GET /search?q=` | triagista, médico, admin | Busca por DNI (desde 3 dígitos) o por nombre (desde 3 letras), solo entre pacientes con DNI |
| `GET /list?limit=200` | triagista, médico, admin | Todos los pacientes con DNI, del más reciente al más antiguo (máx. 500) |
| `GET /reviewed` | médico, admin | Pacientes con al menos un caso revisado, y aparte los revisados sin DNI |
| `GET /by-case/{id}/history` | médico, admin | Visitas previas del paciente del caso que se está revisando |
| `PATCH /by-case/{id}/dni` | triagista (solo sus casos), médico, admin | Carga el DNI a un caso que no lo tiene. Si ya tiene uno distinto, solo el administrador lo corrige; los anónimos devuelven 409 |

## Roles

El flujo de trabajo se centra en dos roles: **Triagista** y **Médico**.

| Rol | Puede |
|---|---|
| `triagista` | Cargar el caso (con nombre o anónimo, DNI opcional con autocompletado), ver la clasificación del modelo, proponer su nivel ESI con una nota y enviarlo al médico; ver el estado y el veredicto de sus casos ("Mis casos"); identificar casos anónimos; buscar pacientes, ver el listado y la ficha completa de cualquier paciente con DNI; cargar el DNI a casos propios anteriores |
| `medico` | Ver la cola de casos pendientes (más graves primero), revisar los tres niveles ESI (modelo, triagista, propio), confirmar o cambiar el nivel y dejar recomendaciones; ver la lista de pacientes revisados, buscar por DNI o nombre y abrir la ficha con todo el historial; cargar el DNI a casos sin DNI |
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

## Historial de pacientes (por DNI)

- El **DNI es opcional** y es lo único que vincula visitas de un mismo paciente: se normaliza a dígitos (6-10). Los **casos anónimos nunca guardan DNI**. La búsqueda por nombre solo ayuda a encontrar el DNI y nunca fusiona historias (los homónimos son frecuentes).
- **Triagista:** al escribir un DNI ya registrado se autocompletan nombre, apellido, edad, sexo, peso y altura y aparece la ficha con el historial. Barra superior: **⌂ Inicio** (limpia formulario y panel), **☰ Listado** (pestañas "Todos los pacientes" / "Mis casos", solo se muestra al tocarlo) y **buscador** por DNI (desde 3 dígitos) o nombre.
- **Médico:** pestañas **Pendientes** y **Revisados**. En Revisados la lista muestra solo nombre y DNI, ordenable **A–Z** (por apellido) o por **DNI**; los revisados sin DNI aparecen aparte. A la derecha, los datos principales del paciente (alergias, comorbilidades, medicación, antecedentes) y todas sus fichas de visitas, con botones **⌂ Inicio** y **Comprimir / Expandir fichas**. Al revisar un caso se ve el historial previo del paciente.
- **Casos viejos sin DNI:** se les puede cargar el DNI desde la vista (no hace falta borrarlos). Un triagista solo puede hacerlo en casos propios; si ya tienen un DNI distinto, solo el administrador lo corrige.
- **Privacidad:** el triagista ve la ficha completa (incluidas las recomendaciones del médico) de cualquier paciente con DNI. Cada consulta queda en el log `triageai.audit` con el DNI enmascarado (`***XXX`).
- Endpoints (`/api/patients`): `GET /lookup`, `GET /record/{dni}`, `GET /search?q=`, `GET /list`, `GET /reviewed` (solo médico), `GET /by-case/{id}/history` (solo médico), `PATCH /by-case/{id}/dni`.

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
- [x] Historial de paciente reincidente (DNI opcional con autocompletado, ficha, buscador, listado, carga de DNI a casos viejos)
- [x] Vista del Triagista con Inicio / Listado / Buscar y vista del Médico con pestaña Revisados (A–Z / por DNI, fichas comprimibles)
- [x] Comorbilidades como desplegable en el formulario del triagista
- [x] `run.py` sin apertura automática del navegador
- [x] Endpoints documentados en este README (sección API), sin `Backend/README.md` aparte
- [ ] "Tomar caso" en la vista del Médico, para evitar que dos médicos revisen el mismo paciente
- [ ] Probar `/api/patients/search`, `/list` y `/reviewed` contra la base real (se verificaron con un backend simulado)
- [ ] Marcar en la cola del médico las reconsultas (paciente que ya vino antes)
- [ ] Unificar las etiquetas de comorbilidades (algunas se muestran en inglés en el resumen del paciente)
- [ ] Tabla propia de pacientes (hoy el paciente se deduce de los casos por DNI)
- [ ] Alojar localmente las fuentes (hoy se cargan desde Google Fonts, y sin internet caen a la fuente del sistema)
- [ ] Panel de administración de usuarios en el Frontend (hoy se gestiona por `/docs`)
- [ ] Confirmar el supuesto de "aire ambiente" usado en el cálculo de `news2_score` contra el pipeline de entrenamiento
- [ ] Capturar los campos administrativos hoy diferidos (modo de llegada, cobertura, visitas previas) cuando exista el módulo de admisión
- [ ] Incorporar señal del texto libre del motivo de consulta al modelo (vectorización) para mejorar el accuracy
- [ ] Migraciones de base de datos con Alembic

## Seguridad y privacidad

- Toda la inferencia y persistencia ocurre en la red local del hospital — ya no hay ninguna llamada a un servicio de IA externo ni a un proceso separado, el modelo se carga en memoria del propio proceso del Backend.
- Autenticación JWT con expiración de 8 horas por turno.
- Acceso a datos de pacientes (búsqueda, listados, fichas) restringido por rol y registrado en el log de auditoría con el DNI enmascarado.
- `SECRET_KEY` debe generarse de forma única por instalación (`python -c "import secrets; print(secrets.token_hex(32))"`) y nunca commitearse — vive solo en `.env`, que está en `.gitignore`.