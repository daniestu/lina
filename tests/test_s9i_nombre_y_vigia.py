# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9i: (1) el vigía no se para por las unidades transitorias que crea tu escritorio al abrir un programa (salen en el informe); sí por lo que dura.
(2) Si falla la consulta que pone el nombre general de una receta, la receta se apunta con un nombre provisional y el nombre general se vuelve a pedir
al final de otra petición. Caso real (medida de A16b, 2026-11-23): un Brave abierto a mano paró la medida, y un 503 dejó «Que KDE Connect…» de nombre."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lina.nucleo import recetas as REC
from lina.nucleo import vigia_medida as VIG

ORDEN = "printf '[Desktop Entry]\\nHidden=true\\n' > ~/.config/autostart/org.kde.kdeconnect.daemon.desktop"
PASOS = [{"herr": "ejecutar_comando", "args": {"comando": ORDEN, "motivo": "ocultarla"}}]
GENERAL = ("quitar una app del inicio automático", "org.kde.kdeconnect.daemon")


# ---------------------------------------------------------------- el vigía
class Systemd:
    def __init__(self):
        self.unidades = {"sincronizar.timer": "enabled", "app-ejemplo.service": "enabled"}

    def __call__(self, orden, **k):
        texto = "\n".join(f"{u} {e} enabled" for u, e in self.unidades.items()) if "list-unit-files" in orden else ""
        return SimpleNamespace(returncode=0, stdout=texto)


@pytest.fixture
def vigia(tmp_path):
    (tmp_path / ".config").mkdir()
    s = Systemd()
    v = VIG.VigiaReal(casa=str(tmp_path), ejecutar=s, espera=0, dormir=lambda x: None)
    v.empezar(lambda m: None)
    return v, s


def test_un_programa_que_abre_el_escritorio_no_para_y_sale_en_el_informe(vigia):
    v, s = vigia
    s.unidades["app-navegador-1234.scope"] = "transient"
    s.unidades["app-navegador-abc.service"] = "transient"
    dicho = []
    assert v.parar_si_cambio(dicho.append) is False and not dicho
    assert any("app-navegador-1234.scope" in linea for linea in v.informe())
    del s.unidades["app-navegador-1234.scope"]                      # cierras el programa: tampoco para
    assert v.parar_si_cambio(dicho.append) is False


@pytest.mark.parametrize("cambio", [("app-ejemplo.service", "masked"), ("app-ejemplo.service", "disabled"), ("nueva.service", "enabled"),
                                    ("app-ejemplo.service", "transient")])
def test_lo_que_dura_si_para(vigia, cambio):
    """Enmascarar, desactivar o activar, y también una unidad que deja de estar instalada para volverse transitoria: lo de antes ha desaparecido."""
    v, s = vigia
    s.unidades[cambio[0]] = cambio[1]
    dicho = []
    assert v.parar_si_cambio(dicho.append) is True and dicho[0].startswith("ME PARO")


def test_un_archivo_nuevo_sigue_parando(vigia, tmp_path):
    v, _ = vigia
    (tmp_path / ".config" / "nuevo.conf").write_text("x")
    assert v.parar_si_cambio(lambda m: None) is True


# ---------------------------------------------------------------- el nombre general, más tarde
@pytest.fixture(autouse=True)
def recetas(tmp_path, monkeypatch):
    monkeypatch.setattr(REC, "ARCHIVO", tmp_path / "recetas.json")
    monkeypatch.setattr(REC, "_en_privado", lambda: False)


def test_la_de_pasos_queda_por_nombrar_y_luego_toma_el_nombre_y_el_hueco():
    r = REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, por_nombrar=True)
    assert r["por_nombrar"] and REC.por_nombrar()["id"] == r["id"] and "{valor}" not in r["pasos"][0]["args"]["comando"]
    assert REC.ordenes_de(r) == ORDEN
    n = REC.poner_nombre(r["id"], *GENERAL)
    assert n["ajuste"] == GENERAL[0] and n["pasos"][0]["args"]["comando"] == ORDEN.replace(GENERAL[1], "{valor}") and n["valor_usado"] == GENERAL[1]
    assert "por_nombrar" not in REC._cargar()[0] and REC.por_nombrar() is None


