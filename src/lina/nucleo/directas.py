# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Órdenes directas (fase 12): «abre Firefox», «sube el volumen»… se entienden y se ejecutan SIN pasar por la IA.

Aquí solo se ENTIENDE la frase (función pura, sin sistema ni red): devuelve qué acción es y con qué datos, o None si no está claro. Quien la ejecuta
(el asistente) usa las mismas herramientas y las mismas reglas de seguridad que cuando decide la IA: esto no es una puerta lateral.
Ante la duda, None y la IA se hace cargo: es preferible tardar un poco a hacer algo que no se pidió. Solo entran acciones de riesgo bajo."""
import re
import unicodedata

from lina.nucleo import idioma as IDI
from lina.nucleo.idioma import N_, T

# Todo lo que se sabe hacer así (para `lina directas`): (id, ejemplo en español, ejemplo en inglés)
ACCIONES = (
    ("abrir_app", N_("abre Firefox · ábreme Steam · puedes abrir Dolphin"), "open Firefox"),
    ("volumen", N_("sube el volumen · baja el volumen · pon el volumen al 40"), "volume up · set the volume to 40"),
    ("silencio", N_("silencia el sonido · quita el silencio"), "mute · unmute"),
)


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9% ]", " ", t.replace("ñ", "n"))
    return re.sub(r"\s+", " ", t).strip()


# Cortesías que se pueden quitar del principio y del final sin cambiar lo que se pide
_CORTESIA_ES = (r"(?:(?:oye|vale|venga|hola|ok|por favor|me puedes|puedes|podrias|me podrias|quiero que|necesito que|me gustaria que|"
                r"quiero|necesito|te pido que|quisiera que)\s+)")
_FINAL_ES = r"(?:\s+(?:por favor|gracias|ahora|ya|un poco|otra vez))*"
_CORTESIA_EN = r"(?:(?:hey|ok|okay|please|can you|could you|would you|i want you to|i need you to|i would like you to|i d like you to)\s+)"
_FINAL_EN = r"(?:\s+(?:please|thanks|thank you|now|again|a bit|a little))*"

# Palabras que delatan que NO es solo «abre X»: se encadena otra cosa o se habla de otro objeto
_CORTA_NOMBRE = {"y", "e", "en", "con", "para", "que", "luego", "despues", "tambien", "pero", "o", "u", "si", "mientras", "cuando", "porque", "por",
                 "and", "in", "on", "with", "for", "that", "then", "after", "also", "but", "or", "if", "while", "when", "because", "at", "to", "from"}
_NO_ES_PROGRAMA = {"ventana", "ventanas", "pestana", "pestanas", "archivo", "archivos", "carpeta", "carpetas", "documento", "documentos", "cosa", "cosas",
                   "algo", "puerta", "enlace", "enlaces", "pagina", "web", "url", "link", "window", "tab", "file", "files", "folder", "document", "door",
                   "something", "thing", "page", "menu", "lista", "todo", "todos", "todas", "nada"}
_ARTICULOS_ES = r"(?:(?:el|la|los|las|un|una|unos|unas|mi|mis|tu)\s+)*(?:(?:programa|aplicacion|app)(?: de)?\s+)?"
_ARTICULOS_EN = r"(?:(?:the|a|an|my|your)\s+)*"


def _nombre_valido(nombre):
    palabras = nombre.split()
    if not 1 <= len(palabras) <= 4 or any(len(p) > 24 for p in palabras):
        return False
    return not any(p in _CORTA_NOMBRE or p in _NO_ES_PROGRAMA for p in palabras)


def _es(n):
    # ---- silencio
    if re.fullmatch(r"(?:silencia(?:r)?|silencialo|silenciala|mutea(?:r)?)(?: el (?:sonido|audio|volumen|ordenador|equipo|pc)| todo| el sonido del ordenador)?", n):
        return ("silencio", {"accion": "silenciar"})
    if re.fullmatch(r"(?:quita(?:r)? (?:el )?silencio|quita(?:r)? el mute|desilencia(?:r)?|desmutea(?:r)?|activa(?:r)? (?:el )?(?:sonido|audio)|"
                    r"pon(?:er)? (?:el )?sonido|vuelve a poner (?:el )?sonido|restaura(?:r)? (?:el )?(?:sonido|audio))", n):
        return ("silencio", {"accion": "activar_sonido"})
    # ---- volumen
    m = re.fullmatch(r"(sube|subir|aumenta|aumentar|incrementa|baja|bajar|reduce|reducir|disminuye|disminuir)(?: (?:un poco|algo|mas|mucho))?"
                     r"(?: (?:el|del))? volumen(?: del (?:sonido|audio|ordenador|equipo))?(?: (?:un|en|de|a) (\d{1,2}) ?(?:%|por ciento)?)?(?: un poco| algo| mas)?", n)
    if m:
        verbo, paso = m.group(1), m.group(2)
        accion = "subir" if verbo.startswith(("sub", "aument", "increment")) else "bajar"
        return ("volumen", {"accion": accion, **({"valor": paso} if paso else {})})
    if re.fullmatch(r"mas volumen(?: por favor)?|volumen mas alto|mas alto el volumen|mas fuerte", n):
        return ("volumen", {"accion": "subir"})
    if re.fullmatch(r"menos volumen|volumen mas bajo|mas bajo el volumen|mas bajo", n):
        return ("volumen", {"accion": "bajar"})
    m = re.fullmatch(r"(?:pon(?:er)?|deja(?:r)?|ajusta(?:r)?|establece(?:r)?|fija(?:r)?|sube|baja)?(?: el)? ?(?:volumen|sonido|audio)(?: del (?:sonido|audio|ordenador|equipo))?"
                     r" (?:al|a|en|hasta el|hasta) ?(\d{1,3}) ?(?:%|por ciento)?", n)
    if m:
        return ("volumen", {"accion": "volumen", "valor": m.group(1)})
    # ---- abrir un programa
    m = re.fullmatch(r"(?:abre|abrir|abreme|abrime|lanza|lanzar|lanzame|ejecuta|ejecutar|inicia|iniciar|arranca|arrancar|pon en marcha)(?: me)? "
                     + _ARTICULOS_ES + r"(.+)", n)
    if m and _nombre_valido(m.group(1)):
        return ("abrir_app", {"nombre": m.group(1)})
    return None


def _en(n):
    if re.fullmatch(r"(?:mute|silence)(?: (?:the )?(?:sound|audio|volume|computer|pc))?", n):
        return ("silencio", {"accion": "silenciar"})
    if re.fullmatch(r"(?:unmute|turn (?:the )?(?:sound|audio) (?:back )?on|un mute)(?: (?:the )?(?:sound|audio|volume))?", n):
        return ("silencio", {"accion": "activar_sonido"})
    m = re.fullmatch(r"(?:turn )?(?:the )?(?:volume )?(up|down)(?: the volume)?(?: (?:by )?(\d{1,2}) ?(?:%|percent)?)?", n) or \
        re.fullmatch(r"(?:turn (up|down)|raise|increase|lower|decrease|reduce)(?: the)? (?:volume)(?: (?:by )?(\d{1,2}) ?(?:%|percent)?)?", n)
    if m:
        d = m.group(1) or ("up" if re.match(r"raise|increase", n) else "down")
        return ("volumen", {"accion": "subir" if d == "up" else "bajar", **({"valor": m.group(2)} if m.group(2) else {})})
    m = re.fullmatch(r"(?:set|put|change|turn) (?:the )?(?:volume|sound|audio)(?: level)? (?:to|at) (\d{1,3}) ?(?:%|percent)?", n)
    if m:
        return ("volumen", {"accion": "volumen", "valor": m.group(1)})
    m = re.fullmatch(r"(?:open|launch|start|run) " + _ARTICULOS_EN + r"(.+?)(?: app| application| program)?", n)
    if m and _nombre_valido(m.group(1)):
        return ("abrir_app", {"nombre": m.group(1)})
    return None


def entender(texto):
    """(id, datos) si la frase ES una orden directa clara; None en cualquier otro caso (preguntas, negaciones, órdenes encadenadas, dudas)."""
    original = str(texto or "")
    if not original.strip() or len(original) > 80 or "¿" in original:
        return None                                              # frases largas o preguntas: las entiende la IA
    n = normalizar(original)
    en = IDI.actual() == "en"
    cortesia, final = (_CORTESIA_EN, _FINAL_EN) if en else (_CORTESIA_ES, _FINAL_ES)
    n = re.sub(r"^" + cortesia + "+", "", n)
    n = re.sub(final + r"$", "", n).strip()
    if re.match(r"^(?:no|nunca|jamas|sin|don t|dont|do not|never)\b", n):
        return None
    if re.match(r"^(?:como|que|cual|cuales|cuando|donde|quien|por que|para que|sabes|dime|how|what|which|when|where|who|why)\b", n):
        return None
    return _en(n) if en else _es(n)


def frase_de_volumen(salida):
    """Lo que dice Lina tras tocar el volumen, a partir de lo que devuelve wpctl («Volume: 0.85» o «Volume: 0.85 [MUTED]»). None si no se pudo leer."""
    m = re.search(r"Volume:\s*([0-9.]+)(\s*\[MUTED\])?", str(salida))
    if not m:
        return None
    if m.group(2):
        return T("Está silenciado.")
    return T("Volumen al {n} %.", n=round(float(m.group(1)) * 100))


def principal(argv, salida=print, activo=True):
    """`lina directas` (qué sabe hacer sin IA) y `lina directas probar "frase"` (qué haría, sin ejecutar nada)."""
    if argv[:1] == ["probar"]:
        frase = " ".join(argv[1:]).strip()
        if not frase:
            salida(T("Uso:  lina directas probar \"abre Firefox\""))
            return 2
        r = entender(frase)
        if not r:
            salida(T("«{frase}»: no es una orden directa; se la dejo a la IA.", frase=frase))
        else:
            salida(T("«{frase}»: orden directa «{id}» con {datos}. Se ejecutaría sin llamar a la IA.", frase=frase, id=r[0], datos=r[1]))
        return 0
    if argv:
        salida(T("Uso:  lina directas   |   lina directas probar \"frase\""))
        return 2
    salida(T("Órdenes directas: se entienden y se hacen sin llamar a la IA (más rápido). Ahora mismo están {estado}.", estado=T("activadas") if activo else T("desactivadas")))
    for ident, ejemplo, _ in ACCIONES:
        salida(f"  {ident:10} " + T(ejemplo))
    salida(T("Si algo no está claro, se lo dejo a la IA. Se apagan con:  lina config poner directas.activo no"))
    return 0
