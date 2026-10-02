from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, RoleEnum
from app.schemas import Token, UserCreate, UserOut
from app.auth import authenticate_user, create_access_token, hash_password, require_roles

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.username, "role": user.role.value})
    return Token(access_token=token, role=user.role, username=user.username)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(RoleEnum.administrador)),
):
    """Solo el Administrador puede dar de alta usuarios (Triagista, Médico de guardia, etc.)."""
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "Ese nombre de usuario ya existe")
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(RoleEnum.administrador)),
):
    return db.query(User).all()
