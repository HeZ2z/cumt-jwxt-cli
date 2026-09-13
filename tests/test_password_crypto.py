"""RSA password encryption tests."""

import base64

import pytest

from cumt_jwxt_cli.client.password_crypto import encrypt_password
from cumt_jwxt_cli.errors import AuthError

# Fixed 1024-bit test keypair generated for these tests only; not a real key.
_MODULUS = (
    "eCwn0mXP2IgDQ0/Lq8lZI3HYl5lrUPGavJDQ9TB7EZPPbeTcEK55g2E4TWX1+gqs/+oK"
    "vR197kK2SBxKtOT/e+2UF0BjUeg5q5YvaroW+uN0bDM+QZk8tKSEXdiZQsjCSROQye4x"
    "sNfS6WYWsi3eQFy4V1VGxKFOKyp5P5J6QHE="
)
_EXPONENT = "AQAB"
_PRIVATE_D = (
    "HRIheAZlJ26Py4LMNHx68dYinVnh2iz4T9GAmy/lNbVaIq2QhwCOKLgmFKMrxBc9"
    "DpOhkWpHApJk4kDl2ajkHNIMQBdUHHy1ynbSrtvEa2K7hD/isoXcJkZHDwmlzQSOTWT"
    "A6+bLwKh5DxnzIDMuwhJ0GEJ1h8JwZZKTeBCv2iE="
)


def _decrypt(ciphertext_b64: str) -> bytes:
    modulus = int.from_bytes(base64.b64decode(_MODULUS), "big")
    private_d = int.from_bytes(base64.b64decode(_PRIVATE_D), "big")
    size = (modulus.bit_length() + 7) // 8
    cipher = int.from_bytes(base64.b64decode(ciphertext_b64), "big")
    return pow(cipher, private_d, modulus).to_bytes(size, "big")


def test_encrypt_password_round_trips_pkcs1_v1_5() -> None:
    encrypted = encrypt_password("secret", _MODULUS, _EXPONENT)

    padded = _decrypt(encrypted)
    assert padded[:2] == b"\x00\x02"
    assert padded.endswith(b"\x00secret")
    padding = padded[2 : -len("secret") - 1]
    assert padding and all(byte != 0 for byte in padding)


def test_encrypt_password_is_non_deterministic() -> None:
    first = encrypt_password("secret", _MODULUS, _EXPONENT)
    second = encrypt_password("secret", _MODULUS, _EXPONENT)

    assert first != second


def test_encrypt_password_rejects_invalid_base64() -> None:
    with pytest.raises(AuthError, match="base64"):
        encrypt_password("secret", "not base64!", _EXPONENT)


def test_encrypt_password_rejects_too_long_password() -> None:
    with pytest.raises(AuthError, match="too long"):
        encrypt_password("x" * 200, _MODULUS, _EXPONENT)
