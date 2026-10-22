# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Memoria de preferencias: solo escribe el usuario con una frase suya, la IA solo lee, nada de claves, topes y borrado de verdad."""
import json

import pytest

from lina.nucleo import grupos as G
from lina.nucleo import herramientas as H
from lina.nucleo import memoria as M
from lina.nucleo import olvidar as OLV


@pytest.fixture(autouse=True)
def archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "ARCHIVO", tmp_path / "memoria.json")
    return tmp_path / "memoria.json"


def test_entender_las_frases():
    assert M.entender("Recuerda que mi opción preferida para jugar es Proton-CachyOS.") == ("recordar", "mi opción preferida para jugar es Proton-CachyOS")
    assert M.entender("apunta que prefiero el tema oscuro")[0] == "recordar"
    assert M.entender("ten en cuenta que uso Brave") == ("recordar", "uso Brave")
    assert M.entender("olvida lo de Proton") == ("olvidar", "Proton")
    assert M.entender("Olvida lo del volumen.") == ("olvidar", "volumen")
    assert M.entender("olvida lo de las cámaras") == ("olvidar", "las cámaras")
    assert M.entender("Olvida todo lo que recuerdas de mí.") == ("todo",)
    assert M.entender("borra todo") == ("todo",)
    assert "por voz" in M.gestionar(("todo",))
    assert M.entender("qué recuerdas de mí") == ("listar",)
    assert M.entender("¿Qué recuerdas de mí?") == ("listar",)
    for no in ("recuérdame mañana llamar a Pedro", "guarda el archivo", "apunta eso", "abre Firefox", "qué hora es", "recuerda"):
        assert M.entender(no) is None, no


def test_guardar_y_recuperar_entre_reinicios(archivo):
    assert M.recordar("mi opción preferida para jugar es Proton-CachyOS")[0]
    assert oct(archivo.stat().st_mode & 0o777) == "0o600"
    assert M.relevantes("instala algo para jugar con Proton") == ["mi opción preferida para jugar es Proton-CachyOS"]
    assert M.relevantes("qué tiempo hace mañana") == []
    assert "NO órdenes" in M.nota_para_la_ia("quiero jugar") and "Proton-CachyOS" in M.nota_para_la_ia("quiero jugar")
    assert M.nota_para_la_ia("hola buenas") == ""


def test_no_guarda_claves_ni_contrasenas_ni_numeros_largos(archivo):
    falsa = "AI" + "zaSy" + "A" * 35
    for texto in (f"mi clave es {falsa}", "mi contraseña de wifi es patata123", "mi tarjeta es 4111 1111 1111 1111", "el token es abc", "usa sk-" + "x" * 30, "mi api key es la de casa"):
        hecho, mensaje = M.recordar(texto)
        assert not hecho and "No guardo" in mensaje, texto
    assert not archivo.exists()


def test_limites(archivo):
    assert not M.recordar("x" * 301)[0]
    assert not M.recordar("de la y el")[0]
    for i in range(M.MAX_ENTRADAS):
        assert M.recordar(f"prefiero el color tono{i} para el escritorio")[0]
    hecho, mensaje = M.recordar("prefiero algo distinto del todo")
    assert not hecho and "llena" in mensaje
    assert len(json.loads(archivo.read_text())) == M.MAX_ENTRADAS


def test_repetido_no_se_duplica(archivo):
    M.recordar("uso Brave como navegador"); M.recordar("uso Brave como navegador")
    assert len(json.loads(archivo.read_text())) == 1


def test_olvidar_borra_de_verdad_y_con_cuidado(archivo):
    M.recordar("mi opción preferida para jugar es Proton-CachyOS")
    M.recordar("mi navegador preferido es Brave")
    hecho, _ = M.olvidar("lo de Proton")
    assert hecho and "Proton" not in archivo.read_text() and "Brave" in archivo.read_text()
    assert not M.olvidar("la nevera")[0]
    M.recordar("mi navegador de reserva es Firefox")
    hecho, mensaje = M.olvidar("mi navegador")
    assert not hecho and "varios" in mensaje and "Brave" in archivo.read_text() and "Firefox" in archivo.read_text()


def test_listar_y_lina_memoria(archivo):
    salida = []
    assert M.principal([], salida.append) == 0 and "No hay nada" in salida[0]
    M.recordar("uso Brave como navegador")
    salida.clear()
    M.principal([], salida.append)
    assert "m0001" in "\n".join(salida) and "Brave" in "\n".join(salida)
    assert "Brave" in M.resumen_hablado()
    assert M.principal(["borrar", "m9999"], salida.append) == 1
    assert M.principal(["borrar", "m0001"], salida.append) == 0 and not archivo.exists()
    M.recordar("a veces juego Skyrim"); assert M.principal(["borrar", "todas"], salida.append) == 0 and not archivo.exists()


def test_la_ia_no_tiene_ninguna_herramienta_que_escriba_en_la_memoria():
    nombres = list(G.NUCLEO) + [h for lista in G.GRUPOS.values() for h in lista]
    assert "ejecutar_comando" in nombres and len(nombres) > 20
    assert not [n for n in nombres if "memoria" in n.lower() or "record" in n.lower() and n != "recordatorios"]


