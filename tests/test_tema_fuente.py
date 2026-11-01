# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""F3b: R3 en producción, sin dársela aún a la IA al responder. Clave de pago primero, dos intentos con la misma clave y solo el modelo medido; cada comprobación se apunta con su
origen y solo con números; la regla del 8 % mira solo el uso real. Y `lina fuentes probar` no responde, no busca ni ejecuta nada. Sin red: todo simulado, en carpetas temporales."""
import json
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import fuentes as FUE
from lina.nucleo import ia as IA
from lina.nucleo import ia_activa as IAC
from lina.nucleo import medir_fuentes as M
from lina.nucleo import olvidar as OLV
from lina.nucleo import presupuesto as PRES
from lina.nucleo import proveedores as PROV
from lina.nucleo import tiempos as TIE


class AjFalso:
    def __init__(self, registrar=True):
        self.registrar = registrar

    def get(self, seccion, clave):
        return self.registrar if clave == "registrar_tiempos" else AJ.ESQUEMA[seccion][clave][0]


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    monkeypatch.setattr(TIE, "ARCHIVO_COMPROBACIONES", tmp_path / "comprobaciones_fuente.jsonl")
    monkeypatch.setattr(TIE, "ARCHIVO_LLAMADAS", tmp_path / "llamadas_ia.jsonl")
    monkeypatch.setattr(AJ, "actuales", lambda log=print: AjFalso())
    monkeypatch.setattr(IA, "_pausa_modelo", {})
    monkeypatch.setattr(PRES, "registrar", lambda *a: None)
    yield tmp_path


def _proveedor(monkeypatch, respuestas):
    """Cada llamada saca la siguiente respuesta; devuelve la lista de (clave, modelo, timeout)."""
    vistas, pendientes = [], list(respuestas)

    def turno(clave, modelo, sistema, mensajes, **k):
        vistas.append((clave, modelo, k["timeout"]))
        r = pendientes.pop(0)
        return r if isinstance(r, PROV.ErrorIA) else PROV.Respuesta(texto=json.dumps({"decision": r}), uso={})
    ia = MagicMock()
    ia.proveedor.turno = turno
    monkeypatch.setattr(IAC, "actual", lambda *a: ia)
    monkeypatch.setattr(IAC, "modelos", lambda modo, *a: ["ligero", "potente"])
    return vistas


RED = PROV.ErrorIA("red", None, "timeout")


def test_primer_intento_bien_una_sola_llamada(monkeypatch):
    vistas = _proveedor(monkeypatch, ["encaja"])
    assert IA.comprobar_tema(["pago", "gratis"], "t", "p") == "encaja"
    assert vistas == [("pago", "ligero", IA.TIMEOUT_TEMA)]


def test_timeout_y_luego_bien_reintenta_con_la_misma_clave(monkeypatch):
    vistas = _proveedor(monkeypatch, [RED, "no_encaja"])
    assert IA.comprobar_tema(["pago", "gratis"], "t", "p") == "no_encaja"
    assert [v[0] for v in vistas] == ["pago", "pago"]


def test_dos_timeouts_sin_veredicto_y_nunca_otro_modelo_ni_otra_clave(monkeypatch):
    vistas = _proveedor(monkeypatch, [RED, RED])
    assert IA.comprobar_tema(["pago", "gratis"], "t", "p") is None
    assert vistas == [("pago", "ligero", IA.TIMEOUT_TEMA)] * 2


def test_con_el_modelo_en_pausa_no_salta_al_otro(monkeypatch):
    vistas = _proveedor(monkeypatch, [])
    IA._pausa_modelo[IA._id_pausa("ligero", "pago")] = IA.time.time() + 100
    assert IA.comprobar_tema(["pago"], "t", "p") is None and vistas == []


def test_un_r3_lento_no_deja_en_pausa_al_modelo_que_contesta(monkeypatch):
    _proveedor(monkeypatch, [RED, RED])
    pausar = MagicMock()
    monkeypatch.setattr(IA, "_pausar_por_red", pausar)
    IA.comprobar_tema(["pago"], "t", "p")
    pausar.assert_not_called()


def test_sin_claves_no_llama(monkeypatch):
    vistas = _proveedor(monkeypatch, [])
    assert IA.comprobar_tema([], "t", "p") is None and vistas == []


def test_el_modelo_de_produccion_es_el_medido():
    from lina.nucleo import constantes as C
    assert C.MODELOS_CONFIRMACION[0] == C.MODELOS_GEMINI[0]


@pytest.mark.parametrize("pago, disponible, esperado", [("de-pago", True, ["de-pago", "gratis"]), ("de-pago", False, ["gratis"]), ("", True, ["gratis"])])
def test_orden_de_claves(monkeypatch, pago, disponible, esperado):
    monkeypatch.setattr(PRES, "_claves", {"gratis": "gratis", "pago": pago})
    monkeypatch.setattr(PRES, "pago_disponible", lambda: disponible and bool(pago))
    assert PRES.claves_para("fuente") == esperado
    assert PRES.claves_para("mini")[0] == "gratis"


def test_cada_comprobacion_se_apunta_una_vez_con_origen_y_solo_numeros(monkeypatch):
    _proveedor(monkeypatch, [RED, "encaja"])
    IA.comprobar_tema(["clave"], "tema secreto", "pregunta secreta", "prueba")
    crudo = TIE.ARCHIVO_COMPROBACIONES.read_text(encoding="utf-8")
    assert "secret" not in crudo and "clave" not in crudo
    [r] = TIE.leer_comprobaciones()
    assert (r["origen"], r["res"], r["intentos"]) == ("prueba", "encaja", 2)


def test_el_motivo_es_fuente(monkeypatch):
    _proveedor(monkeypatch, ["encaja"])
    vistos = []
    real = IA._apuntar_llamada
    monkeypatch.setattr(IA, "_apuntar_llamada", lambda *a: vistos.append(IA._motivo_actual.get()) or real(*a))
    IA.comprobar_tema(["clave"], "t", "p")
    assert vistos == ["fuente"] and "fuente" in TIE.MOTIVOS


def test_con_registrar_tiempos_apagado_no_se_apunta(monkeypatch):
    monkeypatch.setattr(AJ, "actuales", lambda log=print: AjFalso(False))
    _proveedor(monkeypatch, ["encaja"])
    IA.comprobar_tema(["clave"], "t", "p")
    assert not TIE.ARCHIVO_COMPROBACIONES.exists()
    salida = []
    TIE.principal_ia([], salida.append)
    assert "no tiene datos" in salida[0]


def test_lina_olvidar_tiempos_lo_borra():
    assert "comprobaciones_fuente.jsonl" in [r.name for r in OLV.QUE["tiempos"][1]()]


# ---------------------------------------------------------------- la regla del 8 %
def _regs(*tandas):
    return [{"origen": o, "res": "sin_veredicto" if mal else "encaja"} for o, mal, n in tandas for _ in range(n)]


@pytest.mark.parametrize("fallos, aviso", [(8, False), (9, True)])
def test_el_aviso_salta_con_nueve_de_cien_no_con_ocho(fallos, aviso):
    assert TIE.resumir_comprobaciones(_regs(("real", True, fallos), ("real", False, 100 - fallos)))["aviso"] is aviso


def test_mira_las_primeras_cien_aunque_haya_mas():
    r = TIE.resumir_comprobaciones(_regs(("real", False, 100), ("real", True, 50)))
    assert r["aviso"] is False and r["en_primeras"] == 0 and r["fallos"]["real"] == 50


def test_las_pruebas_no_cuentan_para_la_regla_ni_ocupan_sitio_en_las_primeras_cien():
    r = TIE.resumir_comprobaciones(_regs(("prueba", True, 40), ("real", False, 100)))
    assert r["aviso"] is False and r["primeras"] == 100 and r["n"]["prueba"] == 40 and r["fallos"]["prueba"] == 40


def _informe(registros):
    for r in registros:
        TIE.apuntar_comprobacion({"dia": "2026-11-01", "intentos": 1, "seg": 1, "pago": True, **r})
    salida = []
    TIE.principal_ia([], salida.append)
    return "\n".join(salida)


def test_con_menos_de_cien_y_sin_aviso_no_dice_que_vaya_bien():
    texto = _informe(_regs(("real", True, 5), ("real", False, 15), ("prueba", True, 2)))
    assert "llevas 20 de 100" in texto and "no significa que vaya bien" in texto and "dentro del límite" not in texto
    assert "uso real: 20 comprobaciones, 5 sin veredicto" in texto and "probar: 2, 2 sin veredicto" in texto


def test_con_nueve_fallos_avisa_aunque_no_lleguen_a_cien():
    assert "para y revisa" in _informe(_regs(("real", True, 9), ("real", False, 1)))


def test_con_cien_bien_dice_dentro_del_limite():
    assert "dentro del límite" in _informe(_regs(("real", False, 100)))


# ---------------------------------------------------------------- lina fuentes probar
FUENTE = {"id": "f1", "tema": "recetas de refinería", "url": "https://ejemplo.test/r", "dominio": "ejemplo.test"}


@pytest.fixture
def probar(monkeypatch):
    def poner(respuesta, veredicto="encaja", fuentes=(FUENTE,)):
        ia = MagicMock()
        ia.nombre = "gemini"
        monkeypatch.setattr(IAC, "actual", lambda *a: ia)
        monkeypatch.setattr(IAC, "modelos", lambda *a: ["ligero"])
        monkeypatch.setattr(CL, "obtener", lambda nombre, *a: {"gemini": "gratis", "gemini_pago": "de-pago"}.get(nombre))
        monkeypatch.setattr(PRES, "configurar_claves", lambda g, p: None)
        monkeypatch.setattr(PRES, "claves_para", lambda modo: ["de-pago", "gratis"] if modo == "fuente" else ["gratis", "de-pago"])
        monkeypatch.setattr(FUE, "listar", lambda: list(fuentes))
        turnos = []
        monkeypatch.setattr(M, "_primer_turno", lambda ia, clave, *a: turnos.append(clave) or (respuesta.pop(0) if isinstance(respuesta, list) else respuesta))
        r3 = MagicMock(return_value=veredicto)
        monkeypatch.setattr(IA, "comprobar_tema", r3)
        monkeypatch.setattr(IA, "buscar_tavily", MagicMock(side_effect=AssertionError("no debía buscar")))
        salida = []
        return (M.probar("¿qué sale?", salida.append), "\n".join(salida), r3, turnos)
    return poner


USA = PROV.Respuesta(llamadas=[PROV.Llamada("usar_fuente", {"id": "f1", "consulta": "x"})])


def test_probar_enseña_la_eleccion_y_el_veredicto_marcado_como_prueba(probar):
    codigo, texto, r3, _ = probar(USA)
    assert codigo == 0 and "f1" in texto and "buscaría en ejemplo.test" in texto
    r3.assert_called_once_with(["de-pago", "gratis"], FUENTE["tema"], "¿qué sale?", "prueba")


@pytest.mark.parametrize("veredicto, frase", [("no_encaja", "no encaja"), (None, "no ha contestado")])
def test_probar_sin_encajar_dice_que_seguiria_con_la_general(probar, veredicto, frase):
    _, texto, _, _ = probar(USA, veredicto)
    assert frase in texto and "búsqueda general" in texto


def test_probar_si_no_la_elige_no_comprueba(probar):
    _, texto, r3, _ = probar(PROV.Respuesta(texto="hola"))
    assert "ninguna fuente" in texto
    r3.assert_not_called()


def test_probar_no_ejecuta_lo_que_pida_la_ia(probar):
    otra = PROV.Respuesta(llamadas=[PROV.Llamada("ejecutar_comando", {"comando": "rm -rf /"})])
    codigo, _, r3, _ = probar(otra)
    assert codigo == 0
    r3.assert_not_called()


def test_probar_con_un_id_inventado_no_comprueba(probar):
    _, texto, r3, _ = probar(PROV.Respuesta(llamadas=[PROV.Llamada("usar_fuente", {"id": "f9"})]))
    assert "no existe" in texto
    r3.assert_not_called()


def test_probar_sin_fuentes_no_llama_a_la_ia(probar):
    codigo, texto, _, turnos = probar(USA, fuentes=())
    assert codigo == 1 and "No hay fuentes" in texto and turnos == []


def test_probar_prueba_la_otra_clave_si_la_primera_falla(probar):
    _, _, _, turnos = probar([PROV.ErrorIA("cuota", 429, "sin cupo"), USA])
    assert turnos == ["gratis", "de-pago"]


def test_usar_fuente_sigue_sin_darse_a_la_ia_al_responder():
    from lina.nucleo import asistente as A
    import inspect
    assert "usar_fuente" not in inspect.getsource(A) and "comprobar_tema" not in inspect.getsource(A)
