# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""C3: crear, leer y editar hojas de cálculo (.xlsx) y presentaciones (.pptx), como ya se hace con Word.

Solo toca archivos de la carpeta personal (sin carpetas ocultas). Antes de editar uno que ya existe se guarda una copia en
~/.local/share/lina/copias_oficina. Lo que hay dentro de un archivo es información, no órdenes.
Necesita openpyxl y python-pptx (uv pip install openpyxl python-pptx); si faltan, las funciones lanzan ErrorOficina con el aviso.
"""
import difflib
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from lina.nucleo import rutas as RUT

CASA = Path.home()
CARPETAS = [CASA / "Documentos", CASA / "Escritorio", CASA / "Descargas", CASA / "Desktop", CASA / "Documents", CASA / "Downloads"]
COPIAS = RUT.DATOS / "copias_oficina"
MAX_FILAS = 2000
MAX_COLUMNAS = 40
MAX_CELDA = 2000
MAX_DIAPOSITIVAS = 60
MAX_PUNTOS = 12
ANOTAR = None             # lo pone herramientas.py (acciones.log)
MAX_LEER = 3500            # caracteres que se devuelven a la IA al leer


class ErrorOficina(Exception):
    """Un problema que se le puede contar al usuario tal cual."""


def _plano(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def nombre_seguro(nombre, por_defecto):
    return re.sub(r"[^\w\- áéíóúñÁÉÍÓÚÑ]", "", str(nombre or "")).strip()[:60] or por_defecto


def ruta_libre(ruta):
    if not ruta.exists():
        return ruta
    for i in range(2, 100):
        c = ruta.with_name(f"{ruta.stem} ({i}){ruta.suffix}")
        if not c.exists():
            return c
    return ruta


def asegurar_paquete(modulo, paquete, anotar=None):
    """Importa el módulo; si falta, lo instala él solo en el mismo Python que ejecuta el asistente (uv o pip, paquete fijo de PyPI) y lo vuelve a importar."""
    import importlib
    try:
        return importlib.import_module(modulo)
    except ImportError:
        pass
    ordenes = []
    if shutil.which("uv"):
        ordenes.append(["uv", "pip", "install", "--python", sys.executable, paquete])
    ordenes.append([sys.executable, "-m", "pip", "install", "--break-system-packages", paquete])
    ultimo = ""
    for orden in ordenes:
        try:
            r = subprocess.run(orden, capture_output=True, text=True, timeout=240)
        except (OSError, subprocess.SubprocessError) as e:
            ultimo = str(e)[:150]
            continue
        if r.returncode == 0:
            importlib.invalidate_caches()
            try:
                m = importlib.import_module(modulo)
                if anotar:
                    anotar(f"[instalado] {paquete} (lo necesitaba para una petición)")
                return m
            except ImportError:
                pass
        ultimo = (r.stderr or r.stdout or "")[-150:].strip()
    raise ErrorOficina(f"Necesito {paquete} y no he podido instalarlo solo ({ultimo or 'sin detalle'}).")


def _dependencia(modulo, paquete):
    return asegurar_paquete(modulo, paquete, ANOTAR)


def _valido(ruta):
    """Dentro de la carpeta personal, sin carpetas ocultas ni enlaces simbólicos."""
    try:
        r = Path(ruta)
        if r.is_symlink():
            return False
        real = r.resolve()
        rel = real.relative_to(CASA.resolve())
    except (OSError, ValueError):
        return False
    return not any(p.startswith(".") for p in rel.parts)


def encontrar(referencia, extension):
    """Ruta de un archivo existente a partir de su nombre aproximado o ruta. Lanza ErrorOficina si no hay uno claro."""
    ref = str(referencia or "").strip().strip("\"'")
    if not ref:
        raise ErrorOficina("Falta el nombre del archivo.")
    if "/" in ref or ref.startswith("~"):
        p = Path(ref).expanduser()
        if p.suffix.lower() != extension:
            p = p.with_name(p.name + extension)
        if p.is_file() and _valido(p):
            return p
        raise ErrorOficina(f"No encuentro «{ref[:80]}» en tu carpeta personal.")
    q = _plano(re.sub(re.escape(extension) + r"$", "", ref, flags=re.I))
    candidatos = []
    vistos = set()
    for c in CARPETAS:
        if not c.is_dir():
            continue
        for p in c.rglob("*" + extension):
            if p in vistos or p.name.startswith(("~$", ".")) or not p.is_file() or not _valido(p):
                continue
            if len(p.relative_to(c).parts) > 3:
                continue
            vistos.add(p)
            n = _plano(p.stem)
            pts = 1.0 if n == q else (0.85 if q and q in n else difflib.SequenceMatcher(None, q, n).ratio())
            if pts >= 0.5:
                candidatos.append((pts, p.stat().st_mtime, p))
    if not candidatos:
        raise ErrorOficina(f"No encuentro ningún archivo {extension} llamado «{ref[:60]}» en Documentos, Escritorio ni Descargas.")
    candidatos.sort(key=lambda x: (-x[0], -x[1]))
    if len(candidatos) > 1 and candidatos[0][0] - candidatos[1][0] < 0.1 and candidatos[1][0] >= 0.7:
        raise ErrorOficina("Hay varios archivos parecidos: " + "; ".join(f"«{p.name}»" for _, _, p in candidatos[:4]) + ". Pregúntale cuál.")
    return candidatos[0][2]


def copia_previa(ruta):
    COPIAS.mkdir(parents=True, exist_ok=True)
    destino = COPIAS / f"{time.strftime('%Y%m%d-%H%M%S')}__{ruta.name}"
    shutil.copy2(ruta, destino)
    return destino


# ============================ EXCEL ============================
def _valor(v):
    """Texto → valor de celda: números como números, «=…» como fórmula, el resto texto."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    t = str(v).strip()[:MAX_CELDA]
    if not t:
        return None
    if t.startswith("="):
        return t
    if re.fullmatch(r"-?\d{1,15}", t) and not (len(t) > 1 and t.startswith("0")):
        return int(t)
    m = re.fullmatch(r"-?\d{1,3}(\.\d{3})*,\d+|-?\d+,\d+", t)         # 1.234,56 o 12,5 (formato español)
    if m:
        return float(t.replace(".", "").replace(",", "."))
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    m = re.fullmatch(r"(-?\d+(?:[.,]\d+)?)\s*(€|\$|%)", t)             # 12,50 € → número con formato
    if m:
        return float(m.group(1).replace(",", "."))
    return t


