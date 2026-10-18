#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""
Órdenes por voz del asistente.

Las listas de palabras y frases viven en comandos.txt (para verlas y editarlas con comodidad). Este módulo solo
sabe leerlas y aplicarlas. El archivo se relee solo cuando lo guardas; si falta una sección, se usan los valores
de fábrica de abajo. No depende de audio ni de IA, para poder probarlo por separado.
"""
import re
import time
import unicodedata
from pathlib import Path
from lina.nucleo import idioma as IDI
from lina.nucleo.idioma import T
from lina.nucleo import rutas as RUT

ARCHIVO = RUT.editable("comandos.txt")


def archivo():
    """El archivo de palabras del idioma activo: comandos.txt (español) o comandos.<idioma>.txt. Si ese idioma aún no tiene el suyo, el español."""
    codigo = IDI.actual()
    if codigo != IDI.POR_DEFECTO:
        propio = RUT.editable(f"comandos.{codigo}.txt")
        if propio.exists():
            return propio
    return ARCHIVO

# nombre de la sección -> (largo mínimo de cada entrada, para que no salten sin querer)
SECCIONES = {
    "reiniciar_conversacion": 4,
    "profundo_frases": 4,
    "profundo_ordenes_en_cualquier_sitio": 4,
    "profundo_verbos_al_principio": 4,
    "profundo_verbos_no_si_va_despues_de": 2,
    "profundo_automatico": 4,
    "borrar_definitivo": 4,
    "confirmar_si_al_principio": 2,
    "confirmar_si_en_cualquier_sitio": 4,
    "confirmar_no": 2,
    "cancelar": 4,
    "profundo_peticiones_abiertas": 4,
    "ventanas_sensibles": 4,
}
OPCIONALES = {"cancelar", "profundo_peticiones_abiertas", "ventanas_sensibles"}        # si tu comandos.txt es anterior y no la tiene, se usan las de fábrica sin avisar

# ---- Valores de fábrica (se usan solo si falta una sección en comandos.txt) ----
# @@DEFECTOS@@
DEFECTOS = {
    'ventanas_sensibles': [
        'banco', 'bank', 'bbva', 'santander', 'caixabank', 'caixa', 'paypal', 'revolut', 'bizum',
        'facturación', 'billing', 'factura', 'tarjeta', 'tarjetas', 'iban',
        'contraseña', 'contraseñas', 'password', 'passwords', 'keepass', 'keepassxc', 'bitwarden', '1password', 'lastpass', 'kwallet',
        'cartera', 'wallet', 'pago', 'pagos', 'payment', 'checkout',
        'hacienda', 'agencia tributaria', 'sede electrónica',
        'clave de api', 'api key', 'api keys', 'token', 'secreto', 'secret',
        'navegación privada', 'private browsing', 'incógnito', 'incognito'],
    'profundo_peticiones_abiertas': [
        'configúramelo todo',
        'configúrmelo todo',
        'configurármelo todo',
        'déjamelo configurado',
        'déjamelo todo configurado',
        'prepáramelo todo',
        'quiero poder'],
    'cancelar': [
        'para',
        'para ya',
        'para eso',
        'pare',
        'detente',
        'detén eso',
        'stop',
        'alto',
        'cancela',
        'cancela eso',
        'cancélalo',
        'cancela todo',
        'déjalo',
        'déjalo estar',
        'olvídalo',
        'olvida eso',
        'basta',
        'ya vale',
        'da igual',
        'no importa',
        'no hagas nada',
        'no sigas',
        'no continúes'],
    'reiniciar_conversacion': [
        'nueva conversación',
        'olvida lo anterior',
        'olvida todo',
        'empieza de nuevo',
        'empezamos de nuevo',
        'empecemos de nuevo',
        'borra la conversación'],
    'profundo_frases': [
        'piensa bien',
        'piénsalo bien',
        'piénsalo mejor',
        'piénsalo despacio',
        'piénsalo a fondo',
        'piensa a fondo',
        'piensa con calma',
        'razona bien',
        'razónalo bien',
        'razona paso a paso',
        'analiza bien',
        'analízalo bien',
        'analízalo a fondo',
        'analiza a fondo',
        'investígalo a fondo',
        'investiga a fondo',
        'revísalo bien',
        'revisa bien',
        'mira bien',
        'comprueba bien',
        'compruébalo bien',
        'verifica bien',
        'verifícalo bien',
        'tómate tu tiempo',
        'tómate el tiempo',
        'tómate tiempo',
        'con calma',
        'con tranquilidad',
        'sin prisa',
        'con cuidado',
        'paso a paso',
        'paso por paso',
        'en profundidad',
        'a fondo',
        'a conciencia',
        'dale una vuelta',
        'dale vueltas',
        'razonamiento profundo',
        'modo razonamiento',
        'modo profundo',
        'todo tu razonamiento',
        'mejor modelo',
        'modelo potente',
        'modelo más potente',
        'modelo bueno'],
    'profundo_ordenes_en_cualquier_sitio': [
        'piénsalo',
        'pensalo',
        'razónalo',
        'analízalo',
        'investígalo',
        'reflexiónalo',
        'medítalo',
        'estudíalo',
        'examínalo',
        'profundiza',
        'esfuérzate',
        'asegúrate',
        'detenidamente',
        'detalladamente'],
    'profundo_verbos_al_principio': [
        'piensa',
        'pensa',
        'razona',
        'analiza',
        'investiga',
        'reflexiona',
        'medita',
        'estudia',
        'examina',
        'evalúa'],
    'profundo_verbos_no_si_va_despues_de': [
        'qué',
        'quién',
        'quiénes',
        'cómo',
        'cuándo',
        'dónde',
        'no',
        'se',
        'lo',
        'la',
        'le',
        'porque'],
    'profundo_automatico': [
        'diagnostica',
        'diagnóstico',
        'diagnostícame',
        'arregla',
        'arréglame',
        'soluciona',
        'soluciónalo',
        'depura',
        'optimiza',
        'optimízame',
        'automatiza',
        'automatízame',
        'script',
        'backup',
        'copia de seguridad'],
    'borrar_definitivo': [
        'definitivamente',
        'de forma definitiva',
        'para siempre',
        'permanentemente',
        'sin papelera',
        'sin pasar por la papelera'],
    'confirmar_si_al_principio': [
        'sí',
        'vale',
        'ok',
        'okey',
        'okay',
        'dale',
        'adelante',
        'venga',
        'claro',
        'perfecto',
        'genial',
        'correcto',
        'confirmo',
        'confirmado',
        'procede',
        'hazlo',
        'hazla',
        'hazlos'],
    'confirmar_si_en_cualquier_sitio': [
        'instálalo',
        'instálala',
        'instálalos',
        'instálamelo',
        'ejecútalo',
        'ejecútamelo',
        'bórralo',
        'elimínalo',
        'créamelo',
        'créalo',
        'ábrelo',
        'actualízalo',
        'actualízamelo',
        'desinstálalo',
        'arréglalo',
        'configúralo',
        'ponlo',
        'actívalo',
        'desactívalo',
        'hazlo',
        'hazla',
        'hazlos'],
    'confirmar_no': [
        'no',
        'nunca',
        'cancela',
        'cancelar',
        'cancélalo',
        'espera',
        'para',
        'detente',
        'jamás',
        'tampoco',
        'nada',
        'mejor',
        'ni',
        'pero'],
}
# @@FIN_DEFECTOS@@


def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)


def normalizar(texto):
    """Palabras en minúsculas, sin tildes ni signos y separadas por un espacio."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", str(texto).lower()) if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", sin_tildes))


