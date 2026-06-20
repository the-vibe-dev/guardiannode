"""Device pairing — 6-digit codes, hashed at rest, single-use, TTL'd."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from app.db.models import PairingCode
from app.db.session import begin_immediate_if_sqlite

_PH = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
_CODE_LENGTH = 6
_TTL_SECONDS = 600


def generate_code() -> str:
    digits = [str(secrets.randbelow(10)) for _ in range(_CODE_LENGTH)]
    return "".join(digits)


def issue(session: Session, *, ttl_seconds: int = _TTL_SECONDS) -> tuple[str, datetime]:
    code = generate_code()
    code_hash = _PH.hash(code)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    row = PairingCode(code_hash=code_hash, expires_at=expires_at, used=False)
    session.add(row)
    session.flush()
    return code, expires_at


def verify_and_consume(session: Session, code: str) -> bool:
    """Verify a code, mark it used. Returns True on success."""
    begin_immediate_if_sqlite(session)
    now = datetime.now(timezone.utc)
    rows = (
        session.query(PairingCode)
        .filter(PairingCode.used.is_(False), PairingCode.expires_at > now)
        .all()
    )
    for row in rows:
        try:
            if _PH.verify(row.code_hash, code):
                row.used = True
                row.used_at = now
                session.flush()
                return True
        except VerifyMismatchError:
            continue
        except Exception:
            continue
    return False
