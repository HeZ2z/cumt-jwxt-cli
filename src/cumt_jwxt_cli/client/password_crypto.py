"""RSA password encryption for the JWXT login form.

The JWXT login page encrypts the password client-side with the public key from
``/xtgl/login_getPublicKey.html`` before submitting it. This module reproduces
that RSA PKCS#1 v1.5 encryption so the plaintext password is not posted as-is.
"""

from __future__ import annotations

import base64
import os

from cumt_jwxt_cli.errors import AuthError


def encrypt_password(password: str, modulus_b64: str, exponent_b64: str) -> str:
    """Encrypt *password* with RSA PKCS#1 v1.5 and return base64 ciphertext."""

    try:
        modulus = int.from_bytes(base64.b64decode(modulus_b64, validate=True), "big")
        exponent = int.from_bytes(base64.b64decode(exponent_b64, validate=True), "big")
    except (ValueError, TypeError) as exc:
        raise AuthError("JWXT public key was not valid base64.") from exc

    if modulus <= 0 or exponent <= 0:
        raise AuthError("JWXT public key was invalid.")

    key_size = (modulus.bit_length() + 7) // 8
    message = password.encode("utf-8")
    if len(message) > key_size - 11:
        raise AuthError("Password is too long for the JWXT public key.")

    padding_length = key_size - len(message) - 3
    padding = bytearray()
    while len(padding) < padding_length:
        byte = os.urandom(1)[0]
        if byte != 0:
            padding.append(byte)

    encoded = b"\x00\x02" + bytes(padding) + b"\x00" + message
    cipher = pow(int.from_bytes(encoded, "big"), exponent, modulus)
    return base64.b64encode(cipher.to_bytes(key_size, "big")).decode("ascii")