def _parsear(texto):
    """Devuelve ({sección: [entradas]}, [avisos])."""
    secciones, avisos, actual = {}, [], None
    for n, linea in enumerate(texto.splitlines(), 1):
        l = re.split(r"\s#", linea.strip(), maxsplit=1)[0].strip()   # permite comentario al final de la línea
        if not l or l.startswith("#"):
            continue
        if l.startswith("["):
            m = re.fullmatch(r"\[([a-z_]+)\]", l)
            if not m:
                avisos.append(f"línea {n}: «{l}» parece una sección mal escrita (se ignora)")
                actual = None
            elif m.group(1) not in SECCIONES:
                avisos.append(f"línea {n}: la sección [{m.group(1)}] no existe (se ignora). "
                              f"Las válidas son: {', '.join(SECCIONES)}")
                actual = None
            else:
                actual = m.group(1)
                secciones.setdefault(actual, [])
            continue
        if actual is None:
            avisos.append(f"línea {n}: «{l}» está fuera de una sección válida (se ignora)")
            continue
        secciones[actual].append(l)
    return secciones, avisos


def _preparar(secciones, avisos, avisar_faltantes=True):
    datos = {}
    for nombre, minimo in SECCIONES.items():
        if nombre in secciones:
            entradas = secciones[nombre]
        else:
            entradas = DEFECTOS.get(nombre, [])
            if nombre not in OPCIONALES and avisar_faltantes:
                avisos.append(f"falta la sección [{nombre}]: uso los valores de fábrica")
        limpias = []
        for e in entradas:
            n = normalizar(e)
            if not n:
                continue
            if len(n) < minimo:
                avisos.append(f"[{nombre}] «{e}» es demasiado corta (mínimo {minimo} letras): se ignora")
                continue
            if n not in limpias:
                limpias.append(n)
        datos[nombre] = limpias
        if nombre == "reiniciar_conversacion":
            datos["_reiniciar_originales"] = [e.strip() for e in entradas if normalizar(e)]
    si = set(datos["confirmar_si_al_principio"]) | set(datos["confirmar_si_en_cualquier_sitio"])
    for comun in sorted(si & set(datos["confirmar_no"])):
        avisos.append(f"«{comun}» está a la vez en las listas de «sí» y de «no»: ganará el «no»")
    return datos


_cache = {"marca": "sin leer", "datos": None}


