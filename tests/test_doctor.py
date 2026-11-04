# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import pytest

from lina.nucleo import doctor as D


class Todo(D.Sondas):
    """Un equipo en perfecto estado."""
    def sistema(self): return {"distro": "Arch Linux", "familia": "arch", "gestor": "pacman", "escritorio": "kde", "sesion": "wayland"}
    def python(self): return (3, 12, 1)
    def python_origen(self): return "uv", True
    def base_que_falta(self): return []
    def audio(self): return "pipewire"
    def escritorio(self): return "KDE Plasma (wayland)", {"ventana": ("kdotool", ""), "captura": ("spectacle", ""), "portapapeles": ("wl-copy", "")}, []
    def microfonos(self): return ["Micrófono integrado"]
    def modelos(self): return {"whisper": True, "voz": "es_MX-claude-high", "voz_integra": True}
    def tarjeta(self): return True, True
    def clave(self): return "llavero"
    def llavero(self): return True
    def busqueda(self): return "tavily", "llavero", ""
    def servicio(self): return "activo"
    def proceso(self): return True
    def atajo(self): return True
    def enlace(self): return True
    def ajustes(self):
        class A:
            def get(self, s, k): return {"perfil": "autonomo", "capturas": "si"}[k]
        return A()
    def red(self): return True
    def probar_clave(self): return True, "funciona"


def estados(res):
    return {tema: e for e, tema, *_ in res}


def test_equipo_sano_sale_en_orden():
    res = D.comprobar(Todo(), red=True)
    assert all(e == D.OK for e, *_ in res), [r for r in res if r[0] != D.OK]
    assert D.principal([], Todo(), salida=lambda t: None) == 0


def test_cada_fallo_dice_como_arreglarlo():
    class Roto(Todo):
        def base_que_falta(self): return ["portaudio"]
        def modelos(self): return {"whisper": False, "voz": None, "voz_integra": False}
        def clave(self): return ""
        def servicio(self): return "inactivo"
        def microfonos(self): return []
    res = D.comprobar(Roto())
    e = estados(res)
    for tema in ("Paquetes del sistema", "Whisper (voz a texto)", "Voz de Lina", "Clave de Gemini", "Servicio", "Micrófono"):
        assert e[tema] == D.MAL, tema
    assert all(arreglo for est, tema, det, arreglo in res if est == D.MAL)
    assert D.principal([], Roto(), salida=lambda t: None) == 1


def test_una_sonda_que_revienta_no_tumba_el_diagnostico():
    class Explota(Todo):
        def audio(self): raise RuntimeError("boom")
        def microfonos(self): raise OSError("PortAudio library not found")
        def modelos(self): raise ValueError("x")
        def ajustes(self): raise ValueError("config rota")
    res = D.comprobar(Explota())
    e = estados(res)
    assert e["Sonido"] == D.AVISO and e["Micrófono"] == D.MAL and e["Modelos"] == D.AVISO and e["Ajustes"] == D.MAL


def test_voz_corrupta_se_senala():
    class Corrupta(Todo):
        def modelos(self): return {"whisper": True, "voz": "x", "voz_integra": False}
    assert estados(D.comprobar(Corrupta()))["Voz de Lina"] == D.MAL


def test_sin_red_y_clave_invalida():
    class SinRed(Todo):
        def red(self): raise OSError("no")
    assert estados(D.comprobar(SinRed(), red=True))["Red"] == D.MAL

    class Mala(Todo):
        def probar_clave(self): return False, "Google dice que esa clave no es válida"
    assert estados(D.comprobar(Mala(), red=True))["Clave en uso"] == D.MAL


def test_sin_red_no_se_prueba_nada_de_red():
    class Prohibida(Todo):
        def red(self): raise AssertionError("no debe llamarse sin --red")
    assert "Red" not in estados(D.comprobar(Prohibida()))


def test_el_informe_no_lleva_datos_personales():
    home, usuario, equipo = "/ho" + "me/ana", "ana", "portatil-ana"          # (partidos para que el detector de rastros no los tome por reales)
    correo = usuario + "@" + "ejemplo.invalid"
    clave = "AI" + "za" + "SyD-abcdefghijklmnopqrstuvwxyz123456"
    texto = (f"Carpeta {home}/.config/lina · usuario {usuario} · equipo {equipo} · ip 192.168.1.40 · mac aa:bb:cc:dd:ee:ff\n"
             f"correo {correo} · clave {clave}")
    sal = D.anonimizar(texto, home=home, usuario=usuario, equipo=equipo)
    for dato in (usuario, "192.168", "aa:bb", "SyD-abc", "ejemplo", "portatil"):
        assert dato not in sal, dato
    assert "~/.config/lina" in sal


