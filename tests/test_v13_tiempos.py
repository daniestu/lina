# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V13: `lina tiempos` claro. Caso real (2026-11-18): de los 50 registros que leía, 48 eran de una pasada del banco (`lina probar-ia`), que se guardaba en
el mismo archivo. Ahora el banco no escribe, el informe cubre días (y lo dice), separa cómo llegó la petición y por modo, da la mediana y cuántas pasan
de 10 s, y lo antiguo que no se puede saber de dónde viene no cuenta. Con un archivo inventado y carpetas temporales: sin audio, red ni IA."""
import inspect
import json
import sys
import time
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ia as IA
from lina.nucleo import tiempos as TIE

AHORA = 1_800_000_000.0


def _reg(dias_atras, via=None, modo="rapido", ia=2.0, whisper=None, herramientas=0, llamadas=None):
    fases = {"previas": 0.01, "ia": ia, "sintesis": 0.1, "voz": 1.5}
    if whisper is not None:
        fases["whisper"] = whisper
    reg = {"t": int(AHORA - dias_atras * 86400), "ruta": "gemini-3.5-flash-lite", "modo": modo, "herramientas": herramientas, "fases": fases,
           "hasta_oirte": round(sum(v for k, v in fases.items() if k in TIE.HASTA_OIRTE), 3)}
    if via:
        reg["via"] = via
    if llamadas:
        reg["llamadas"] = llamadas
    return reg


@pytest.fixture
def archivo(tmp_path):
    """20 días mezclados: uso real por las tres vías, registros antiguos por voz y una pasada del banco antigua (sin vía ni Whisper)."""
    regs = []
    for d in range(20, 0, -1):
        regs.append(_reg(d, "atajo", whisper=0.4, ia=2.0 if d % 4 else 14.0, llamadas=[[1.0, "ok"]]))
        if d % 3 == 0:
            regs.append(_reg(d, "manos_libres", whisper=0.6, modo="profundo", ia=6.0))
        if d % 5 == 0:
            regs.append(_reg(d, "texto", modo="directa", ia=0.0))
    regs += [_reg(3, whisper=0.5)]                                              # voz, antes de V13
    regs += [_reg(1, ia=1.0, herramientas=2, llamadas=[[1.0, "ok"], [9.0, "503"]]) for _ in range(48)]   # el banco de antes
    f = tmp_path / "tiempos.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in regs), encoding="utf-8")
    return f


def _informe(archivo, argv=()):
    salida = []
    assert TIE.principal(list(argv), salida.append, archivo, archivo.parent / "no-hay.jsonl", ahora=AHORA) == 0
    return salida


def test_el_banco_antiguo_no_cuenta_y_se_dice(archivo):
    texto = "\n".join(_informe(archivo))
    assert "503" not in texto                                                     # las llamadas del banco no se cuelan
    assert "Sin contar: 48 registros antiguos sin origen ni voz" in texto


def test_dice_las_fechas_y_cuantas(archivo):
    linea = _informe(archivo)[0]
    desde = time.strftime("%Y-%m-%d", time.localtime(AHORA - 14 * 86400))
    assert linea.startswith("Tiempos de los últimos 14 días (del ") and desde in linea
    assert "21 peticiones" in linea                                              # 14 del atajo, 4 manos libres, 2 texto, 1 antigua por voz
    assert "(del " in _informe(archivo, ["30"])[0] and "31 peticiones" in _informe(archivo, ["30"])[0]


def test_separa_las_tres_vias_y_los_modos(archivo):
    texto = "\n".join(_informe(archivo))
    for titulo in ("Con el atajo: 14 peticiones (rápido 14)", "Por manos libres: 4 peticiones (a fondo 4)", "Con «lina di» (texto): 2 peticiones (directas 2)",
                   "Por voz (registros antiguos: atajo y manos libres juntos): 1 peticiones"):
        assert titulo in texto, titulo


def test_mediana_y_cuantas_pasan_de_10_s_sin_media(archivo):
    texto = "\n".join(_informe(archivo))
    bloque = texto.split("Con el atajo")[1].split("Por manos libres")[0]
    assert "IA" in bloque and "mediana 2,0 s · 3 de 14 pasan de 10 s" in bloque and "media " not in texto.replace("mediana", "")
    assert "Lo que más te hace esperar: IA" in bloque


def test_ninguna_linea_pasa_de_100_columnas(archivo):
    """Con la ruta de verdad (unos 45 caracteres) y con escuchas apuntadas."""
    escuchas = archivo.parent / "escuchas.jsonl"
    TIE.apuntar_escucha(TIE.registro_escucha("silencio", ajuste=True, silencio=1.0), escuchas)
    salida = []
    TIE.principal([], salida.append, archivo, escuchas, ahora=AHORA)
    assert any("lina tiempos escucha" in t for t in salida)
    for linea in salida:
        linea = linea.replace(str(archivo), "/home/usuario/.local/state/lina/tiempos.jsonl")
        assert len(linea) <= 100, linea


def test_el_registro_apunta_la_via_y_nada_mas():
    c = TIE.Cronometro(lambda: 0.0)
    assert c.registro("g", "rapido", "manos_libres")["via"] == "manos_libres"
    assert "via" not in c.registro("g", "rapido") and "via" not in c.registro("g", "rapido", "inventada")


def test_dias_raros_se_rechazan(archivo):
    for malo in ("abc", "0", "366"):
        salida = []
        assert TIE.principal([malo], salida.append, archivo) == 2 and "Uso:  lina tiempos [días]" in salida[0]


# ---------------------------------------------------------------- las medidas no escriben en el archivo real
@pytest.fixture
def asistente(monkeypatch):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.origen_texto = a.origen_voz_libre = False
    a.guardar = MagicMock()
    monkeypatch.setattr(A.TIE, "guardar", a.guardar)
    monkeypatch.setattr(A, "log", lambda m: None)
    return a


def test_una_peticion_normal_se_guarda_con_su_via(asistente):
    asistente.origen_voz_libre = True
    asistente._anotar_tiempos(TIE.Cronometro(lambda: 0.0), "g", "rapido")
    assert asistente.guardar.call_args.args[0]["via"] == "manos_libres"


def test_dentro_de_una_medida_no_se_guarda(asistente):
    with IA.solo_medida():
        assert IA.en_medida()
        asistente._anotar_tiempos(TIE.Cronometro(lambda: 0.0), "g", "rapido")
    asistente.guardar.assert_not_called()
    assert not IA.en_medida()


@pytest.mark.parametrize("modulo", ["banco_ia", "probar_ponme", "probar_busqueda"])
def test_cada_medida_corre_dentro_de_solo_medida(modulo):
    """Las tres pasan por la Lina de verdad (`_atender`, que es quien guarda): todas lo hacen dentro de solo_medida."""
    import importlib
    assert "IA.solo_medida()" in inspect.getsource(importlib.import_module(f"lina.nucleo.{modulo}"))