def _datos():
    """Los datos actuales; vuelve a leer comandos.txt solo si ha cambiado."""
    ruta = archivo()
    try:
        marca = (str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
        marca = None
    if _cache["datos"] is not None and _cache["marca"] == marca:
        return _cache["datos"]
    avisos = []
    leido = True
    if marca is None:
        avisos.append(f"no encuentro {ruta.name}: uso los valores de fábrica")
        secciones, leido = {}, False                  # un solo aviso: no tiene sentido avisar además de cada sección que «falta»
    else:
        try:
            secciones, avisos = _parsear(ruta.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            avisos.append(f"no he podido leer {ruta.name} ({e}): uso los valores de fábrica")
            secciones, leido = {}, False
    datos = _preparar(secciones, avisos, avisar_faltantes=leido)
    if _cache["datos"] is None:
        log(f"Órdenes por voz cargadas de {ruta.name}")
    else:
        log(f"{ruta.name} cambiado: órdenes por voz recargadas")
    for aviso in avisos:
        log(f"   Aviso en {ruta.name}: {aviso}")
    _cache["marca"], _cache["datos"] = marca, datos
    return datos


def cargar():
    """Fuerza la lectura (útil al arrancar, para ver los avisos en el registro)."""
    return _datos()


# ---- Cómo se compara lo que dices con cada lista ----
def _contiene(solo, entrada):
    """La palabra o frase aparece completa en cualquier parte."""
    return f" {entrada} " in f" {solo} "


def _empieza(solo, entrada):
    """La frase empieza por la palabra o frase."""
    return solo == entrada or solo.startswith(entrada + " ")


# ---- Lo que usa el asistente ----
_RELLENO_CANCELAR_ES = {"ya", "eso", "esto", "todo", "por", "favor", "porfa", "vale", "venga", "gracias", "ahora", "mismo", "asistente", "y"}
_RELLENO_CANCELAR_EN = {"it", "that", "this", "all", "please", "now", "thanks", "thank", "you", "assistant", "right", "already", "and", "lina"}
_RELLENO_CANCELAR = IDI.PorIdioma({"es": _RELLENO_CANCELAR_ES, "en": _RELLENO_CANCELAR_EN})


_PANTALLA_CLARA_EN = {"this", "here", "screen", "window", "look", "see", "says", "shows", "appears", "these"}
_PANTALLA_FRASES_EN = ("what do i do", "what do i click", "where do i click", "what does this mean", "what is that", "what is this", "what's this", "what's on", "what i see", "what you see")
_PANTALLA_CLARA_ES = {"esto", "aqui", "ahi", "pantalla", "ventana", "mira", "mirar", "mirame", "ves", "veo", "pone", "dice", "salio", "sale", "aparece", "este", "estos"}
_PANTALLA_FRASES_ES = ("que hago", "que pulso", "donde le doy", "donde pulso", "que significa", "que es eso", "que me sale", "que me aparece", "lo que veo", "lo que ves")


_PANTALLA_CLARA = {"es": _PANTALLA_CLARA_ES, "en": _PANTALLA_CLARA_EN}
_PANTALLA_FRASES = {"es": _PANTALLA_FRASES_ES, "en": _PANTALLA_FRASES_EN}


def pide_mirar(texto):
    """¿Hablas de lo que ves en pantalla («esto», «aquí», «qué pone», «mira…»)? Es solo un atajo: si no lo detecta, la IA puede pedir la captura."""
    solo = normalizar(texto)
    return bool(set(solo.split()) & IDI.segun(_PANTALLA_CLARA)) or any(f in solo for f in IDI.segun(_PANTALLA_FRASES))


def ventana_sensible(titulo, clase=""):
    """¿La ventana (por su título o su clase) parece de banco, facturación, contraseñas…? Si sí, NUNCA se envía su captura. Es tu lista
    (sección [ventanas_sensibles] de comandos.txt); una lista nunca es perfecta, pero esto no depende de lo que decida la IA."""
    texto = normalizar(f"{titulo or ''} {clase or ''}")
    if not texto:
        return False
    for e in _datos()["ventanas_sensibles"]:
        if len(e) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(e) + r"(?![a-z0-9])", texto):
            return True
    return False


def quiere_cancelar(texto):
    """¿Has dicho solo «para», «cancela», «déjalo»…? (con un «ya» o un «por favor» vale; si sigue otra cosa, como «para qué sirve», no)."""
    solo = normalizar(texto)
    if not solo or len(solo.split()) > 6:
        return False
    for e in _datos()["cancelar"]:
        if solo == e or (solo.startswith(e + " ") and all(w in _RELLENO_CANCELAR for w in solo[len(e):].split())):
            return True
    return False


def quiere_reiniciar(texto):
    """¿Has dicho «nueva conversación», «olvida lo anterior»...?"""
    solo = normalizar(texto)
    return any(_empieza(solo, e) for e in _datos()["reiniciar_conversacion"])


def prompt_reinicio():
    """Pista para Whisper: las dos primeras frases de reinicio, tal como las has escrito."""
    originales = _datos()["_reiniciar_originales"][:2]
    return ". ".join(o[:1].upper() + o[1:] for o in originales) + "." if originales else ""


def elegir_modo(texto, tipo_contexto=None):
    """('profundo', motivo) si lo pides o si es una tarea pesada; si no, ('rapido', '')."""
    d = _datos()
    solo = normalizar(texto)
    palabras = solo.split()
    for e in d["profundo_frases"]:
        if _contiene(solo, e):
            return "profundo", f"frase «{e}»"
    for e in d["profundo_ordenes_en_cualquier_sitio"]:
        if _contiene(solo, e):
            return "profundo", f"orden «{e}»"
    for e in d["profundo_peticiones_abiertas"]:                  # «configúramelo todo», «quiero poder…»: hay que decidir QUÉ hacer, no solo hacerlo
        if _contiene(solo, e):
            return "profundo", f"petición abierta «{e}»"
    for i, p in enumerate(palabras[:4]):
        if p in d["profundo_verbos_al_principio"] and not (i > 0 and palabras[i - 1] in d["profundo_verbos_no_si_va_despues_de"]):
            return "profundo", f"orden «{p}»"
    if tipo_contexto != "juego":
        for e in d["profundo_automatico"]:
            if _contiene(solo, e):
                return "profundo", f"palabra «{e}»"
    return "rapido", ""


def es_afirmativo(texto):
    """¿Ha dicho «sí», «vale», «hazlo», «instálalo»...? Cualquier duda cuenta como «no»."""
    solo = normalizar(texto)
    palabras = solo.split()
    if not palabras or len(palabras) > 8:
        return False
    d = _datos()
    if any(_contiene(solo, e) for e in d["confirmar_no"]):
        return False
    return (any(_empieza(solo, e) for e in d["confirmar_si_al_principio"])
            or any(_contiene(solo, e) for e in d["confirmar_si_en_cualquier_sitio"]))


def confirmacion_clara(texto):
    """'si' o 'no' SOLO cuando la respuesta es cortísima y todas sus palabras están en tus listas de sí o de no
    («sí», «vale hazlo», «no», «mejor no»...). Si hay cualquier palabra de más («sí, pero mejor muévelo»), devuelve None
    y decide la IA. Así un «sí» al principio de una frase larga ya no ejecuta algo que el usuario está cambiando."""
    solo = normalizar(texto)
    palabras = solo.split()
    if not palabras or len(palabras) > 4:
        return None
    d = _datos()
    vocab_no = {w for e in d["confirmar_no"] for w in e.split()}
    vocab_si = {w for e in d["confirmar_si_al_principio"] + d["confirmar_si_en_cualquier_sitio"] for w in e.split()}
    if all(w in vocab_no for w in palabras) and any(_contiene(solo, e) for e in d["confirmar_no"]):
        return "no"
    if all(w in vocab_si for w in palabras) and es_afirmativo(texto):
        return "si"
    return None


_NUMEROS = (r"\d|\b(?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieciseis|diecisiete|"
            r"dieciocho|diecinueve|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|"
            r"doscientos|trescientos|cuatrocientos|quinientos|mil|medio|media)\b|\b(?:un|una)\s+(?:euro|dolar|centimo)")


def menciona_cantidad(texto):
    """¿Ha dicho una cantidad («5 euros», «hasta cinco»...)? Para lo que cuesta dinero se exige que la diga el usuario."""
    return re.search(_NUMEROS, normalizar(texto)) is not None


def borrado_definitivo(texto):
    """¿Has pedido borrar «definitivamente» / «para siempre» / «sin papelera»? Si no, los borrados van a la papelera."""
    solo = normalizar(texto)
    return any(_contiene(solo, e) for e in _datos()["borrar_definitivo"])


# ======================= PROGRAMAS INSTALADOS Y PISTAS DE VOZ =======================
# Whisper falla sobre todo con NOMBRES de programas y palabras en inglés dichas en español. Estas utilidades no saben nada de ningún
# programa en concreto: leen los que hay instalados (archivos .desktop) y comparan cómo SUENA lo que se oyó con cómo suenan sus nombres.
import os
from difflib import SequenceMatcher

_cache_apps: dict = {"firma": None, "datos": []}


def _dirs_apps():
    base = [Path("/usr/share/applications"), Path("/usr/local/share/applications"), Path.home() / ".local/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"), Path.home() / ".local/share/flatpak/exports/share/applications"]
    for d in os.environ.get("XDG_DATA_DIRS", "").split(":"):
        if d:
            base.append(Path(d) / "applications")
    vistos, dirs = set(), []
    for d in base:
        if str(d) not in vistos:
            vistos.add(str(d))
            dirs.append(d)
    return dirs