def test_informe_completo_no_filtra_el_usuario():
    sal = []
    D.principal(["--informe"], Todo(), salida=sal.append, home="/ho" + "me/zoe", usuario="zoe", equipo="mipc")
    assert "/ho" + "me/zoe" not in sal[0] and "Lina " in sal[0]


def test_estado_del_servicio_lo_que_dice_systemctl_de_verdad():
    assert D.estado_servicio("active\n") == "activo"
    assert D.estado_servicio("failed\n") == "failed" and D.estado_servicio("") == "inactivo"


def test_escritorio_sin_herramientas_dice_que_instalar():
    class Pelado(Todo):
        def escritorio(self):
            return "sway (wayland)", {"ventana": ("swaymsg", ""), "captura": (None, "no hay programa de captura: instala grim"),
                                       "portapapeles": (None, "no hay programa de portapapeles: instala wl-clipboard")}, ["grim", "wl-clipboard"]
    res = D.comprobar(Pelado())
    e = {t: (est, arreglo) for est, t, d, arreglo in res}
    assert e["Captura de pantalla"][0] == D.MAL and "grim" in e["Captura de pantalla"][1]
    assert e["Portapapeles"][0] == D.AVISO and e["Ventana activa"][0] == D.OK


def test_aviso_de_gnome_wayland_sale_como_aviso():
    class Gnome(Todo):
        def escritorio(self):
            return "GNOME (wayland)", {"ventana": ("xdotool", "solo ven XWayland"), "captura": ("gnome-screenshot", ""), "portapapeles": ("wl-copy", "")}, []
    assert estados(D.comprobar(Gnome()))["Ventana activa"] == D.AVISO


class _IA:
    def __init__(self, nombre, local=False):
        self.nombre, self.local, self.rapido = nombre, local, ["m"]
    def listo(self): return True, ""
    def servidor(self): return ("ejemplo.test", 443)


@pytest.mark.parametrize("modo, tavily, pago, ia, estado, con_arreglo, texto", [
    ("auto", "", "", "gemini", D.AVISO, True, "solo Wikipedia y wikis de juegos"),
    ("auto", "llavero", "", "gemini", D.OK, False, "Tavily (clave en llavero)"),
    ("auto", "", "archivo", "gemini", D.OK, False, "Gemini con tu clave de pago"),
    ("tavily", "llavero", "", "gemini", D.OK, True, "solo Tavily, clave guardada en llavero"),
    ("tavily", "", "", "gemini", D.OK, True, "sin datos de hoy"),
    ("google", "", "archivo", "gemini", D.OK, False, "clave de pago"),
    ("google", "llavero", "", "gemini", D.AVISO, True, "no funcionará"),
    ("google", "", "archivo", "ollama", D.AVISO, True, "solo existe con Gemini"),
    ("ninguna", "", "", "gemini", D.OK, False, "desactivada"),
])
def test_linea_de_la_busqueda(modo, tavily, pago, ia, estado, con_arreglo, texto):
    class Con(Todo):
        def busqueda(self): return modo, tavily, pago
        def ia(self): return _IA(ia, local=ia == "ollama")
    linea = [r for r in D.comprobar(Con()) if r[1] == "Búsqueda en internet"]
    assert len(linea) == 1
    est, _, det, arreglo = linea[0]
    assert est == estado and texto in det
    assert bool(arreglo) == con_arreglo
    if modo == "tavily":                                                        # lo conserva quien lo eligió, y se le explica qué implica
        assert ("lina clave tavily" if not tavily else "ia.busqueda auto") in arreglo
    if modo == "auto" and not (tavily or pago):
        assert "Tavily" in arreglo and "lina bienvenida" in arreglo
    if modo == "google" and ia == "gemini" and not pago:
        assert "gemini_pago" in arreglo and "ia.busqueda auto" in arreglo


def test_sin_tavily_sigue_todo_en_orden():
    class SinTavily(Todo):
        def busqueda(self): return "tavily", "", ""
    assert D.principal([], SinTavily(), salida=lambda t: None) == 0


def test_la_busqueda_que_revienta_no_tumba_el_diagnostico():
    class Explota(Todo):
        def busqueda(self): raise ValueError("config rota")
    e = {tema: est for est, tema, *_ in D.comprobar(Explota())}
    assert e["Búsqueda en internet"] == D.AVISO and "Servicio" in e