def _formato_celda(v):
    t = str(v).strip() if isinstance(v, str) else ""
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?\s*€", t):
        return '#,##0.00 "€"'
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?\s*\$", t):
        return '#,##0.00 "$"'
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?\s*%", t):
        return "0.0%"
    return None


def _limpiar_filas(filas):
    if not isinstance(filas, list) or not filas:
        raise ErrorOficina("No hay filas que guardar.")
    if len(filas) > MAX_FILAS:
        raise ErrorOficina(f"Son demasiadas filas (máximo {MAX_FILAS}).")
    salida = []
    for f in filas:
        if isinstance(f, str):
            f = [c for c in re.split(r"\s*[|;\t]\s*", f)]
        if not isinstance(f, (list, tuple)):
            f = [f]
        if len(f) > MAX_COLUMNAS:
            raise ErrorOficina(f"Son demasiadas columnas (máximo {MAX_COLUMNAS}).")
        salida.append(list(f))
    return salida


def _es_numerico(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) or (isinstance(v, str) and v.startswith("="))


def _heredar_formatos(hoja, primera, ultima):
    """Una celda numérica o de fórmula sin formato coge el de la celda de más arriba de su columna (así un importe nuevo sale «30,00 €» como los demás)."""
    for r in range(primera, ultima + 1):
        for c in range(1, hoja.max_column + 1):
            cel = hoja.cell(row=r, column=c)
            if cel.value is None or not _es_numerico(cel.value) or cel.number_format != "General":
                continue
            for rr in range(r - 1, 1, -1):
                arriba = hoja.cell(row=rr, column=c)
                if _es_numerico(arriba.value) and arriba.number_format != "General":
                    cel.number_format = arriba.number_format
                    break


