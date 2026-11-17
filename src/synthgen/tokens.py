"""Deterministic hex tokens, compatible with the STEMStar HMAC (16 lowercase characters)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from synthgen.constants import TOKEN_HEX_LENGTH

TOKEN_PATTERN = re.compile(rf"^[0-9a-f]{{{TOKEN_HEX_LENGTH}}}$")


def make_token(*parts: object) -> str:
    """Return a 16-character hex token, stable for the given parts."""
    material = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    token = digest[:TOKEN_HEX_LENGTH]
    assert TOKEN_PATTERN.fullmatch(token), token
    return token


def is_token(value: object) -> bool:
    return isinstance(value, str) and TOKEN_PATTERN.fullmatch(value) is not None


def read_seed_tokens(lines: Iterable[str]) -> list[str]:
    """Keep only 16-character hex tokens from an optional STEMStar extract."""
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_line in lines:
        candidate = raw_line.strip().casefold()
        if not TOKEN_PATTERN.fullmatch(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        tokens.append(candidate)
    return tokens
