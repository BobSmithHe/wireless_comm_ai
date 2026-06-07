from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ...core.config import get_db
from ...schemas.user import (
    UserRegisterRequest, UserLoginRequest, TokenRefreshRequest,
    UserResponse, TokenResponse,
)
from ...services.auth_service import AuthService
from ..deps import get_current_user, get_auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(
    req: UserRegisterRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    user, error = auth_service.register(db, req.username, req.email, req.password)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    req: UserLoginRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    tokens, error = auth_service.login(db, req.username, req.password)
    if error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)
    return tokens


@router.post("/refresh", response_model=dict)
def refresh(
    req: TokenRefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    tokens, error = auth_service.refresh_token(req.refresh_token)
    if error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)
    return tokens


@router.get("/me", response_model=UserResponse)
def get_me(user=Depends(get_current_user)):
    return user