DIRS_APPS = _dirs_apps


def _leer_desktop(ruta):
    """{'nombre', 'comando'} de un .desktop que sea un programa con ventana; None si no lo es."""
    campos, dentro = {}, False
    try:
        lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for l in lineas:
        l = l.strip()
        if l.startswith("["):
            dentro = (l == "[Desktop Entry]")
            continue
        if dentro and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1)
            campos.setdefault(k.strip(), v.strip())
    if campos.get("Type", "Application") != "Application" or campos.get("NoDisplay", "").lower() == "true" or campos.get("Hidden", "").lower() == "true":
        return None
    nombre, ejec = campos.get("Name", ""), campos.get("Exec", "")
    if not nombre or not ejec:
        return None
    ejec = re.sub(r"\s*%[a-zA-Z]", "", ejec).strip()
    ejec = re.sub(r"^env\s+(?:\w+=\S+\s+)+", "", ejec)
    return {"nombre": nombre, "comando": ejec[:90], "es": campos.get("Name[es]", ""), "id": ruta.stem,
            "generico": campos.get("GenericName[es]", "") or campos.get("GenericName", ""),
            "claves": campos.get("Keywords[es]", "") or campos.get("Keywords", ""),
            "terminal": campos.get("Terminal", "").lower() == "true"}


