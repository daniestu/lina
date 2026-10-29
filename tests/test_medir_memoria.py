# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""`lina memoria medir` (A1, paso 1): las reglas se miden igual que las aplica Lina, la tanda tiene casos de cada tipo, y `--mios` solo da números,
sin escribir nada ni mostrar ningún texto. Memoria en tmp_path; sin IA ni red."""
from unittest.mock import MagicMock

import pytest
import requests

from lina.nucleo import memoria as MEM
from lina.nucleo import medir_memoria as MM


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(MEM, "ARCHIVO", tmp_path / "memoria.json")
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    monkeypatch.setattr(requests, "get", MagicMock(side_effect=AssertionError("no debía ir a la red")))
    return tmp_path


def _guardar(textos):
    MEM._guardar([{"id": f"m{i:04d}", "texto": t, "fecha": "2026-10-01"} for i, t in enumerate(textos, 1)])


def test_la_regla_de_hoy_es_exactamente_la_de_relevantes():
    """Si no, lo medido no sería lo que hace Lina."""
    _guardar(list(MM.RECUERDOS.values()))
    regla = MM.REGLAS[0][1]
    raices = {t: MEM._raices(t) for t in MM.RECUERDOS.values()}
    for peticion, _ in MM.CASOS:
        n, k = MM._comunes(peticion, raices)
        esperado = {t for t in raices if regla(k[t], len(n))}
        assert set(MEM.relevantes(peticion, maximo=100, caracteres=100_000)) == esperado, peticion


def test_cada_regla_con_pares_de_juguete():
    recuerdos = {"a": "mi navegador favorito es Brave", "b": "el volumen de los auriculares lo prefiero bajo"}
    casos = [("abre el navegador", {"a"}),                                  # 1 raíz en común y viene al caso
             ("sube el volumen", set()),                                    # 1 raíz en común y no viene al caso
             ("haz un pantallazo", set())]                                  # nada en común
    m = MM.medir(recuerdos, casos, directa=lambda p: None)
    por = {r["regla"]: r for r in m["reglas"]}
    hoy, dos = por["1 palabra (la de hoy)"], por["2 palabras o más"]
    assert (hoy["aciertos"], hoy["falsos"], hoy["perdidos"]) == (1, 1, 0)
    assert (dos["aciertos"], dos["falsos"], dos["perdidos"]) == (0, 0, 1)
    assert m["relevantes"] == 1 and m["sin_raices"] == 0


def test_se_cuentan_las_directas_perdidas_y_las_que_ignoran_una_preferencia():
    recuerdos = {"a": "Firefox lo uso solo para el banco", "b": "mi impresora es la del despacho"}
    casos = [("abre Firefox", set()), ("imprime la foto", {"b"})]
    m = MM.medir(recuerdos, casos, directa=lambda p: ("abrir", {}))
    hoy = m["reglas"][0]
    assert hoy["directas_perdidas"] == 1                                    # «abre Firefox» iría a la IA sin motivo
    assert hoy["directas_sin_preferencia"] == 1                             # «imprime» e «impresora» no comparten raíz
    assert m["sin_raices"] == 1


def test_la_tanda_tiene_de_todo():
    m = MM.medir()
    hoy = m["reglas"][0]
    assert len(MM.CASOS) >= 70 and m["directas"] > 5
    assert hoy["falsos"] > 0 and m["sin_raices"] > 0 and hoy["directas_perdidas"] > 0
    assert sum(1 for _, e in MM.CASOS if e) >= 30 and sum(1 for _, e in MM.CASOS if not e) >= 20
    assert all(e <= set(MM.RECUERDOS) for _, e in MM.CASOS)


def test_medir_sale_en_una_tabla():
    salida = []
    assert MM.principal([], salida.append) == 0
    texto = "\n".join(salida)
    for r, _ in MM.REGLAS:
        assert r in texto
    assert "techo" in texto


def test_mios_solo_da_numeros_y_no_escribe_nada(aislado):
    privados = ["mi equipo de baloncesto juega los jueves", "la contraseña no", "el café lo tomo sin azúcar"]
    _guardar(privados)
    antes = (aislado / "memoria.json").read_bytes()
    salida = []
    assert MEM.principal(["medir", "--mios"], salida.append) == 0
    texto = "\n".join(salida)
    for t in privados:
        for palabra in t.split():
            if len(palabra) > 4:
                assert palabra not in texto, palabra
    assert "3" in texto
    assert (aislado / "memoria.json").read_bytes() == antes
    assert len(list(aislado.iterdir())) == 1                                # ni copias ni archivos nuevos


def test_mios_cuenta_por_regla():
    m = MM.medir_mios(["mi navegador favorito es Brave"], casos=[("abre el navegador", set()), ("¿qué hora es?", set())],
                      directa=lambda p: ("abrir", {}) if p.startswith("abre") else None)
    hoy = m["reglas"][0]
    assert m["recuerdos"] == 1 and hoy["tocadas"] == 1 and hoy["directas_desactivadas"] == 1 and m["sin_alcance"] == 0
    assert m["reglas"][1]["tocadas"] == 0


def test_mios_sin_recuerdos_y_uso():
    salida = []
    assert MEM.principal(["medir", "--mios"], salida.append) == 0 and "nada" in salida[0]
    assert MEM.principal(["medir", "otra"], salida.append) == 2
    assert not MEM.ARCHIVO.exists()
