import json
from types import SimpleNamespace

from lina.escritorio import sesion as S


def hay(*programas):
    return lambda p: "/usr/bin/" + p if p in programas else None


def falso(respuestas, registro=None):
    """ejecutar falso: respuestas = {('xdotool', 'getactivewindow'): 'salida', …} por los primeros elementos de la orden."""
    def ejecutar(orden, **k):
        if registro is not None:
            registro.append(list(orden))
        for clave, valor in respuestas.items():
            if tuple(orden[:len(clave)]) == clave:
                if callable(valor):
                    return valor(orden)
                return SimpleNamespace(returncode=0, stdout=valor, stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="no")
    return ejecutar


def sesion(desktop, tipo, programas=(), respuestas=None, registro=None, extra=None):
    env = {"XDG_CURRENT_DESKTOP": desktop, "XDG_SESSION_TYPE": tipo, **(extra or {})}
    return S.Sesion(env, ejecutar=falso(respuestas or {}, registro), which=hay(*programas))


# ---------------------------------------------------------------- detección
def test_detecta_los_escritorios_de_verdad():
    casos = {"KDE": "kde", "ubuntu:GNOME": "gnome", "GNOME": "gnome", "X-Cinnamon": "cinnamon", "XFCE": "xfce", "MATE": "mate", "LXQt": "lxqt",
             "Budgie:GNOME": "gnome", "COSMIC": "cosmic", "sway": "sway", "Hyprland": "hyprland", "": "otro", "i3": "otro"}
    for valor, esperado in casos.items():
        assert S.detectar({"XDG_CURRENT_DESKTOP": valor, "XDG_SESSION_TYPE": "x11"})["escritorio"] == esperado, valor


def test_las_variables_del_compositor_mandan():
    assert S.detectar({"SWAYSOCK": "/run/sway.sock"})["escritorio"] == "sway"
    assert S.detectar({"HYPRLAND_INSTANCE_SIGNATURE": "abc", "XDG_CURRENT_DESKTOP": "KDE"})["escritorio"] == "hyprland"


