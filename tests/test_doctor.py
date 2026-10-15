from lina.nucleo import doctor as D


class Todo(D.Sondas):
    """Un equipo en perfecto estado."""
    def sistema(self): return {"distro": "Arch Linux", "familia": "arch", "gestor": "pacman", "escritorio": "kde", "sesion": "wayland"}
    def python(self): return (3, 12, 1)
    def base_que_falta(self): return []
    def audio(self): return "pipewire"
    def microfonos(self): return ["Micrófono integrado"]
    def modelos(self): return {"whisper": True, "voz": "es_MX-claude-high", "voz_integra": True}
    def clave(self): return "llavero"
    def llavero(self): return True
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
