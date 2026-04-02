import os
from pathlib import Path

from cryptography.fernet import Fernet


def get_or_generate_fernet_key() -> str:
    env_key = os.environ.get("FERNET_KEY")
    if env_key:
        return env_key

    key_path = Path("data/fernet.key")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()

    generated = Fernet.generate_key().decode("utf-8")
    key_path.write_text(generated, encoding="utf-8")
    return generated


def _fernet() -> Fernet:
    key = get_or_generate_fernet_key()
    return Fernet(key.encode("utf-8"))


def encrypt(plain: str) -> str:
    return _fernet().encrypt((plain or "").encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def mask_student_id(student_id: str) -> str:
    value = student_id or ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]
