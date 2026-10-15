import os
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="hace falta bash")


def ejecutar(tmp_path, *args):
    env = {**os.environ, "HOME": str(tmp_path), "XDG_CONFIG_HOME": "", "XDG_DATA_HOME": "", "XDG_STATE_HOME": "", "XDG_CACHE_HOME": "",
           "LINA_PERMITIR_ROOT": "1", "LINA_DISTRO": "arch"}
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        env.pop(k)
    return subprocess.run(["bash", str(RAIZ / "install.sh"), *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120, stdin=subprocess.DEVNULL)


def test_simulacion_no_toca_nada(tmp_path):
    r = ejecutar(tmp_path, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "simulación" in (r.stdout + r.stderr).lower()
    assert list(tmp_path.rglob("*")) == [], list(tmp_path.rglob("*"))


def test_sintaxis_valida():
    assert subprocess.run(["bash", "-n", str(RAIZ / "install.sh")]).returncode == 0


def test_opcion_desconocida_se_rechaza(tmp_path):
    r = ejecutar(tmp_path, "--no-existe")
    assert r.returncode != 0 and list(tmp_path.rglob("*")) == []
