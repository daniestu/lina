# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def lina(*args, home):
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(SRC)}
    env.pop("XDG_RUNTIME_DIR", None)
    for k in [k for k in env if k.startswith("XDG_") and k != "XDG_SESSION_TYPE"]:
        env.pop(k)
    return subprocess.run([sys.executable, "-m", "lina", *args], env=env, capture_output=True, text=True, timeout=60)


def test_version(tmp_path):
    r = lina("--version", home=tmp_path)
    assert r.returncode == 0 and r.stdout.strip()[0].isdigit()


def test_ayuda_menciona_las_ordenes(tmp_path):
    r = lina("ayuda", home=tmp_path)
    assert r.returncode == 0 and "lina pulsar" in r.stdout and "lina clave" in r.stdout


def test_pulsar_sin_lina_arrancada_avisa(tmp_path):
    r = lina("pulsar", home=tmp_path)
    assert r.returncode == 1 and "no está arrancada" in r.stderr


def test_orden_desconocida(tmp_path):
    assert lina("loquesea", home=tmp_path).returncode == 2
