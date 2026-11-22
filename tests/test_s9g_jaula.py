# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9g: la jaula sin bus tapa entera la carpeta de tu sesión ($XDG_RUNTIME_DIR), no solo el socket del bus. Caso real (medida de A16b, 2026-11-22):
`systemctl --user mask …` desde la jaula «sin bus» enmascaró de verdad una unidad, porque el socket privado de systemd seguía a la vista."""
import os
import re
import shutil
import subprocess

import pytest

from lina.nucleo import aislamiento as AIS


def _tapada(orden, ruta):
    return any(orden[i:i + 2] == ["--tmpfs", ruta] for i in range(len(orden) - 1))


def test_sin_bus_se_tapa_toda_la_carpeta_de_la_sesion(monkeypatch, tmp_path):
    sesion = tmp_path / "run-user"
    (sesion / "systemd").mkdir(parents=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(sesion))
    orden = AIS.orden(["true"], AIS.Jaula(casa=str(tmp_path / "casa"), bus=False))
    assert _tapada(orden, str(sesion))
    con_bus = AIS.orden(["true"], AIS.Jaula(casa=str(tmp_path / "casa"), bus=True))
    assert not _tapada(con_bus, str(sesion)) and ["--bind", str(sesion), str(sesion)] == con_bus[con_bus.index(str(sesion)) - 1:con_bus.index(str(sesion)) + 2]


def test_tambien_la_de_tu_usuario_aunque_falte_la_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    sin_bus = AIS.orden(["true"], AIS.Jaula(casa=str(tmp_path), bus=False), existe=lambda r: True)
    assert f"/run/user/{os.getuid()}" in sin_bus


_SESION = f"/run/user/{os.getuid()}"


@pytest.mark.skipif(not shutil.which("bwrap") or not shutil.which("systemctl") or not os.path.exists(os.path.join(_SESION, "systemd", "private")),
                    reason="hace falta bwrap y una sesión de usuario con systemd (no en la CI)")
def test_de_verdad_systemctl_user_no_llega_a_tu_gestor_desde_la_jaula(tmp_path, monkeypatch):
    """Solo pregunta (is-system-running, no cambia nada). Fuera de la jaula responde; dentro, sin bus, no puede ni conectar."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", _SESION)
    entorno = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_RUNTIME_DIR": _SESION}
    fuera = subprocess.run(["systemctl", "--user", "is-system-running"], capture_output=True, text=True, timeout=20, env=entorno)
    if "Failed to connect" in fuera.stderr or "No medium found" in fuera.stderr:
        pytest.skip("aquí ni siquiera fuera de la jaula se llega al gestor de tu usuario")
    dentro = subprocess.run(AIS.orden(["systemctl", "--user", "is-system-running"], AIS.Jaula(casa=str(tmp_path), red=False, bus=False)),
                            capture_output=True, text=True, timeout=20, env=entorno)
    assert dentro.returncode != 0 and re.search(r"Failed to connect|No medium found|No such file|not been booted", dentro.stderr + dentro.stdout), dentro
