# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9l: (1) al USAR una receta que sustituía en tu carpeta un archivo del sistema, si el valor del hueco no sustituye nada que exista, no se refuerza,
no se da por hecho y la IA recibe el hecho para buscar el nombre bueno; (2) Lina no da por hecho lo que no se ha podido comprobar, se diga como se
diga: la respuesta es lo que consta, escrito por el código; (3) una receta con nombre provisional lo pide también cuando se usa. Caso real (medida
a16f, 2026-11-27): «arch-update.desktop» y «kdeconnectd.desktop» en vez de los nombres reales, la receta reforzada y «He quitado…». Sin nada de
ningún programa: tres casos con programas y carpetas distintos, y un «sistema» de prueba en una carpeta temporal."""
import contextlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lina.nucleo import herramientas as H
from lina.nucleo import recetas as REC

# (cómo lo pide el usuario, carpeta, nombre real, otro nombre real de la misma carpeta, nombre que no existe)
CASOS = [
    ("Que lanzador-uno no se abra solo al iniciar sesión", "autostart", "lanzador-uno.desktop", "otro-lanzador.desktop", "lanzador1.desktop"),
    ("Quita org.ejemplo.Dos del arranque, porfa", "autostart", "org.ejemplo.Dos.desktop", "org.ejemplo.Tres.desktop", "dos.desktop"),
    ("No quiero que el servicio de sincronizar se ponga en marcha él solo", "systemd/user", "sincronizar.service", "copiar.service",
     "sincroniza.service"),
]


def orden(carpeta, nombre):
    return f"mkdir -p ~/.config/{carpeta} && printf '[Entrada]\\nOculta=true\\n' > ~/.config/{carpeta}/{nombre}"


@pytest.fixture
def sistema(tmp_path, monkeypatch):
    """Un /etc/xdg de prueba con los archivos reales de los tres casos, y las recetas en una carpeta temporal."""
    xdg = tmp_path / "etc-xdg"
    for _, carpeta, real, otro, _ in CASOS:
        (xdg / carpeta).mkdir(parents=True, exist_ok=True)
        for n in (real, otro):
            (xdg / carpeta / n).write_text("[Entrada]\nExec=algo\n")
        os.makedirs(os.path.join(H._HOME, ".config", carpeta), exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(xdg))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(REC, "ARCHIVO", tmp_path / "recetas.json")
    monkeypatch.setattr(REC, "_en_privado", lambda: False)
    return xdg


def aprender(peticion, carpeta, real):
    pasos = [{"herr": "ejecutar_comando", "args": {"comando": orden(carpeta, real), "motivo": "ocultarlo"}}]
    return REC.aprender_pasos(peticion, pasos, nombre="ocultar una entrada del sistema", valor=real)


# ---------------------------------------------------------------- (1) el hueco tiene que sustituir lo que sustituía
@pytest.mark.parametrize("peticion, carpeta, real, otro, falso", CASOS)
def test_un_valor_que_no_sustituye_nada_da_el_hecho_a_la_ia(sistema, peticion, carpeta, real, otro, falso):
    aprender(peticion, carpeta, real)
    ej = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    aviso = ej._hueco_de_receta(orden(carpeta, falso))
    assert aviso.startswith("⚠ COMPROBADO AHORA") and "no sustituye a ningún archivo del sistema" in aviso
    assert f"«{falso}»" in aviso and f"«{real}»" in aviso and f"ls {sistema / carpeta}" in aviso
    assert ej._hueco_de_receta(orden(carpeta, otro)) == ""                  # otro nombre que sí existe: bien
    assert ej._hueco_de_receta(orden(carpeta, real)) == ""


def test_si_la_receta_no_sustituia_nada_no_se_juzga(sistema):
    REC.aprender_pasos("guarda mis notas", [{"herr": "ejecutar_comando", "args": {"comando": orden("misnotas", "a.conf"), "motivo": "m"}}],
                       nombre="guardar una nota", valor="a.conf")
    ej = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    assert ej._hueco_de_receta(orden("misnotas", "b.conf")) == ""


def test_en_la_ejecucion_queda_la_duda_y_no_cuenta_como_comprobado(sistema, monkeypatch):
    peticion, carpeta, real, _, falso = CASOS[0]
    aprender(peticion, carpeta, real)
    ej = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    ruta = os.path.join(H._HOME, ".config", carpeta, falso)

    def ejecutar(comando, motivo="", clase=""):
        open(ruta, "w").write("[Entrada]\nOculta=true\n")               # lo que haría la orden, sin ejecutar nada
        return "código de salida: 0 (0 s)\n"
    monkeypatch.setattr(ej, "ejecutar", ejecutar)
    r = ej._con_red(orden(carpeta, falso), "ocultarlo", "autonomo")
    assert "no sustituye a ningún archivo del sistema" in r and ej.cambio_comprobado is False
    assert "ese nombre no es el bueno" in ej.duda_corta() and ej.tapados == []


def test_con_la_duda_la_receta_no_se_refuerza(sistema):
    peticion, carpeta, real, _, falso = CASOS[1]
    receta = aprender(peticion, carpeta, real)
    a = _asistente(peticion, orden(carpeta, falso))
    a.ejecutor.duda = "⚠ COMPROBADO AHORA: no sustituye a ningún archivo del sistema"
    a._aprender_pasos()
    assert REC._cargar()[0]["exitos"] == receta["exitos"]


# ---------------------------------------------------------------- (2) no se da por hecho lo que no consta, se diga como se diga
RESPUESTAS = ["Hecho.", "He quitado el aviso del inicio automático.", "Listo, ya no se abrirá solo al encender.",
              "Ya está: lo he ocultado del arranque.", "Vale, ya no arrancará solo."]


def _con(ej):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor, a.pregunta_pura, a.acciones_turno, a._fuentes_antes = ej, "quítalo del arranque", [], None
    a._enlace_sin_comprobar = lambda: None
    return a, A


def _ej(**cambios):
    datos = {"pendientes": [], "duda": "", "efecto_sin_comprobar": False, "cambio_sin_comprobar": False, "tapados": []}
    datos.update(cambios)
    ej = SimpleNamespace(**datos)
    ej.duda_corta = lambda: "lo que he escrito no sustituye a ningún archivo del sistema: ese nombre no es el bueno"
    return ej


@pytest.mark.parametrize("respuesta", RESPUESTAS)
@pytest.mark.parametrize("hechos, empieza", [
    ({"duda": "⚠ COMPROBADO AHORA: …"}, "Todavía no sé si ha funcionado: lo que he escrito no sustituye"),
    ({"efecto_sin_comprobar": True, "tapados": [("/casa/.config/autostart/a.desktop", "/etc/xdg/autostart/a.desktop")]},
     "He dejado a.desktop en tu carpeta, en lugar de los del sistema"),
    ({"efecto_sin_comprobar": True}, "He cambiado la configuración, pero no he podido comprobar"),
    ({"cambio_sin_comprobar": True}, "La orden ha salido bien, pero no he podido comprobar"),
])
def test_lo_que_no_consta_no_se_da_por_hecho(monkeypatch, respuesta, hechos, empieza):
    a, A = _con(_ej(**hechos))
    monkeypatch.setattr(A.FUE, "firma", lambda: None)
    r = a._honestidad_de_lo_hecho(respuesta)
    assert r.startswith(empieza) and respuesta not in r and "Hecho" not in r and "He quitado" not in r


@pytest.mark.parametrize("respuesta", RESPUESTAS)
def test_lo_comprobado_se_dice_tal_cual(monkeypatch, respuesta):
    a, A = _con(_ej())
    a.acciones_turno = [("ejecutar_comando", {"comando": "printf x > ~/.config/autostart/a.desktop"}, "código de salida: 0 (0 s)\n\n✔ existe")]
    monkeypatch.setattr(A.FUE, "firma", lambda: None)
    assert a._honestidad_de_lo_hecho(respuesta) == respuesta


def test_si_la_ia_ya_reconoce_la_duda_se_deja(monkeypatch):
    a, A = _con(_ej(cambio_sin_comprobar=True))
    monkeypatch.setattr(A.FUE, "firma", lambda: None)
    texto = "Lo he cambiado, pero no he podido comprobar que funcione."
    assert a._honestidad_de_lo_hecho(texto) == texto


def test_la_receta_repetida_sin_ia_tampoco_dice_hecho_sin_comprobar(sistema):
    peticion, carpeta, real, _, _ = CASOS[2]
    receta = aprender(peticion, carpeta, real)
    ej = _ej(efecto_sin_comprobar=True, tapados=[(os.path.join(H._HOME, ".config", carpeta, real), str(sistema / carpeta / real))])
    ej.herramienta = lambda args: "código de salida: 0 (0 s)\n\n✔ existe con lo escrito"
    a, _ = _con(ej)
    a._REC = lambda: REC
    frase, nota = a._repetir_pasos(receta, None)
    assert frase.startswith(f"He dejado {real} en tu carpeta") and nota == ""
    ej.efecto_sin_comprobar, ej.tapados = False, []
    assert a._repetir_pasos(receta, None)[0] == "Hecho."                    # comprobado: «hecho» sí


# ---------------------------------------------------------------- (3) el nombre general, también al usarla
def _asistente(peticion, comando, general=("ocultar una entrada del sistema", "")):
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    a.ejecutor = SimpleNamespace(cambio_comprobado=True, duda="", contaminado="", receta_turno=False, pendientes=[])
    a.modo_privado, a.turno_aceptado, a.insistiendo, a.historial, a.pregunta_pura = False, True, False, [], peticion
    a.acciones_turno = [("ejecutar_comando", {"comando": comando, "motivo": "otro"}, "código de salida: 0 (0 s)\n\n✔ existe el archivo")]
    a._recetas_de_pasos_activas = lambda: True
    a._generalizar_receta = MagicMock(return_value=general)
    a._REC = lambda: REC
    return a


@pytest.mark.parametrize("peticion, carpeta, real, otro, falso", CASOS)
def test_la_provisional_recibe_su_nombre_al_usarla(sistema, peticion, carpeta, real, otro, falso):
    pasos = [{"herr": "ejecutar_comando", "args": {"comando": orden(carpeta, real), "motivo": "m"}}]
    r = REC.aprender_pasos(peticion, pasos, por_nombrar=True)
    assert r["por_nombrar"] and r["ajuste"] == REC._libre(peticion, 60)
    a = _asistente(peticion, orden(carpeta, real))
    a._aprender_pasos()                                                      # la usa (se refuerza) y, sin nombre aún, lo pide
    [n] = REC._cargar()
    assert n["ajuste"] == "ocultar una entrada del sistema" and "por_nombrar" not in n and n["exitos"] == 2


def test_al_repetirla_sin_ia_pide_el_nombre_sin_retrasar_la_respuesta(sistema, monkeypatch):
    from lina.nucleo import asistente_pasos as AP
    peticion, carpeta, real, _, _ = CASOS[0]
    receta = REC.aprender_pasos("quita lanzador uno del arranque", [{"herr": "ejecutar_comando", "args": {"comando": orden(carpeta, real),
                                                                                                          "motivo": "m"}}], verificada=True, por_nombrar=True)
    hilos = []
    monkeypatch.setattr(AP.threading, "Thread", lambda target, kwargs, daemon: SimpleNamespace(start=lambda: hilos.append((target, kwargs))))
    ej = _ej()
    ej.herramienta = lambda args: "código de salida: 0 (0 s)\n\n✔ existe con lo escrito"
    ej.cancelar, ej.recetas_diferidas, ej.continuar, ej.pregunta_pura, ej.borrado_definitivo = (lambda: None), [], None, "", False
    a, _ = _con(ej)
    a._REC, a._recetas_de_pasos_activas, a.nueva_tarea, a._continuar_peticion = (lambda: REC), (lambda: True), (lambda: None), None
    hallada = a._intentar_receta_pasos("quita lanzador uno del arranque", SimpleNamespace(medir=lambda n: contextlib.nullcontext()))
    assert hallada and hallada[0] == "Hecho." and hilos and hilos[0][1]["receta"]["id"] == receta["id"]