def _escribir_filas(hoja, filas, desde_fila):
    for i, fila in enumerate(filas):
        for j, bruto in enumerate(fila, 1):
            v = _valor(bruto)
            if v is None:
                continue
            c = hoja.cell(row=desde_fila + i, column=j, value=v)
            fmt = _formato_celda(bruto)
            if fmt:
                c.number_format = fmt
    _heredar_formatos(hoja, desde_fila, desde_fila + len(filas) - 1)


def _dar_estilo(hoja):
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    if hoja.max_row >= 1:
        for c in hoja[1]:
            if c.value is not None:
                c.font = Font(name="Calibri", bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="305496")
                c.alignment = Alignment(horizontal="center", vertical="center")
        hoja.freeze_panes = "A2"
    for col in range(1, hoja.max_column + 1):
        ancho = 8
        for fila in range(1, min(hoja.max_row, 300) + 1):
            v = hoja.cell(row=fila, column=col).value
            if v is not None:
                ancho = max(ancho, min(50, len(str(v)) + 3) if not str(v).startswith("=") else 12)
        hoja.column_dimensions[get_column_letter(col)].width = ancho


def crear_xlsx(ruta, hojas):
    """hojas: [{nombre, filas}]. La primera fila de cada hoja es la cabecera."""
    openpyxl = _dependencia("openpyxl", "openpyxl")
    if not isinstance(hojas, list) or not hojas:
        raise ErrorOficina("Falta el contenido de la hoja.")
    libro = openpyxl.Workbook()
    libro.remove(libro.active)
    usados = set()
    for k, h in enumerate(hojas[:10], 1):
        nombre = re.sub(r"[\[\]:*?/\\]", "", str((h or {}).get("nombre") or f"Hoja{k}")).strip()[:31] or f"Hoja{k}"
        while nombre.lower() in usados:
            nombre = (nombre[:28] + f"_{k}")
        usados.add(nombre.lower())
        hoja = libro.create_sheet(nombre)
        _escribir_filas(hoja, _limpiar_filas((h or {}).get("filas")), 1)
        _dar_estilo(hoja)
    libro.save(str(ruta))
    return [(h.title, h.max_row, h.max_column) for h in libro.worksheets]


def _hoja(libro, nombre):
    if not nombre:
        return libro.worksheets[0]
    q = _plano(nombre)
    for h in libro.worksheets:
        if _plano(h.title) == q:
            return h
    for h in libro.worksheets:
        if q in _plano(h.title):
            return h
    raise ErrorOficina("No hay una hoja llamada «%s». Hojas: %s." % (str(nombre)[:40], ", ".join(h.title for h in libro.worksheets)))


def leer_xlsx(ruta, hoja=None):
    openpyxl = _dependencia("openpyxl", "openpyxl")
    try:
        f = openpyxl.load_workbook(str(ruta))                      # con fórmulas
        v = openpyxl.load_workbook(str(ruta), data_only=True)      # con los últimos valores calculados
    except Exception as e:
        raise ErrorOficina(f"No he podido abrir ese Excel ({type(e).__name__}).")
    destino = [_hoja(f, hoja)] if hoja else f.worksheets[:5]
    salida, total = [], 0
    for h in destino:
        hv = v[h.title]
        salida.append(f"HOJA «{h.title}» ({h.max_row} filas × {h.max_column} columnas)")
        for r in range(1, min(h.max_row, 60) + 1):
            celdas = []
            for c in range(1, min(h.max_column, 20) + 1):
                x, y = h.cell(row=r, column=c).value, hv.cell(row=r, column=c).value
                if x is None:
                    celdas.append("")
                elif isinstance(x, str) and x.startswith("="):
                    celdas.append(f"{x} → {y}" if y is not None else x)
                else:
                    cel = h.cell(row=r, column=c)
                    celdas.append(str(x)[:60] + (" €" if isinstance(x, (int, float)) and "€" in (cel.number_format or "") else ""))
            linea = f"{r}: " + " | ".join(celdas)
            total += len(linea)
            if total > MAX_LEER:
                salida.append("[…hay más; pide una hoja o unas filas concretas]")
                return "\n".join(salida)
            salida.append(linea)
        if h.max_row > 60:
            salida.append(f"[…{h.max_row - 60} filas más]")
    return "\n".join(salida)


