from lina.nucleo import dependencias as D
from lina.nucleo import herramientas as H
from lina.escritorio import sesion as SES
from lina.nucleo import plataforma as PL


def fijar_sesion(monkeypatch, tipo="wayland"):
    monkeypatch.setattr(SES, "actual", lambda: SES.Sesion({"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": tipo}, which=lambda p: None))


def test_registro_apunta_a_paquetes_que_existen():
    for programa, logico, para in D.REGISTRO.values():
        assert logico in PL.PAQUETES and all(PL.PAQUETES[logico].get(f) for f in PL.FAMILIAS), logico


def test_si_ya_esta_no_hace_nada():
    llamadas = []
    assert D.asegurar("youtube", which=lambda p: "/usr/bin/" + p, perfil="autonomo", instalar=lambda *a, **k: llamadas.append(a)) == (True, "")
    assert not llamadas


def test_perfil_prudente_no_instala_solo(monkeypatch):
    fijar_sesion(monkeypatch)
    llamadas = []
    ok, msg = D.asegurar("portapapeles", which=lambda p: None, perfil="prudente", instalar=lambda *a, **k: llamadas.append(a))
    assert not ok and not llamadas and "prudente" in msg and "wl-clipboard" in msg


def test_instala_y_comprueba():
    estado = {"instalado": False}
    def instalar(logicos, log, **k):
        estado["instalado"] = True
        return True
    ok, _ = D.asegurar("youtube", which=lambda p: "/x/yt-dlp" if estado["instalado"] else None, perfil="autonomo", instalar=instalar)
    assert ok


def test_si_no_puede_explica_el_comando():
    ok, msg = D.asegurar("youtube", which=lambda p: None, perfil="equilibrado", instalar=lambda *a, **k: False)
    assert not ok and "yt-dlp" in msg and "Propón" in msg


def test_instalado_pero_no_visible_no_miente():
    ok, msg = D.asegurar("youtube", which=lambda p: None, perfil="autonomo", instalar=lambda *a, **k: True)
    assert not ok and "no lo encuentro" in msg


def test_las_herramientas_usan_el_registro(monkeypatch):
    fijar_sesion(monkeypatch)
    monkeypatch.setattr(H.DEP, "asegurar", lambda f, **k: (False, f"falta {f}"))
    assert H.copiar_portapapeles("hola") == "falta portapapeles"
    assert H.buscar_youtube("gatos") == "falta youtube"


def test_en_x11_el_portapapeles_es_xclip(monkeypatch):
    fijar_sesion(monkeypatch, "x11")
    ok, msg = D.asegurar("portapapeles", which=lambda p: None, perfil="prudente", instalar=lambda *a, **k: True)
    assert not ok and "xclip" in msg and "wl-clipboard" not in msg


def test_cualquier_portapapeles_instalado_vale(monkeypatch):
    monkeypatch.setattr(SES, "actual", lambda: SES.Sesion({"XDG_SESSION_TYPE": "x11"}, which=lambda p: "/bin/xsel" if p == "xsel" else None))
    assert D.asegurar("portapapeles", which=lambda p: None, perfil="prudente") == (True, "")