def test_la_de_comando_igual():
    cambiar = ORDEN.replace("\\n", " ⏎ ")
    r = REC.aprender_comando("Que KDE Connect no se inicie solo", "", "Que KDE Connect no se inicie solo", cambiar, "", "", "✔", por_nombrar=True)
    assert REC.ordenes_de(r) == cambiar.replace(" ⏎ ", "\n")
    n = REC.poner_nombre(r["id"], *GENERAL)
    assert n["ajuste"] == GENERAL[0] and n["cambiar"] == cambiar.replace(GENERAL[1], "{valor}")


def test_tras_diez_fallos_se_deja_de_intentar():
    r = REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, por_nombrar=True)
    for _ in range(REC.MAX_INTENTOS_NOMBRE):
        assert REC.por_nombrar() is not None
        REC.fallo_nombre(r["id"])
    assert REC.por_nombrar() is None and REC._cargar()[0]["ajuste"] == "Quita KDE Connect del arranque"


def test_una_igual_con_nombre_general_gana_a_la_provisional_y_no_al_reves():
    r = REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, por_nombrar=True)
    REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, nombre=GENERAL[0])
    [a] = REC._cargar()
    assert a["id"] == r["id"] and a["ajuste"] == GENERAL[0] and "por_nombrar" not in a
    REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, por_nombrar=True)
    [b] = REC._cargar()
    assert b["ajuste"] == GENERAL[0] and "por_nombrar" not in b


def _asistente(general, **ej):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    datos = {"cambio_comprobado": True, "duda": "", "contaminado": "", "receta_turno": False, "pendientes": []}
    datos.update(ej)
    a.ejecutor = SimpleNamespace(**datos)
    a.modo_privado, a.turno_aceptado, a.insistiendo, a.historial = False, True, False, []
    a.pregunta_pura = "Quita KDE Connect del arranque"
    a.acciones_turno = [("ejecutar_comando", {"comando": ORDEN, "motivo": "ocultarla"}, "código de salida: 0 (0 s)\n\n✔ existe el archivo")]
    a._recetas_de_pasos_activas = lambda: True
    a._generalizar_receta = MagicMock(side_effect=general) if isinstance(general, Exception) else MagicMock(return_value=general)
    a._REC = lambda: REC
    return a


@pytest.mark.parametrize("falla", [None, Exception("503")])
def test_si_la_consulta_falla_al_aprender_queda_por_nombrar_y_la_siguiente_peticion_lo_pide(falla):
    a = _asistente(falla)
    a._aprender_pasos()
    [r] = REC._cargar()
    assert r["por_nombrar"] and r["ajuste"] == "Quita KDE Connect del arranque"
    a._nombrar_pendiente()                                   # en la misma petición en que se aprendió, no se repite la consulta
    assert a._generalizar_receta.call_count == 1
    otra = _asistente(GENERAL)
    otra._nombrar_pendiente()
    [n] = REC._cargar()
    assert n["ajuste"] == GENERAL[0] and "{valor}" in n["pasos"][0]["args"]["comando"]
    otra._generalizar_receta.assert_called_once_with("Quita KDE Connect del arranque", ORDEN)


@pytest.mark.parametrize("cambio", [{"contaminado": "página web"}, {"modo_privado": True}])
def test_no_se_pide_en_privado_ni_tras_leer_de_fuera(cambio):
    REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, por_nombrar=True)
    a = _asistente(GENERAL, **{k: v for k, v in cambio.items() if k != "modo_privado"})
    a.modo_privado = cambio.get("modo_privado", False)
    a._nombrar_pendiente()
    assert not a._generalizar_receta.called and REC._cargar()[0]["por_nombrar"]


def test_un_fallo_mas_cuenta_un_intento():
    r = REC.aprender_pasos("Quita KDE Connect del arranque", PASOS, por_nombrar=True)
    _asistente(None)._nombrar_pendiente()
    assert REC._cargar()[0]["intentos_nombre"] == 1 and REC._cargar()[0]["id"] == r["id"]
