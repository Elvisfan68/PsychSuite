"""
Deterministic seed derivation helpers for PsychSuite.
"""
import hashlib


def derive_seed(master_seed: int, *parts: str) -> int:
    payload = f"{int(master_seed)}::" + "::".join(str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    # Keep in a safe 31-bit positive range for broad compatibility.
    return (int.from_bytes(digest[:8], "big") % (2**31 - 2)) + 1
