import base64
import json
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
import hmac


MANILA_TZ = ZoneInfo("Asia/Manila")


def format_datetime(dt: datetime | None = None) -> str:
    """Format datetime in Manila timezone as 'yyyyMMddHHmmss' per BIR EIS spec."""
    if dt is None:
        dt = datetime.now(MANILA_TZ)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=MANILA_TZ)
    else:
        dt = dt.astimezone(MANILA_TZ)
    return dt.strftime("%Y%m%d%H%M%S")


def generate_auth_key() -> str:
    """Generate a fresh 32-character random auth secret key per authorization request.

    Fixes the Node.js singleton bug where authKey became stale or shared.
    """
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#$%^&*()"
    return "".join(secrets.choice(chars) for _ in range(32))


def _wrap_pem_public(public_key_str: str) -> bytes:
    """Wrap raw base64 public key in PEM headers if not already formatted."""
    cleaned = public_key_str.strip()
    if "-----BEGIN PUBLIC KEY-----" in cleaned:
        return cleaned.encode("utf-8")
    lines = [cleaned[i : i + 64] for i in range(0, len(cleaned), 64)]
    pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"
    return pem.encode("utf-8")


def _wrap_pem_private(private_key_str: str) -> bytes:
    """Wrap raw base64 private key in PEM headers if not already formatted."""
    cleaned = private_key_str.strip()
    if "-----BEGIN" in cleaned and "PRIVATE KEY-----" in cleaned:
        return cleaned.encode("utf-8")
    lines = [cleaned[i : i + 64] for i in range(0, len(cleaned), 64)]
    pem = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"
    return pem.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    """Encode bytes into unpadded Base64URL string (RFC 7515)."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def rsa_encrypt(plain_text: str, public_key_b64: str) -> str:
    """Encrypt plaintext string using BIR RSA public key with PKCS#1 v1.5 padding.

    BIR EIS API Guide Section 7.1.2, Page 30 specifies PKCS#1 v1.5 padding.
    Returns Base64-encoded ciphertext string.
    """
    pem_bytes = _wrap_pem_public(public_key_b64)
    public_key = load_pem_public_key(pem_bytes)

    ciphertext = public_key.encrypt(
        plain_text.encode("utf-8"),
        asym_padding.PKCS1v15(),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def aes_encrypt(plain_text: str, key: str) -> str:
    """Encrypt plaintext string using AES-CBC with PKCS7 padding.

    Key: session key or temporary auth key.
    IV: First 16 characters of the key (per BIR Guide & Node.js reference implementation).
    Returns Base64-encoded ciphertext string.
    """
    key_bytes = key.encode("utf-8")
    iv_bytes = key[:16].encode("utf-8")

    # Ensure key is valid AES key length (16, 24, or 32 bytes)
    if len(key_bytes) not in (16, 24, 32):
        # Truncate or pad to 32 bytes for AES-256
        key_bytes = key_bytes[:32].ljust(32, b"\0")

    padder = sym_padding.PKCS7(128).padder()
    padded_data = padder.update(plain_text.encode("utf-8")) + padder.finalize()

    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    return base64.b64encode(ciphertext).decode("ascii")


def aes_decrypt(ciphertext_b64: str, key: str) -> str:
    """Decrypt Base64-encoded ciphertext string using AES-CBC with PKCS7 unpadding.

    Key: session key or temporary auth key.
    IV: First 16 characters of the key.
    Returns decrypted UTF-8 string.
    """
    ciphertext = base64.b64decode(ciphertext_b64)
    key_bytes = key.encode("utf-8")
    iv_bytes = key[:16].encode("utf-8")

    if len(key_bytes) not in (16, 24, 32):
        key_bytes = key_bytes[:32].ljust(32, b"\0")

    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = sym_padding.PKCS7(128).unpadder()
    plain_bytes = unpadder.update(padded_data) + unpadder.finalize()

    return plain_bytes.decode("utf-8")


def hmac_sign(value: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature encoded as Base64 string (NOT hex).

    BIR Guide Section 7.1, Page 29: Signature format is Base64 string.
    """
    sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=value.encode("utf-8"),
        digestmod="sha256",
    ).digest()
    return base64.b64encode(sig).decode("ascii")


def jws_sign(payload_json_str: str, private_key_b64: str, key_id: str) -> str:
    """Generate compact RS256 JWS (header.payload.signature) for a validated invoice.

    BIR Guide Section 7.2.2, Page 35: Compact serialization with RS256.
    Header: {"alg": "RS256", "kid": key_id}
    """
    header_json = json.dumps({"alg": "RS256", "kid": key_id}, separators=(",", ":"))
    header_b64 = _b64url_encode(header_json.encode("utf-8"))
    payload_b64 = _b64url_encode(payload_json_str.encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    pem_bytes = _wrap_pem_private(private_key_b64)
    private_key = load_pem_private_key(pem_bytes, password=None)

    signature = private_key.sign(
        signing_input,
        asym_padding.PKCS1v15(),
        hashes.SHA256(),
    )
    sig_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"
