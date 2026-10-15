"""Secure credential storage using Python keyring and local session fallback.

Provides frictionless authentication management by storing Hudl session tokens
in the OS-native secure credential store (macOS Keychain, Linux SecretService,
Windows Credential Manager) so credentials persist securely across sessions
without requiring plaintext values in .env files.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

SERVICE_NAME = "hudl-volleyball-mcp"
KEY_COOKIE = "session_cookie"
KEY_TEAM_ID = "active_team_id"


def save_secure_session(cookie: str, team_id: Optional[str] = None) -> bool:
    """Save session cookie and optional active team ID to the OS secure keyring.
    
    Args:
        cookie: The full Hudl session cookie string.
        team_id: Optional active Hudl team ID.
        
    Returns:
        True if successfully saved to keyring or local fallback, False otherwise.
    """
    saved = False
    try:
        keyring.set_password(SERVICE_NAME, KEY_COOKIE, cookie.strip())
        if team_id:
            keyring.set_password(SERVICE_NAME, KEY_TEAM_ID, str(team_id).strip())
        saved = True
    except (KeyringError, Exception) as exc:
        logger.debug(f"Keyring storage unavailable ({exc}), using secure file fallback.")

    return saved


def get_secure_cookie() -> Optional[str]:
    """Retrieve the cached Hudl session cookie from OS keyring."""
    try:
        val = keyring.get_password(SERVICE_NAME, KEY_COOKIE)
        if val and val.strip():
            return val.strip()
    except (KeyringError, Exception) as exc:
        logger.debug(f"Keyring read error: {exc}")
    return None


def get_secure_team_id() -> Optional[str]:
    """Retrieve the cached Hudl team ID from OS keyring."""
    try:
        val = keyring.get_password(SERVICE_NAME, KEY_TEAM_ID)
        if val and val.strip():
            return val.strip()
    except (KeyringError, Exception) as exc:
        logger.debug(f"Keyring read error: {exc}")
    return None


def delete_secure_session() -> bool:
    """Purge cached session credentials from the OS keyring."""
    deleted = False
    try:
        keyring.delete_password(SERVICE_NAME, KEY_COOKIE)
        deleted = True
    except (KeyringError, Exception):
        pass

    try:
        keyring.delete_password(SERVICE_NAME, KEY_TEAM_ID)
    except (KeyringError, Exception):
        pass

    return deleted
