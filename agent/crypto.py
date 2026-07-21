"""Symmetric encryption for mail-account secrets at rest (Fernet)."""
import os
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("scambaiter.crypto")

_fernet: Fernet | None = None
_key_from_env: bool = False


def _get_fernet() -> Fernet:
    global _fernet, _key_from_env
    if _fernet is not None:
        return _fernet

    key = os.getenv("MAIL_ENCRYPTION_KEY", "").strip()
    if key:
        _key_from_env = True
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    else:
        _key_from_env = False
        _fernet = Fernet(Fernet.generate_key())
        logger.warning(
            "MAIL_ENCRYPTION_KEY is not set — generated an EPHEMERAL in-memory key. "
            "Stored mail secrets will NOT decrypt after a restart. "
            "Set MAIL_ENCRYPTION_KEY in .env "
            "(generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\")."
        )
    return _fernet


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a string to a Fernet token (str). None/empty passes through as None."""
    if not plaintext:
        return None
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(token: str | None) -> str | None:
    """Decrypt a Fernet token back to a string. None/empty passes through as None."""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Failed to decrypt a stored mail secret. The MAIL_ENCRYPTION_KEY may have "
            "changed or is missing; re-enter the account credentials."
        ) from exc


def encryption_configured() -> bool:
    """True only if MAIL_ENCRYPTION_KEY was explicitly provided via the environment."""
    _get_fernet()  # ensure initialized so _key_from_env is set
    return _key_from_env


def generate_key_for_env() -> str:
    """Helper: a fresh key string to paste into .env as MAIL_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode("utf-8")
