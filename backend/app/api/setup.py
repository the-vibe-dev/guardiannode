"""First-run setup endpoints (status + recovery code generation)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_dep
from app.db.models import User
from app.services.parent_auth import generate_recovery_code

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupStatus(BaseModel):
    completed: bool
    admin_exists: bool


@router.get("/status", response_model=SetupStatus)
def status(db: Session = Depends(get_db_dep)):
    admin = db.query(User).filter(User.role == "admin").first()
    return SetupStatus(completed=admin is not None, admin_exists=admin is not None)


class RecoveryCodeResponse(BaseModel):
    words: list[str]
    code: str
    word_count: int


@router.post("/recovery", response_model=RecoveryCodeResponse)
def get_recovery_code():
    """Generate a fresh recovery code candidate for the parent to write down.

    The parent must POST the same code text back to /auth/setup to finalize
    setup. This endpoint never stores anything — it's the parent's responsibility
    to record the code.
    """
    rc = generate_recovery_code(12)
    return RecoveryCodeResponse(words=rc.words, code=rc.as_string(), word_count=len(rc.words))
