"""El documento con columnas (currículum) debe dejar holgura en la hoja: una tabla que llena el A4 al milímetro acaba en dos páginas."""
import shutil

import pytest

from lina.modulos import oficina as O

SPEC = {"titulo": "Alex Pérez", "resumen": "Ingeniero de software", "foto": "hueco", "color": "azul",
        "izquierda": [{"titulo": "CONTACTO", "elementos": [{"tipo": "texto", "texto": "contacto de ejemplo"}]}],
        "derecha": [{"titulo": "EXPERIENCIA", "elementos": [{"tipo": "entrada", "texto": "Dev", "detalle": "X", "fecha": "2023", "puntos": ["uno", "dos"]}]}]}


def test_la_suma_de_alturas_deja_holgura_en_el_a4():
    assert 29.7 - (O.ALTO_CABECERA + O.ALTO_CUERPO) >= 0.5


@pytest.mark.skipif(not (shutil.which("soffice") or shutil.which("libreoffice")), reason="hace falta LibreOffice para contar páginas")
def test_con_medio_centimetro_mas_de_cuerpo_sigue_en_una_pagina(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "ALTO_CUERPO", O.ALTO_CUERPO + 0.5)          # si cambia de renderizador y crece un poco, aún cabe
    ruta = tmp_path / "cv.docx"
    O._crear_docx_columnas(ruta, SPEC, 1.0)
    assert O._paginas_pdf(ruta) == 1
