"""Add or replace the configured Proton Drive remote via a password-protected web UI.

Never expose credentials in subprocess arguments, logs, responses or URLs.
"""
import configparser
import os
from pathlib import Path
import subprocess
import tempfile
from secure_sync.core import validate_remote

CONFIG = Path(os.environ.get("RCLONE_CONFIG", "/etc/proton-drive-secure-sync/rclone.conf"))
REMOTE = validate_remote(os.environ.get("PDSS_REMOTE", "proton:"))[:-1]

def _obscure(value):
    try:
        result = subprocess.run(["rclone", "obscure", "-"], input=value + "\n",
                                capture_output=True, text=True, timeout=15,
                                env={**os.environ, "RCLONE_ASK_PASSWORD": "false"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Rclone non disponibile") from exc
    if result.returncode or not result.stdout.strip():
        raise ValueError("Impossibile proteggere la password con Rclone")
    return result.stdout.strip()

def configured():
    parser = configparser.RawConfigParser(interpolation=None)
    try:
        parser.read(CONFIG)
        return parser.has_section(REMOTE) and parser.get(REMOTE, "type", fallback="") == "protondrive"
    except (OSError, configparser.Error):
        return False

def save_proton(data):
    user = data.get("username")
    password = data.get("password")
    code = data.get("two_factor", "")
    if not isinstance(user, str) or not (3 <= len(user) <= 254) or any(c in user for c in "\r\n\x00"):
        raise ValueError("Indirizzo Proton non valido")
    if not isinstance(password, str) or not (1 <= len(password) <= 1024) or "\x00" in password:
        raise ValueError("Password Proton non valida")
    if not isinstance(code, str) or len(code) > 32 or any(c in code for c in "\r\n\x00"):
        raise ValueError("Codice 2FA non valido")
    if not CONFIG.is_file() or CONFIG.is_symlink():
        raise ValueError("Configurazione Rclone non disponibile")
    parser = configparser.RawConfigParser(interpolation=None)
    try:
        with CONFIG.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as exc:
        raise ValueError("Impossibile leggere la configurazione Rclone") from exc
    if parser.has_section(REMOTE):
        parser.remove_section(REMOTE)
    parser.add_section(REMOTE)
    parser.set(REMOTE, "type", "protondrive")
    parser.set(REMOTE, "username", user)
    parser.set(REMOTE, "password", _obscure(password))
    if code:
        parser.set(REMOTE, "2fa", code)
    else:
        parser.remove_option(REMOTE, "2fa")
    # Validate the new remote before replacing the working configuration.
    fd, candidate = tempfile.mkstemp(prefix=".pdss-rclone-", dir=str(CONFIG.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            parser.write(stream)
        os.chmod(candidate, 0o600)
        try:
            result = subprocess.run(["rclone", "lsd", REMOTE + ":"],
                                    stdin=subprocess.DEVNULL, capture_output=True,
                                    timeout=90, check=False,
                                    env={**os.environ, "RCLONE_CONFIG": candidate,
                                         "RCLONE_ASK_PASSWORD": "false"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Connessione Proton non riuscita o scaduta") from exc
        if result.returncode:
            raise ValueError("Autenticazione Proton non riuscita. Verifica credenziali, 2FA e compatibilità Rclone.")
        # Preserve session tokens written by Rclone during successful login.
        parser = configparser.RawConfigParser(interpolation=None)
        with open(candidate, encoding="utf-8") as stream:
            parser.read_file(stream)
        parser.remove_option(REMOTE, "2fa")
        with open(candidate, "w", encoding="utf-8") as stream:
            parser.write(stream)
        os.chmod(candidate, 0o600)
        os.replace(candidate, CONFIG)
    finally:
        if os.path.exists(candidate):
            os.unlink(candidate)

def connection_status(check=False):
    """Default status reads local configuration only; no network login.

    Explicit checks may authenticate with Proton, so never run automatically.
    """
    if not configured():
        return {"configured": False, "connected": False, "status": "disconnected"}
    if not check:
        return {"configured": True, "connected": None, "status": "configured"}
    try:
        result = subprocess.run(
            ["rclone", "lsd", REMOTE + ":"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=25, check=False,
            env={**os.environ, "RCLONE_ASK_PASSWORD": "false"})
    except subprocess.TimeoutExpired:
        return {"configured": True, "connected": False, "status": "timeout"}
    except OSError:
        return {"configured": True, "connected": False, "status": "error"}
    return {"configured": True, "connected": result.returncode == 0,
            "status": "connected" if result.returncode == 0 else "error"}

def remove_proton():
    """Remove only the active Proton remote, preserving unrelated remotes."""
    if not CONFIG.is_file() or CONFIG.is_symlink():
        raise ValueError("Configurazione Rclone non disponibile")
    parser = configparser.RawConfigParser(interpolation=None)
    try:
        with CONFIG.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as exc:
        raise ValueError("Impossibile leggere la configurazione Rclone") from exc
    if not parser.has_section(REMOTE):
        return False
    if parser.get(REMOTE, "type", fallback="") != "protondrive":
        raise ValueError("Il remoto attivo non è Proton Drive")
    parser.remove_section(REMOTE)
    fd, candidate = tempfile.mkstemp(prefix=".pdss-rclone-", dir=str(CONFIG.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            parser.write(stream)
        os.chmod(candidate, 0o600)
        os.replace(candidate, CONFIG)
    finally:
        if os.path.exists(candidate):
            os.unlink(candidate)
    return True
