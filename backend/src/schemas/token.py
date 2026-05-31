from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: str  # user_id
    type: str  # "access" | "refresh"
    exp: int | None = None
