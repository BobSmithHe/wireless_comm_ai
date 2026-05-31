from sqlalchemy.orm import Session
from ..database.models import User
from ..config.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from ..utils.logger import logger


class AuthService:
    def register(self, db: Session, username: str, email: str, password: str) -> tuple[User | None, str | None]:
        existing = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            if existing.username == username:
                return None, "Username already taken"
            return None, "Email already registered"

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"User registered: {username}")
        return user, None

    def login(self, db: Session, username: str, password: str) -> tuple[dict | None, str | None]:
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            return None, "Invalid username or password"
        if not user.is_active:
            return None, "Account is disabled"

        tokens = {
            "access_token": create_access_token({"sub": str(user.id)}),
            "refresh_token": create_refresh_token({"sub": str(user.id)}),
            "token_type": "bearer",
        }
        logger.info(f"User logged in: {username}")
        return tokens, None

    def refresh_token(self, refresh_token: str) -> tuple[dict | None, str | None]:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None, "Invalid or expired refresh token"

        new_tokens = {
            "access_token": create_access_token({"sub": payload["sub"]}),
            "token_type": "bearer",
        }
        return new_tokens, None

    def get_current_user(self, db: Session, token: str) -> User | None:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == int(user_id)).first()
