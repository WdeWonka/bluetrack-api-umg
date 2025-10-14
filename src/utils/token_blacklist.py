"""
Sistema simple de lista negra para tokens JWT.
"""
from typing import Set

# 🗑️ Tokens invalidados (en memoria)
_blacklisted_tokens: Set[str] = set()


def add_to_blacklist(token: str):
    """Invalida un token."""
    _blacklisted_tokens.add(token)


def is_blacklisted(token: str) -> bool:
    """Verifica si un token está invalidado."""
    return token in _blacklisted_tokens