_RANGO = re.compile(r"(\$?[A-Z]{1,3}\$?)(\d+):(\$?[A-Z]{1,3}\$?)(\d+)")


def _fila_de_totales(h):
    """Número de la última fila si es una fila de totales (empieza por «Total», «Suma»... o suma lo de arriba); si no, None."""
    ult = h.max_row
    if ult < 3 or not any(c.value is not None for c in h[ult]):
        return None
    primera = _plano(h.cell(row=ult, column=1).value)
    por_nombre = bool(re.match(r"\s*(total|suma|subtotal|saldo|media|promedio)", primera))
    formulas = [c.value for c in h[ult] if isinstance(c.value, str) and c.value.startswith("=")]
    suma_arriba = any(m.group(4) == str(ult - 1) for f in formulas for m in _RANGO.finditer(f))
    return ult if (por_nombre and formulas) or suma_arriba else None


def anadir_filas_xlsx(ruta, filas, hoja=None):
    """Añade filas al final de los datos; si la última fila es de totales, las mete justo antes y alarga sus sumas."""
    from copy import copy
    openpyxl = _dependencia("openpyxl", "openpyxl")
    libro = _abrir_xlsx(openpyxl, ruta)
    h = _hoja(libro, hoja)
    filas = _limpiar_filas(filas)
    n = len(filas)
    if h.max_row + n > MAX_FILAS * 5:
        raise ErrorOficina("La hoja ya es demasiado grande.")
    tot = _fila_de_totales(h)
    if tot:
        guardada = [(c.column, c.value, copy(c._style)) for c in h[tot]]
        for c in h[tot]:
            c.value = None
        _escribir_filas(h, filas, tot)
        for j in range(1, h.max_column + 1):                        # las filas nuevas se ven como la de datos de encima
            modelo = h.cell(row=tot - 1, column=j)
            for i in range(n):
                nueva = h.cell(row=tot + i, column=j)
                nueva.font, nueva.fill, nueva.border, nueva.alignment = copy(modelo.font), copy(modelo.fill), copy(modelo.border), copy(modelo.alignment)
                if nueva.number_format == "General" and nueva.value is not None and _es_numerico(nueva.value):
                    nueva.number_format = modelo.number_format
        for col, valor, estilo in guardada:
            cel = h.cell(row=tot + n, column=col)
            if isinstance(valor, str) and valor.startswith("="):
                valor = _RANGO.sub(lambda m: m.group(0) if m.group(4) != str(tot - 1) else f"{m.group(1)}{m.group(2)}:{m.group(3)}{tot - 1 + n}", valor)
            cel.value = valor
            cel._style = estilo
        libro.save(str(ruta))
        return h.title, tot, tot + n - 1, True
    ultima = h.max_row if any(c.value is not None for c in h[h.max_row]) else h.max_row - 1
    _escribir_filas(h, filas, ultima + 1)
    if ultima >= 2:
        for j in range(1, h.max_column + 1):
            modelo = h.cell(row=ultima, column=j)
            for i in range(n):
                nueva = h.cell(row=ultima + 1 + i, column=j)
                nueva.font, nueva.fill, nueva.border, nueva.alignment = copy(modelo.font), copy(modelo.fill), copy(modelo.border), copy(modelo.alignment)
    libro.save(str(ruta))
    return h.title, ultima + 1, ultima + n, False


