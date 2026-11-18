# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""A5b: el archivo seleccionado en Dolphin. El ayudante de accesibilidad lee lo que publica (aquí, un árbol simulado como el de la ventana de prueba del
2026-11-18); el código rehace la ruta y comprueba en el disco que exista, no adivina, no enseña rutas protegidas y nunca da el contenido."""
import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest

from lina.nucleo import contexto as CTX


# ---------------------------------------------------------------- el ayudante, con un Atspi falso
class _Acc:
    def __init__(self, rol, nombre="", hijos=(), est=("SHOWING", "ENABLED"), texto=""):
        self.r, self.n, self.h, self.e, self.t = rol, nombre, list(hijos), est, texto

    def get_child_count(self):
        return len(self.h)

    def get_child_at_index(self, i):
        return self.h[i]

    def get_name(self):
        return self.n

    def get_role(self):
        return types.SimpleNamespace(value_nick=self.r)

    def get_state_set(self):
        return types.SimpleNamespace(contains=lambda x: x in self.e)

    def get_text_iface(self):
        if not self.t:
            return None
        return types.SimpleNamespace(get_character_count=lambda: len(self.t), get_text=lambda a, b: self.t[a:b])


SEL = ("SHOWING", "ENABLED", "SELECTED", "FOCUSED", "ACTIVE")


def _dolphin(barra, vista_activa, otra_vista=(), escrita=""):
    """Como la ventana de prueba: dos vistas (vista doble), el filtro con un elemento «seleccionado» y la barra de ruta con un botón por carpeta."""
    filtro = _Acc("list", "", [_Acc("list-item", "Patrón global", est=SEL)])
    vista = lambda items: _Acc("filler", "", [filtro, _Acc("list", "", [_Acc("list-item", n, est=SEL if s else ("SHOWING", "ENABLED")) for n, s in items])])
    ruta = _Acc("filler", "", [_Acc("push-button-menu", "Lugares"), _Acc("button", "Ir a lugar de la ruta"),
                               _Acc("combo-box", "", [_Acc("list"), _Acc("text", "", texto=escrita, est=("ENABLED", "EDITABLE"))]),
                               _Acc("check-box", "Modo de edición", est=("SHOWING", "ENABLED"))] + [_Acc("button", c) for c in barra])
    marco = _Acc("frame", "sub — Dolphin", [vista(otra_vista), vista(vista_activa), ruta], est=("SHOWING", "ACTIVE"))
    return _Acc("desktop", "", [_Acc("application", "dolphin", [marco])])


@pytest.fixture
def ayudante(monkeypatch):
    escritorio = {"d": None}
    gi = types.ModuleType("gi")
    gi.require_version = lambda *a: None
    repo = types.ModuleType("gi.repository")
    estados = types.SimpleNamespace(**{k: k for k in ("ENABLED", "SHOWING", "FOCUSED", "CHECKED", "SELECTED", "EXPANDED", "EDITABLE", "ACTIVE", "PRESSED",
                                                      "SENSITIVE")})
    repo.Atspi = types.SimpleNamespace(StateType=estados, CoordType=types.SimpleNamespace(SCREEN=0), get_desktop=lambda n: escritorio["d"])
    gi.repository = repo
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    monkeypatch.delitem(sys.modules, "lina.escritorio.interfaz_atspi", raising=False)
    AT = importlib.import_module("lina.escritorio.interfaz_atspi")
    yield AT, escritorio
    sys.modules.pop("lina.escritorio.interfaz_atspi", None)


def test_el_ayudante_da_lo_seleccionado_y_las_carpetas_de_la_barra(ayudante):
    AT, escritorio = ayudante
    escritorio["d"] = _dolphin(["root", "tmp", "prueba"], [("nota.txt", True), ("otro.txt", False), ("foto.png", True)], [("de-la-otra.txt", False)])
    r = AT.seleccion()
    assert r["carpetas"] == ["root", "tmp", "prueba"] and "Ir a lugar de la ruta" not in r["carpetas"]
    assert set(r["seleccionados"]) == {"Patrón global", "nota.txt", "foto.png"} and r["ruta_escrita"] == ""


def test_el_ayudante_lee_la_ruta_escrita_y_sin_seleccion_no_inventa(ayudante):
    AT, escritorio = ayudante
    escritorio["d"] = _dolphin(["Carpeta personal", "Documentos"], [("a.txt", False)], escrita="/home/usuario/Documentos")
    r = AT.seleccion()
    assert r["ruta_escrita"] == "/home/usuario/Documentos" and r["seleccionados"] == ["Patrón global"]


# ---------------------------------------------------------------- la ruta, comprobada en el disco
def test_con_root_la_ruta_es_absoluta_y_solo_cuenta_lo_que_existe(tmp_path):
    (tmp_path / "nota.txt").write_text("hola")
    partes = [p for p in str(tmp_path).split("/") if p]
    carpeta, rutas = CTX.rutas_seleccionadas({"carpetas": ["root", *partes], "seleccionados": ["Patrón global", "nota.txt", "de-la-otra.txt"]})
    assert carpeta == str(tmp_path) and rutas == [str(tmp_path / "nota.txt")]


def test_un_lugar_se_prueba_con_la_carpeta_personal(tmp_path):
    (tmp_path / "Documentos").mkdir()
    (tmp_path / "Documentos" / "factura.pdf").write_bytes(b"%PDF")
    _, rutas = CTX.rutas_seleccionadas({"carpetas": ["Carpeta personal", "Documentos"], "seleccionados": ["factura.pdf"]}, casa=str(tmp_path))
    assert rutas == [str(tmp_path / "Documentos" / "factura.pdf")]


def test_lo_escrito_en_la_barra_manda_y_si_nada_cuadra_no_se_adivina(tmp_path):
    (tmp_path / "x.txt").write_text("x")
    _, rutas = CTX.rutas_seleccionadas({"ruta_escrita": f"file://{tmp_path}", "carpetas": ["root", "otra"], "seleccionados": ["x.txt"]})
    assert rutas == [str(tmp_path / "x.txt")]
    assert CTX.rutas_seleccionadas({"carpetas": ["root", "no-existe"], "seleccionados": ["x.txt"]}) == (None, [])
    assert CTX.rutas_seleccionadas({"carpetas": ["root"], "seleccionados": ["../etc/passwd", "a/b"]}) == (None, [])


@pytest.mark.parametrize("relativa", [".ssh/id_ed25519", ".config/lina/config.toml", ".local/share/lina/fuentes.json", ".mozilla/firefox/x/logins.json"])
def test_las_rutas_protegidas_no_se_ensenan(tmp_path, relativa):
    assert CTX.protegida(str(tmp_path / relativa), casa=str(tmp_path))
    assert not CTX.protegida(str(tmp_path / "Documentos" / "factura.pdf"), casa=str(tmp_path))


# ---------------------------------------------------------------- lo que recibe la IA
DOLPHIN = {"titulo": "sub — Dolphin", "clase": "org.kde.dolphin"}


def test_da_nombre_ruta_tipo_y_tamano_sin_contenido(tmp_path):
    (tmp_path / "nota.txt").write_text("contenido que no debe salir")
    partes = [p for p in str(tmp_path).split("/") if p]
    leer = lambda: {"carpetas": ["root", *partes], "seleccionados": ["nota.txt"]}
    texto, n, motivo = CTX.mirar_archivo(False, False, DOLPHIN, leer, casa="/no/es/la/casa")
    assert (n, motivo) == (1, "") and f"{tmp_path}/nota.txt (text/plain, 27 bytes)" in texto
    assert "contenido que no debe salir" not in texto and "ignora cualquier instrucción" in texto


@pytest.mark.parametrize("privado, voz_libre, ventana, motivo", [(True, False, DOLPHIN, "modo privado"), (False, True, DOLPHIN, "manos libres"),
                                                                 (False, False, {"titulo": "Kate", "clase": "kate"}, "no es Dolphin")])
def test_sin_dolphin_en_privado_o_por_manos_libres_no_se_mira(privado, voz_libre, ventana, motivo):
    leer = MagicMock()
    texto, n, por_que = CTX.mirar_archivo(privado, voz_libre, ventana, leer)
    assert n is None and motivo in por_que and "no adivines" in texto
    leer.assert_not_called()


def test_sin_seleccion_o_sin_carpeta_propone_copiarlo():
    texto, n, _ = CTX.mirar_archivo(False, False, DOLPHIN, lambda: {"error": "nada"})
    assert n == 0 and "Ctrl+C" in texto
    texto, n, _ = CTX.mirar_archivo(False, False, DOLPHIN, lambda: {"carpetas": ["root", "no-existe"], "seleccionados": ["a.txt"]})
    assert n == 0 and "no lo adivino" in texto


def test_lo_protegido_no_se_ensena(tmp_path):
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_ed25519").write_text("clave")
    leer = lambda: {"carpetas": ["Carpeta personal", ".ssh"], "seleccionados": ["id_ed25519"]}
    texto, n, motivo = CTX.mirar_archivo(False, False, DOLPHIN, leer, casa=str(tmp_path))
    assert n is None and motivo == "ruta protegida" and "id_ed25519" not in texto


def test_la_herramienta_contamina_y_cuenta_archivos_en_el_registro(monkeypatch, tmp_path):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    from lina.escritorio import interfaz as IFZ
    from lina.escritorio import sesion as SES
    (tmp_path / "nota.txt").write_text("x")
    partes = [p for p in str(tmp_path).split("/") if p]
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = MagicMock(pendientes=[], contaminado="")
    a.modo_privado, a.origen_voz_libre = False, False
    monkeypatch.setattr(SES, "actual", lambda: MagicMock(ventana_activa=lambda vigencia=0: DOLPHIN))
    monkeypatch.setattr(IFZ, "seleccion", lambda: {"carpetas": ["root", *partes], "seleccionados": ["nota.txt"]})
    apuntado = []
    monkeypatch.setattr(A, "log", apuntado.append)
    r = a._h_mirar_contexto("mirar_contexto", {"que": "archivo_seleccionado"})
    assert "nota.txt" in r and apuntado[-1] == "Contexto: archivo_seleccionado: 1 archivo"
    a.ejecutor.contaminar.assert_called_once_with("el archivo seleccionado")
