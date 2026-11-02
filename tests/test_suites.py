# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Ejecuta cada suite de tests/suites/ como un programa aparte (con un HOME temporal, para no tocar el del desarrollador).

Una suite falla si termina con error, si imprime «FALLO:», o si su línea final dice «fallos N» / «FALLOS: N» con N > 0.
Las que dependen del entorno (programas o librerías que no están en todas partes) se marcan como «esperadas», y los fallos ya conocidos solo valen si son esos.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
SUITES = sorted((AQUI / "suites").glob("t_*.py"))
SRC = AQUI.parent / "src"

# suite -> por qué puede fallar según el entorno
DEPENDEN_DEL_ENTORNO = {
    "t_err.py": "necesita la librería del sistema PortAudio",
}
# suite -> (por qué, los casos que fallan hoy): en cualquier equipo. Un caso nuevo ya no se perdona.
FALLOS_CONOCIDOS = {
    "t_mov.py": ("mover el puntero de esquina a esquina con un ratón muy acelerado: dos casos simulados todavía no convergen (mejora pendiente)",
                 {"suave (3000, 1000) (10, 10)", "dura (3000, 1000) (10, 10)"}),
}


def _ejecutar(suite):
    with tempfile.TemporaryDirectory(prefix="suite-", dir=os.environ.get("LINA_PRUEBAS_BASE")) as casa:   # fuera de /tmp, como la del conftest
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        os.mkdir(os.path.join(casa, "run"), 0o700)
        env.update(HOME=casa, PYTHONPATH=str(SRC) + os.pathsep + env.get("PYTHONPATH", ""), PYTHONDONTWRITEBYTECODE="1",
                   XDG_CURRENT_DESKTOP="KDE", XDG_SESSION_TYPE="wayland", XDG_RUNTIME_DIR=os.path.join(casa, "run"))
        r = subprocess.run([sys.executable, suite.name], cwd=suite.parent, env=env, capture_output=True, text=True, timeout=600)
    salida = r.stdout + r.stderr
    malos = [l for l in salida.splitlines() if l.startswith("FALLO:") or l.startswith("FALLA ")]
    finales = re.findall(r"^(?:FALLOS|fallos):?\s*(\d+)", salida, flags=re.M | re.I)
    return r.returncode, malos, [int(n) for n in finales], salida


def solo_fallos_conocidos(suite, salida):
    """¿Falla algún caso, y todos son de los ya conocidos?"""
    casos = set(re.findall(r"^FALLO (.+?) error \d+", salida, flags=re.M))
    return bool(casos) and casos <= FALLOS_CONOCIDOS.get(suite, (None, set()))[1]


@pytest.mark.parametrize("salida, perdona", [
    ("FALLO suave (3000, 1000) (10, 10) error 3 pasos 40\nFALLOS: 1\n", True),
    ("FALLO suave (3000, 1000) (10, 10) error 3 pasos 40\nFALLO dura (3000, 1000) (10, 10) error 17 pasos 40\nFALLOS: 2\n", True),
    ("FALLO suave (3000, 1000) (10, 10) error 3 pasos 40\nFALLO plano (100, 100) (103, 98) error 5 pasos 9\nFALLOS: 2\n", False),
    ("Traceback\n", False),
])
def test_un_tercer_fallo_de_t_mov_no_se_perdona(salida, perdona):
    assert solo_fallos_conocidos("t_mov.py", salida) is perdona


@pytest.mark.parametrize("suite", SUITES, ids=[s.stem for s in SUITES])
def test_suite(suite):
    codigo, malos, finales, salida = _ejecutar(suite)
    correcta = codigo == 0 and not malos and all(n == 0 for n in finales)
    if suite.name in DEPENDEN_DEL_ENTORNO and not correcta:
        pytest.xfail(DEPENDEN_DEL_ENTORNO[suite.name])
    if solo_fallos_conocidos(suite.name, salida):
        pytest.xfail(FALLOS_CONOCIDOS[suite.name][0])
    assert correcta, f"{suite.name}: código {codigo}, fallos {malos[:5]}, totales {finales}\n{salida[-1500:]}"