def nombres_de_apps():
    """Los programas con ventana que hay instalados: [{'nombre': 'Kate', 'comando': 'kate', 'es': ...}]. Se recalcula si cambian las carpetas."""
    dirs = [d for d in DIRS_APPS() if d.is_dir()]
    try:
        firma = tuple((str(d), d.stat().st_mtime_ns) for d in dirs)
    except OSError:
        firma = None
    if firma is not None and firma == _cache_apps["firma"]:
        return _cache_apps["datos"]
    vistos, datos = set(), []
    for d in dirs:
        try:
            archivos = sorted(d.glob("*.desktop"))
        except OSError:
            continue
        for f in archivos:
            app = _leer_desktop(f)
            clave = normalizar(app["nombre"]) if app else ""
            if app and clave and clave not in vistos:
                vistos.add(clave)
                app["origen"] = str(d)
                datos.append(app)
    _cache_apps["firma"], _cache_apps["datos"] = firma, datos
    return datos


def esqueleto(texto):
    """Cómo SUENA un texto, a grandes rasgos: las consonantes, escritas con las reglas del español («cait» y «Kate» → «kt»)."""
    t = re.sub(r"[^a-z0-9]", "", normalizar(texto))
    for a, b in (("ph", "f"), ("ck", "k"), ("qu", "k"), ("sh", "X"), ("ch", "X"), ("th", "t"), ("ll", "i")):
        t = t.replace(a, b)
    t = t.replace("x", "ks")
    t = re.sub(r"c(?=[ei])", "s", t).replace("c", "k").replace("z", "s").replace("v", "b").replace("w", "u").replace("y", "i").replace("j", "X")
    t = t.replace("h", "")
    t = re.sub(r"(.)\1+", r"\1", t)
    return re.sub(r"[aeiou]", "", t)


def _parecido(oido, nombre):
    """0-1: cuánto SUENA «oido» como «nombre». Se mira cómo suenan las consonantes Y cómo se escriben; los nombres con pocas consonantes
    (que casan con casi cualquier palabra) tienen que sonar exactamente igual o escribirse casi igual."""
    a, b = esqueleto(oido), esqueleto(nombre)
    if not a or not b or a[0] != b[0]:
        return 0.0
    sonido = 1.0 if a == b else SequenceMatcher(None, a, b).ratio()
    letras = SequenceMatcher(None, normalizar(oido).replace(" ", ""), normalizar(nombre).replace(" ", "")).ratio()
    combinado = 0.7 * sonido + 0.3 * letras
    if sonido == 1.0 or (sonido >= 0.8 and letras >= 0.75):
        return combinado
    return 0.0


UMBRAL_PARECIDO = 0.78
_VERBOS_DE_PROGRAMA = {"abre", "abrir", "abra", "abres", "lanza", "lanzar", "ejecuta", "ejecutar", "inicia", "iniciar", "arranca", "arrancar",
                       "cierra", "cerrar", "cierre"}
_RELLENO = {"el", "la", "los", "las", "un", "una", "mi", "mis", "me", "programa", "aplicacion", "app", "por", "favor", "de", "del", "y", "e", "que", "ahora"}


def pistas_de_voz(texto, apps=None):
    """Si le pides abrir o cerrar algo y lo que se oyó no es ningún programa pero SUENA como uno instalado, una pista para la IA.
    Vacío si no hay nada que sugerir (o si lo que dijiste ya es el nombre de un programa)."""
    palabras = normalizar(texto).split()
    idx = next((i for i, w in enumerate(palabras) if w in _VERBOS_DE_PROGRAMA), None)
    if idx is None:
        return ""
    apps = nombres_de_apps() if apps is None else apps
    objeto = [w for w in palabras[idx + 1:idx + 5] if w not in _RELLENO]
    if not objeto or not apps:
        return ""
    frases = {" ".join(objeto[i:j]) for i in range(len(objeto)) for j in range(i + 1, min(i + 3, len(objeto)) + 1)}
    propios = {}
    for app in apps:
        cmd = app["comando"].split()[0].rsplit("/", 1)[-1] if app["comando"].split() else ""
        propios[app["nombre"]] = {n for n in {normalizar(app["nombre"]), normalizar(app.get("es", "")), normalizar(cmd), normalizar(app["nombre"]).split(" ")[0]} if n}
    for f in frases:
        if any(f == n or f.replace(" ", "") == n.replace(" ", "") for ns in propios.values() for n in ns):
            return ""                                     # ya dijiste el nombre de un programa: no hace falta ninguna pista
    mejores = []
    for app in apps:
        puntos = max((_parecido(f, n) for f in frases for n in propios[app["nombre"]] if len(n) >= 3), default=0.0)
        if puntos >= UMBRAL_PARECIDO:
            frase = max(frases, key=lambda f: max((_parecido(f, n) for n in propios[app["nombre"]] if len(n) >= 3), default=0.0))
            mejores.append((puntos, frase, app))
    if not mejores:
        return ""
    mejores.sort(key=lambda x: (-x[0], len(x[2]["nombre"])))
    partes = [f"«{f}» suena como el programa «{a['nombre']}» (se lanza con `{a['comando']}`)" for _, f, a in mejores[:2]]
    return ("Posible error de la transcripción (el reconocimiento de voz falla con nombres de programas): " + "; ".join(partes)
            + ". Si la frase no tiene sentido tal cual, usa esa pista.")


def _nombres_de_app(app):
    """Todas las formas en que se puede llamar a un programa instalado (normalizadas): su nombre, el nombre en español, su comando y su id."""
    cmd = app["comando"].split()[0].rsplit("/", 1)[-1] if app["comando"].split() else ""
    ident = str(app.get("id", ""))
    return {n for n in {normalizar(app["nombre"]), normalizar(app.get("es", "")), normalizar(cmd), normalizar(ident),
                        normalizar(ident.rsplit(".", 1)[-1])} if len(n) >= 2}


