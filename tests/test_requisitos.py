# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""packaging/requisitos.txt (S8a): cada dependencia con versión exacta y hash, todas las de pyproject.toml presentes, y generado por el script.
No va a la red: lee los archivos del repositorio."""
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
REQUISITOS = RAIZ / "packaging" / "requisitos.txt"


def _bloques():
    """[(nombre, línea con la versión, hashes)] de requisitos.txt."""
    bloques, actual = [], None
    for linea in REQUISITOS.read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        if not linea.startswith(" "):
            actual = [re.split(r"[=<>!~; ]", linea, maxsplit=1)[0].lower(), linea, []]
            bloques.append(actual)
        else:
            actual[2] += re.findall(r"--hash=sha256:[0-9a-f]{64}", linea)
    return bloques


def test_cada_dependencia_tiene_version_exacta_y_hash():
    bloques = _bloques()
    assert len(bloques) > 20
    for nombre, linea, hashes in bloques:
        assert re.match(r"^[A-Za-z0-9_.-]+==[^ ;]+", linea), linea
        assert hashes, nombre


def test_estan_todas_las_de_pyproject_y_las_que_mas_importan():
    proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    fijadas = {n.replace("_", "-") for n, _, _ in _bloques()}
    for dep in proyecto["project"]["dependencies"]:
        nombre = re.split(r"[=<>!~; \[]", dep, maxsplit=1)[0].lower().replace("_", "-")
        assert nombre in fijadas, nombre
    assert {"ctranslate2", "onnxruntime", "faster-whisper", "piper-tts"} <= fijadas


def test_lo_genera_el_script():
    assert "scripts/fijar_dependencias.sh" in REQUISITOS.read_text(encoding="utf-8").splitlines()[1]


@pytest.mark.skipif(shutil.which("bash") is None, reason="hace falta bash")
def test_el_script_tiene_sintaxis_valida_y_cubre_de_3_11_a_3_14():
    script = RAIZ / "scripts" / "fijar_dependencias.sh"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    assert "PYTHONS=(3.11 3.12 3.13 3.14)" in script.read_text(encoding="utf-8")


def test_install_sh_y_el_ci_instalan_con_hashes():
    assert "--require-hashes -r \"$REQUISITOS\"" in (RAIZ / "install.sh").read_text(encoding="utf-8")
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert ci.count("--require-hashes -r packaging/requisitos.txt") >= 2 and '"3.14"' in ci
