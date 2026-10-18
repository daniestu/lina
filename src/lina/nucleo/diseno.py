# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Documentos con diseño propio: la IA escribe el HTML y el CSS y Lina lo convierte en PDF.

No hay plantillas: un currículum, una factura, un cartel o un menú los diseña la IA cada vez, como lo haría un diseñador web. Aquí solo está
la parte mecánica y segura:
  - limpiar_html: quita todo lo que no sea diseño (scripts, formularios, recursos de internet) e incrusta las imágenes locales permitidas;
  - renderizar: lo pasa a PDF con un navegador sin cabeza (Chromium, Chrome, Brave, Edge, Vivaldi) o, si no hay, con WeasyPrint (se instala sola);
  - paginas_pdf: cuenta cuántas páginas ocupa, para que quien diseña sepa si cabe.
El navegador se lanza sin red (ni siquiera resuelve nombres) y sobre un perfil temporal.
"""
import base64
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

NAVEGADORES = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "chrome", "brave", "brave-browser",
               "microsoft-edge-stable", "microsoft-edge", "vivaldi", "vivaldi-stable")
MAX_HTML = 200_000
MAX_IMAGEN = 4_000_000
IMAGENES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}

_ETIQUETAS_CON_CONTENIDO = re.compile(r"<\s*(script|noscript|template|iframe|object|applet|frameset)\b.*?(?:<\s*/\s*\1\s*>|\Z)", re.I | re.S)
_ETIQUETAS_SUELTAS = re.compile(r"<\s*/?\s*(?:embed|base|link|frame|form|input|button|select|textarea|audio|video|source|track|portal|meta\s+http-equiv)\b[^>]*>", re.I)
_EVENTOS = re.compile(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_ATRIBUTO_RECURSO = re.compile(r"""\b(src|poster|srcset|data|background)\s*=\s*(["'])(.*?)\2""", re.I | re.S)
_ATRIBUTO_ENLACE = re.compile(r"""\bhref\s*=\s*(["'])(.*?)\1""", re.I | re.S)
_URL_CSS = re.compile(r"""url\(\s*(["']?)(.*?)\1\s*\)""", re.I | re.S)
_IMPORT_CSS = re.compile(r"@import\b[^;]*;?", re.I)
_ENLACE_PELIGROSO = re.compile(r"\s*(?:javascript|data|file|vbscript):", re.I)


def _imagen_local(valor, casa=None):
    """Data URI de una imagen del usuario (dentro de su carpeta personal, no oculta, de tipo imagen y no enorme) o None."""
    casa = Path(casa) if casa else Path.home()
    texto = valor.strip()
    if texto.lower().startswith("file://"):
        texto = texto[7:]
    if not texto or "\x00" in texto:
        return None
    try:
        ruta = Path(texto).expanduser()
        if not ruta.is_absolute():
            ruta = casa / ruta
        ruta = ruta.resolve()
        relativa = ruta.relative_to(casa.resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    tipo = IMAGENES.get(ruta.suffix.lower())
    if tipo is None or any(p.startswith(".") for p in relativa.parts):
        return None
    try:
        if not ruta.is_file() or ruta.stat().st_size > MAX_IMAGEN:
            return None
        return f"data:{tipo};base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")
    except OSError:
        return None


def limpiar_html(html, casa=None):
    """(html limpio, avisos). Deja solo diseño: sin scripts, formularios ni nada que se descargue de internet."""
    html = str(html or "")
    avisos = []
    quitados = {"n": 0}

    def recurso(valor):
        v = valor.strip()
        if v.lower().startswith("data:image/") or v.startswith("#") or not v:
            return v
        propio = _imagen_local(v, casa)
        if propio is not None:
            return propio
        quitados["n"] += 1
        return ""

    def enlace(m):
        destino = "#" if _ENLACE_PELIGROSO.match(m.group(2)) else m.group(2)       # los enlaces a webs valen (en el PDF no se descargan); los de código, no
        return f"href={m.group(1)}{destino}{m.group(1)}"

    html = _ETIQUETAS_CON_CONTENIDO.sub("", html)
    html = _ETIQUETAS_SUELTAS.sub("", html)
    html = _EVENTOS.sub("", html)
    html = _ATRIBUTO_RECURSO.sub(lambda m: f"{m.group(1)}={m.group(2)}{recurso(m.group(3))}{m.group(2)}", html)
    html = _ATRIBUTO_ENLACE.sub(enlace, html)
    html = _IMPORT_CSS.sub("", html)
    html = _URL_CSS.sub(lambda m: f"url({recurso(m.group(2))})", html)       # sin comillas: puede ir dentro de un style="…"
    if quitados["n"]:
        avisos.append(f"Quité {quitados['n']} imagen/es o recurso/s que no eran del usuario ni estaban incrustados (por seguridad no se descarga nada de internet).")
    if not re.search(r"<\s*html\b", html, re.I):
        html = f'<!doctype html><html lang="es"><head><meta charset="utf-8"></head><body>{html}</body></html>'
    elif not re.search(r"<\s*meta\s+charset", html, re.I):
        html = re.sub(r"(<\s*head\b[^>]*>)", r'\1<meta charset="utf-8">', html, count=1, flags=re.I) if re.search(r"<\s*head\b", html, re.I) \
            else re.sub(r"(<\s*html\b[^>]*>)", r'\1<head><meta charset="utf-8"></head>', html, count=1, flags=re.I)
    return html, avisos


def navegador(which=shutil.which):
    for nombre in NAVEGADORES:
        ruta = which(nombre)
        if ruta:
            return ruta
    return None


def motor_disponible(which=shutil.which):
    """'navegador', 'weasyprint' o None, según lo que haya instalado."""
    if navegador(which):
        return "navegador"
    return "weasyprint" if which("weasyprint") else None


def renderizar(ruta_html, ruta_pdf, timeout=90, ejecutar=subprocess.run, which=shutil.which):
    """Convierte el HTML en PDF. Devuelve (motor, "") o (None, motivo)."""
    ruta_html, ruta_pdf = Path(ruta_html), Path(ruta_pdf)
    motivos = []
    nav = navegador(which)
    if nav:
        # Sin --no-sandbox primero; si no arranca (root, o Ubuntu 24.04 que restringe los espacios de usuario sin perfil de AppArmor para
        # ese navegador) se repite sin él: el HTML ya viene limpio (sin scripts ni recursos externos) y no hay red.
        for sin_caja in ((True,) if os.geteuid() == 0 else (False, True)):
            if ruta_pdf.is_file():
                ruta_pdf.unlink()
            with tempfile.TemporaryDirectory(prefix="lina-nav-") as perfil:
                orden = [nav, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--hide-scrollbars", "--disable-extensions",
                         "--no-first-run", "--mute-audio", "--disable-dev-shm-usage", f"--user-data-dir={perfil}",
                         "--host-resolver-rules=MAP * ~NOTFOUND", f"--print-to-pdf={ruta_pdf}", ruta_html.resolve().as_uri()]
                if sin_caja:
                    orden.insert(2, "--no-sandbox")
                try:
                    r = ejecutar(orden, capture_output=True, text=True, timeout=timeout)
                    ultimo = [x for x in (getattr(r, "stderr", "") or "").strip().splitlines() if x.strip()][-1:]
                except (OSError, subprocess.SubprocessError) as e:
                    motivos.append(f"el navegador no pudo: {e}")
                    ultimo = []
            if ruta_pdf.is_file() and ruta_pdf.stat().st_size > 0:
                return "navegador", ""
        motivos.append("el navegador no generó el PDF" + (f" ({ultimo[0][:160]})" if ultimo else ""))
    peso = which("weasyprint")
    if peso:
        try:
            ejecutar([peso, str(ruta_html), str(ruta_pdf)], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as e:
            motivos.append(f"WeasyPrint no pudo: {e}")
        if ruta_pdf.is_file() and ruta_pdf.stat().st_size > 0:
            return "weasyprint", ""
        motivos.append("WeasyPrint no generó el PDF")
    return None, "; ".join(motivos) or "no hay navegador ni WeasyPrint para generar el PDF"


def paginas_pdf(ruta, ejecutar=subprocess.run, which=shutil.which):
    """Páginas del PDF, o None si no se puede saber."""
    if which("pdfinfo"):
        try:
            r = ejecutar(["pdfinfo", str(ruta)], capture_output=True, text=True, timeout=20)
            m = re.search(r"^Pages:\s+(\d+)", r.stdout or "", re.M)
            if m:
                return int(m.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        n = len(re.findall(rb"/Type\s*/Page(?![s\w])", Path(ruta).read_bytes()))
    except OSError:
        return None
    return n or None


# ---- Word: el mismo HTML, pasado por LibreOffice (solo entiende tablas y CSS sencillo; sin flexbox ni grid)
def programa_oficina(which=shutil.which):
    return which("soffice") or which("libreoffice")


def _con_libreoffice(entrada, formato, carpeta, ejecutar, timeout, filtro=None):
    perfil = Path(carpeta) / "perfil"
    orden = [programa_oficina(), f"-env:UserInstallation={perfil.resolve().as_uri()}", "--headless"]
    if filtro:
        orden += [f"--infilter={filtro}"]
    orden += ["--convert-to", formato, "--outdir", str(carpeta), str(entrada)]
    ejecutar(orden, capture_output=True, text=True, timeout=timeout)


def a_word(ruta_html, ruta_docx, timeout=120, ejecutar=subprocess.run, which=shutil.which):
    """Convierte el HTML en .docx. Devuelve ("libreoffice", "") o (None, motivo)."""
    if not programa_oficina(which):
        return None, "falta LibreOffice para crear el Word"
    ruta_html, ruta_docx = Path(ruta_html), Path(ruta_docx)
    with tempfile.TemporaryDirectory(prefix="lina-doc-") as t:
        copia = Path(t) / "documento.html"
        copia.write_bytes(ruta_html.read_bytes())
        try:
            _con_libreoffice(copia, "docx:MS Word 2007 XML", t, ejecutar, timeout, filtro="HTML (StarWriter)")
        except (OSError, subprocess.SubprocessError) as e:
            return None, f"LibreOffice no pudo: {e}"
        hecho = Path(t) / "documento.docx"
        if not hecho.is_file() or hecho.stat().st_size == 0:
            return None, "LibreOffice no generó el Word"
        shutil.copyfile(hecho, ruta_docx)
    return "libreoffice", ""


def paginas_word(ruta, timeout=120, ejecutar=subprocess.run, which=shutil.which):
    """Páginas del .docx tal como las pone LibreOffice (Word puede variar un poco), o None."""
    if not programa_oficina(which):
        return None
    with tempfile.TemporaryDirectory(prefix="lina-doc-") as t:
        copia = Path(t) / "documento.docx"
        copia.write_bytes(Path(ruta).read_bytes())
        try:
            _con_libreoffice(copia, "pdf", t, ejecutar, timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        pdf = Path(t) / "documento.pdf"
        return paginas_pdf(pdf, ejecutar=ejecutar, which=which) if pdf.is_file() else None
