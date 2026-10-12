"""
Wallet implementation using ECDSA cryptography on the SECP256k1 curve.
Provides key pair generation, message signing, signature verification,
and secure local persistence.
"""

import hashlib
import json
import os
from typing import Any
from ecdsa import SECP256k1, SigningKey, VerifyingKey


def verify_signature(public_key_hex: str, payload_bytes: bytes, signature_hex: str) -> bool:
    """
    Verify an ECDSA SECP256k1 signature using SHA-256.

    This function never raises an exception: any malformed input, invalid hex,
    wrong key length, or signature mismatch safely returns False.
    """
    try:
        # Validate parameter types
        if not isinstance(public_key_hex, str) or not isinstance(signature_hex, str):
            return False
        if not isinstance(payload_bytes, (bytes, bytearray)):
            return False

        # Parse public key and signature bytes from hex strings
        vk_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)

        # Reconstruct the verifying key and verify the signature
        verifying_key = VerifyingKey.from_string(vk_bytes, curve=SECP256k1)
        return verifying_key.verify(sig_bytes, payload_bytes, hashfunc=hashlib.sha256)
    except Exception:
        return False


class Wallet:
    """
    Cryptographic wallet holding a private/public key pair.
    The public address is represented by the raw public key bytes in hex.
    """

    def __init__(self, signing_key: SigningKey | None = None) -> None:
        """
        Initialize wallet. If no signing key is provided, a fresh SECP256k1
        key pair is generated.
        """
        if signing_key is None:
            self._signing_key: SigningKey = SigningKey.generate(curve=SECP256k1)
        else:
            self._signing_key = signing_key

        # The address is the public key raw bytes formatted as a hexadecimal string
        self.verifying_key: VerifyingKey = self._signing_key.verifying_key
        self.address: str = self.verifying_key.to_string().hex()

    @property
    def private_key_hex(self) -> str:
        """Return the raw private key bytes formatted as a hexadecimal string."""
        return self._signing_key.to_string().hex()

    def get_private_key_hex(self) -> str:
        """Return the raw private key bytes formatted as a hexadecimal string."""
        return self._signing_key.to_string().hex()

    @classmethod
    def from_private_key_hex(cls, hex_string: str) -> "Wallet":
        """
        Reconstruct a Wallet from a private key hexadecimal string.
        NOTE: Passing or transmitting private keys over a network is strictly
        for educational demonstration purposes only! Never do this in production.
        """
        private_key_bytes = bytes.fromhex(hex_string)
        signing_key = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        return cls(signing_key=signing_key)

    def sign(self, payload_bytes: bytes) -> str:
        """
        Sign arbitrary payload bytes using the private key and SHA-256.
        Returns the signature formatted as a hexadecimal string.
        """
        signature_bytes = self._signing_key.sign(payload_bytes, hashfunc=hashlib.sha256)
        return signature_bytes.hex()

    def save_to_file(self, path: str = "wallets/wallet.json") -> None:
        """
        Save the wallet's private key and public address to a JSON file.
        WARNING: Never commit private key files or wallets to version control!
        """
        # Ensure target folder exists
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        data: dict[str, str] = {
            "private_key": self.get_private_key_hex(),
            "address": self.address,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_file(cls, path: str = "wallets/wallet.json") -> "Wallet":
        """
        Load a wallet from a JSON file containing the private key in hex.
        WARNING: Never commit private key files or wallets to version control!
        """
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        private_key_bytes = bytes.fromhex(data["private_key"])
        signing_key = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        return cls(signing_key=signing_key)
