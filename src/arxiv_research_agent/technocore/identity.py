"""Encrypted Ed25519 identity and did:key support for Technocore."""

import base64
import os
import re
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MULTICODEC_ED25519 = b"\xed\x01"
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
NONCE_RE = re.compile(r"^[0-9]{1,19}$")


class IdentityError(ValueError):
    pass


def _base58btc(raw: bytes) -> str:
    leading_zeroes = len(raw) - len(raw.lstrip(b"\0"))
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = B58[remainder] + encoded
    return (B58[0] * leading_zeroes) + encoded


def did_from_private_key(key: Ed25519PrivateKey) -> str:
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "did:key:z" + _base58btc(MULTICODEC_ED25519 + public)


def sweep_text(text: str, limit: int = 4096) -> str:
    cleaned = "".join(
        " " if unicodedata.category(char) in INVISIBLE_CATEGORIES else char
        for char in text
    ).strip()
    if not cleaned:
        raise IdentityError("message is empty after Technocore single-line sweep")
    if len(cleaned) > limit:
        raise IdentityError(
            "message is %d characters; Technocore limit is %d" % (len(cleaned), limit)
        )
    return cleaned


def create_identity(path: Path, passphrase: str) -> str:
    if len(passphrase) < 12:
        raise IdentityError("identity passphrase must be at least 12 characters")
    if path.exists():
        raise IdentityError("identity already exists: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(pem)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return did_from_private_key(key)


def load_identity(path: Path, passphrase: str) -> Ed25519PrivateKey:
    if not path.exists():
        raise IdentityError("identity does not exist: %s" % path)
    try:
        key = serialization.load_pem_private_key(
            path.read_bytes(), password=passphrase.encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise IdentityError("could not decrypt identity") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise IdentityError("identity is not an Ed25519 private key")
    return key


def sign_message(
    key: Ed25519PrivateKey, room: str, nonce: str, text: str, limit: int = 4096
) -> tuple:
    if not ROOM_RE.fullmatch(room):
        raise IdentityError("invalid Technocore room name")
    if not NONCE_RE.fullmatch(nonce):
        raise IdentityError("nonce must contain 1-19 ASCII digits")
    cleaned = sweep_text(text, limit)
    canonical = "%s|%s|%s" % (room, nonce, cleaned)
    signature = base64.urlsafe_b64encode(
        key.sign(canonical.encode("utf-8"))
    ).decode("ascii").rstrip("=")
    return did_from_private_key(key), signature, cleaned
