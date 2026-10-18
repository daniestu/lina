# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El repositorio no debe llevar secretos ni datos personales, y el comprobador tiene que detectarlos."""
import importlib.util
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comprobar_rastros", RAIZ / "scripts" / "comprobar_rastros.py")
CR = importlib.util.module_from_spec(spec)
sys.modules["comprobar_rastros"] = CR
spec.loader.exec_module(CR)


def test_repositorio_limpio():
    assert CR.revisar() == []


def test_detecta_lo_malo(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("k = 'AIza" + "A" * 35 + "'\nr = '/home/" + "pepito/docs/'\nc = 'pepe@" + "gmail.com'\nok = '/home/usuario/x'\nm = 'ana@example.com'\n", encoding="utf-8")
    motivos = [m for _, _, m in CR.revisar([f], personales=[])]
    assert any("Google" in m for m in motivos)
    assert any("ruta personal" in m for m in motivos)
    assert any("correo real" in m for m in motivos)
    assert len(motivos) == 3


def test_palabras_personales(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hola Pepito\n", encoding="utf-8")
    assert CR.revisar([f], personales=[("pepito", re.compile("pepito", re.I))])
