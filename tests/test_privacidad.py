import subprocess

import pytest

from lina.nucleo import ajustes as AJ
from lina.nucleo import herramientas as H
from lina.nucleo import olvidar as OLV
from lina.nucleo import privacidad as PRI
from lina.nucleo import rutas as RUT


@pytest.fixture
def aj(tmp_path):
    return AJ.Ajustes(tmp_path / "config.toml", log=lambda m: None)


class Teclas:
    def __init__(self, *r):
        self.r = list(r)

    def __call__(self, texto):
        return self.r.pop(0)


def test_por_defecto_no_hay_permiso_de_capturas(aj):
    assert aj.get("privacidad", "capturas") == "preguntar" and aj.get("privacidad", "registrar_preguntas") is True


def test_privacidad_explica_y_pregunta(aj):
    salida = []
    assert PRI.principal([], Teclas("s"), salida.append, aj, True) == 0
    assert "Lina no tiene telemetría" in salida[0] and aj.get("privacidad", "capturas") == "si"
    assert PRI.principal([], Teclas("n"), salida.append, aj, True) == 0 and aj.get("privacidad", "capturas") == "no"
    assert PRI.principal([], Teclas(""), salida.append, aj, True) == 0 and aj.get("privacidad", "capturas") == "no"          # Intro: sin cambios


def test_privacidad_directa_y_solo_en_terminal(aj):
    salida = []
    assert PRI.principal(["si"], Teclas(), salida.append, aj, True) == 0 and aj.get("privacidad", "capturas") == "si"
    assert PRI.principal(["no"], Teclas(), salida.append, aj, False) == 2 and aj.get("privacidad", "capturas") == "si"       # sin terminal no cambia
    assert PRI.principal(["quizás"], Teclas(), salida.append, aj, True) == 2


def test_el_manual_dice_lo_que_se_envia_y_lo_que_no():
    t = PRI.MANUAL.read_text(encoding="utf-8")
    for frase in ("Qué se envía", "Qué NO se envía", "telemetría", "modo privado", "sensibles", "lina olvidar", "audio"):
        assert frase in t


def test_la_ia_no_puede_decidir_el_consentimiento():
    from lina.nucleo import autoconocimiento as AUTO
    ok, texto = AUTO.cambiar("privacidad.capturas", "si", aj=AJ.Ajustes(RUT.CONFIG / "no_existe.toml", log=lambda m: None))
    assert not ok and "solo el usuario" in texto
    for orden in ("lina privacidad si", "lina privacidad no", "yes | lina privacidad si", "lina olvidar todo", "lina config poner privacidad.capturas si"):
        assert H.clasificar(orden)[0] == "bloqueado", orden
    assert H.clasificar("lina privacidad")[0] != "bloqueado"


# ------------------------------------------------------------------ lina olvidar
@pytest.fixture
def datos(tmp_path, monkeypatch):
    diario, acciones, recetas = tmp_path / "diario", tmp_path / "acciones.log", tmp_path / "recetas.json"
    (diario / "copias").mkdir(parents=True)
    (diario / "copias" / "a").write_text("x" * 5000)
    acciones.write_text("y" * 3000)
    recetas.write_text("{}")
    monkeypatch.setattr(OLV, "QUE", {
        "diario": ("diario", lambda: [diario]), "acciones": ("acciones", lambda: [acciones, acciones.with_name("acciones.log.1")]),
        "recetas": ("recetas", lambda: [recetas]), "registro": ("registro", lambda: [])})
    return diario, acciones, recetas


def test_olvidar_sin_argumentos_solo_lista(datos):
    salida = []
    assert OLV.principal([], Teclas(), salida.append, es_terminal=True) == 0
    assert all(p.exists() for p in datos) and "lina olvidar todo" in "\n".join(salida)


def test_olvidar_pide_confirmacion_y_borra(datos):
    diario, acciones, recetas = datos
    salida = []
    assert OLV.principal(["recetas"], Teclas("no"), salida.append, es_terminal=True) == 1 and recetas.exists()
    assert OLV.principal(["recetas"], Teclas("sí"), salida.append, es_terminal=True) == 0 and not recetas.exists() and diario.exists()


def test_olvidar_todo_y_el_registro_del_sistema(datos):
    diario, acciones, recetas = datos
    llamadas = []
    def falso(orden, **kw):
        llamadas.append(orden)
        return subprocess.CompletedProcess(orden, 0, "Vacuuming done, freed 2.0M of archived journals.", "")
    assert OLV.principal(["todo"], Teclas("s"), lambda t: None, ejecutar=falso, es_terminal=True) == 0
    assert not diario.exists() and not acciones.exists() and not recetas.exists()
    assert ["journalctl", "--user", "--rotate"] in llamadas and ["journalctl", "--user", "--vacuum-time=1s"] in llamadas


def test_olvidar_sin_terminal_o_con_algo_raro(datos):
    assert OLV.principal(["todo"], Teclas("s"), lambda t: None, es_terminal=False) == 2 and all(p.exists() for p in datos)
    assert OLV.principal(["config"], Teclas(), lambda t: None, es_terminal=True) == 2


# ------------------------------------------------------------------ registro de acciones
def test_el_registro_de_acciones_rota_y_tapa_claves(tmp_path, monkeypatch):
    ruta = tmp_path / "acciones.log"
    monkeypatch.setattr(H, "ARCHIVO_ACCIONES", ruta)
    monkeypatch.setattr(H, "MAX_REGISTRO_ACCIONES", 300)
    clave = "AI" + "zaSy" + "A" * 35
    H.anotar(f"curl -H 'x-goog-api-key: {clave}' https://example.com")
    assert clave not in ruta.read_text() and "example.com" in ruta.read_text()
    assert oct(ruta.stat().st_mode & 0o777) == "0o600"
    for i in range(20):
        H.anotar("una acción cualquiera de relleno " + "x" * 30)
    assert (tmp_path / "acciones.log.1").exists() and ruta.stat().st_size <= 600