def buscar_app(consulta, apps=None):
    """Los programas INSTALADOS que encajan con lo que se ha dicho, de más a menos parecido: [(puntos 0-100, app)]. Mira nombre, nombre en
    español, comando, id del lanzador, tipo de programa y palabras clave, y tolera que el reconocimiento de voz haya oído otra cosa que suena igual.
    100 = el nombre exacto. Vacío si nada se parece."""
    q = [w for w in normalizar(consulta).split() if w not in _RELLENO and w not in _VERBOS_DE_PROGRAMA]
    if not q:
        return []
    qj = " ".join(q)
    apps = nombres_de_apps() if apps is None else apps
    resultado = []
    for a in apps:
        nombres = _nombres_de_app(a)
        palabras_nombre = set(normalizar(a["nombre"] + " " + a.get("es", "")).split())
        texto = set(normalizar(" ".join([a["nombre"], a.get("es", ""), a.get("generico", ""), a.get("claves", "").replace(";", " ")])).split())
        if qj in nombres or qj.replace(" ", "") in {n.replace(" ", "") for n in nombres}:
            puntos = 100
        elif all(w in palabras_nombre for w in q):                       # «code» dentro de «Visual Studio Code»
            puntos = 88
        elif any(n and set(n.split()) <= set(q) for n in nombres if len(n) >= 4):   # «claude desktop» cuando el programa se llama «Claude»
            puntos = 84
        elif all(w in texto for w in q):
            puntos = 70
        else:
            sonido = max((_parecido(qj, n) for n in nombres if len(n) >= 3), default=0.0)
            puntos = int(80 * sonido) if sonido >= UMBRAL_PARECIDO else 0
        if puntos >= 55:
            resultado.append((puntos, a))
    resultado.sort(key=lambda x: (-x[0], len(x[1]["nombre"]), normalizar(x[1]["nombre"])))
    return resultado


def _usos_de_apps(apps, ruta_log, ultimas=3000):
    """{nombre_de_la_app: veces que se ha ejecutado su comando} según acciones.log (para poner primero lo que más usas)."""
    try:
        lineas = Path(ruta_log).read_text(encoding="utf-8", errors="replace").splitlines()[-ultimas:]
    except OSError:
        return {}
    cuentas = {}
    for l in lineas:
        m = re.search(r"\[fin rc=-?\d+\]\s+(?:sudo\s+)?(\S+)", l)
        if m:
            c = m.group(1).rsplit("/", 1)[-1]
            cuentas[c] = cuentas.get(c, 0) + 1
    usos = {}
    for a in apps:
        cmd = a["comando"].split()[0].rsplit("/", 1)[-1] if a["comando"].split() else ""
        usos[a["nombre"]] = cuentas.get(cmd, 0)
    return usos


def ordenar_apps(apps, ruta_log=None):
    """Primero los programas que más usas; el resto por orden alfabético."""
    usos = _usos_de_apps(apps, ruta_log) if ruta_log else {}
    return sorted(apps, key=lambda a: (-usos.get(a["nombre"], 0), normalizar(a["nombre"])))


def lista_de_apps_para_la_ia(texto, apps=None, ruta_log=None, maximo=70, caracteres=1100):
    """Si le pides abrir o cerrar algo y no has dicho el nombre de ningún programa, los que hay instalados (para que la IA deduzca cuál era
    por el contexto cuando el reconocimiento de voz ha oído otra cosa). Vacío si no hace falta."""
    palabras = normalizar(texto).split()
    if not any(w in _VERBOS_DE_PROGRAMA for w in palabras):
        return ""
    apps = nombres_de_apps() if apps is None else apps
    if not apps:
        return ""
    dicho = " ".join(palabras)
    for a in apps:
        for n in {normalizar(a["nombre"]), normalizar(a.get("es", "")), normalizar(a["comando"].split()[0].rsplit("/", 1)[-1]) if a["comando"].split() else ""}:
            if len(n) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", dicho):
                return ""                                  # ya has dicho el nombre de uno: no hace falta la lista
    nombres, total = [], 0
    for a in ordenar_apps(apps, ruta_log):
        if total + len(a["nombre"]) + 2 > caracteres or len(nombres) >= maximo:
            break
        nombres.append(a["nombre"])
        total += len(a["nombre"]) + 2
    return ("Programas instalados en este PC (por si el reconocimiento de voz ha oído mal el nombre del que quiere abrir o cerrar): "
            + ", ".join(nombres) + ".")


# ======================= ALIAS: lo que el reconocimiento de voz oye mal y lo que querías decir =======================
# Se apuntan en alias.txt («cait = Kate»). Lo escribe el asistente cuando le enseñas («cuando oigas cait quiero decir Kate») o le corriges,
# y también puedes editarlo a mano. Es una lista TUYA: ninguna actualización la pisa.
ARCHIVO_ALIAS = RUT.CONFIG / "alias.txt"
MAX_ALIAS = 200
_cache_alias: dict = {"marca": None, "datos": {}}
_CABECERA_ALIAS = ("# Lo que el reconocimiento de voz suele OÍR mal = lo que querías decir. Una por línea: «lo oído = lo que significa».\n"
                   "# Las apunta el asistente cuando le dices «cuando oigas cait quiero decir Kate»; también puedes editar este archivo a mano.\n")
