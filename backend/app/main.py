from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine, SessionLocal
from app.config import settings
from app.models import User, RoleEnum
from app.auth import hash_password
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


@app.on_event("startup")
def on_startup():
    # Crea las tablas si no existen (para algo más robusto, migrar a Alembic más adelante)
    Base.metadata.create_all(bind=engine)

    # Siembra un usuario Administrador inicial si la tabla de usuarios está vacía,
    # para poder crear al resto de los usuarios (Triagista, Médico de guardia, etc.) desde /api/auth/users
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                username=settings.seed_admin_username,
                full_name="Administrador inicial",
                hashed_password=hash_password(settings.seed_admin_password),
                role=RoleEnum.administrador,
            )
            db.add(admin)
            db.commit()
            print(
                f"⚠️  Usuario admin creado: '{settings.seed_admin_username}' / "
                f"'{settings.seed_admin_password}' — CAMBIAR la contraseña cuanto antes."
            )
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "triageai-backend"}
