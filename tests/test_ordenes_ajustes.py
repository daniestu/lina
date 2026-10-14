import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import ordenes_ajustes as OA


@pytest.fixture
def aj(tmp_path):
    ruta = tmp_path / "config.toml"
    AJ.escribir_privado(ruta, AJ.texto_de_fabrica())
    return AJ.Ajustes(ruta, log=lambda m: None)


def test_frases_que_si_son_ordenes():
    casos = {
        "habla más rápido": ("mover", "voz", "velocidad"), "Habla más despacio, por favor": ("mover", "voz", "velocidad"),
        "háblame a velocidad normal": ("poner", "voz", "velocidad"), "pon la velocidad de la voz a 1,3": ("poner", "voz", "velocidad"),
        "quita el resplandor": ("poner", "interfaz", "indicador"), "enciende el resplandor": ("poner", "interfaz", "indicador"),
        "pon el resplandor rojo": ("poner", "interfaz", "indicador_color"), "el resplandor más grueso": ("mover", "interfaz", "indicador_grosor"),
        "pasa al perfil prudente": ("poner", "autonomia", "perfil"), "ponte en modo autónomo": ("poner", "autonomia", "perfil"),
        "cuál es el tope de gasto": ("ver", "tope"),
    }
    for frase, esperado in casos.items():
        o = OA.entender(frase)
        assert o and o[:3] == esperado, (frase, o)


def test_frases_que_no_son_ordenes():
    for frase in ("abre más rápido el navegador", "lee más despacio este documento y resúmelo", "ponte las pilas", "modo oscuro", "qué hora es",
                  "quiero que busques un perfil de usuario autónomo para mi proyecto de empresa y me lo cuentes todo con detalle"):
        assert OA.entender(frase) is None, frase


def test_velocidad_sube_y_baja_con_limites(aj):
    assert "más rápido" in OA.aplicar(OA.entender("habla más rápido"), aj) and aj.get("voz", "velocidad") == 1.15
    for _ in range(10):
        OA.aplicar(OA.entender("habla más rápido"), aj)
    assert aj.get("voz", "velocidad") == 2.0 and "más allá" in OA.aplicar(OA.entender("habla más rápido"), aj)
    OA.aplicar(OA.entender("habla a velocidad normal"), aj)
    assert aj.get("voz", "velocidad") == 1.0


def test_resplandor_por_voz_libre_si_se_puede(aj):
    OA.aplicar(OA.entender("quita el resplandor"), aj, voz_libre=True)
    assert aj.get("interfaz", "indicador") is False
    OA.aplicar(OA.entender("pon el resplandor verde"), aj, voz_libre=True)
    assert aj.get("interfaz", "indicador_color") == "verde"


def test_apretar_se_puede_por_cualquier_via_aflojar_solo_con_el_atajo(aj):
    assert "prudente" in OA.aplicar(OA.entender("pasa al perfil prudente"), aj, voz_libre=True)
    assert aj.get("autonomia", "perfil") == "prudente"
    r = OA.aplicar(OA.entender("pasa al perfil autónomo"), aj, voz_libre=True)
    assert "atajo" in r and aj.get("autonomia", "perfil") == "prudente"                      # por «Oye Lina» no
    OA.aplicar(OA.entender("pasa al perfil autónomo"), aj, voz_libre=False)                    # con el atajo, sí
    assert aj.get("autonomia", "perfil") == "autonomo"


def test_tope_de_gasto_solo_se_consulta_aqui(aj):
    assert OA.entender("sube el tope de gasto a 50 euros") is None          # subirlo lo gestiona presupuesto.py (con la misma regla del atajo)
    assert "10 euros" in OA.aplicar(OA.entender("cuál es el tope de gasto"), aj)


def test_tope_por_voz_libre_no_sube_pero_si_baja(monkeypatch):
    from lina.nucleo import presupuesto as P
    monkeypatch.setattr(P, "hay_clave_de_pago", lambda: True)
    monkeypatch.setattr(P, "estado", lambda: {"tope_eur": 10.0})
    assert "atajo" in P.subir_tope(50, voz_libre=True)



def test_preguntas_sobre_cambiar_la_voz_se_contestan_en_local(aj):
    for frase in ("¿Cómo puedo cambiar tu voz?", "qué voces tienes", "cámbiate la voz", "cómo se cambia la voz"):
        assert OA.entender(frase) == ("ayuda", "voz"), frase
    r = OA.aplicar(OA.entender("¿Cómo puedo cambiar tu voz?"), aj)
    assert "lina voz" in r and "Claude" in r
    assert OA.entender("cómo cambio la configuración") == ("ayuda", "ajustes")
    assert OA.entender("cómo cambio la voz de este personaje en el juego de rol que estoy haciendo ahora mismo") is None
