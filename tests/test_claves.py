# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import importlib
import os
import subprocess
import sys

import pytest

AJ = None
GOOGLE = "AI" + "zaSyEJEMPLOEJEMPLOEJEMPLOEJEMPLO12345"          # con forma de clave de Google pero inventada (partida para que el antirrastros no la vea)


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    """Una casa vacía y un «llavero» falso (secret-tool simulado en memoria)."""
    for k in list(os.environ):
        if k.startswith("XDG_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("HOME", str(tmp_path))
    from lina.nucleo import rutas as R
    importlib.reload(R)
    from lina.nucleo import ajustes as A
    A._instancia.update(ajustes=None, ruta=None)
    from lina.nucleo import claves as C
    C._cache.clear()
    C.BUSCAR = lambda programa: "/usr/bin/" + programa

    class Llavero:
        def __init__(self):
            self.datos, self.roto = {}, False

        def __call__(self, orden, input=None, **k):
            if self.roto:
                raise FileNotFoundError("secret-tool")
            a = orden[1:]
            if a[0] == "--version":                                   # el secret-tool de verdad no la admite
                return subprocess.CompletedProcess(orden, 2, "", "Usage: secret-tool...")
            nombre = a[a.index("nombre") + 1] if "nombre" in a else None
            if a[0] == "store":
                self.datos[nombre] = input
                return subprocess.CompletedProcess(orden, 0, "", "")
            if a[0] == "lookup":
                return subprocess.CompletedProcess(orden, 0 if nombre in self.datos else 1, self.datos.get(nombre, ""), "")
            if a[0] == "clear":
                return subprocess.CompletedProcess(orden, 0 if self.datos.pop(nombre, None) is not None else 1, "", "")
    return C, Llavero(), R


def test_guarda_en_el_llavero_y_no_deja_archivo(mundo):
    C, ll, R = mundo
    donde, _ = C.guardar("gemini", GOOGLE, ll)
    assert donde == "llavero" and not (R.CONFIG / "gemini.key").exists()
    assert C.obtener("gemini", ll).startswith("AIza") and C.donde_esta("gemini", ll) == "llavero"


def test_sin_llavero_cae_a_archivo_600(mundo):
    C, ll, R = mundo
    ll.roto = True
    donde, detalle = C.guardar("pago", "clave-de-pago-1234567890", ll)
    ruta = R.CONFIG / "gemini_pago.key"
    assert donde == "archivo" and ruta.read_text().strip() == "clave-de-pago-1234567890" and oct(ruta.stat().st_mode & 0o777) == "0o600"
    assert C.obtener("gemini_pago", ll) == "clave-de-pago-1234567890"


def test_alias_y_nombres(mundo):
    C, ll, R = mundo
    assert C.normalizar("pago") == "gemini_pago" and C.normalizar("Gemini") == "gemini" and C.normalizar("GITHUB_TOKEN") == "GITHUB_TOKEN"
    with pytest.raises(ValueError):
        C.guardar("no valido!", "x", ll)
    with pytest.raises(ValueError):
        C.guardar("gemini", "dos\nlineas", ll)


def test_claves_de_servidores_mcp_en_llavero_o_archivo(mundo):
    C, ll, R = mundo
    C.guardar("SERVICIO_TOKEN", "ghp_" + "a" * 36, ll)
    assert C.valor_mcp("SERVICIO_TOKEN", ll).startswith("ghp_")
    ll.roto = True
    C.guardar("OTRA", "valor-secreto-123", ll)
    C.guardar("OTRA2", "valor-secreto-456", ll)
    texto = (R.CONFIG / "mcp_claves.env").read_text()
    assert "OTRA=valor-secreto-123" in texto and "OTRA2=valor-secreto-456" in texto
    assert oct((R.CONFIG / "mcp_claves.env").stat().st_mode & 0o777) == "0o600"
    assert C.borrar("OTRA", ll) and "OTRA=" not in (R.CONFIG / "mcp_claves.env").read_text() and "OTRA2=" in (R.CONFIG / "mcp_claves.env").read_text()


def test_el_entorno_manda_sobre_lo_guardado(mundo, monkeypatch):
    C, ll, R = mundo
    C.guardar("TOKEN_X", "guardado-123456", ll)
    monkeypatch.setenv("TOKEN_X", "del-entorno-1")
    assert C.valor_mcp("TOKEN_X", ll) == "del-entorno-1"


def test_migrar_mueve_los_archivos_al_llavero(mundo):
    C, ll, R = mundo
    ll.roto = True
    C.guardar("gemini", "clave-gratis-123456", ll)
    C.guardar("MI_TOKEN", "token-123456789", ll)
    ll.roto = False
    C._cache.clear()
    hechas = C.migrar_a_llavero(ll)
    assert ("gemini", True) in hechas and ("MI_TOKEN", True) in hechas
    assert not (R.CONFIG / "gemini.key").exists() and ll.datos["gemini"] == "clave-gratis-123456"
    assert C.obtener("gemini", ll) == "clave-gratis-123456"


def test_si_el_llavero_no_devuelve_lo_guardado_se_usa_archivo(mundo):
    C, ll, R = mundo
    original = ll.__call__

    def mentiroso(orden, input=None, **k):
        r = original(orden, input, **k)
        if orden[1] == "lookup":
            return subprocess.CompletedProcess(orden, 1, "", "")
        return r
    donde, _ = C.guardar("gemini", "clave-123456789", mentiroso)
    assert donde == "archivo" and (R.CONFIG / "gemini.key").exists()


def test_almacen_archivo_no_toca_el_llavero(mundo):
    C, ll, R = mundo
    from lina.nucleo import ajustes as A
    A.actuales(log=lambda m: None).establecer("privacidad", "almacen_claves", "archivo")
    donde, _ = C.guardar("gemini", "clave-123456789", ll)
    assert donde == "archivo" and ll.datos == {}


def test_limpiar_tapa_claves_conocidas_y_con_forma_de_clave(mundo):
    C, ll, R = mundo
    C.guardar("gemini", "valor-propio-de-lina-xyz", ll)
    sucio = ("error con valor-propio-de-lina-xyz; Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456; x-goog-api-key: " + GOOGLE + "; "
             "token ghp_" + "b" * 36 + "; sk-" + "c" * 30)
    limpio = C.limpiar(sucio)
    for secreto in ("valor-propio-de-lina-xyz", "abcdefghijklmnopqrstuvwxyz123456", "AIzaSyEJEMPLO", "ghp_bbbb", "sk-cccc"):
        assert secreto not in limpio
    assert C.limpiar("hola, todo normal 12345") == "hola, todo normal 12345"


def test_filtro_de_salida(mundo):
    C, ll, R = mundo
    import io
    c = io.StringIO()
    f = C.FiltroSalida(c)
    print("clave " + GOOGLE + " fin", file=f)
    assert "AIza" not in c.getvalue() and "fin" in c.getvalue()


def test_lina_clave_pago_exige_tope(mundo):
    C, ll, R = mundo
    salida = []
    respuestas = iter(["nada", "-5", ""])                    # tres intentos mal: no se guarda
    cod = C.principal(["pago"], entrada=lambda p: next(respuestas), secreto=lambda p: "clave-pago-123456", salida=salida.append, ejecutar=ll)
    assert cod == 1 and C.donde_esta("gemini_pago", ll) == "" and any("Sin tope" in l for l in salida)
    salida.clear()
    cod = C.principal(["pago"], entrada=lambda p: "25", secreto=lambda p: "clave-pago-123456", salida=salida.append, ejecutar=ll)
    from lina.nucleo import ajustes as A
    assert cod == 0 and C.donde_esta("gemini_pago", ll) == "llavero" and A.actuales(log=lambda m: None).get("gasto", "tope_mensual_eur") == 25
    assert not any("clave-pago-123456" in l for l in salida)


def test_lina_clave_lista_sin_enseñar_valores(mundo):
    C, ll, R = mundo
    C.guardar("gemini", "clave-gratis-123456", ll)
    salida = []
    assert C.principal([], salida=salida.append, ejecutar=ll) == 0
    assert any("gemini" in l and "llavero" in l for l in salida) and not any("clave-gratis-123456" in l for l in salida)
    assert C.principal(["borrar", "gemini"], salida=salida.append, ejecutar=ll) == 0 and C.donde_esta("gemini", ll) == ""


def test_sin_secret_tool_instalado_se_dice(mundo):
    C, ll, R = mundo
    C.BUSCAR = lambda programa: None
    assert not C.llavero_disponible(ll)
    salida = []
    C.principal([], salida=salida.append, ejecutar=ll)
    assert any("no encontrado" in l for l in salida)
    C.BUSCAR = lambda programa: "/usr/bin/" + programa
    salida.clear()
    C.principal([], salida=salida.append, ejecutar=ll)
    assert any("disponible" in l and "no" not in l.split("disponible")[0][-3:] for l in salida)


def test_lina_clave_gemini_explica_que_clave_es_y_donde_se_crea(mundo):
    C, ll, R = mundo
    salida, prompts = [], []
    cod = C.principal(["gemini"], secreto=lambda p: prompts.append(p) or GOOGLE, salida=salida.append, ejecutar=ll)
    assert cod == 0
    explicacion = " ".join(salida)
    assert "aistudio.google.com/apikey" in explicacion and "AIza" in explicacion and "Crear clave de API" in explicacion
    assert "clave gratuita de Gemini" in prompts[0]                         # el prompt dice QUÉ se pega, no un nombre interno