def test_la_sonda_lee_el_ajuste_y_no_las_claves(monkeypatch):
    vistas = []
    monkeypatch.setattr(D.CL, "donde_esta", lambda n: vistas.append(n) or "")
    monkeypatch.setattr(D.CL, "obtener", lambda n: pytest.fail("no debe leer la clave"))
    class Aj:
        def get(self, s, k): return {("ia", "busqueda"): "ninguna"}[(s, k)]
    monkeypatch.setattr(D.AJ, "actuales", lambda log=None: Aj())
    assert D.Sondas().busqueda() == ("ninguna", "", "")
    assert vistas == ["tavily", "gemini_pago"]


@pytest.mark.parametrize("version, origen, hay_uv, estado", [((3, 14, 8), "uv", True, D.OK), ((3, 14, 8), "sistema", False, D.OK),
                                                            ((3, 14, 8), "sistema", True, D.AVISO), ((3, 15, 0), "uv", True, D.MAL), ((3, 10, 2), "sistema", False, D.MAL)])
def test_la_linea_de_python_dice_rango_y_origen(version, origen, hay_uv, estado):
    class S(Todo):
        def python(self): return version
        def python_origen(self): return origen, hay_uv
    [(e, _, detalle, arreglo)] = [x for x in D.comprobar(S()) if x[1] == "Python"]
    assert e == estado and ("de uv" if origen == "uv" else "del sistema") in detalle
    assert ("instalador" in arreglo) is (estado != D.OK)


def test_el_origen_real_se_lee_sin_romperse():
    origen, hay_uv = D.Sondas().python_origen()
    assert origen in ("uv", "sistema") and isinstance(hay_uv, bool)


@pytest.mark.parametrize("tarjeta, procesador, estado", [
    ((True, True), "auto", D.OK), ((True, False), "auto", D.AVISO), ((True, False), "cpu", None), ((False, False), "auto", None),
])
def test_la_linea_de_la_tarjeta_nvidia(tarjeta, procesador, estado):
    """El driver ve la tarjeta aunque falten cuBLAS y cuDNN: entonces Whisper va en la CPU, y el doctor dice cómo arreglarlo."""
    class Equipo(Todo):
        def tarjeta(self): return tarjeta
        def ajustes(self):
            class A:
                def get(self, s, k): return {"perfil": "autonomo", "capturas": "si", "reconocimiento_procesador": procesador}[k]
            return A()
    fila = [r for r in D.comprobar(Equipo()) if r[1] == "Tarjeta NVIDIA para la voz"]
    assert [f[0] for f in fila] == ([estado] if estado else [])
    if estado == D.AVISO:
        assert fila[0][3] == "lina modelos gpu" and "CPU" in fila[0][2]


def test_la_tarjeta_que_revienta_no_tumba_el_diagnostico():
    class Equipo(Todo):
        def tarjeta(self): raise OSError("driver roto")
    assert "Tarjeta NVIDIA para la voz" not in estados(D.comprobar(Equipo()))


@pytest.mark.parametrize("tipo, texto", [("gratis", "en las pruebas tu clave de Gemini no ha podido usarla"), ("pago", "tope de gasto")])
def test_la_busqueda_de_google_bloqueada_dice_por_que_y_cuando_vuelve(tipo, texto):
    class Con(Todo):
        def busqueda(self): return "auto", "", ("archivo" if tipo == "pago" else "")
        def busqueda_detalle(self): return False, None, [(tipo, 1_800_000_000.0, None)]
    fila = [r for r in D.comprobar(Con()) if r[1] == "Búsqueda de Google"]
    assert len(fila) == 1 and fila[0][0] == D.AVISO and texto in fila[0][2]
    assert ("al cambiar la clave" in fila[0][2]) and ("mañana" in fila[0][2]) is (tipo == "pago")
    assert "no puede" not in fila[0][2]                                       # solo lo medido: «no ha podido»


def test_duckduckgo_encendido_avisa_y_si_bloqueo_no_promete_arreglarlo(monkeypatch):
    import time
    class Con(Todo):
        def busqueda(self): return "auto", "llavero", ""
        def busqueda_detalle(self): return True, time.time() - 60, []
    fila = [r for r in D.comprobar(Con()) if r[1] == "DuckDuckGo"]
    assert len(fila) == 1 and fila[0][0] == D.AVISO
    assert "poco fiable" in fila[0][2] and "dirección IP" in fila[0][2] and "no lo esquiva" in fila[0][2]
    assert fila[0][3] == "lina config poner ia.busqueda_reserva false"


def test_duckduckgo_apagado_no_sale():
    class Con(Todo):
        def busqueda_detalle(self): return False, 1.0, []
    assert "DuckDuckGo" not in estados(D.comprobar(Con()))

