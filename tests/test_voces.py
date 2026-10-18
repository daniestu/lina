# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import io

from lina.voz import voces as V


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def falso(contenidos, pedidas=None):
    def abrir(url, tiempo):
        if pedidas is not None:
            pedidas.append(url)
        for fin, datos in contenidos.items():
            if url.endswith(fin):
                return Respuesta(datos)
        raise OSError("sin red")
    return abrir


def test_voz_por_defecto_y_elegida(tmp_path):
    assert V.voz_elegida(tmp_path) == "es_MX-claude-high"
    (tmp_path / "voz.txt").write_text("# mi voz\nes_ES-sharvard-medium-1  # la de siempre\n", encoding="utf-8")
    assert V.voz_elegida(tmp_path) == "es_ES-sharvard-medium-1"


def test_descarga_una_sola_vez(tmp_path):
    pedidas = []
    abrir = falso({".onnx.json": b"{}", ".onnx": b"modelo"}, pedidas)
    logs = []
    assert V.asegurar("es_MX-claude-high", tmp_path, logs.append, abrir)
    assert V.instalada("es_MX-claude-high", tmp_path)
    assert len(pedidas) == 2 and all(V.REVISION in u and "claude/high" in u for u in pedidas)
    assert V.asegurar("es_MX-claude-high", tmp_path, logs.append, abrir) and len(pedidas) == 2      # no vuelve a bajarla


def test_sin_red_no_deja_basura_y_devuelve_falso(tmp_path):
    assert V.asegurar("es_MX-claude-high", tmp_path, lambda m: None, falso({})) is False
    assert not V.instalada("es_MX-claude-high", tmp_path)
    assert not list(tmp_path.glob("*.parcial"))


def test_voz_desconocida(tmp_path):
    assert V.asegurar("inventada", tmp_path, lambda m: None, falso({})) is False


def test_preparar_cae_a_otra_instalada_si_no_hay_red(tmp_path):
    (tmp_path / "otra.onnx").write_bytes(b"x")
    (tmp_path / "otra.onnx.json").write_bytes(b"{}")
    elegida = V.preparar(log=lambda m: None, carpeta=tmp_path, carpeta_config=tmp_path / "cfg", abrir=falso({}))
    assert elegida == "otra"


def test_preparar_sin_nada_devuelve_none(tmp_path):
    assert V.preparar(log=lambda m: None, carpeta=tmp_path, carpeta_config=tmp_path / "cfg", abrir=falso({})) is None


def test_catalogo_coherente():
    for idioma, voces in V.CATALOGO.items():
        assert V.VOZ_POR_DEFECTO in V.CATALOGO["es"]
        for nombre, ficha in voces.items():
            assert nombre.startswith(idioma + "_")
            assert ficha["carpeta"].startswith(idioma + "/") and ficha["modelo"] in nombre
            assert ficha["locutor"] is None or isinstance(ficha["locutor"], int)


def test_modelo_y_locutor():
    assert V.modelo("es_ES-sharvard-medium-2") == "es_ES-sharvard-medium" and V.locutor("es_ES-sharvard-medium-2") == 1
    assert V.modelo("es_MX-claude-high") == "es_MX-claude-high" and V.locutor("es_MX-claude-high") is None
    assert V.modelo("voz_antigua") == "voz_antigua" and V.locutor("voz_antigua") is None      # fuera del catálogo: se toma tal cual


def test_dos_hablantes_comparten_modelo(tmp_path):
    pedidas = []
    abrir = falso({".onnx.json": b"{}", ".onnx": b"modelo"}, pedidas)
    assert V.asegurar("es_ES-sharvard-medium-1", tmp_path, lambda m: None, abrir)
    assert V.instalada("es_ES-sharvard-medium-2", tmp_path) and len(pedidas) == 2


def test_voz_antigua_ya_instalada_sigue_funcionando(tmp_path):
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "voz.txt").write_text("es_ES-mls_10246-low\n", encoding="utf-8")
    (tmp_path / "es_ES-mls_10246-low.onnx").write_bytes(b"x")
    (tmp_path / "es_ES-mls_10246-low.onnx.json").write_bytes(b"{}")
    assert V.preparar(log=lambda m: None, carpeta=tmp_path, carpeta_config=tmp_path / "cfg", abrir=falso({})) == "es_ES-mls_10246-low"


def test_lina_voz_lista_y_elige(tmp_path):
    salida = []
    abrir = falso({".onnx.json": b"{}", ".onnx": b"modelo"})
    assert V.principal([], tmp_path / "v", tmp_path / "cfg", abrir, salida.append) == 0
    assert any("*" in l and "es_MX-claude-high" in l for l in salida)
    salida.clear()
    assert V.principal(["es_ES-sharvard-medium-1"], tmp_path / "v", tmp_path / "cfg", abrir, salida.append) == 0
    assert V.voz_elegida(tmp_path / "cfg") == "es_ES-sharvard-medium-1" and V.instalada("es_ES-sharvard-medium-1", tmp_path / "v")
    assert V.principal(["no_existe"], tmp_path / "v", tmp_path / "cfg", abrir, salida.append) == 2
    assert V.voz_elegida(tmp_path / "cfg") == "es_ES-sharvard-medium-1"


def test_lina_voz_sin_red_no_cambia_la_elegida(tmp_path):
    assert V.principal(["es_ES-sharvard-medium-1"], tmp_path / "v", tmp_path / "cfg", falso({}), lambda m: None) == 1
    assert V.voz_elegida(tmp_path / "cfg") == V.VOZ_POR_DEFECTO
