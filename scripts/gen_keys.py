"""Generate the static RS256 test keypair used to sign delegation JWTs.

Demo/dev only. In a real deployment these live in a KMS and the gateway only
ever sees the public half.
"""
from __future__ import annotations

import pathlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEYS = pathlib.Path(__file__).resolve().parent.parent / "keys"


def main() -> None:
    KEYS.mkdir(exist_ok=True)
    priv_path = KEYS / "delegation_private.pem"
    pub_path = KEYS / "delegation_public.pem"
    if priv_path.exists() and pub_path.exists():
        print(f"keypair already present in {KEYS}, leaving it alone")
        return

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


if __name__ == "__main__":
    main()