def test_la_ia_tampoco_puede_tocar_el_archivo_ni_borrarlo_con_la_orden(tmp_path):
    for orden in ("lina memoria borrar todas", "rm ~/.local/share/lina/memoria.json", "echo '[]' > ~/.local/share/lina/memoria.json",
                  "sed -i s/a/b/ ~/.local/share/lina/memoria.json", "python3 -c \"open('/x/lina/nucleo/memoria.py','w')\""):
        assert H.clasificar(orden)[0] in {"critico", "bloqueado"}, orden


def test_lina_olvidar_incluye_la_memoria():
    assert "memoria" in OLV.QUE and "memoria" in OLV.TODO


# ---- «abre el navegador»: el tuyo, no uno que tenga «Browser» en el nombre
def _apps():
    return [{"nombre": "Avahi Zeroconf Browser", "comando": "avahi-discover", "es": "", "id": "avahi-discover", "generico": "Navegador Zeroconf", "claves": ""},
            {"nombre": "Brave", "comando": "brave", "es": "", "id": "brave-browser", "generico": "Navegador web", "claves": ""},
            {"nombre": "Firefox", "comando": "firefox", "es": "", "id": "firefox", "generico": "Navegador web", "claves": ""}]


def test_abre_el_navegador_usa_el_predeterminado(monkeypatch):
    from lina.nucleo import comandos as C
    monkeypatch.setattr(C, "_predeterminada", lambda tipo: "firefox")
    r = C.buscar_app("abre el navegador", _apps())
    assert r[0][0] == 100 and r[0][1]["nombre"] == "Firefox" and all(p < 100 for p, _ in r[1:])


def test_abre_el_navegador_usa_lo_que_pediste_recordar(monkeypatch):
    from lina.nucleo import comandos as C
    monkeypatch.setattr(C, "_predeterminada", lambda tipo: "firefox")
    M.recordar("mi navegador favorito es el de Brave")
    r = C.buscar_app("el navegador", _apps())
    assert r[0][1]["nombre"] == "Brave" and r[0][0] == 100


def test_un_programa_con_nombre_propio_no_se_toca(monkeypatch):
    from lina.nucleo import comandos as C
    monkeypatch.setattr(C, "_predeterminada", lambda tipo: "firefox")
    M.recordar("mi navegador favorito es el de Brave")
    assert C.buscar_app("abre Firefox", _apps())[0][1]["nombre"] == "Firefox"


# ---- vale para cualquier cosa, no solo el navegador
def _camaras():
    return [{"nombre": "Cheese", "comando": "cheese", "es": "", "id": "org.gnome.Cheese", "generico": "Cámara web", "claves": "camara;webcam"},
            {"nombre": "Kamoso", "comando": "kamoso", "es": "", "id": "org.kde.kamoso", "generico": "Cámara web", "claves": "camara;webcam"},
            {"nombre": "Kate", "comando": "kate", "es": "", "id": "org.kde.kate", "generico": "Editor de texto", "claves": ""}]


def test_con_dos_camaras_se_abre_la_que_dijiste(monkeypatch):
    from lina.nucleo import comandos as C
    monkeypatch.setattr(C, "_predeterminada", lambda tipo: "")
    r = C.buscar_app("abre la cámara", _camaras())
    assert r[0][0] < 100 and r[1][0] < 100 or r[0][0] == r[1][0]            # sin recuerdo, no hay una elegida: se pregunta o decide la IA
    M.recordar("mi cámara favorita es Kamoso")
    r = C.buscar_app("abre la cámara", _camaras())
    assert r[0][1]["nombre"] == "Kamoso" and r[0][0] == 100 and all(p < 100 for p, _ in r[1:])


def test_un_recuerdo_que_nombra_dos_no_decide(monkeypatch):
    from lina.nucleo import comandos as C
    monkeypatch.setattr(C, "_predeterminada", lambda tipo: "")
    M.recordar("mi cámara es Cheese o Kamoso según el día")
    r = C.buscar_app("abre la cámara", _camaras())
    assert not (r[0][0] == 100 and r[1][0] < 100)


def test_sin_recuerdo_se_usa_el_predeterminado_del_sistema_para_otros_tipos(monkeypatch):
    from lina.nucleo import comandos as C
    pedidos = []
    monkeypatch.setattr(C, "_predeterminada", lambda tipo: pedidos.append(tipo) or "org.kde.kate")
    r = C.buscar_app("abre el editor de texto", _camaras())
    assert pedidos == ["text/plain"] and r[0][1]["nombre"] == "Kate" and r[0][0] == 100


def test_un_atajo_no_se_salta_lo_que_pediste_recordar(archivo):
    import sys
    from unittest.mock import MagicMock
    for m in ("sounddevice", "faster_whisper"):
        sys.modules.setdefault(m, MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    assert not a._hay_recuerdos_pertinentes("sube el volumen")
    M.recordar("quiero el volumen siempre al 40 por ciento")
    assert a._hay_recuerdos_pertinentes("sube el volumen")
    assert not a._hay_recuerdos_pertinentes("abre Firefox")