def cambiar_celdas_xlsx(ruta, celdas, hoja=None):
    openpyxl = _dependencia("openpyxl", "openpyxl")
    libro = _abrir_xlsx(openpyxl, ruta)
    h = _hoja(libro, hoja)
    hechas = []
    for item in celdas or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("celda", "")).strip().upper()
        if not re.fullmatch(r"[A-Z]{1,2}[1-9]\d{0,4}", ref):
            raise ErrorOficina(f"«{ref[:20]}» no es una celda válida (como B3).")
        valor = item.get("valor")
        h[ref] = _valor(valor) if str(valor or "").strip() else None
        fmt = _formato_celda(valor)
        if fmt:
            h[ref].number_format = fmt
        hechas.append(ref)
    if not hechas:
        raise ErrorOficina("No hay celdas que cambiar.")
    libro.save(str(ruta))
    return h.title, hechas


def _abrir_xlsx(openpyxl, ruta):
    try:
        return openpyxl.load_workbook(str(ruta))
    except Exception as e:
        raise ErrorOficina(f"No he podido abrir ese Excel ({type(e).__name__}).")


# ============================ POWERPOINT ============================
def _escalar_a_16_9(prs):
    """La plantilla de python-pptx es 4:3; se pasa a 16:9 y se estiran los huecos para que todo siga encajando."""
    from pptx.util import Inches
    factor = 13.333 / 10.0
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    contenedores = [prs.slide_master] + list(prs.slide_layouts)
    for cont in contenedores:
        for sh in cont.shapes:
            try:
                if sh._element.spPr.xfrm is None:                  # hereda del patrón: ya se ha escalado allí
                    continue
                if sh.left is not None and sh.width is not None:
                    sh.left, sh.width = int(sh.left * factor), int(sh.width * factor)
            except Exception:
                pass


def _layout(prs, con_cuerpo):
    from pptx.enum.shapes import PP_PLACEHOLDER as P
    for lay in prs.slide_layouts:
        tipos = [ph.placeholder_format.type for ph in lay.placeholders]
        tiene_titulo = any(t in (P.TITLE, P.CENTER_TITLE) for t in tipos)
        tiene_cuerpo = any(t in (P.BODY, P.OBJECT) for t in tipos)
        if con_cuerpo and tiene_titulo and tiene_cuerpo and len(tipos) <= 4:
            return lay
        if not con_cuerpo and any(t == P.CENTER_TITLE for t in tipos) and any(t == P.SUBTITLE for t in tipos):
            return lay
    return prs.slide_layouts[1 if con_cuerpo and len(prs.slide_layouts) > 1 else 0]


def _sin_vineta(p):
    return re.sub(r"^\s*[-•*]\s+", "", str(p)).strip()


def _texto_con_negrita(parrafo, texto):
    parrafo.text = ""
    for i, trozo in enumerate(str(texto).split("**")):
        if trozo:
            r = parrafo.add_run()
            r.text = trozo
            if i % 2 == 1:
                r.font.bold = True


def _rellenar(tf, puntos):
    from pptx.util import Pt
    puntos = [str(p).strip()[:300] for p in (puntos or []) if str(p).strip()][:MAX_PUNTOS]
    tf.word_wrap = True
    tam = Pt(32) if len(puntos) <= 4 else Pt(28) if len(puntos) <= 6 else Pt(24) if len(puntos) <= 9 else Pt(20)
    for i, p in enumerate(puntos):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.level = 1 if p.startswith("  ") else 0
        _texto_con_negrita(par, _sin_vineta(p))
        for r in par.runs:
            r.font.size = tam if par.level == 0 else Pt(int(tam.pt * 0.85))


def _poner_cuerpo(slide, puntos):
    from pptx.enum.shapes import PP_PLACEHOLDER as P
    cuerpo = next((ph for ph in slide.placeholders if ph.placeholder_format.type in (P.BODY, P.OBJECT)), None)
    if cuerpo is not None and any(str(p).strip() for p in (puntos or [])):
        _rellenar(cuerpo.text_frame, puntos)


