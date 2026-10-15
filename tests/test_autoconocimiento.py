import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import autoconocimiento as AUTO


@pytest.fixture
def aj(tmp_path):
    return AJ.Ajustes(tmp_path / "config.toml", log=lambda m: None)


def test_la_ayuda_trae_comandos_ajustes_con_valor_y_voces(aj):
    t = AUTO.ayuda(aj=aj)
    assert "lina voz" in t and "lina config poner" in t
    assert "voz.velocidad = 1.0" in t and "autonomia.perfil = " in t
    assert "es_ES-davefx-medium" in t and "no lo inventes" in t         # solo consta el género de dos voces: de las demás se le dice que no lo invente
    assert "femenina (por defecto)" in t and "masculina" in t


def test_los_manuales_se_leen_enteros(aj):
    assert "configuracion" in AUTO.manuales()
    assert "Perfiles de autonomía" in AUTO.ayuda("configuracion", aj)
    assert "No hay manual" in AUTO.ayuda("nada", aj)


def test_cambiar_un_ajuste_normal(aj):
    ok, texto = AUTO.cambiar("voz.velocidad", "1.3", aj=aj)
    assert ok and aj.get("voz", "velocidad") == 1.3 and "1.3" in texto
    ok, texto = AUTO.cambiar("interfaz.indicador_color", "verde", voz_libre=True, aj=aj)      # por «Oye Lina» lo normal sí
    assert ok and aj.get("interfaz", "indicador_color") == "verde"


def test_valores_y_ajustes_que_no_valen(aj):
    assert AUTO.cambiar("voz.velocidad", "9", aj=aj)[0] is False and aj.get("voz", "velocidad") == 1.0
    assert AUTO.cambiar("voz.nada", "1", aj=aj)[0] is False


def test_dinero_y_claves_no_los_toca_la_ia(aj):
    for clave, valor in (("gasto.tope_mensual_eur", "500"), ("gasto.eur_por_usd", "1"), ("privacidad.almacen_claves", "archivo")):
        ok, texto = AUTO.cambiar(clave, valor, aj=aj)
        assert not ok and "solo el usuario" in texto
    assert aj.get("gasto", "tope_mensual_eur") == 10


def test_mas_permisos_solo_con_el_atajo_y_sin_contenido_de_fuera(aj):
    aj.establecer("autonomia", "perfil", "prudente")
    ok, texto = AUTO.cambiar("autonomia.perfil", "autonomo", voz_libre=True, aj=aj)
    assert not ok and "atajo" in texto and aj.get("autonomia", "perfil") == "prudente"
    ok, texto = AUTO.cambiar("autonomia.perfil", "autonomo", contaminado=True, aj=aj)
    assert not ok and aj.get("autonomia", "perfil") == "prudente"
    assert AUTO.cambiar("autonomia.perfil", "autonomo", aj=aj)[0] and aj.get("autonomia", "perfil") == "autonomo"
    assert AUTO.cambiar("autonomia.perfil", "prudente", voz_libre=True, contaminado=True, aj=aj)[0]      # apretar vale siempre
