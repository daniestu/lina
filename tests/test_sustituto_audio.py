# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El `sounddevice` de mentira del conftest: aguanta monkeypatch con cualquier pytest y cubre lo que usa el código. Ni audio ni librería real."""
import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "lina"


def _nombres_usados(arbol):
    """Los `sd.ALGO` de un archivo, con el alias que tenga allí `import sounddevice`."""
    alias = {a.asname or a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names if a.name == "sounddevice"}
    return {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias}


def test_input_stream_sobrevive_a_dos_rondas_de_monkeypatch():
    sd = sys.modules["sounddevice"]
    assert type(sd).__name__ == "SustitutoAudio"                # la librería real no se ha cargado
    original = sd.InputStream
    for _ in range(2):                                          # con un MagicMock pelado, la segunda ronda da AttributeError
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sd, "InputStream", object())
        assert sd.InputStream is original


def test_lo_que_usa_el_codigo_existe_en_el_sustituto():
    usados = {n for f in SRC.rglob("*.py") for n in _nombres_usados(ast.parse(f.read_text(encoding="utf-8")))}
    assert {"InputStream", "rec", "wait", "play", "query_devices"} <= usados     # si no, esta lectura del código ha dejado de encontrar nada
    assert usados <= set(vars(sys.modules["sounddevice"]))      # vars: sin pasar por __getattr__, que inventaría lo que falte