_NO_ES_ALIAS = {"para", "por", "con", "sin", "que", "los", "las", "una", "uno", "del", "como", "pero", "sobre", "esto", "eso", "este", "esta", "mas", "muy",
                "hay", "ese", "esa", "mis", "tus", "sus", "nos", "les", "ahora", "favor", "abre", "abrir", "cierra", "cerrar", "pon", "poner", "dime",
                "hola", "vale", "gracias", "quiero", "puedes", "haz", "hacer", "algo", "todo", "nada", "sii", "nooo"}


def _leer_alias(ruta=None):
    """{oído normalizado: (oído, significa)} de alias.txt; se vuelve a leer solo si el archivo ha cambiado."""
    ruta = Path(ruta or ARCHIVO_ALIAS)
    try:
        marca = (str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
        return {}
    if _cache_alias["marca"] == marca:
        return _cache_alias["datos"]
    datos = {}
    try:
        lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for l in lineas:
        l = l.strip()
        if not l or l.startswith("#") or "=" not in l:
            continue
        oido, significa = (x.strip() for x in l.split("=", 1))
        clave = normalizar(oido)
        if clave and significa:
            datos[clave] = (oido, significa)
    _cache_alias["marca"], _cache_alias["datos"] = marca, datos
    return datos


def listar_alias(ruta=None):
    return [v for v in _leer_alias(ruta).values()]


def _limpiar_alias(texto, maximo):
    texto = re.sub(r"\s+", " ", str(texto or "")).strip(" \t.,;:¡!¿?\"'«»()[]")
    if not texto or len(texto) > maximo or not re.fullmatch(r"[\w'.+\- ]+", texto, re.UNICODE):
        return ""
    return texto


def guardar_alias(oido, significa, ruta=None):
    """Apunta «oido = significa». Devuelve (hecho, mensaje para decirle al usuario). Se rechaza lo que podría romper algo."""
    ruta = Path(ruta or ARCHIVO_ALIAS)
    o, s = _limpiar_alias(oido, 30), _limpiar_alias(significa, 40)
    if not o or not s or len(o.split()) > 3 or len(s.split()) > 4:
        return False, T("No lo he apuntado: tiene que ser una palabra (o hasta tres) que se oye mal y lo que quieres decir, cortos y sin símbolos raros.")
    clave = normalizar(o)
    if len(clave.replace(" ", "")) < 3 or clave.replace(" ", "").isdigit() or all(w in _NO_ES_ALIAS for w in clave.split()):
        return False, T("No lo he apuntado: «{palabra}» es una palabra demasiado corriente y se usaría sin querer en otras frases.", palabra=o)
    if clave == normalizar(s):
        return False, T("«{oido}» y «{significa}» ya suenan igual para mí: no hace falta apuntar nada.", oido=o, significa=s)
    alias = _leer_alias(ruta)
    if clave not in alias and len(alias) >= MAX_ALIAS:
        return False, T("Ya hay {n} alias apuntados: borra alguno antes de añadir más.", n=MAX_ALIAS)
    lineas = []
    try:
        lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lineas = _CABECERA_ALIAS.splitlines()
    nuevas, puesta = [], False
    for l in lineas:
        if "=" in l and not l.strip().startswith("#") and normalizar(l.split("=", 1)[0]) == clave:
            if not puesta:
                nuevas.append(f"{o} = {s}")
                puesta = True
            continue
        nuevas.append(l)
    if not puesta:
        nuevas.append(f"{o} = {s}")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(ruta.name + ".tmp")
        tmp.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
        tmp.replace(ruta)
    except OSError as e:
        return False, f"No he podido guardarlo ({e.strerror or e})."
    return True, f"Apuntado: cuando oiga «{o}» entenderé «{s}»."


def borrar_alias(oido, ruta=None):
    """Quita un alias. Devuelve (hecho, mensaje)."""
    ruta = Path(ruta or ARCHIVO_ALIAS)
    clave = normalizar(_limpiar_alias(oido, 30))
    if not clave or clave not in _leer_alias(ruta):
        return False, T("No tengo apuntado ningún alias para «{oido}».", oido=str(oido).strip())
    lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
    nuevas = [l for l in lineas if not ("=" in l and not l.strip().startswith("#") and normalizar(l.split("=", 1)[0]) == clave)]
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
    tmp.replace(ruta)
    return True, T("Hecho: ya no entenderé «{oido}» como otra cosa.", oido=str(oido).strip())


def aplicar_alias(texto, ruta=None):
    """Cambia en tu frase lo que tienes apuntado como mal oído por lo que querías decir. Devuelve (frase nueva, [(oído, significa)])."""
    alias = _leer_alias(ruta)
    if not alias or not texto:
        return texto, []
    tokens = re.findall(r"\S+", texto)
    norm = [normalizar(x) for x in tokens]
    mas_largo = max(len(k.split()) for k in alias)
    salida, hechos, i = [], [], 0
    while i < len(tokens):
        for n in range(min(mas_largo, len(tokens) - i), 0, -1):
            tramo = norm[i:i + n]
            if all(tramo) and " ".join(tramo) in alias:
                oido, significa = alias[" ".join(tramo)]
                pre = re.match(r"^[^\w]*", tokens[i]).group()
                post = re.search(r"[^\w]*$", tokens[i + n - 1]).group()
                salida.append(pre + significa + post)
                hechos.append((oido, significa))
                i += n
                break
        else:
            salida.append(tokens[i])
            i += 1
    return " ".join(salida), hechos


def _acentos(frase):
    """Una frase como patrón que tolera tildes y espacios variables."""
    clases = {"a": "[aáà]", "e": "[eéè]", "i": "[ií]", "o": "[oó]", "u": "[uúü]"}
    return "".join(r"\s+" if c == " " else clases.get(c, re.escape(c)) for c in frase)


def _alt(frases):
    return "(?:" + "|".join(_acentos(f) for f in sorted(frases, key=len, reverse=True)) + ")"


_ENSENAR = re.compile(r"^(?:cuando|si)\s+(?:te\s+)?" + _alt(["diga", "digas", "digo", "oigas", "oiga", "escuches", "escuche", "entiendas", "entienda"])
                      + r"\s+(?P<oido>.+?)[,;]?\s+" + _alt(["quiero decir", "quiero que entiendas", "me refiero a", "significa", "es", "entiéndelo como",
                                                                "entiende", "en realidad es", "quiero"]) + r"\s+(?P<sig>.+)$", re.IGNORECASE)
_ENSENAR_POR = re.compile(r"^por\s+(?P<oido>.+?)\s+" + _alt(["entiende", "entiéndeme", "entiendes"]) + r"\s+(?P<sig>.+)$|^entiende\s+(?P<oido2>.+?)\s+como\s+(?P<sig2>.+)$",
                          re.IGNORECASE)
_APRENDE = re.compile(r"^aprende\s+que\s+(?P<oido>.+?)\s+" + _alt(["es", "significa", "quiere decir"]) + r"\s+(?P<sig>.+)$", re.IGNORECASE)
_OLVIDAR = re.compile(r"^(?:olvida|borra|quita|elimina)\s+(?:el\s+)?alias\s+(?:de\s+)?(?P<oido>.+)$|^olvida\s+que\s+(?P<oido2>.+?)\s+(?:es|significa)\s+.+$",
                      re.IGNORECASE)


_EN_ENSENAR = re.compile(r"^(?:when|if)\s+(?:i|you\s+hear|you\s+see)\s+(?:say\s+|hear\s+)?(?P<oido>.+?)[,;]?\s+(?:i\s+mean|i\s+meant|it\s+means|that\s+means|understand\s+it\s+as)\s+(?P<sig>.+)$", re.IGNORECASE)
_EN_ENSENAR_POR = re.compile(r"^(?:understand|read)\s+(?P<oido>.+?)\s+as\s+(?P<sig>.+)$", re.IGNORECASE)
_EN_APRENDE = re.compile(r"^(?:learn|remember)\s+that\s+(?P<oido>.+?)\s+(?:is|means|stands\s+for)\s+(?P<sig>.+)$", re.IGNORECASE)
_EN_OLVIDAR = re.compile(r"^(?:forget|delete|remove|drop)\s+(?:the\s+)?alias\s+(?:for\s+)?(?P<oido>.+)$|^forget\s+that\s+(?P<oido2>.+?)\s+(?:is|means)\s+.+$", re.IGNORECASE)
_ALIAS_POR_IDIOMA = {"es": (_ENSENAR, _ENSENAR_POR, _APRENDE, _OLVIDAR), "en": (_EN_ENSENAR, _EN_ENSENAR_POR, _EN_APRENDE, _EN_OLVIDAR)}          # las frases con las que se enseña o se quita un alias, por idioma


def entender_alias(texto, apps=None):
    """¿Le estás enseñando o quitando un alias? → ('aprender', oído, significa) / ('olvidar', oído) / None.
    «Cuando oigas cait quiero decir Kate» enseña. «Aprende que cait es Kate» solo vale si Kate es un programa instalado (para no confundirlo
    con «aprende que el cielo es azul»). «Recuerda que mañana es lunes» no es nada de esto."""
    frase = re.sub(r"\s+", " ", str(texto or "")).strip().rstrip(".!?¡¿ ")
    if not frase or len(frase.split()) > 16:
        return None
    _ENSENAR, _ENSENAR_POR, _APRENDE, _OLVIDAR = IDI.segun(_ALIAS_POR_IDIOMA)
    m = _OLVIDAR.match(frase)
    if m:
        return ("olvidar", (m.group("oido") or m.group("oido2")).strip())
    m = _ENSENAR.match(frase)
    if m:
        return ("aprender", m.group("oido").strip(), m.group("sig").strip())
    m = _ENSENAR_POR.match(frase)
    if m:
        return ("aprender", (m.group("oido") or m.group("oido2")).strip(), (m.group("sig") or m.group("sig2")).strip())
    m = _APRENDE.match(frase)
    if m:
        destino = normalizar(m.group("sig"))
        conocidos = set()
        for a in (nombres_de_apps() if apps is None else apps):
            cmd = a["comando"].split()[0].rsplit("/", 1)[-1] if a["comando"].split() else ""
            conocidos |= {normalizar(a["nombre"]), normalizar(a.get("es", "")), normalizar(cmd)}
        if destino and destino in conocidos:
            return ("aprender", m.group("oido").strip(), m.group("sig").strip())
    return None

