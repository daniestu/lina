# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""V4a: cada llamada a la IA deja en llamadas_ia.jsonl sus tokens (de entrada, desde la caché, de salida, de razonamiento), cuánto tardó, el tamaño y la
huella del principio fijo (instrucciones y herramientas) y si se repite; nunca texto. `lina tiempos ia` resume si la caché se aprovecha y cuánto pesa el
tamaño, con el criterio de la fila V4. Archivo en tmp_path; proveedor falso, sin red."""
import datetime
import json

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import ia as IA
from lina.nucleo import olvidar as OLV
from lina.nucleo import proveedores as PROV
from lina.nucleo import tiempos as TIE

HOY = datetime.date(2026, 11, 20)


class AjFalso:
    def __init__(self, registrar=True):
        self.registrar = registrar

    def get(self, seccion, clave):
        return self.registrar if (seccion, clave) == ("privacidad", "registrar_tiempos") else AJ.ESQUEMA[seccion][clave][0]


class Proveedor:
    nombre = "gemini"

    def __init__(self, respuesta):
        self.respuesta = respuesta

    def turno(self, clave, modelo, sistema, mensajes, **k):
        return self.respuesta


@pytest.fixture
def archivo(tmp_path, monkeypatch):
    a = tmp_path / "llamadas_ia.jsonl"
    monkeypatch.setattr(TIE, "ARCHIVO_LLAMADAS", a)
    monkeypatch.setattr(IA.AJ, "actuales", lambda log=None: AjFalso())
    IA._huellas.clear()
    return a


def _lineas(archivo):
    return [json.loads(l) for l in archivo.read_text(encoding="utf-8").splitlines()]


USO = {"promptTokenCount": 6800, "cachedContentTokenCount": 4000, "candidatesTokenCount": 40, "thoughtsTokenCount": 12}
SISTEMA = "INSTRUCCIONES-SECRETAS-DE-PRUEBA " * 50
HERR = [{"name": "abrir_app", "description": "abre un programa"}]
MENSAJES = [{"rol": "user", "texto": "una pregunta privada sobre mi banco"}]


# ---------------------------------------------------------------- lo que se apunta
def test_cada_llamada_apunta_tokens_tiempo_tamano_y_huella_sin_texto(archivo):
    IA._turno_medido(Proveedor(PROV.Respuesta(texto="vale", uso=USO, modelo_real="gemini-flash-lite-latest")), "clave", "flash", SISTEMA, MENSAJES,
                     herramientas=HERR, timeout=5)
    [r] = _lineas(archivo)
    assert set(r) <= set(TIE.CAMPOS_LLAMADA)
    assert (r["modelo"], r["res"], r["ent"], r["cache"], r["sal"], r["raz"]) == ("gemini-flash-lite-latest", "ok", 6800, 4000, 40, 12)
    assert r["pref"] == IA.huella_principio(SISTEMA, HERR)[0] and len(r["huella"]) == 8 and r["conv"] == len(MENSAJES[0]["texto"])
    assert "repite" not in r and r["pago"] is False and len(r["dia"]) == 10
    texto = archivo.read_text(encoding="utf-8")
    assert "SECRETAS" not in texto and "banco" not in texto and "abrir_app" not in texto


def test_el_mismo_principio_repetido_se_marca_y_otro_no(archivo):
    p = Proveedor(PROV.Respuesta(uso=USO))
    IA._turno_medido(p, "c", "m", SISTEMA, MENSAJES, herramientas=HERR)
    IA._turno_medido(p, "c", "m", SISTEMA, MENSAJES + [{"rol": "user", "texto": "otra"}], herramientas=HERR)    # otra conversación, mismo principio
    IA._turno_medido(p, "c", "m", SISTEMA, MENSAJES, herramientas=HERR + [{"name": "otra"}])                    # otro grupo de herramientas
    a, b, c = _lineas(archivo)
    assert a["huella"] == b["huella"] != c["huella"]
    assert "repite" not in a and b["repite"] >= 0 and "repite" not in c


def test_una_llamada_fallida_se_apunta_sin_tokens(archivo):
    IA._turno_medido(Proveedor(PROV.ErrorIA("servidor", 503, "ocupado")), "c", "m", SISTEMA, MENSAJES)
    [r] = _lineas(archivo)
    assert r["res"] == "503" and "ent" not in r


def test_con_registrar_tiempos_apagado_no_se_apunta_nada(archivo, monkeypatch):
    monkeypatch.setattr(IA.AJ, "actuales", lambda log=None: AjFalso(False))
    IA._turno_medido(Proveedor(PROV.Respuesta(uso=USO)), "c", "m", SISTEMA, MENSAJES)
    assert not archivo.exists()


def test_si_apuntar_falla_la_llamada_sigue(archivo, monkeypatch):
    monkeypatch.setattr(TIE, "apuntar_llamada", lambda *a: (_ for _ in ()).throw(OSError("disco lleno")))
    r = IA._turno_medido(Proveedor(PROV.Respuesta(texto="hola", uso=USO)), "c", "m", SISTEMA, MENSAJES)
    assert r.texto == "hola"


def test_solo_campos_permitidos_y_tope_propio(tmp_path, monkeypatch):
    a = tmp_path / "l.jsonl"
    TIE.apuntar_llamada({"dia": "2026-11-20", "modelo": "m", "res": "ok", "seg": 1.0, "pregunta": "algo privado", "hora": "10:00"}, a)
    assert set(_lineas(a)[0]) == {"dia", "modelo", "res", "seg"}
    monkeypatch.setattr(TIE, "MAX_LINEAS_LLAMADAS", 7)
    for _ in range(30):
        TIE.apuntar_llamada(TIE.registro_llamada("m", "ok", 1.0, USO, pref=100, conv=10, huella="abcd1234", hoy=HOY), a)
    assert len(_lineas(a)) == 7


def test_olvidar_tiempos_borra_tambien_las_llamadas():
    assert "llamadas_ia.jsonl" in [r.name for r in OLV.QUE["tiempos"][1]()]


# ---------------------------------------------------------------- el resumen y el criterio
def _reg(ent=6000, cache=0, seg=2.0, pref=24000, conv=500, repite=None, pago=False, modelo="m"):
    return TIE.registro_llamada(modelo, "ok", seg, {"promptTokenCount": ent, "cachedContentTokenCount": cache, "candidatesTokenCount": 50},
                                pref=pref, conv=conv, huella="abcd1234", repite=repite, pago=pago, hoy=HOY)


def test_con_pocas_llamadas_no_se_decide():
    [m] = TIE.resumir_ia([_reg(repite=10) for _ in range(49)])
    assert m["decide_cache"] is None and m["decide_tamano"] is None


def test_cache_poco_aprovechada_con_el_principio_repetido_pide_v4b():
    regs = [_reg(cache=500, repite=30) for _ in range(40)] + [_reg() for _ in range(20)]
    [m] = TIE.resumir_ia(regs)
    assert m["repetidas"] == 40 and m["cache_repetidas"] == pytest.approx(500 / 6000) and m["decide_cache"] == "arreglar"


def test_cache_bien_aprovechada_no_se_toca():
    [m] = TIE.resumir_ia([_reg(cache=4000, repite=30) for _ in range(50)])
    assert m["decide_cache"] == "bien" and m["seg_con"] == 2.0 and m["seg_sin"] is None


def test_el_tamano_pesa_si_el_principio_es_grande_y_lo_grande_tarda_medio_segundo_mas():
    regs = [_reg(ent=7000 + 100 * i, seg=1.5 + 0.02 * i, pref=28000) for i in range(100)]
    [m] = TIE.resumir_ia(regs)
    assert m["principio"] > TIE.UMBRAL_PRINCIPIO_TOKENS and m["diferencia_tamano"] >= 0.5 and m["decide_tamano"] == "aligerar"
    regs = [_reg(ent=7000 + 100 * i, seg=2.0, pref=28000) for i in range(100)]          # grande, pero no tarda más
    assert TIE.resumir_ia(regs)[0]["decide_tamano"] == "no tocar"


def test_con_la_clave_de_pago_cuenta_el_coste_y_lo_ideal():
    def precio(m, ent, sal, raz, cache):
        return ((ent - cache) * 1.0 + cache * 0.1 + (sal + raz) * 10.0) / 1e6
    regs = [_reg(ent=6000, cache=0, pref=24000, pago=True) for _ in range(100)]
    [m] = TIE.resumir_ia(regs, precio)
    assert m["coste"] == pytest.approx(100 * (6000 + 500) / 1e6) and m["parte_entrada"] > 0.9
    assert m["coste_ideal"] < m["coste"] and m["decide_tamano"] == "aligerar"         # la entrada es más del 70 % del gasto


def test_lina_tiempos_ia(tmp_path):
    a = tmp_path / "l.jsonl"
    salida = []
    assert TIE.principal_ia([], salida.append, a, HOY) == 0 and "Todavía no hay llamadas" in salida[0]
    for _ in range(60):
        TIE.apuntar_llamada(_reg(cache=4500, repite=20), a)
    TIE.apuntar_llamada(TIE.registro_llamada("m", "503", 8.0, hoy=HOY), a)                # las fallidas no cuentan
    salida.clear()
    assert TIE.principal_ia([], salida.append, a, HOY, precio=lambda *x: 0.0) == 0
    texto = "\n".join(salida)
    assert "m: 60 llamadas" in texto and "75 % desde la caché" in texto and "Caché: la caché ya sirve" in texto
    assert "Tamaño: hacen falta al menos 100 llamadas" in texto and "lina olvidar tiempos" in texto
    for malo in ("x", "0", "400"):
        assert TIE.principal(["ia", malo], salida.append) == 2
