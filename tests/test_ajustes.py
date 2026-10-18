# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import tomllib

import pytest

from lina.nucleo import ajustes as AJ


@pytest.fixture
def aj(tmp_path):
    ruta = tmp_path / "config.toml"
    AJ.escribir_privado(ruta, AJ.texto_de_fabrica())
    return AJ.Ajustes(ruta, log=lambda m: None)


def test_el_archivo_de_fabrica_es_toml_valido_y_sin_avisos(aj):
    datos = tomllib.loads(aj.ruta.read_text(encoding="utf-8"))
    assert set(datos) == set(AJ.ESQUEMA)
    assert aj.avisos == []
    assert aj.get("asistente", "nombre") == "Lina" and aj.get("autonomia", "perfil") == "autonomo"


def test_permisos_del_archivo_son_privados(aj):
    assert oct(aj.ruta.stat().st_mode & 0o777) == "0o600"


def test_valores_mal_escritos_vuelven_al_defecto_y_avisan(tmp_path):
    ruta = tmp_path / "c.toml"
    ruta.write_text('[voz]\nvelocidad = 9\n[autonomia]\nperfil = "loco"\n[inventada]\nx = 1\n[asistente]\nnombre = ""\n', encoding="utf-8")
    a = AJ.Ajustes(ruta, log=lambda m: None)
    assert a.get("voz", "velocidad") == 1.0 and a.get("autonomia", "perfil") == "autonomo" and a.get("asistente", "nombre") == "Lina"
    assert len(a.avisos) == 4


def test_toml_roto_no_tumba_nada(tmp_path):
    ruta = tmp_path / "c.toml"
    ruta.write_text("esto [no es toml", encoding="utf-8")
    a = AJ.Ajustes(ruta, log=lambda m: None)
    assert a.get("asistente", "nombre") == "Lina" and a.avisos


def test_establecer_conserva_comentarios_y_orden(aj):
    antes = aj.ruta.read_text(encoding="utf-8")
    aj.establecer("asistente", "nombre", "Jarvis")
    aj.establecer("gasto", "avisos_porcentaje", "40, 90")
    despues = aj.ruta.read_text(encoding="utf-8")
    assert 'nombre = "Jarvis"' in despues and "avisos_porcentaje = [40, 90]" in despues
    assert despues.count("\n") == antes.count("\n") and "# Cómo se llama el asistente" in despues
    assert AJ.Ajustes(aj.ruta, log=lambda m: None).get("asistente", "nombre") == "Jarvis"


def test_establecer_rechaza_lo_invalido_sin_tocar_el_archivo(aj):
    antes = aj.ruta.read_text(encoding="utf-8")
    for s, k, v in (("voz", "velocidad", "rapidísima"), ("voz", "velocidad", "5"), ("autonomia", "perfil", "temerario"), ("nada", "nada", "1"),
                    ("asistente", "nombre", "")):
        with pytest.raises(ValueError):
            aj.establecer(s, k, v)
    assert aj.ruta.read_text(encoding="utf-8") == antes


def test_establecer_crea_la_seccion_si_falta(tmp_path):
    ruta = tmp_path / "c.toml"
    ruta.write_text('[asistente]\nnombre = "Ana"\n', encoding="utf-8")
    a = AJ.Ajustes(ruta, log=lambda m: None)
    a.establecer("voz", "velocidad", "1,2")
    assert a.get("voz", "velocidad") == 1.2 and a.get("asistente", "nombre") == "Ana"


def test_recarga_en_caliente(aj):
    assert not aj.recargar_si_cambio()
    aj.ruta.write_text('[asistente]\nnombre = "Otra"\n', encoding="utf-8")
    assert aj.recargar_si_cambio() and aj.get("asistente", "nombre") == "Otra"


def test_nombres_planos_del_manos_libres(aj):
    p = aj.planas()
    assert p["nombre"] == "Lina" and p["activo"] == "si" and p["en_juegos"] == "no" and p["indicador_grosor"] == "40"
    assert set(AJ.PLANAS) >= {"nombre", "alias", "prefijos", "indicador_color", "registro_ruido"}


