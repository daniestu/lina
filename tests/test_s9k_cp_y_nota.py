# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""S9k: (1) un cp de un archivo que se puede leer se juzga por lo que escribiría de verdad, y lo copiado se vuelve a leer justo antes de ejecutar;
(2) cuando una orden de persistencia pide «sí», la IA recibe el motivo exacto y la alternativa general, y si después resuelve lo mismo con una orden
que no necesita «sí» sobre los mismos archivos, la pendiente se descarta. Caso real (medida de A16b, 2026-11-26): «copia la entrada del sistema entera
y añade Hidden=true» pedía un segundo «sí». Sin nada de ningún programa: tres peticiones distintas, con programas y carpetas distintos, y la decisión
no depende de cómo se diga. Todo en la carpeta personal de la prueba y en una carpeta temporal que hace de «sistema»."""
import os
from unittest.mock import MagicMock

import pytest

from lina.nucleo import efectos as EF
from lina.nucleo import herramientas as H

# (cómo lo pide el usuario, carpeta de persistencia, archivo, lo que trae el del sistema, lo mínimo que basta escribir)
CASOS = [
    ("Que lanzador-uno no se abra solo al iniciar sesión", ".config/autostart", "lanzador-uno.desktop",
     "[Desktop Entry]\nName=Uno\nExec=lanzador-uno --bandeja\n", "[Desktop Entry]\\nHidden=true\\n"),
    ("Quita org.ejemplo.Dos del arranque, porfa", ".config/autostart", "org.ejemplo.Dos.desktop",
     "[Desktop Entry]\nTryExec=dos\nExec=dos\nX-Fase=Aplicaciones\n", "[Desktop Entry]\\nX-GNOME-Autostart-enabled=false\\n"),
    ("No quiero que el servicio de sincronizar se ponga en marcha él solo", ".config/systemd/user", "sincronizar.service",
     "[Unit]\nDescription=Sincroniza\n[Service]\nExecStart=/usr/bin/sincronizar\n", "[Unit]\\nDescription=sin cambios\\n"),
]


@pytest.fixture
def sistema(tmp_path):
    """Una carpeta que hace de «sistema» (como /etc/xdg o /usr/lib), con los archivos originales de los tres casos."""
    for _, _, archivo, original, _ in CASOS:
        (tmp_path / archivo).write_text(original)
    return tmp_path


@pytest.fixture
def ej(monkeypatch):
    e = H.Ejecutor(avisar=MagicMock(), confirmar=True)
    e.ejecutados = []
    e.resultado = "código de salida: 0 (0 s)\nhecho"
    monkeypatch.setattr(e, "_con_red", lambda comando, motivo, clase: e.ejecutados.append((comando, clase)) or e.resultado)
    monkeypatch.setattr(H, "notificar", lambda *a, **k: None)
    for carpeta in {c[1] for c in CASOS}:
        os.makedirs(os.path.join(H._HOME, carpeta), exist_ok=True)
    return e


def copiar_y_anadir(sistema, carpeta, archivo):
    return f"mkdir -p ~/{carpeta} && cp {sistema}/{archivo} ~/{carpeta}/ && echo 'Hidden=true' >> ~/{carpeta}/{archivo}"


def solo_las_claves(carpeta, archivo, minimo):
    return f"mkdir -p ~/{carpeta} && printf '{minimo}' > ~/{carpeta}/{archivo}"


# ---------------------------------------------------------------- (1) el cp se juzga por su contenido
@pytest.mark.parametrize("peticion, carpeta, archivo, original, minimo", CASOS)
def test_el_cp_se_juzga_por_lo_que_escribiria(sistema, peticion, carpeta, archivo, original, minimo):
    destino = os.path.join(H._HOME, carpeta, archivo)
    origenes = []
    hechas, _ = EF.escrituras(f"cp {sistema}/{archivo} ~/{carpeta}/", H._HOME, origenes)
    assert hechas == [(destino, original, ">")] and origenes[0][0] == str(sistema / archivo)
    inocuo, por_que = EF.reversible_e_inocuo(copiar_y_anadir(sistema, carpeta, archivo), H._HOME)
    assert inocuo is False and "puede hacer que se ejecute" in por_que       # lleva las claves Exec del original: sigue pidiendo «sí»


def test_un_cp_sin_claves_que_ejecuten_va_sin_si(sistema, ej):
    (sistema / "sin-exec.desktop").write_text("[Desktop Entry]\nHidden=true\n")
    orden = f"cp {sistema}/sin-exec.desktop ~/.config/autostart/"
    r = ej.herramienta({"comando": orden, "motivo": "ocultarlo"})
    assert not r.startswith("PREPARADO") and ej.ejecutados == [(orden, "autonomo")]


@pytest.mark.parametrize("orden", ["cp -r {s}/carpeta ~/.config/autostart/", "cp {s}/*.desktop ~/.config/autostart/", "cp {s}/binario ~/.config/autostart/x",
                                   "cp {s}/no-existe.desktop ~/.config/autostart/", "cp -n {s}/lanzador-uno.desktop ~/.config/autostart/",
                                   "cp {s}/lanzador-uno.desktop {s}/org.ejemplo.Dos.desktop ~/.config/autostart/uno-solo"])
def test_lo_que_no_se_puede_juzgar_sigue_como_siempre(sistema, orden):
    (sistema / "carpeta").mkdir()
    (sistema / "binario").write_bytes(b"\xff\xfe\x00binario")
    o = orden.format(s=sistema)
    assert EF.escrituras(o, H._HOME) is None
    assert EF.reversible_e_inocuo(o, H._HOME) == (False, "escribe algo cuyo contenido no se puede saber antes")


# ---------------------------------------------------------------- (1b) lo copiado se vuelve a leer justo antes de ejecutar
def test_si_lo_copiado_cambia_antes_de_ejecutar_no_se_ejecuta(sistema, ej, monkeypatch):
    origen = sistema / "sin-exec.desktop"
    origen.write_text("[Desktop Entry]\nHidden=true\n")
    orden = f"cp {origen} ~/.config/autostart/"
    ej.herramienta({"comando": orden, "motivo": "ocultarlo"})               # se juzga (reversible e inocuo) y se apunta su huella
    origen.write_text("[Desktop Entry]\nExec=otra-cosa\n")                  # y cambia antes de que se ejecute
    monkeypatch.setattr(H.PRIV, "adaptar", MagicMock(side_effect=AssertionError("no debía llegar a ejecutarse")))
    r = H.Ejecutor.ejecutar(ej, orden, "ocultarlo", "autonomo")
    assert r.startswith("NO EJECUTADO") and "sin-exec.desktop" in r


def test_si_lo_copiado_no_ha_cambiado_se_ejecuta(sistema, ej, monkeypatch):
    origen = sistema / "sin-exec.desktop"
    origen.write_text("[Desktop Entry]\nHidden=true\n")
    orden = f"cp {origen} ~/.config/autostart/"
    ej.herramienta({"comando": orden, "motivo": "ocultarlo"})

    class Llego(Exception):
        pass
    monkeypatch.setattr(H.PRIV, "adaptar", MagicMock(side_effect=Llego))
    with pytest.raises(Llego):                                              # pasa la comprobación y sigue hacia la ejecución
        H.Ejecutor.ejecutar(ej, orden, "ocultarlo", "autonomo")


# ---------------------------------------------------------------- (2) la nota y la alternativa
@pytest.mark.parametrize("peticion, carpeta, archivo, original, minimo", CASOS)
def test_la_ia_recibe_el_motivo_y_la_alternativa_y_lo_minimo_sustituye_a_la_pendiente(sistema, ej, peticion, carpeta, archivo, original, minimo):
    preparada = ej.herramienta({"comando": copiar_y_anadir(sistema, carpeta, archivo), "motivo": peticion})
    assert preparada.startswith("PREPARADO") and not ej.ejecutados
    assert f"copia entero {archivo}" in preparada and "puedes escribir solo esas" in preparada and "no necesita «sí»" in preparada
    assert ej.pendientes[0]["sustituible"] == [os.path.join(H._HOME, carpeta, archivo)]
    hecha = ej.herramienta({"comando": solo_las_claves(carpeta, archivo, minimo), "motivo": peticion})
    assert not hecha.startswith("PREPARADO") and ej.pendientes == [] and "Queda descartada la orden pendiente" in hecha


def test_no_se_descarta_si_escribe_otros_archivos_o_si_falla(sistema, ej):
    peticion, carpeta, archivo, _, minimo = CASOS[0]
    ej.herramienta({"comando": copiar_y_anadir(sistema, carpeta, archivo), "motivo": peticion})
    ej.herramienta({"comando": solo_las_claves(carpeta, "otro.desktop", minimo), "motivo": peticion})
    assert len(ej.pendientes) == 1                                          # escribe en otro archivo: la pendiente sigue
    ej.resultado = "código de salida: 1 (0 s)\nfalló"
    ej.herramienta({"comando": solo_las_claves(carpeta, archivo, minimo), "motivo": peticion})
    assert len(ej.pendientes) == 1                                          # no salió bien: la pendiente sigue


def test_sin_poder_saber_lo_que_escribe_tambien_se_explica(sistema, ej):
    open(os.path.join(H._HOME, ".config/autostart/a.desktop"), "w").write("[Desktop Entry]\nExec=a\n")
    preparada = ej.herramienta({"comando": "mv ~/.config/autostart/a.desktop ~/.config/autostart/b.desktop", "motivo": "renombrarlo"})
    assert preparada.startswith("PREPARADO") and "no se puede saber antes qué escribirá" in preparada


def test_la_nota_no_nombra_ningun_programa(sistema):
    for peticion, carpeta, archivo, _, _ in CASOS:
        orden = copiar_y_anadir(sistema, carpeta, archivo)
        nota = EF.nota_para_la_ia(orden, EF.reversible_e_inocuo(orden, H._HOME)[1], H._HOME)
        otros = [c[2] for c in CASOS if c[2] != archivo]
        assert archivo in nota and not any(o in nota for o in otros) and peticion not in nota


def test_tras_leer_de_fuera_sigue_pidiendo_si(sistema, ej):
    peticion, carpeta, archivo, _, minimo = CASOS[0]
    ej.contaminar("página web")
    assert ej.herramienta({"comando": solo_las_claves(carpeta, archivo, minimo), "motivo": peticion}).startswith("PREPARADO")
