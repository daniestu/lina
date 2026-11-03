# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
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


def test_la_simulacion_instala_las_dependencias_fijadas_con_hash(tmp_path):
    r = ejecutar(tmp_path, "--simular", "-y", "--sin-bienvenida")
    salida = r.stdout + r.stderr
    assert "--require-hashes -r" in salida and "--no-deps -e" in salida, salida


# ---------------------------------------------------------------- qué Python usa (con programas falsos en el PATH: ni uv ni Python de verdad)
HERRAMIENTAS = ("bash", "sh", "env", "id", "uname", "sed", "dirname", "cat", "mkdir", "date", "tee", "grep", "rm", "head", "tr")


def _python_falso(carpeta, nombre, version):
    p = carpeta / nombre
    p.write_text(f"#!/bin/sh\ncase \"$*\" in *version_info*) echo {version} ;; -V) echo Python {version}.0 ;; esac\nexit 0\n")
    p.chmod(0o755)
    return p


def _entorno(tmp_path, pythons=(), uv=None):
    """bin/ con lo justo para el instalador, los Python falsos {nombre: versión} y, si uv es una versión, un uv que «tiene» ese Python."""
    binario = tmp_path / "bin"
    binario.mkdir()
    for h in HERRAMIENTAS:
        if shutil.which(h):
            (binario / h).symlink_to(shutil.which(h))
    for nombre, version in dict(pythons).items():
        _python_falso(binario, nombre, version)
    if uv:
        gestionado = tmp_path / "uv" / "python" / "cpython-3.14-linux-x86_64-gnu" / "bin"
        gestionado.mkdir(parents=True)
        _python_falso(gestionado, "python3.14", uv)
        (binario / "uv").write_text(f"#!/bin/sh\ncase \"$*\" in *find*) echo {gestionado / 'python3.14'} ;; esac\nexit 0\n")
        (binario / "uv").chmod(0o755)
    casa = tmp_path / "casa"
    casa.mkdir()
    return binario, casa


def ejecutar_con(binario, casa, *args):
    env = {"HOME": str(casa), "PATH": str(binario), "LINA_PERMITIR_ROOT": "1", "LINA_DISTRO": "arch"}
    return subprocess.run(["bash", str(RAIZ / "install.sh"), *args], capture_output=True, text=True, env=env, cwd=casa, timeout=120, stdin=subprocess.DEVNULL)


def test_con_uv_usa_su_python_aunque_el_del_sistema_sea_nuevo(tmp_path):
    binario, casa = _entorno(tmp_path, {"python3": "3.15"}, uv="3.14")
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Python para Lina: Python 3.14.0 de uv" in r.stdout and "uv/python/cpython-3.14" in r.stdout


def test_sin_uv_usa_el_primer_python_del_sistema_que_vale_y_avisa(tmp_path):
    binario, casa = _entorno(tmp_path, {"python3": "3.15", "python3.13": "3.13", "python3.14": "3.14"})
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Python 3.14.0 del sistema" in r.stdout and str(binario / "python3.14") in r.stdout and "repite este instalador" in r.stdout


def test_sin_un_python_que_valga_para_antes_de_tocar_nada(tmp_path):
    binario, casa = _entorno(tmp_path, {"python3": "3.15"})
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode != 0 and "entre 3.11 y 3.14" in r.stderr and "python3 es 3.15" in r.stderr and "uv" in r.stderr
    assert "2/6" not in r.stdout and list(casa.rglob("*")) == []


def test_un_entorno_de_otro_python_se_crea_de_nuevo(tmp_path):
    binario, casa = _entorno(tmp_path, {"python3": "3.14"}, uv="3.14")
    venv = casa / ".local" / "share" / "lina" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.14.7\n")
    _python_falso(venv / "bin", "python", "3.14")
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "es de otro Python o está roto" in r.stdout and f"[simulación] rm -rf {venv}" in r.stdout and "-m venv" in r.stdout
    assert (venv / "pyvenv.cfg").exists()                          # simulación: no se ha borrado


def test_un_entorno_del_mismo_python_se_respeta(tmp_path):
    binario, casa = _entorno(tmp_path, {}, uv="3.14")
    gestionado = tmp_path / "uv" / "python" / "cpython-3.14-linux-x86_64-gnu" / "bin"
    venv = casa / ".local" / "share" / "lina" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = {gestionado}\nversion = 3.14.8\n")
    _python_falso(venv / "bin", "python", "3.14")
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "otro Python" not in r.stdout and "-m venv" not in r.stdout


def test_un_entorno_que_cambio_de_version_se_crea_de_nuevo(tmp_path):
    """Lo que le pasará a Arch: el venv apunta a /usr/bin/python3, que ahora es 3.15, y sus paquetes siguen en lib/python3.14."""
    binario, casa = _entorno(tmp_path, {"python3.14": "3.14"})
    venv = casa / ".local" / "share" / "lina" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = {binario}\nversion = 3.14.7\n")
    _python_falso(venv / "bin", "python", "3.15")
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert "es de otro Python o está roto" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("tenia", [True, False])
def test_al_recrear_el_entorno_repone_las_librerias_de_nvidia_si_las_tenia(tmp_path, tenia):
    """Lo que pasó al pasar al Python de uv: el entorno nuevo no tenía cuBLAS y Whisper cargaba en la tarjeta pero no podía transcribir."""
    binario, casa = _entorno(tmp_path, {"python3": "3.14"}, uv="3.14")
    venv = casa / ".local" / "share" / "lina" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.14.7\n")
    _python_falso(venv / "bin", "python", "3.14")
    if tenia:
        (venv / "lib" / "python3.14" / "site-packages" / "nvidia" / "cublas").mkdir(parents=True)
    r = ejecutar_con(binario, casa, "--simular", "-y", "--sin-bienvenida")
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("pip install --quiet nvidia-cublas-cu12 nvidia-cudnn-cu12" in r.stdout) is tenia
    assert ("las vuelvo a poner" in r.stdout) is tenia

