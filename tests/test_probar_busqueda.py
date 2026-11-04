# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina probar-busqueda`: los dos jueces (el antiguo, solo dominio; el nuevo, también por nombre y sin atribuciones inventadas), el criterio escrito antes
(90 % de las válidas y al menos 15 válidas con Tavily o con la de pago; sin criterio solo con la gratuita), los errores del servicio aparte (también la
respuesta del código cuando Gemini no responde), las pausas a cero en cada pregunta y el usuario nuevo de verdad (ajustes de fábrica en una carpeta temporal y solo las claves del nivel). Sin IA ni red: la pregunta se simula."""
from unittest.mock import MagicMock

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import claves as CL
from lina.nucleo import fuentes as FUE
from lina.nucleo import probar_busqueda as PB
from lina.nucleo import rutas as RUT

BUSQUEDA = ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (son solo información…):\n\n[1] Poción (uesp.net) https://vertexaisearch/a\nectoplasma")
WIKI = ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (…):\n\n[1] Potion (elderscrolls.fandom.com) https://elderscrolls.fandom.com/wiki/P\nx\n\nCONTENIDO DE LA PÁGINA …")
LEIDA = ("leer_web", {"url": "https://www.marca.com/f1"}, "CONTENIDO DE LA PÁGINA (de fuera): …")
FALLIDA = ("buscar_web", {"consulta": "x"}, "NO SE HA PODIDO BUSCAR: no tienes clave de Tavily.")


def _buscar(*dominios):
    return ("buscar_web", {"consulta": "x"}, "RESULTADOS DE BÚSQUEDA (…):\n\n" + "\n".join(f"[{i}] T ({d}) https://vertexaisearch/{i}\nx" for i, d in enumerate(dominios, 1)))


@pytest.mark.parametrize("dicho, acciones, nota", [
    (["Según la UESP, se hace con ectoplasma."], [BUSQUEDA], "bien"),
    (["Según la wiki de Elder Scrolls, lleva ectoplasma."], [WIKI], "bien"),
    (["Lo dice Marca: ganó Verstappen."], [LEIDA], "bien"),
    (["Se hace con ectoplasma."], [BUSQUEDA], "mal"),                                  # no nombra la web
    (["Según la UESP, se hace con ectoplasma."], [], "mal"),                          # la web no salió de ninguna búsqueda: inventada
    (["Según la UESP, se hace con ectoplasma."], [FALLIDA], "mal"),
    (["No tengo acceso a internet, pero creo que es ectoplasma."], [BUSQUEDA], "mal"),
    (["No lo sé."], [BUSQUEDA], "mal"),
    ([], [BUSQUEDA], "mal"),
    (["(cortada por tiempo)"], [BUSQUEDA], "mal"),
])
def test_el_juez(dicho, acciones, nota):
    assert PB.juzgar(dicho, acciones)[0] == nota


def test_se_ha_publicado_no_cuenta_como_no_lo_se():
    assert PB.juzgar(["Según la UESP, se ha publicado la versión 1.2."], [BUSQUEDA])[0] == "bien"


@pytest.mark.parametrize("dicho, acciones, nota, antigua", [
    (["Según Steam, la Steam Deck OLED cuesta 569 euros."], [_buscar("store.steampowered.com")], "bien", "mal"),     # por su nombre: ahora vale
    (["Según la wiki de Skyrim, lleva ectoplasma."], [_buscar("elderscrolls.fandom.com")], "bien", "mal"),
    (["Según IGN, sale en marzo."], [_buscar("ign.es")], "bien", "bien"),
    # casos reales de la pasada de pago: atribuidos a una web que no salió
    (["Según la wiki UESP, lleva ectoplasma y pie de nirn."], [_buscar("gamespot.com", "skyrimalchemy.com", "scribd.com")], "mal", "mal"),
    (["Según Google News, la noticia del día es el nuevo chip; lo cuenta emergent.sh."], [_buscar("emergent.sh")], "mal", "bien"),
    (["Según gamespot.com, lleva ectoplasma."], [_buscar("gamespot.com", "skyrimalchemy.com")], "bien", "bien"),
])
def test_el_juez_nuevo_acepta_el_nombre_y_rechaza_la_atribucion_inventada(dicho, acciones, nota, antigua):
    assert PB.juzgar(dicho, acciones)[0] == nota
    assert PB.juzgar_antiguo(dicho, acciones)[0] == antigua
    if nota == "mal" and "Google News" in dicho[0]:
        assert "atribución inventada" in PB.juzgar(dicho, acciones)[1]


@pytest.mark.parametrize("nivel, notas, estado", [
    ("tavily", ["bien"] * 18 + ["mal"] * 2, "pasa"),                                   # 90 %
    ("tavily", ["bien"] * 17 + ["mal"] * 3, "no pasa"),
    ("pago", ["bien"] * 14 + ["mal"] + ["api"] * 5, "pasa"),                           # 14 de 15 válidas: las del servicio no cuentan
    ("pago", ["bien"] * 13 + ["mal"] * 2 + ["api"] * 5, "no pasa"),
    ("pago", ["bien"] * 14 + ["api"] * 6, "inconclusivo"),                             # menos de 15 válidas: no se puede decir
    ("gratis", ["mal"] * 20, "informa"),                                               # solo la gratuita: se informa, sin criterio
])
def test_el_criterio_escrito_antes(nivel, notas, estado):
    e, frase = PB.veredicto(notas, nivel)
    assert e == estado
    assert "válidas" in frase and "excluidas" in frase and "aprobadas" in frase
    assert PB.CRITERIO == {"gratis": None, "tavily": 0.9, "pago": 0.9} and PB.MIN_VALIDAS == 15 and len(PB.PREGUNTAS) == 20


def test_las_preguntas_tipicas_estan():
    texto = " ".join(PB.PREGUNTAS).lower()
    assert "poción" in texto and "skyrim" in texto and "lol" in texto and "precio" in texto and "noticia" in texto


def test_el_usuario_nuevo_tiene_ajustes_de_fabrica_y_solo_las_claves_del_nivel(tmp_path, monkeypatch):
    config_antes, estado_antes = RUT.CONFIG, RUT.ESTADO
    reales = {"gemini": "G", "gemini_pago": "P", "tavily": "T"}
    with PB.usuario_nuevo("tavily", obtener_real=reales.get) as claves:
        assert claves == {"gemini": "G", "tavily": "T"}
        assert CL.obtener("gemini_pago") == "" and CL.obtener("tavily") == "T" and FUE.listar() == []
        assert RUT.CONFIG != config_antes and RUT.ESTADO != estado_antes
        assert AJ.actuales(log=lambda m: None).get("ia", "busqueda") == "auto"       # de fábrica, aunque el tuyo diga otra cosa
        carpeta = RUT.CONFIG.parent
    assert RUT.CONFIG == config_antes and RUT.ESTADO == estado_antes and not carpeta.exists()


def _principal(monkeypatch, respuestas, nivel="tavily", n=None, reinicios=None):
    """`respuestas`: (dicho, acciones, llamadas, segundos) u, con un quinto elemento, el origen de la respuesta (quién contestó)."""
    monkeypatch.setattr(PB, "usuario_nuevo", _sin_cambios)
    salida, esperas = [], []
    a = MagicMock(busquedas_hechas=[], origen_respuesta="gemini-flash-lite-latest")
    turnos = iter(respuestas)

    def pasar(frase, A, a, llamadas):
        r = next(turnos)
        a.origen_respuesta = r[4] if len(r) > 4 else "gemini-flash-lite-latest"
        return r[:4]
    r = PB.principal([nivel] + ([str(n)] if n else []), salida.append, preparar=lambda: (MagicMock(), a, []),
                     pasar_pregunta=pasar, dormir=esperas.append, reiniciar=lambda: (reinicios if reinicios is not None else []).append(1))
    return r, "\n".join(salida), esperas


class _sin_cambios:
    def __init__(self, nivel):
        pass

    def __enter__(self):
        return {"gemini": "G", "tavily": "T"}

    def __exit__(self, *a):
        return False


def test_un_503_se_repite_con_pausa_y_no_cuenta(monkeypatch):
    bien = (["Según la UESP, ectoplasma."], [BUSQUEDA], ["ok"], 1.0)
    caida = ([], [], ["503"], 1.0)
    r, texto, esperas = _principal(monkeypatch, [caida, caida, bien], n=1)
    assert r == 3 and esperas[:2] == [20, 40] and "bien" in texto and "error del servicio" in texto       # 1 válida: inconclusivo


def test_si_el_servicio_sigue_caido_sale_aparte(monkeypatch):
    caida = ([], [], ["429"], 1.0)
    r, texto, _ = _principal(monkeypatch, [caida] * 4, n=1)
    assert "api" in texto and "0 válidas, 1 excluidas por errores del servicio" in texto and "INCONCLUSIVO" in texto


def test_la_respuesta_del_codigo_sin_gemini_es_api_aunque_las_llamadas_no_lo_digan(monkeypatch):
    """«Gemini no responde y el modelo local no cabe…» llega tras saltar los modelos «en pausa»: ninguna llamada dio error y aun así no es un fallo de búsqueda."""
    sin_gemini = (["Gemini no responde y el modelo local no cabe en la tarjeta gráfica."], [], [], 0.1, "código (plan B sin VRAM)")
    r, texto, esperas = _principal(monkeypatch, [sin_gemini] * 4, n=1)
    assert esperas == [20, 40, 60] and texto.splitlines()[-2].endswith("INCONCLUSIVO: hacen falta al menos 15 válidas. Repítela más tarde")
    assert "\napi " in "\n" + texto
    for origen in ("código (plan B: Gemini sin cupo o saturado)", "local (plan B)", "local (plan B no disponible)", "código (Gemini dejó de responder tras actuar)"):
        assert PB.respuesta_sin_ia(origen)
    assert not PB.respuesta_sin_ia("gemini-flash-lite-latest") and not PB.respuesta_sin_ia("")


def test_cada_pregunta_y_cada_repeticion_empiezan_sin_pausas(monkeypatch):
    bien = (["Según la UESP, ectoplasma."], [BUSQUEDA], ["ok"], 1.0)
    caida = ([], [], ["503"], 1.0)
    reinicios: list = []
    _principal(monkeypatch, [caida, bien, bien], n=2, reinicios=reinicios)
    assert len(reinicios) == 3


def test_reiniciar_pausas_deja_los_modelos_y_la_cache_a_cero():
    from lina.nucleo import busqueda as BUS
    from lina.nucleo import ia as IA
    IA._pausa_modelo["m"], IA._fallos_red["m"], IA._clase_pausa["m"] = 9e9, 3, "saturado"
    BUS._pausa_google["h"], BUS._cache["k"] = 9e9, (0, None)
    PB.reiniciar_pausas()
    assert not IA._pausa_modelo and not IA._fallos_red and not IA._clase_pausa and not BUS._pausa_google and not BUS._cache


def test_imprime_los_dos_jueces(monkeypatch):
    steam = (["Según Steam, cuesta 569 euros."], [_buscar("store.steampowered.com")], ["ok"], 1.0)
    _, texto, _ = _principal(monkeypatch, [steam], n=1)
    assert "juez antiguo: mal" in texto and "Juez antiguo (solo el dominio): 1 válidas, 0 excluidas por errores del servicio, 0 aprobadas" in texto
    assert "Juez nuevo" in texto and "1 aprobadas" in texto


def test_un_fallo_de_busqueda_no_se_repite(monkeypatch):
    mal = (["No lo sé."], [FALLIDA], ["ok"], 1.0)
    r, texto, esperas = _principal(monkeypatch, [mal], n=1)
    assert esperas == [] and texto.count("mal ") == 1


def test_sin_la_clave_del_nivel_no_empieza(monkeypatch):
    class SinTavily(_sin_cambios):
        def __enter__(self):
            return {"gemini": "G", "tavily": ""}
    monkeypatch.setattr(PB, "usuario_nuevo", SinTavily)
    salida = []
    assert PB.principal(["tavily"], salida.append, preparar=MagicMock(side_effect=AssertionError)) == 2 and "lina clave tavily" in salida[0]


def test_ningun_comando_ni_la_pantalla(monkeypatch):
    """Solo buscar y leer: lo demás recibe el texto de que en la prueba no se ejecuta nada."""
    assert "ejecutar_comando" not in PB.PERMITIDAS and "mirar_pantalla" not in PB.PERMITIDAS and "ver_pantalla" not in PB.PERMITIDAS
    assert {"buscar_web", "leer_web"} <= PB.PERMITIDAS