def test_migracion_desde_los_archivos_de_antes(tmp_path):
    (tmp_path / "activacion.txt").write_text("nombre = jarvis\nen_juegos = si   # jugando\nindicador_color = rojo\nseguimiento = 12\n", encoding="utf-8")
    (tmp_path / "voz.txt").write_text("es_ES-sharvard-medium-1\n", encoding="utf-8")
    (tmp_path / "presupuesto.txt").write_text("tope_mensual_eur = 25\neur_por_usd = 0.9\navisos_porcentaje = 60, 100\n[precios]\nx = 1, 2\n", encoding="utf-8")
    (tmp_path / "politica.txt").write_text("[modo]\nautonomia prudente\n", encoding="utf-8")
    destino, migrado = AJ.migrar(tmp_path, log=lambda m: None)
    a = AJ.Ajustes(destino, log=lambda m: None)
    assert a.avisos == []
    assert (a.get("asistente", "nombre"), a.get("activacion", "en_juegos"), a.get("interfaz", "indicador_color"), a.get("activacion", "seguimiento")) == \
        ("jarvis", True, "rojo", 12)
    assert a.get("voz", "voz") == "es_ES-sharvard-medium-1" and a.get("gasto", "tope_mensual_eur") == 25 and a.get("gasto", "avisos_porcentaje") == [60, 100]
    assert a.get("autonomia", "perfil") == "prudente" and len(migrado) >= 8
    assert (tmp_path / "activacion.txt.antiguo").exists() and not (tmp_path / "activacion.txt").exists()
    assert (tmp_path / "presupuesto.txt").exists() and (tmp_path / "politica.txt").exists()      # estos siguen mandando (precios y reglas)
    assert AJ.migrar(tmp_path, log=lambda m: None)[1] == []                                       # no se repite


def test_migracion_ignora_valores_malos_sin_caerse(tmp_path):
    (tmp_path / "activacion.txt").write_text("seguimiento = muchos\nnombre = ana\n", encoding="utf-8")
    destino, _ = AJ.migrar(tmp_path, log=lambda m: None)
    a = AJ.Ajustes(destino, log=lambda m: None)
    assert a.get("asistente", "nombre") == "ana" and a.get("activacion", "seguimiento") == 8


def test_perfiles(aj):
    assert AJ.politica_efectiva(aj) == ("alta", False, {})
    aj.establecer("autonomia", "perfil", "equilibrado")
    assert AJ.politica_efectiva(aj)[:2] == ("alta", True)
    aj.establecer("autonomia", "perfil", "prudente")
    aj.establecer("autonomia", "borrado", "libre")
    assert AJ.politica_efectiva(aj) == ("prudente", True, {"borrado": "libre"})


def test_cambios_sensibles(aj):
    assert not AJ.cambio_sensible("asistente", "nombre", "x", aj)
    assert AJ.cambio_sensible("gasto", "tope_mensual_eur", 20, aj) and not AJ.cambio_sensible("gasto", "tope_mensual_eur", 5, aj)
    aj.establecer("autonomia", "perfil", "equilibrado")
    assert AJ.cambio_sensible("autonomia", "perfil", "autonomo", aj) and not AJ.cambio_sensible("autonomia", "perfil", "prudente", aj)
    assert AJ.cambio_sensible("autonomia", "borrado", "libre", aj) and not AJ.cambio_sensible("autonomia", "borrado", "confirmar", aj)


def test_lina_config(aj):
    salida = []
    assert AJ.principal([], salida.append, ajustes=aj) == 0 and any("[autonomia]" in l for l in salida)
    salida.clear()
    assert AJ.principal(["poner", "voz.velocidad", "1.2"], salida.append, ajustes=aj) == 0 and aj.get("voz", "velocidad") == 1.2
    assert AJ.principal(["poner", "indicador_color", "rojo"], salida.append, ajustes=aj) == 0 and aj.get("interfaz", "indicador_color") == "rojo"
    assert AJ.principal(["perfil", "prudente"], salida.append, ajustes=aj) == 0 and aj.get("autonomia", "perfil") == "prudente"
    assert AJ.principal(["poner", "voz.velocidad", "99"], salida.append, ajustes=aj) == 2
    assert AJ.principal(["ver", "nada.nada"], salida.append, ajustes=aj) == 2
    assert AJ.principal(["comprobar"], salida.append, ajustes=aj) == 0


def test_la_documentacion_cubre_todos_los_ajustes():
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / "docs" / "configuracion.md").read_text(encoding="utf-8")
    faltan = [f"{s}.{k}" for s, c in AJ.ESQUEMA.items() for k in c if f"`{k}`" not in doc]
    assert not faltan, faltan
