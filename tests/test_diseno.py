"""Documentos con diseño propio: HTML de la IA → PDF, con comprobación de páginas."""
import shutil

import pytest

from lina.nucleo import diseno as DIS
from lina.nucleo import documentos as DOC
from lina.nucleo import registro as REG
from lina.nucleo import rutas as RUT

HTML = "<html><head><style>@page{size:A4;margin:0}body{font:11pt Arial}</style></head><body><h1>Título</h1><p>Hola</p></body></html>"


def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(REG, "ARCHIVO_ACCIONES", tmp_path / "acciones.log")
    monkeypatch.setattr(DOC, "CARPETA_DOCUMENTOS", tmp_path / "Documentos")
    monkeypatch.setattr(DOC, "DIR_DISENOS", tmp_path / "disenos")
    monkeypatch.setattr(DOC, "_abrir_con_escritorio", lambda r: None)
    monkeypatch.setattr(DOC, "_CREADOS", {})
    monkeypatch.setattr(DIS, "motor_disponible", lambda which=None: "chromium")


def _falso_render(paginas, motor="chromium"):
    def render(html, pdf, **k):
        pdf.write_bytes(b"%PDF-falso")
        return motor, ""
    return render, (lambda ruta, *a, **k: paginas)


def test_el_limpiador_quita_scripts_y_recursos_externos():
    limpio, avisos = DIS.limpiar_html('<p onclick="x()">a</p><script>alert(1)</script><img src="https://ejemplo.invalid/a.png">'
                                      '<style>@import url(http://x.invalid/a.css);p{background:url(http://x.invalid/b.png)}</style>')
    assert "<script" not in limpio and "onclick" not in limpio and "invalid" not in limpio
    assert avisos


def test_una_imagen_local_se_incrusta(tmp_path):
    foto = tmp_path / "foto.png"
    foto.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000201a5f645400000000049454e44ae426082"))
    limpio, _ = DIS.limpiar_html(f'<img src="{foto}">', casa=tmp_path)
    assert "data:image/png;base64," in limpio and str(foto) not in limpio


def test_renderizar_prefiere_el_navegador_y_cae_en_weasyprint(tmp_path):
    llamadas = []

    def ejecutar(cmd, *a, **k):
        llamadas.append(cmd[0])
        (tmp_path / "s.pdf").write_bytes(b"%PDF")
        class R:
            returncode = 0
            stdout = stderr = ""
        return R()
    html = tmp_path / "e.html"
    html.write_text(HTML)
    motor, _ = DIS.renderizar(html, tmp_path / "s.pdf", ejecutar=ejecutar, which=lambda n: f"/usr/bin/{n}" if n in ("brave-browser", "weasyprint") else None)
    assert motor and llamadas[0].endswith("brave-browser")
    llamadas.clear()
    motor, _ = DIS.renderizar(html, tmp_path / "s.pdf", ejecutar=ejecutar, which=lambda n: "/usr/bin/weasyprint" if n == "weasyprint" else None)
    assert motor == "weasyprint" and llamadas[0].endswith("weasyprint")
    motor, motivo = DIS.renderizar(html, tmp_path / "s.pdf", ejecutar=ejecutar, which=lambda n: None)
    assert motor is None and motivo


def test_caben_las_paginas(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    r, p = _falso_render(1)
    monkeypatch.setattr(DIS, "renderizar", r)
    monkeypatch.setattr(DIS, "paginas_pdf", p)
    texto = DOC.disenar_documento({"nombre": "cv", "html": HTML, "abrir": False})
    assert "1 página" in texto and "NO cabe" not in texto
    assert (tmp_path / "Documentos" / "cv.pdf").is_file() and (tmp_path / "disenos" / "cv.html").is_file()


def test_no_cabe_avisa_y_rehacer_sustituye(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    r, _ = _falso_render(2)
    monkeypatch.setattr(DIS, "renderizar", r)
    monkeypatch.setattr(DIS, "paginas_pdf", lambda *a, **k: 2)
    texto = DOC.disenar_documento({"nombre": "cv", "html": HTML, "abrir": False})
    assert "NO cabe" in texto and "2 páginas" in texto and "MISMO" in texto
    monkeypatch.setattr(DIS, "paginas_pdf", lambda *a, **k: 1)
    texto = DOC.disenar_documento({"nombre": "cv", "html": HTML, "abrir": False})
    assert "NO cabe" not in texto
    assert sorted(p.name for p in (tmp_path / "Documentos").iterdir()) == ["cv.pdf"]          # sin copias «(2)»


def test_si_no_se_pueden_contar_las_paginas_no_se_afirma_que_caben(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    r, _ = _falso_render(None)
    monkeypatch.setattr(DIS, "renderizar", r)
    monkeypatch.setattr(DIS, "paginas_pdf", lambda *a, **k: None)
    texto = DOC.disenar_documento({"nombre": "x", "html": HTML, "abrir": False})
    assert "no he podido contar" in texto and "A4, como se pidió" not in texto


def test_sin_html_o_demasiado_largo(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    assert "Falta el html" in DOC.disenar_documento({"nombre": "x"})
    assert "demasiado largo" in DOC.disenar_documento({"nombre": "x", "html": "a" * (DIS.MAX_HTML + 1)})


def test_sin_motor_pide_la_dependencia(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    from lina.nucleo import dependencias as DEP
    monkeypatch.setattr(DIS, "motor_disponible", lambda which=None: None)
    monkeypatch.setattr(DEP, "asegurar", lambda f, **k: (False, "Falta weasyprint"))
    assert DOC.disenar_documento({"nombre": "x", "html": HTML}) == "Falta weasyprint"


def test_ver_html_devuelve_lo_guardado(tmp_path, monkeypatch):
    _aislar(tmp_path, monkeypatch)
    r, _ = _falso_render(1)
    monkeypatch.setattr(DIS, "renderizar", r)
    monkeypatch.setattr(DIS, "paginas_pdf", lambda *a, **k: 1)
    DOC.disenar_documento({"nombre": "cv", "html": HTML, "abrir": False})
    assert "Título" in DOC.disenar_documento({"nombre": "cv", "accion": "ver_html"})


@pytest.mark.skipif(not DIS.navegador(), reason="sin navegador para renderizar")
def test_render_real_en_una_pagina(tmp_path):
    html = tmp_path / "a.html"
    html.write_text(HTML)
    pdf = tmp_path / "a.pdf"
    motor, motivo = DIS.renderizar(html, pdf)
    assert motor, motivo
    assert DIS.paginas_pdf(pdf) in (1, None)
