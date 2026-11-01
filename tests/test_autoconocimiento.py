# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
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
    assert "es_ES-sharvard-medium-1" in t and "no lo inventes" in t     # solo consta el género de las voces que lo dicen: de las demás se le dice que no lo invente
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


# ---------------------------------------------------------------- ayuda reducida y su coherencia con lo que Lina tiene de verdad (punto 3)
import inspect  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from lina import __main__ as PRINCIPAL  # noqa: E402
from lina.nucleo import clasificador as CLA  # noqa: E402
from lina.nucleo import grupos as G  # noqa: E402
from lina.nucleo import herramientas as H  # noqa: E402
from lina.nucleo import ia as IA  # noqa: E402

NOMBRES = {d["name"] for d in H.DECLARACIONES} | {d["name"] for d in IA.HERRAMIENTA_BUSCAR["functionDeclarations"]} | {G.META}
REALES = ["Revisa a ver cómo funcionas y respóndeme a ver si yo te puedo dar como una fuente, una página web.",
          "Pero yo me refiero a que en vez de buscar tú en las páginas oficiales, que yo te doy una página y tú buscas en la página que yo te doy.",
          "Claro, pero yo quiero que revises cómo funciona la aplicación, a ver cómo funcionas tú por dentro, a ver si te puedo dejar en algún sitio la URL."]


@pytest.mark.parametrize("frase", REALES + ["¿Qué puedes hacer?", "¿Puedes usar una fuente que te dé?", "¿Hay alguna forma de pasarte una lista?"])
def test_las_preguntas_sobre_ella_cargan_su_ayuda(frase):
    assert G.pregunta_por_mi(frase) and "yo" in G.elegir(frase)


@pytest.mark.parametrize("frase", ["Ábreme Steam", "Sube el volumen", "Dime la hora", "Pon música", "¿Qué tiempo hace?"])
def test_lo_demas_no(frase):
    assert not G.pregunta_por_mi(frase)


def test_el_resumen_sale_de_las_herramientas_de_verdad():
    t = AUTO.resumen()
    assert all(n in t for n in G.NUCLEO) and all(g in t for g in G.GRUPOS) and all(m in t for m in AUTO.manuales()) and "uso" in AUTO.manuales()
    assert "Si no consta, di que no lo sabes" in t and len(t) < 3000                # reducida: la ayuda completa son 14 000 caracteres
    assert "buscar_web" not in AUTO.resumen(False).split("Límites:")[0]


def test_cada_herramienta_que_nombra_existe():
    nombradas = set(re.findall(r"\b[a-z]+_[a-z_]+\b", AUTO.resumen()))
    assert nombradas and nombradas <= NOMBRES | set(G.GRUPOS) | {"usar_fuente"}, nombradas - NOMBRES    # usar_fuente no es de las de siempre: solo se ofrece con fuentes guardadas
    assert set(G.NUCLEO) <= NOMBRES and all(set(h) <= NOMBRES for h in G.GRUPOS.values())


def test_cada_comando_que_nombra_existe():
    for orden in re.findall(r"\blina [a-z]+", " ".join(AUTO.LIMITES)):
        assert orden in PRINCIPAL.AYUDA, orden


def test_los_limites_siguen_siendo_verdad_en_el_codigo():
    # no hay ninguna herramienta para escribir en la memoria ni para guardar fuentes
    assert not {n for n in NOMBRES if re.search(r"recordar|memoria|fuente", n)}
    # dinero y permisos no se tocan desde aquí
    assert ("gasto", "tope_mensual_eur") in AUTO.INTOCABLES and ("privacidad", "capturas") in AUTO.INTOCABLES
    # ni contraseñas, ni cookies, ni su propio código ni sus permisos
    for orden in ("cat ~/.mozilla/firefox/x/cookies.sqlite", "yt-dlp --cookies-from-browser firefox x", "lina clave tavily", "lina config perfil autonomo",
                  "sed -i s/a/b/ ~/.config/lina/config.toml"):
        assert CLA._bloqueado(orden), orden
    # lo crítico no se confirma por voz libre ni por lina di
    sys.modules.setdefault("sounddevice", MagicMock())
    sys.modules.setdefault("faster_whisper", MagicMock())
    from lina.nucleo import asistente as A
    fuente = inspect.getsource(A.Asistente.resolver_pendientes)
    assert 'decision == "confirma" and self.origen_texto' in fuente and 'decision == "confirma" and self.origen_voz_libre' in fuente


def test_la_nota_va_con_la_peticion_pero_no_entra_en_el_historial():
    sys.modules.setdefault("sounddevice", MagicMock())
    sys.modules.setdefault("faster_whisper", MagicMock())
    from lina.nucleo import asistente as A
    a = A.Asistente.__new__(A.Asistente)
    assert "PREGUNTAN POR TI" in a._nota_sobre_mi(REALES[0]) and a._nota_sobre_mi("Ábreme Steam") == ""
    fuente = inspect.getsource(A.Asistente._atender)
    assert fuente.index("pregunta_sin_receta = pregunta") < fuente.index("_nota_sobre_mi")


def test_el_manual_de_uso_lo_ve_lina_y_sigue_en_docs():
    assert "lina di" in AUTO.ayuda("uso")
