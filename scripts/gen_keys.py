"""Generate the static RS256 test keypairs. Demo/dev only.

Two independent keypairs, because they sign for two different trust domains:

  * delegation_{private,public}.pem — the control plane signs delegation JWTs
    with the private half; the gateway verifies with the public half and never
    holds the private one.
  * payment_{private,public}.pem — the gateway signs its scoped single-use
    payment tokens and human-approval tokens with the private half; the mock
    payment provider verifies with the public half.

In a real deployment each of these lives in a KMS and the signing half never
touches a filesystem.
"""
from __future__ import annotations

import pathlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEYS = pathlib.Path(__file__).resolve().parent.parent / "keys"

PAIRS = ("delegation", "payment")


def _write_pair(name: str) -> bool:
    priv_path = KEYS / f"{name}_private.pem"
    pub_path = KEYS / f"{name}_public.pem"
    if priv_path.exists() and pub_path.exists():
        print(f"{name} keypair already present, leaving it alone")
        return False

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    priv_path.chmod(0o600)
    print(f"wrote {priv_path} and {pub_path}")
    return True


def main() -> None:
    KEYS.mkdir(exist_ok=True)
    for name in PAIRS:
        _write_pair(name)


if __name__ == "__main__":
    main()