def _nueva_diapositiva(prs, d):
    titulo = str((d or {}).get("titulo", "") or "").strip()[:120]
    slide = prs.slides.add_slide(_layout(prs, True))
    if slide.shapes.title is not None:
        slide.shapes.title.text = titulo
    _poner_cuerpo(slide, (d or {}).get("puntos"))
    for ph in list(slide.placeholders):                        # sin huecos vacíos que salgan como «Haga clic para…»
        if ph.has_text_frame and not ph.text_frame.text.strip():
            ph._element.getparent().remove(ph._element)
    notas = str((d or {}).get("notas", "") or "").strip()[:3000]
    if notas:
        slide.notes_slide.notes_text_frame.text = notas
    return slide



# ---------- temas (fondo, colores y una barra de acento) ----------
TEMAS = {
    "oscuro":  {"fondo": ("0F172A", "1E293B"), "titulo": "FFFFFF", "texto": "E2E8F0", "acento": "38BDF8"},
    "azul":    {"fondo": ("1E3A8A", "3B82F6"), "titulo": "FFFFFF", "texto": "EFF6FF", "acento": "FDE68A"},
    "verde":   {"fondo": ("064E3B", "10B981"), "titulo": "FFFFFF", "texto": "ECFDF5", "acento": "FDE68A"},
    "morado":  {"fondo": ("3B0764", "7E22CE"), "titulo": "FFFFFF", "texto": "FAF5FF", "acento": "F0ABFC"},
    "rojo":    {"fondo": ("7F1D1D", "DC2626"), "titulo": "FFFFFF", "texto": "FEF2F2", "acento": "FDE68A"},
    "naranja": {"fondo": ("7C2D12", "EA580C"), "titulo": "FFFFFF", "texto": "FFF7ED", "acento": "FEF3C7"},
    "claro":   {"fondo": ("F8FAFC", "E2E8F0"), "titulo": "0F172A", "texto": "334155", "acento": "2563EB"},
}
_ALIAS_TEMAS = {"negro": "oscuro", "noche": "oscuro", "dark": "oscuro", "azul oscuro": "azul", "morada": "morado", "violeta": "morado", "lila": "morado",
                "naranja": "naranja", "calido": "naranja", "rojo": "rojo", "verde": "verde", "blanco": "claro", "claro": "claro", "light": "claro", "gris": "claro",
                "oscura": "oscuro", "moderno": "oscuro"}
TEMA_POR_DEFECTO = "oscuro"
_MARCA_TEMA = "lina-tema:"


def _tema(nombre):
    n = _plano(nombre).strip() or TEMA_POR_DEFECTO
    n = _ALIAS_TEMAS.get(n, n)
    if n in TEMAS:
        return n, TEMAS[n]
    m = re.fullmatch(r"#?([0-9a-f]{6})", n)
    if m:
        hexa = m.group(1).upper()
        r, g, b = int(hexa[0:2], 16), int(hexa[2:4], 16), int(hexa[4:6], 16)
        claro = (0.299 * r + 0.587 * g + 0.114 * b) > 150
        return "#" + hexa, {"fondo": (hexa, hexa), "titulo": "0F172A" if claro else "FFFFFF", "texto": "1E293B" if claro else "F1F5F9", "acento": "2563EB" if claro else "FDE68A"}
    raise ErrorOficina("No conozco el estilo «%s». Estilos: %s, o un color como #1E3A8A." % (str(nombre)[:30], ", ".join(TEMAS)))


def _rgb(hexa):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(hexa)


