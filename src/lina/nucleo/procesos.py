"""Lanzar programas fuera del servicio del asistente."""
import os
import shutil
import subprocess

_SCOPE_OK = None


def _fuera_del_servicio(orden):
    """Antepone `systemd-run --user --scope` para que el programa NO viva dentro del servicio del asistente (si no, al reiniciar el servicio
    systemd lo mata: un juego, LibreOffice...). Si no está disponible o no funciona, la orden se deja como estaba."""
    global _SCOPE_OK
    if _SCOPE_OK is None:
        _SCOPE_OK = False
        if shutil.which("systemd-run") and os.environ.get("XDG_RUNTIME_DIR"):
            try:
                _SCOPE_OK = subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--collect", "true"], capture_output=True,
                                           timeout=5).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _SCOPE_OK = False
    return ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--"] + list(orden) if _SCOPE_OK else list(orden)
