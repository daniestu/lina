# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""C1: leer una página web en local (descarga, extracción de texto y troceado). No usa IA ni dependencias: solo la librería estándar y requests.

Lo que trae una web son DATOS, nunca órdenes: aquí solo se descarga y se limpia; quien lo use lo marca como contenido de fuera.
Seguridad de la descarga: solo http/https en puertos normales, nunca direcciones internas (ni tras una redirección), tamaño y tiempo limitados.
"""
import ipaddress
import re
import shutil
import socket
import subprocess
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin

import requests

MAX_BYTES = 3_000_000          # lo máximo que se descarga
TIMEOUT = 12
MAX_REDIRECCIONES = 4
PUERTOS = {80, 443, 8080, 8443}
TIPOS_TEXTO = ("text/html", "application/xhtml+xml", "text/plain")
PERMITIR_PRIVADAS = False      # solo lo cambian las pruebas
CABECERAS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0 lina",
             "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,application/pdf;q=0.8,*/*;q=0.5",
             "Accept-Language": "es-ES,es;q=0.9,en;q=0.7"}


class ErrorWeb(Exception):
    """Un problema que se le puede contar al usuario tal cual."""


def normalizar_url(url):
    url = str(url or "").strip().strip("<>\"'")
    if not url:
        raise ErrorWeb("Falta la dirección de la página.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        if re.match(r"^[\w-]+(\.[\w-]+)+(/|$|\?|:)", url):
            url = "https://" + url
        else:
            raise ErrorWeb("Eso no parece una dirección web.")
    p = urlparse(url)
    if p.scheme.lower() not in ("http", "https"):
        raise ErrorWeb("Solo leo páginas http o https.")
    if not p.hostname:
        raise ErrorWeb("La dirección no tiene servidor.")
    if p.username or p.password:
        raise ErrorWeb("No leo direcciones con usuario y contraseña dentro.")
    puerto = p.port or (443 if p.scheme.lower() == "https" else 80)
    if puerto not in PUERTOS:
        raise ErrorWeb("Ese puerto no es el de una web normal.")
    return url


def _comprobar_destino(url):
    """Nunca se descarga de una dirección interna (127.x, 192.168.x, 10.x, enlace local, la red de metadatos...)."""
    host = urlparse(url).hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ErrorWeb(f"No encuentro el servidor {host}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global and not PERMITIR_PRIVADAS:
            raise ErrorWeb("Esa dirección es de la red interna de este equipo o de tu casa: no la leo.")


def descargar(url):
    """(bytes, tipo, url_final). Sigue las redirecciones a mano para revisar cada salto."""
    url = normalizar_url(url)
    for _ in range(MAX_REDIRECCIONES + 1):
        _comprobar_destino(url)
        try:
            r = requests.get(url, headers=CABECERAS, timeout=TIMEOUT, stream=True, allow_redirects=False)
        except requests.exceptions.SSLError:
            raise ErrorWeb("El certificado de esa web no es válido: no la leo.")
        except requests.RequestException:
            raise ErrorWeb("No he podido conectar con esa página.")
        try:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                url = normalizar_url(urljoin(url, r.headers["Location"]))
                continue
            if r.status_code in (401, 403):
                raise ErrorWeb(f"La web no me deja leerla (error {r.status_code}); puede que pida iniciar sesión o bloquee a los programas.")
            if r.status_code == 404:
                raise ErrorWeb("Esa página no existe (error 404).")
            if not r.ok:
                raise ErrorWeb(f"La web ha respondido con un error {r.status_code}.")
            tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if tipo not in TIPOS_TEXTO and tipo != "application/pdf":
                raise ErrorWeb(f"Eso no es una página de texto (es {tipo or 'un tipo desconocido'}).")
            trozos, total = [], 0
            for t in r.iter_content(65536):
                trozos.append(t)
                total += len(t)
                if total > MAX_BYTES:
                    break
            datos = b"".join(trozos)[:MAX_BYTES]
            return datos, tipo, url, (r.encoding if "charset" in (r.headers.get("Content-Type") or "").lower() else None)
        finally:
            r.close()
    raise ErrorWeb("Demasiadas redirecciones.")


def _decodificar(datos, codificacion):
    if not codificacion:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", datos[:4096], re.I)
        codificacion = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        return datos.decode(codificacion, errors="replace")
    except LookupError:
        return datos.decode("utf-8", errors="replace")


_SALTAR = {"script", "style", "noscript", "svg", "nav", "footer", "aside", "form", "template", "iframe", "button", "select", "head", "canvas"}
_BLOQUE = {"p", "div", "br", "li", "ul", "ol", "tr", "section", "article", "main", "blockquote", "pre", "table", "dd", "dt", "figcaption", "header", "td", "th"}
_TITULOS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}


_VACIAS = {"br", "img", "hr", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titulo = ""
        self._en_titulo = False
        self.todo, self.principal = [], []
        self._pila = []          # (etiqueta, está_saltada): las ocultas y las de menús/scripts no cuentan
        self._saltar = 0
        self._principal = 0

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._en_titulo = True
        a = dict(attrs)
        oculta = (tag in _SALTAR or "hidden" in a or a.get("aria-hidden") == "true"
                  or bool(re.search(r"display:\s*none|visibility:\s*hidden|font-size:\s*0", a.get("style") or "", re.I)))
        if tag in _VACIAS:
            if tag == "br" and not self._saltar:
                self._escribir("\n")
            return
        self._pila.append((tag, oculta))
        if oculta:
            self._saltar += 1
            return
        if self._saltar:
            return
        if tag in ("article", "main"):
            self._principal += 1
        if tag in _TITULOS:
            self._escribir("\n" + _TITULOS[tag])
        elif tag in _BLOQUE:
            self._escribir("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._en_titulo = False
        if tag in _VACIAS or not any(t == tag for t, _ in self._pila):
            return
        while self._pila:                                   # cierra hasta la etiqueta que se cierra (el HTML real no siempre está bien anidado)
            t, oculta = self._pila.pop()
            if oculta:
                self._saltar -= 1
            elif not self._saltar:
                if t in ("article", "main"):
                    self._principal = max(0, self._principal - 1)
                if t in _TITULOS or t in _BLOQUE:
                    self._escribir("\n")
            if t == tag:
                break

    def handle_data(self, data):
        if self._en_titulo:
            self.titulo += data
            return
        if self._saltar == 0:
            self._escribir(data)

    def _escribir(self, texto):
        self.todo.append(texto)
        if self._principal:
            self.principal.append(texto)


def _limpiar(trozos):
    texto = "".join(trozos)
    lineas, previa = [], None
    for l in texto.split("\n"):
        l = re.sub(r"[ \t\r\f\v\xa0]+", " ", l).strip()
        if not l or l == previa:
            continue
        if not l.startswith("#") and len(l.split()) < 4 and len(l) < 25:      # restos de menús y botones
            continue
        lineas.append(l)
        previa = l
    return "\n".join(lineas)


def extraer_html(html):
    """(título, texto) de una página: se queda con <article>/<main> si hay bastante texto; si no, con todo el cuerpo."""
    e = _Extractor()
    try:
        e.feed(html)
        e.close()
    except Exception:
        pass
    principal, todo = _limpiar(e.principal), _limpiar(e.todo)
    texto = principal if len(principal) >= 600 and len(principal) >= len(todo) * 0.25 else todo
    return re.sub(r"\s+", " ", e.titulo).strip(), texto


def extraer_pdf(datos):
    if not shutil.which("pdftotext"):
        raise ErrorWeb("Es un PDF y no tengo pdftotext instalado (paquete poppler).")
    try:
        r = subprocess.run(["pdftotext", "-l", "30", "-layout", "-", "-"], input=datos, capture_output=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        raise ErrorWeb("No he podido leer ese PDF.")
    texto = r.stdout.decode("utf-8", "replace")
    if not texto.strip():
        raise ErrorWeb("Ese PDF no tiene texto (puede ser un escaneo).")
    return "", _limpiar([texto])


def leer(url):
    """{url, titulo, texto}: el texto limpio de la página. Lanza ErrorWeb con un mensaje para el usuario."""
    datos, tipo, final, codificacion = descargar(url)
    if tipo == "application/pdf":
        titulo, texto = extraer_pdf(datos)
    elif tipo == "text/plain":
        titulo, texto = "", _limpiar([_decodificar(datos, codificacion)])
    else:
        titulo, texto = extraer_html(_decodificar(datos, codificacion))
    if len(texto) < 200:
        raise ErrorWeb("La página casi no tiene texto que leer (puede cargarse con JavaScript o pedir iniciar sesión).")
    return {"url": final, "titulo": titulo, "texto": texto}


def trozos(texto, tamano=7000, maximo=8):
    """Parte el texto por párrafos en trozos de unos `tamano` caracteres. Devuelve (trozos, se_cortó)."""
    salida, actual = [], ""
    for p in texto.split("\n"):
        while len(p) > tamano:                       # un párrafo enorme: se corta por frases o a la fuerza
            corte = p.rfind(". ", 0, tamano) + 1 or tamano
            if actual:
                salida.append(actual)
                actual = ""
            salida.append(p[:corte])
            p = p[corte:].strip()
        if len(actual) + len(p) + 1 > tamano and actual:
            salida.append(actual)
            actual = ""
        actual += ("\n" if actual else "") + p
    if actual:
        salida.append(actual)
    return salida[:maximo], len(salida) > maximo