def _estilar_diapositiva(slide, indice, t, ancho):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu
    for sh in list(slide.shapes):                               # fuera la barra de un estilo anterior
        if sh.name == "acento_asistente":
            sh._element.getparent().remove(sh._element)
    fondo = slide.background.fill
    a, b = t["fondo"]
    if a == b:
        fondo.solid()
        fondo.fore_color.rgb = _rgb(a)
    else:
        fondo.gradient()
        fondo.gradient_angle = 45
        paradas = fondo.gradient_stops
        paradas[0].color.rgb, paradas[1].color.rgb = _rgb(a), _rgb(b)
    titulo = slide.shapes.title
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        if titulo is not None and sh.shape_id == titulo.shape_id:
            color, negrita = t["titulo"], True
        elif indice == 0:
            color, negrita = t["acento"], None                  # el subtítulo de la portada
        else:
            color, negrita = t["texto"], None
        for par in sh.text_frame.paragraphs:
            for r in par.runs:
                r.font.color.rgb = _rgb(color)
                if negrita and sh.shape_id == titulo.shape_id:
                    r.font.bold = True
    if titulo is not None:
        try:
            ancho_barra = Emu(1600000)
            barra = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, int((ancho - ancho_barra) / 2), int(titulo.top + titulo.height + 30000), ancho_barra, Emu(55000))
            barra.name = "acento_asistente"
            barra.fill.solid()
            barra.fill.fore_color.rgb = _rgb(t["acento"])
            barra.line.fill.background()
            barra.shadow.inherit = False
        except Exception:
            pass


def _aplicar_tema(prs, nombre, indices=None):
    clave, t = _tema(nombre)
    for i, s in enumerate(prs.slides):
        if indices is None or i in indices:
            _estilar_diapositiva(s, i, t, prs.slide_width)
    prs.core_properties.keywords = _MARCA_TEMA + clave
    return clave


def _tema_guardado(prs):
    k = prs.core_properties.keywords or ""
    return k[len(_MARCA_TEMA):] if k.startswith(_MARCA_TEMA) else None


def aplicar_tema_pptx(ruta, tema, numero=None):
    """Cambia el aspecto (fondo, colores, barra de acento) de toda la presentación o de una diapositiva."""
    pptx = _dependencia("pptx", "python-pptx")
    prs = _abrir_pptx(pptx, ruta)
    if numero not in (None, "", 0):
        try:
            n = int(numero)
        except (TypeError, ValueError):
            raise ErrorOficina("Falta el número de la diapositiva.")
        if not 1 <= n <= len(prs.slides):
            raise ErrorOficina(f"La presentación tiene {len(prs.slides)} diapositivas; no hay la {n}.")
        _tema(tema)
        clave, t = _tema(tema)
        _estilar_diapositiva(prs.slides[n - 1], n - 1, t, prs.slide_width)
        prs.save(str(ruta))
        return clave, 1
    clave = _aplicar_tema(prs, tema)
    prs.save(str(ruta))
    return clave, len(prs.slides)


def crear_pptx(ruta, titulo, subtitulo, diapositivas, tema=None):
    pptx = _dependencia("pptx", "python-pptx")
    if not isinstance(diapositivas, list) or not diapositivas:
        raise ErrorOficina("Faltan las diapositivas.")
    if len(diapositivas) > MAX_DIAPOSITIVAS:
        raise ErrorOficina(f"Son demasiadas diapositivas (máximo {MAX_DIAPOSITIVAS}).")
    prs = pptx.Presentation()
    _escalar_a_16_9(prs)
    portada = prs.slides.add_slide(_layout(prs, False))
    portada.shapes.title.text = str(titulo or "Presentación")[:120]
    sub = next((ph for ph in portada.placeholders if ph.placeholder_format.idx == 1), None)
    if sub is not None:
        if str(subtitulo or "").strip():
            sub.text = str(subtitulo).strip()[:200]
        else:
            sub._element.getparent().remove(sub._element)
    for d in diapositivas:
        _nueva_diapositiva(prs, d)
    _aplicar_tema(prs, tema or TEMA_POR_DEFECTO)
    prs.save(str(ruta))
    return len(prs.slides)


def _abrir_pptx(pptx, ruta):
    try:
        return pptx.Presentation(str(ruta))
    except Exception as e:
        raise ErrorOficina(f"No he podido abrir esa presentación ({type(e).__name__}).")


