# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""M3: el estado de cada petición tiene su valor de partida en TareaActual, y el `estado` del asistente se cambia con el cerrojo. Sin audio ni IA."""
import ast
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def A():
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente
    return asistente


def test_los_valores_de_partida_valen_antes_de_la_primera_peticion(A):
    a = A.Asistente.__new__(A.Asistente)
    assert a.pregunta_pura == "" and a.miradas == 0 and a.fuente_cerrada is False and a.max_busquedas == A.MAX_BUSQUEDAS and list(a.acciones_turno) == []


def test_recordar_un_paso_no_toca_el_valor_compartido(A):
    a, b = A.Asistente.__new__(A.Asistente), A.Asistente.__new__(A.Asistente)
    a.pasos_receta = [*a.pasos_receta, {"accion": "clic"}]
    assert b.pasos_receta == [] and A.TareaActual.pasos_receta == []


def test_el_estado_compartido_no_se_modifica_en_su_sitio():
    """Con un .append sobre pasos_receta, todas las peticiones compartirían la lista."""
    carpeta = Path(__file__).resolve().parents[1] / "src" / "lina" / "nucleo"
    for archivo in carpeta.glob("asistente*.py"):
        for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("append", "extend", "clear", "pop", "insert"):
                dueno = n.func.value
                assert not (isinstance(dueno, ast.Attribute) and dueno.attr == "pasos_receta"), f"{archivo.name}:{n.lineno}"


def test_avisar_devuelve_el_estado_con_el_cerrojo_y_lo_deja_libre(A):
    a = A.Asistente.__new__(A.Asistente)
    a.cerrojo, a.estado = threading.Lock(), "esperando"
    durante = []
    a._hablar = lambda texto, tipo: durante.append((a.estado, a.cerrojo.locked()))
    assert a.avisar("hola") is True
    assert durante == [("hablando", False)] and a.estado == "esperando" and not a.cerrojo.locked()
