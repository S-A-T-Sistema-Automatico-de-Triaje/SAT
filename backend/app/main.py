from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine, SessionLocal
from app.config import settings
from app.models import RoleEnum, User
from app.security import hash_password
from app.routers import auth as auth_router
from app.routers import classify as classify_router
from app.routers import cases as cases_router
from app.routers import meta as meta_router

app = FastAPI(
    title="TriageAI Backend",
    description="API on-premise para clasificación ESI asistida por IA. Ningún dato sale de la red del hospital.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(classify_router.router)
app.include_router(cases_router.router)
app.include_router(meta_router.router)


# Usuarios iniciales: se crean al arrancar si no existen (solo los que falten).
# ⚠️ Contraseñas de DESARROLLO. Cambiarlas antes de un uso real.
DEMO_PASSWORD = "cambiar123"


def _initial_users():
    return [
        (settings.seed_admin_username, "Administrador inicial", settings.seed_admin_password, RoleEnum.administrador),
        ("triagista1", "Triagista de prueba", DEMO_PASSWORD, RoleEnum.triagista),
        ("medico1", "Médico de prueba", DEMO_PASSWORD, RoleEnum.medico_guardia),
    ]


@app.on_event("startup")
def on_startup():
    # Crea las tablas si no existen (para algo más robusto, migrar a Alembic más adelante)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        created = []
        for username, full_name, password, role in _initial_users():
            if not db.query(User).filter(User.username == username).first():
                db.add(User(
                    username=username,
                    full_name=full_name,
                    hashed_password=hash_password(password),
                    role=role,
                ))
                created.append(username)
        if created:
            db.commit()
            print(f"⚠️  Usuarios iniciales creados: {', '.join(created)} — CAMBIAR las contraseñas cuanto antes.")
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "triageai-backend"}