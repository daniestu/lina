# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 11: el cronómetro por fases, el archivo de tiempos (solo números) y `lina tiempos`. Sin audio ni red: reloj falso."""
import json

from lina.nucleo import ajustes as AJ
from lina.nucleo import olvidar as OLV
from lina.nucleo import tiempos as TIE


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def pasa(self, s):
        self.t += s


def test_el_cronometro_suma_por_fase_con_un_reloj_falso():
    reloj = Reloj()
    c = TIE.Cronometro(reloj)
    with c.medir("whisper"):
        reloj.pasa(0.9)
    with c.medir("herramientas"):
        reloj.pasa(0.4)
    with c.medir("herramientas"):
        reloj.pasa(0.1)
    c.sumar("sintesis", 0.3)
    c.sumar("voz", 2.0)
    assert round(c.fases["whisper"], 3) == 0.9 and round(c.fases["herramientas"], 3) == 0.5
    assert round(c.hasta_oirte(), 3) == 1.7                 # la reproducción no cuenta hasta oírte
    assert round(c.total(), 3) == 1.4


def test_una_fase_que_falla_tambien_se_mide_y_no_hay_tiempos_negativos():
    reloj = Reloj()
    c = TIE.Cronometro(reloj)
    try:
        with c.medir("ia"):
            reloj.pasa(1.0)
            raise RuntimeError
    except RuntimeError:
        pass
    c.sumar("voz", -5)
    assert c.fases["ia"] == 1.0 and c.fases["voz"] == 0.0


def test_el_registro_solo_lleva_numeros_y_la_ruta():
    c = TIE.Cronometro(Reloj())
    c.sumar("ia", 2.1)
    c.herramientas = 2
    reg = c.registro("gemini-flash", "rapido")
    assert set(reg) == {"t", "ruta", "modo", "herramientas", "fases", "hasta_oirte"}
    assert all(isinstance(v, (int, float)) for v in reg["fases"].values())
    linea = TIE.linea_de_registro(reg)
    assert "ia 2,1 s" in linea and "2 herramientas" in linea and "hasta oírte 2,1 s" in linea


def test_guardar_lee_y_recorta_el_archivo(tmp_path, monkeypatch):
    archivo = tmp_path / "estado" / "tiempos.jsonl"
    monkeypatch.setattr(TIE, "MAX_BYTES", 2000)
    monkeypatch.setattr(TIE, "MAX_LINEAS_TRAS_ROTAR", 5)
    for i in range(60):
        c = TIE.Cronometro(Reloj())
        c.sumar("ia", i)
        assert TIE.guardar(c.registro("x"), archivo)
    registros = TIE.leer(archivo, 1000)
    assert 0 < len(registros) <= 60 and archivo.stat().st_size <= 2000 + 400
    assert registros[-1]["fases"]["ia"] == 59                  # se queda con lo último
    archivo.write_text(archivo.read_text() + "esto no es json\n[1]\n", encoding="utf-8")
    assert TIE.leer(archivo) == TIE.leer(archivo)               # las líneas rotas se saltan sin fallar


def test_guardar_nunca_falla(tmp_path):
    (tmp_path / "f").write_text("x")
    assert TIE.guardar({"fases": {}}, tmp_path / "f" / "dentro" / "t.jsonl") is False


def test_resumir_da_media_mediana_y_la_fase_mas_lenta():
    regs = []
    for ia, wh in ((1.0, 0.5), (3.0, 0.5), (8.0, 0.5)):
        c = TIE.Cronometro(Reloj())
        c.sumar("ia", ia)
        c.sumar("whisper", wh)
        c.sumar("voz", 99)                                       # larga, pero no es una espera
        regs.append(c.registro("g"))
    r = TIE.resumir(regs)
    assert r["fases"]["ia"][:2] == (4.0, 3.0) and r["mas_lenta"] == "ia" and r["n"] == 3


def test_lina_tiempos_sin_datos_y_con_datos(tmp_path):
    archivo = tmp_path / "t.jsonl"
    salida = []
    assert TIE.principal([], salida.append, archivo) == 0 and "Todavía no hay tiempos" in salida[0]
    for ia, herr, ruta in ((1.0, 0, "g"), (5.0, 2, "g"), (0.0, 0, "directa:abrir_app")):
        c = TIE.Cronometro(Reloj())
        c.sumar("ia", ia)
        c.herramientas = herr
        TIE.guardar(c.registro(ruta), archivo)
    salida.clear()
    assert TIE.principal([], salida.append, archivo) == 0
    texto = "\n".join(salida)
    assert "Con la IA, sin herramientas: 1 peticiones" in texto and "Con la IA y herramientas: 1 peticiones" in texto and "La fase más lenta" in texto
    assert "Órdenes directas (sin IA): 1 peticiones" in texto


def test_lina_tiempos_rechaza_un_numero_raro(tmp_path):
    for malo in ("abc", "0", "-3", "999999"):
        salida = []
        assert TIE.principal([malo], salida.append, tmp_path / "t.jsonl") == 2 and "Uso:" in salida[0]


def test_el_ajuste_existe_y_esta_activo_por_defecto(tmp_path):
    aj = AJ.Ajustes(tmp_path / "config.toml", log=lambda m: None)
    assert aj.get("privacidad", "registrar_tiempos") is True
    assert "tiempos" in OLV.QUE and "tiempos" in OLV.TODO