def leer_pptx(ruta):
    pptx = _dependencia("pptx", "python-pptx")
    prs = _abrir_pptx(pptx, ruta)
    salida, total = [f"PRESENTACIÓN con {len(prs.slides)} diapositivas"], 0
    for i, s in enumerate(prs.slides, 1):
        titulo = s.shapes.title.text.strip() if s.shapes.title is not None and s.shapes.title.has_text_frame else ""
        textos = []
        for sh in s.shapes:
            if sh.has_text_frame and sh != s.shapes.title:
                textos += [p.text.strip() for p in sh.text_frame.paragraphs if p.text.strip()]
        notas = s.notes_slide.notes_text_frame.text.strip() if s.has_notes_slide else ""
        linea = f"{i}. «{titulo}»" + (": " + " / ".join(t[:100] for t in textos[:8]) if textos else "") + (f" [notas: {notas[:80]}]" if notas else "")
        total += len(linea)
        if total > MAX_LEER:
            salida.append("[…hay más diapositivas]")
            break
        salida.append(linea)
    return "\n".join(salida)


def anadir_diapositivas_pptx(ruta, diapositivas):
    pptx = _dependencia("pptx", "python-pptx")
    prs = _abrir_pptx(pptx, ruta)
    if not isinstance(diapositivas, list) or not diapositivas:
        raise ErrorOficina("Faltan las diapositivas.")
    if len(prs.slides) + len(diapositivas) > MAX_DIAPOSITIVAS:
        raise ErrorOficina(f"La presentación pasaría de {MAX_DIAPOSITIVAS} diapositivas.")
    antes = len(prs.slides)
    for d in diapositivas:
        _nueva_diapositiva(prs, d)
    if _tema_guardado(prs):
        _aplicar_tema(prs, _tema_guardado(prs), set(range(antes, len(prs.slides))))
    prs.save(str(ruta))
    return len(diapositivas), len(prs.slides)


def cambiar_diapositiva_pptx(ruta, numero, titulo=None, puntos=None, notas=None):
    """Cambia el título, los puntos y/o las notas de una diapositiva existente."""
    pptx = _dependencia("pptx", "python-pptx")
    prs = _abrir_pptx(pptx, ruta)
    try:
        n = int(numero)
    except (TypeError, ValueError):
        raise ErrorOficina("Falta el número de la diapositiva.")
    if not 1 <= n <= len(prs.slides):
        raise ErrorOficina(f"La presentación tiene {len(prs.slides)} diapositivas; no hay la {n}.")
    if not (str(titulo or "").strip() or puntos or str(notas or "").strip()):
        raise ErrorOficina("No has dicho qué cambiar de esa diapositiva (título, puntos o notas). Para el fondo y los colores usa la acción estilo.")
    s = prs.slides[n - 1]
    if titulo is not None and str(titulo).strip() and s.shapes.title is not None:
        s.shapes.title.text = str(titulo).strip()[:120]
    if puntos:
        from pptx.enum.shapes import PP_PLACEHOLDER as P
        cuerpo = next((ph for ph in s.placeholders if ph.placeholder_format.type in (P.BODY, P.OBJECT, P.SUBTITLE)), None)
        if cuerpo is None:
            raise ErrorOficina("Esa diapositiva no tiene un hueco de texto donde poner los puntos.")
        tf = cuerpo.text_frame
        for p in list(tf.paragraphs)[1:]:
            p._p.getparent().remove(p._p)
        tf.paragraphs[0].text = ""
        _poner_cuerpo_en(tf, puntos)
    if notas is not None and str(notas).strip():
        s.notes_slide.notes_text_frame.text = str(notas).strip()[:3000]
    if _tema_guardado(prs):
        _aplicar_tema(prs, _tema_guardado(prs), {n - 1})
    prs.save(str(ruta))
    return n


_poner_cuerpo_en = _rellenar