def test_sesion_se_deduce_si_falta_el_tipo():
    assert S.detectar({"WAYLAND_DISPLAY": "wayland-0"})["sesion"] == "wayland"
    assert S.detectar({"DISPLAY": ":0"})["sesion"] == "x11"
    assert S.detectar({})["sesion"] == "desconocida"
    assert S.detectar({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"})["xwayland"] is True


# ---------------------------------------------------------------- ventana activa
def test_kde_usa_kdotool_como_siempre():
    s = sesion("KDE", "wayland", ["kdotool", "xdotool"], {("kdotool", "getactivewindow", "getwindowname"): "Skyrim",
                                                          ("kdotool", "getactivewindow", "getwindowclassname"): "steam_app_72850",
                                                          ("kdotool", "getactivewindow", "getwindowpid"): "4242"})
    assert s.ventana_activa() == {"titulo": "Skyrim", "clase": "steam_app_72850", "pid": 4242, "metodo": "kdotool"}


def test_x11_con_xdotool_y_xprop():
    s = sesion("XFCE", "x11", ["xdotool", "xprop"], {("xdotool", "getactivewindow"): "123", ("xdotool", "getwindowname"): "Terminal",
                                                      ("xdotool", "getwindowpid"): "77", ("xprop",): 'WM_CLASS(STRING) = "xfce4-terminal", "Xfce4-terminal"'})
    v = s.ventana_activa()
    assert v["titulo"] == "Terminal" and v["clase"] == "Xfce4-terminal" and v["pid"] == 77 and v["metodo"] == "xdotool"


def test_sway_lee_la_ventana_con_foco():
    arbol = {"nodes": [{"nodes": [{"focused": False, "name": "otra", "app_id": "x", "pid": 1},
                                  {"focused": True, "name": "Firefox", "app_id": "firefox", "pid": 99, "rect": {"x": 10, "y": 20, "width": 800, "height": 600}}]}]}
    s = sesion("sway", "wayland", ["swaymsg"], {("swaymsg", "-t", "get_tree"): json.dumps(arbol)})
    assert s.ventana_activa()["clase"] == "firefox" and s.ventana_activa()["pid"] == 99


def test_hyprland_lee_la_ventana_con_foco():
    s = sesion("Hyprland", "wayland", ["hyprctl"], {("hyprctl", "activewindow"): json.dumps({"title": "Kitty", "class": "kitty", "pid": 5, "at": [1, 2], "size": [300, 200]})})
    assert s.ventana_activa()["titulo"] == "Kitty" and s.ventana_activa()["metodo"] == "hyprctl"


def test_gnome_wayland_sin_xdotool_no_inventa_nada():
    s = sesion("ubuntu:GNOME", "wayland", [])
    v = s.ventana_activa()
    assert v == {"titulo": "", "clase": "", "pid": 0, "metodo": None}
    ventana, nota = s.capacidades()["ventana"]
    assert ventana is None and "xdotool" in nota


def test_gnome_wayland_con_xdotool_avisa_del_limite():
    s = sesion("GNOME", "wayland", ["xdotool"], {("xdotool", "getactivewindow"): "9", ("xdotool", "getwindowname"): "Juego", ("xdotool", "getwindowpid"): "3",
                                                  ("xdotool", "getwindowclassname"): "steam_app_1"})
    assert s.ventana_activa()["clase"] == "steam_app_1"
    assert "XWayland" in s.capacidades()["ventana"][1]


def test_una_ventana_vacia_pasa_al_siguiente_metodo():
    s = sesion("KDE", "wayland", ["kdotool", "xdotool"], {("kdotool",): lambda o: SimpleNamespace(returncode=1, stdout="", stderr=""),
                                                          ("xdotool", "getactivewindow"): "5", ("xdotool", "getwindowname"): "Algo",
                                                          ("xdotool", "getwindowpid"): "8", ("xdotool", "getwindowclassname"): "algo"})
    assert s.ventana_activa()["metodo"] == "xdotool"


def test_la_ventana_se_reutiliza_unos_instantes():
    reg = []
    s = sesion("XFCE", "x11", ["xdotool"], {("xdotool", "getactivewindow"): "1", ("xdotool", "getwindowname"): "T", ("xdotool", "getwindowpid"): "2",
                                            ("xdotool", "getwindowclassname"): "c"}, reg)
    s.ventana_activa()
    n = len(reg)
    s.ventana_activa()
    assert len(reg) == n and s.ventana_activa(vigencia=0)["titulo"] == "T"


# ---------------------------------------------------------------- captura
def captura_que_escribe(destino_idx=-1, contenido=b"png"):
    def f(orden):
        from pathlib import Path
        Path(orden[destino_idx]).write_bytes(contenido)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return f


def test_kde_captura_con_spectacle(tmp_path):
    reg = []
    s = sesion("KDE", "wayland", ["spectacle"], {("spectacle",): captura_que_escribe()}, reg)
    d = tmp_path / "c.png"
    assert s.capturar(d, activa=True) and reg[0] == ["spectacle", "-b", "-n", "-a", "-o", str(d)]
    assert s.capturar(d, activa=False) and reg[1][3] == "-f"


def test_gnome_x11_y_wayland_usan_gnome_screenshot(tmp_path):
    reg = []
    s = sesion("GNOME", "wayland", ["gnome-screenshot", "scrot"], {("gnome-screenshot",): captura_que_escribe()}, reg)
    assert s.capturar(tmp_path / "c.png", activa=True) and reg[0][:2] == ["gnome-screenshot", "-w"]


def test_sway_recorta_con_grim_a_la_ventana_activa(tmp_path):
    arbol = {"nodes": [{"focused": True, "name": "F", "app_id": "firefox", "pid": 9, "rect": {"x": 10, "y": 20, "width": 800, "height": 600}}]}
    reg = []
    s = sesion("sway", "wayland", ["grim", "swaymsg"], {("swaymsg",): json.dumps(arbol), ("grim",): captura_que_escribe()}, reg)
    d = tmp_path / "c.png"
    assert s.capturar(d, activa=True) and ["grim", "-g", "10,20 800x600", str(d)] in reg
    assert s.capturar(d, activa=False) and ["grim", str(d)] in reg


def test_x11_prueba_el_siguiente_si_el_primero_falla(tmp_path):
    reg = []
    s = sesion("XFCE", "x11", ["xfce4-screenshooter", "scrot"], {("xfce4-screenshooter",): lambda o: SimpleNamespace(returncode=1, stdout="", stderr=""),
                                                                  ("scrot",): captura_que_escribe()}, reg)
    d = tmp_path / "c.png"
    assert s.capturar(d, activa=True) and [r[0] for r in reg] == ["xfce4-screenshooter", "scrot"] and reg[1] == ["scrot", "-u", str(d)]


def test_captura_vacia_no_cuenta_como_exito(tmp_path):
    s = sesion("KDE", "wayland", ["spectacle"], {("spectacle",): captura_que_escribe(contenido=b"")})
    assert not s.capturar(tmp_path / "c.png")


def test_sin_programa_de_captura_lo_dice(tmp_path):
    s = sesion("sway", "wayland", [])
    assert not s.capturar(tmp_path / "c.png") and "grim" in s.capacidades()["captura"][1]


def test_en_wayland_no_se_usan_las_herramientas_de_x11():
    assert S.Sesion({"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}).programas_captura()[0] == "gnome-screenshot"
    ordenado = S.Sesion({"XDG_CURRENT_DESKTOP": "sway", "XDG_SESSION_TYPE": "wayland"}).programas_captura()
    assert ordenado[0] == "grim" and not {"scrot", "maim", "import"} & set(ordenado)             # en Wayland darían imagen negra: ni se prueban
    assert "scrot" in S.Sesion({"XDG_CURRENT_DESKTOP": "XFCE", "XDG_SESSION_TYPE": "x11"}).programas_captura()


# ---------------------------------------------------------------- portapapeles
def test_wayland_copia_con_wl_copy_y_pega_con_wl_paste():
    reg = []
    s = sesion("KDE", "wayland", ["wl-copy", "wl-paste"], {("wl-copy",): "", ("wl-paste",): "https://ejemplo.invalid"}, reg)
    assert s.copiar("hola") and s.pegar() == "https://ejemplo.invalid" and reg[0] == ["wl-copy"] and reg[1] == ["wl-paste", "-n"]


def test_x11_copia_con_xclip_y_cae_a_xsel():
    reg = []
    s = sesion("XFCE", "x11", ["xclip", "xsel"], {("xclip",): lambda o: SimpleNamespace(returncode=1, stdout="", stderr=""), ("xsel",): ""}, reg)
    assert s.copiar("hola") and [r[0] for r in reg] == ["xclip", "xsel"]


def test_sin_portapapeles_no_finge():
    s = sesion("XFCE", "x11", [])
    assert not s.copiar("hola") and s.pegar() == "" and "xclip" in s.capacidades()["portapapeles"][1]


# ---------------------------------------------------------------- qué sabe la IA
def test_la_ia_sabe_lo_que_no_puede():
    s = sesion("sway", "wayland", [])
    texto = "\n".join(s.describir())
    assert "NO puedes" in texto and "capturar la pantalla" in texto and "no lo finjas" in texto and "KDE" in texto


def test_en_kde_no_se_dice_que_falten_herramientas_de_kde():
    s = sesion("KDE", "wayland", ["kdotool", "spectacle", "wl-copy"])
    assert "no valen aquí" not in "\n".join(s.describir())


def test_principal_lista_capacidades():
    salida = []
    S.principal([], sesion("KDE", "wayland", ["spectacle"]), salida.append)
    assert "KDE Plasma (wayland)" in salida[0] and any("captura: spectacle" in l for l in salida)


def test_paquetes_que_faltan_segun_el_escritorio():
    assert sesion("XFCE", "x11", []).paquetes_que_faltan() == ["xfce4-screenshooter", "xclip", "xdotool"]
    assert sesion("sway", "wayland", []).paquetes_que_faltan() == ["grim", "wl-clipboard"]
    assert sesion("KDE", "wayland", ["spectacle", "wl-copy"]).paquetes_que_faltan() == []          # kdotool no se pide: no está en todos los repositorios
    assert sesion("GNOME", "wayland", ["gnome-screenshot", "wl-copy", "xdotool"]).paquetes_que_faltan() == []
    from lina.nucleo import plataforma as PL
    for esc, tipo in (("XFCE", "x11"), ("sway", "wayland"), ("GNOME", "wayland"), ("KDE", "wayland")):
        for logico in sesion(esc, tipo, []).paquetes_que_faltan():
            assert logico in PL.PAQUETES, logico


def test_wayland_sin_programa_valido_no_usa_scrot(tmp_path):
    reg = []
    s = sesion("GNOME", "wayland", ["scrot", "import"], {("scrot",): captura_que_escribe(), ("import",): captura_que_escribe()}, reg)
    assert not s.capturar(tmp_path / "c.png") and reg == [] and s.capacidades()["captura"][0] is None


def test_el_resplandor_avisa_de_sus_limites():
    assert sesion("GNOME", "wayland", []).capacidades()["indicador"][0] == "ventana"
    assert "pitidos" in sesion("GNOME", "wayland", []).capacidades()["indicador"][1]
    assert sesion("KDE", "wayland", []).capacidades()["indicador"] == ("capa", "")
    assert sesion("sway", "wayland", []).capacidades()["indicador"] == ("capa", "")
    assert "compositor" in sesion("XFCE", "x11", []).capacidades()["indicador"][1]
