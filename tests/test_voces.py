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
    assert V.voz_elegida(tmp_path) == "es_ES-mls_10246-low"
    (tmp_path / "voz.txt").write_text("# mi voz\nes_ES-davefx-medium  # la de siempre\n", encoding="utf-8")
    assert V.voz_elegida(tmp_path) == "es_ES-davefx-medium"


def test_descarga_una_sola_vez(tmp_path):
    pedidas = []
    abrir = falso({".onnx.json": b"{}", ".onnx": b"modelo"}, pedidas)
    logs = []
    assert V.asegurar("es_ES-mls_10246-low", tmp_path, logs.append, abrir)
    assert V.instalada("es_ES-mls_10246-low", tmp_path)
    assert len(pedidas) == 2 and all(V.REVISION in u and "mls_10246/low" in u for u in pedidas)
    assert V.asegurar("es_ES-mls_10246-low", tmp_path, logs.append, abrir) and len(pedidas) == 2      # no vuelve a bajarla


def test_sin_red_no_deja_basura_y_devuelve_falso(tmp_path):
    assert V.asegurar("es_ES-mls_10246-low", tmp_path, lambda m: None, falso({})) is False
    assert not V.instalada("es_ES-mls_10246-low", tmp_path)
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
