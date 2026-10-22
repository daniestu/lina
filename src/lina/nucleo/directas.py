# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Órdenes directas (fase 12): «abre Firefox», «sube el volumen»… se entienden y se ejecutan SIN pasar por la IA.

Aquí solo se ENTIENDE la frase (función pura, sin sistema ni red): devuelve qué acción es y con qué datos, o None si no está claro. Quien la ejecuta
(el asistente) usa las mismas herramientas y las mismas reglas de seguridad que cuando decide la IA: esto no es una puerta lateral.
Ante la duda, None y la IA se hace cargo: es preferible tardar un poco a hacer algo que no se pidió. Solo entran acciones de riesgo bajo."""
import re
import unicodedata

from lina.nucleo import idioma as IDI
from lina.nucleo import texto as TXT
from lina.nucleo.idioma import N_, T

# Todo lo que se sabe hacer así (para `lina directas`): (id, ejemplo en español, ejemplo en inglés)
ACCIONES = (
    ("abrir_app", N_("abre Firefox · ábreme Steam · puedes abrir Dolphin"), "open Firefox"),
    ("volumen", N_("sube el volumen · baja el volumen · pon el volumen al 40"), "volume up · set the volume to 40"),
    ("silencio", N_("silencia el sonido · quita el silencio"), "mute · unmute"),
    ("ventanas", N_("maximiza esta ventana · pantalla completa · minimiza esta ventana · muestra el escritorio"), "maximize this window · full screen"),
    ("reproduccion", N_("pausa · sigue con la música · siguiente canción · canción anterior · para la música"), "pause · resume · next song · previous song · stop the music"),
    ("bluetooth", N_("conecta mis auriculares · desconecta el mando · enciende el bluetooth"), "connect my headphones · disconnect the controller"),
    ("hora", N_("qué hora es · qué día es hoy"), "what time is it · what day is it"),
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


_VENT = r"(?:esta |la |mi )?(?:ventana|aplicacion|app|programa)?(?: actual| activa)?"


def _es(n):
    # ---- hora y fecha (se preguntan con «qué…»: van antes de descartar las preguntas)
    if re.fullmatch(r"(?:que hora es|que hora tenemos|que hora tengo|que hora son|dime la hora|dame la hora|decir la hora|la hora|hora actual|tienes hora)"
                    r"(?: actual| ahora| en este momento| ahora mismo)?", n):
        return ("hora", {"que": "hora"})
    if re.fullmatch(r"(?:que dia es|que fecha es|que fecha tenemos|a que dia estamos|en que dia estamos|a que fecha estamos|que dia de la semana es|dime la fecha|dame la fecha|"
                    r"decir la fecha|la fecha|fecha actual)(?: de| es)?(?: hoy| actual| ahora)?", n):
        return ("hora", {"que": "fecha"})
    if re.match(r"^(?:como|que|cual|cuales|cuando|donde|quien|por que|para que|sabes|dime|saber)\b", n):
        return None
    # ---- ventanas (sobre la ventana activa; nunca cerrar: se podría perder trabajo)
    if re.fullmatch(r"(?:maximiza|maximizar|ponla a pantalla maximizada|agranda|agrandar)(?: " + _VENT + r")?|pon " + _VENT + r" (?:en|a) (?:modo )?maximizad[oa]", n):
        return ("ventanas", {"accion": "maximizar", "ventana": "activa"})
    if re.fullmatch(r"(?:pon|poner|ponla|pasa|pasar|cambia|cambiar)(?: " + _VENT + r")? (?:en|a) pantalla completa|pantalla completa|(?:quita|quitar|sal de|salir de) (?:la )?pantalla completa"
                    r"|(?:pon|poner|activa|activar|quita|quitar|sal de|salir de) (?:el )?(?:modo )?pantalla completa", n):
        return ("ventanas", {"accion": "pantalla_completa", "ventana": "activa"})
    if re.fullmatch(r"(?:minimiza|minimizar|esconde|esconder|oculta|ocultar)(?: " + _VENT + r")?", n):
        return ("ventanas", {"accion": "minimizar", "ventana": "activa"})
    if re.fullmatch(r"(?:muestra|mostrar|enseña|ensena|ver|ve al|ir al|vete al)(?: me)? (?:el )?escritorio|(?:minimiza|esconde|oculta) todo|(?:minimiza|esconde|oculta) todas las ventanas", n):
        return ("ventanas", {"accion": "mostrar_escritorio"})
    # ---- silencio
    if re.fullmatch(r"(?:silencia(?:r)?|silencialo|silenciala|mutea(?:r)?)(?: (?:el|al) (?:sonido|audio|volumen|ordenador|equipo|pc)| todo| el sonido del ordenador)?", n):
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
    # ---- música y vídeo que ya suenan (playerctl): no empieza nada nuevo, solo controla lo que hay
    _OBJ = r"(?:musica|cancion|reproduccion|video|podcast|pista)"
    _OBJ_DET = r"(?:musica|cancion|reproduccion|podcast)"
    if re.fullmatch(r"(?:pausa|pausar|pausame|pausalo|pausala)(?: (?:la|el|esta|esa|este))?(?: " + _OBJ + r")?(?: un momento| un segundo)?"
                    r"|(?:pon|poner|ponla|ponlo)(?: (?:la|el|esta|ese|esa))?(?: " + _OBJ + r")? en pausa|(?:pon|poner) pausa(?: a(?:l| la| el)? " + _OBJ + r")?"
                    , n):
        return ("reproduccion", {"accion": "pausar"})
    if re.fullmatch(r"(?:para|parar|deten|detener|calla|callar|quita|quitar|apaga|apagar|cierra|cerrar)(?: me)?(?: (?:la|el|esta|esa|este))? " + _OBJ_DET, n):
        return ("reproduccion", {"accion": "detener"})
    if re.fullmatch(r"(?:reanuda|reanudar|reanudala|reanudalo|retoma|retomar)(?: (?:la|el|esta|esa|este))?(?: " + _OBJ + r")?"
                    r"|(?:continua|continuar|sigue|seguir|continualo|continuala)(?: con)?(?: (?:la|el|esta|esa|este)) " + _OBJ
                    + r"|(?:dale|dar|dame|pulsa|pon|poner)(?: (?:al|a|el))? play|play|(?:quita|quitar) (?:la )?pausa", n):
        return ("reproduccion", {"accion": "reanudar"})
    if re.fullmatch(r"(?:la )?(?:siguiente|proxima)(?: (?:cancion|pista|tema))?|(?:cancion|pista|tema) (?:siguiente|proxima)"
                    r"|(?:pasa|pasar|salta|saltar|cambia|cambiar|ve|ir|pon|poner|ponme|avanza|avanzar)(?: (?:a|de|la|el|esta|esa))* (?:siguiente|proxima)(?: (?:cancion|pista|tema))?"
                    r"|(?:salta|saltar|pasa|pasar|cambia|cambiar|omite|omitir)(?: (?:de|esta|esa|la))* (?:cancion|pista)(?: actual)?", n):
        return ("reproduccion", {"accion": "siguiente"})
    if re.fullmatch(r"(?:la )?anterior|(?:la )?(?:cancion|pista|tema) anterior|(?:vuelve|volver|ve|ir|retrocede|retroceder|pon|poner|ponme)(?: (?:a|de|la|el))* anterior"
                    r"|(?:vuelve|volver|retrocede|retroceder)(?: (?:a|de|la|el))* (?:cancion|pista|tema)(?: anterior)?", n):
        return ("reproduccion", {"accion": "anterior"})
    # ---- bluetooth (dispositivos ya emparejados; emparejar uno nuevo no se hace por aquí)
    if re.fullmatch(r"(?:enciende|encender|activa|activar|pon|poner)(?: el)? bluetooth", n):
        return ("bluetooth", {"accion": "bluetooth_encender"})
    m = re.fullmatch(r"(conecta|conectar|conectame|conectate|desconecta|desconectar|desconectame)(?: me)?(?: a)? ((?:(?:mis|mi|los|las|el|la|unos|unas) )?[a-z0-9 ]{3,30})", n)
    if m:
        objetivo = re.sub(r"^(?:(?:mis|mi|los|las|el|la|unos|unas)(?: |$))+", "", re.sub(r"\b(?:por )?bluetooth\b", "", m.group(2)).strip()).strip()
        if not objetivo and m.group(2).strip().endswith("bluetooth") and m.group(1).startswith("conec"):
            return ("bluetooth", {"accion": "bluetooth_encender"})         # «conecta el bluetooth» = enciéndelo
        if objetivo and not re.search(r"\b(?:wifi|wi fi|red|redes|internet|vpn|ethernet|cable|servidor|ordenador|pc|equipo|base de datos|sesion|cuenta)\b", objetivo) \
                and len(objetivo.split()) <= 4 and not set(objetivo.split()) & _CORTA_NOMBRE:
            return ("bluetooth", {"accion": "bluetooth_desconectar" if m.group(1).startswith("desc") else "bluetooth_conectar", "objetivo": objetivo})
    # ---- abrir un programa
    m = re.fullmatch(r"(?:abre|abrir|abreme|abrime|lanza|lanzar|lanzame|ejecuta|ejecutar|inicia|iniciar|arranca|arrancar|pon en marcha)(?: me)? "
                     + _ARTICULOS_ES + r"(.+)", n)
    if m and _nombre_valido(m.group(1)):
        return ("abrir_app", {"nombre": m.group(1)})
    return None


def _en(n):
    if re.fullmatch(r"(?:what time is it|what s the time|what is the time|tell me the time|give me the time|the time|what time do we have)(?: now| right now)?", n):
        return ("hora", {"que": "hora"})
    if re.fullmatch(r"(?:what day is it|what s the date|what is the date|what is today s date|what s today s date|tell me the date|the date|what date is it)(?: today)?", n):
        return ("hora", {"que": "fecha"})
    if re.match(r"^(?:how|what|which|when|where|who|why|tell|do you know)\b", n):
        return None
    if re.fullmatch(r"(?:maximi[sz]e)(?: (?:this |the |my )?(?:window|app|application|program))?", n):
        return ("ventanas", {"accion": "maximizar", "ventana": "activa"})
    if re.fullmatch(r"(?:(?:make|put|set|turn)(?: (?:this |the |my )?(?:window|app|application|program))? (?:in|into|to|on) full ?screen|full ?screen|(?:exit|leave) full ?screen)", n):
        return ("ventanas", {"accion": "pantalla_completa", "ventana": "activa"})
    if re.fullmatch(r"(?:minimi[sz]e|hide)(?: (?:this |the |my )?(?:window|app|application|program))?", n):
        return ("ventanas", {"accion": "minimizar", "ventana": "activa"})
    if re.fullmatch(r"(?:show|go to) (?:the )?desktop|minimi[sz]e (?:everything|all(?: windows)?)", n):
        return ("ventanas", {"accion": "mostrar_escritorio"})
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
    _OBJ = r"(?:music|song|track|playback|video|podcast|audio)"
    if re.fullmatch(r"pause(?: (?:the|this|that))?(?: " + _OBJ + r")?", n):
        return ("reproduccion", {"accion": "pausar"})
    if re.fullmatch(r"(?:stop|halt|turn off|shut off|kill) (?:the|this|that) " + _OBJ + r"|stop (?:playing|the playback)", n):
        return ("reproduccion", {"accion": "detener"})
    if re.fullmatch(r"(?:resume|unpause|continue)(?: (?:the|this|that))?(?: " + _OBJ + r")?|play|hit play|press play|(?:keep|go on) playing", n):
        return ("reproduccion", {"accion": "reanudar"})
    if re.fullmatch(r"(?:the )?next(?: (?:song|track))?|(?:skip|go to|play)(?: (?:to|the|this|that))* (?:next(?: (?:song|track))?|(?:song|track))|(?:skip|next)", n):
        return ("reproduccion", {"accion": "siguiente"})
    if re.fullmatch(r"(?:the )?(?:previous|last)(?: (?:song|track))?|(?:go back|back|go to|play)(?: (?:to|the|a|one))* (?:previous|last)(?: (?:song|track))?|(?:go back|back)(?: (?:a|one))? (?:song|track)", n):
        return ("reproduccion", {"accion": "anterior"})
    if re.fullmatch(r"(?:turn on|switch on|enable) (?:the )?bluetooth", n):
        return ("bluetooth", {"accion": "bluetooth_encender"})
    m = re.fullmatch(r"(connect|disconnect)(?: to)? ((?:(?:my|the|your) )?[a-z0-9 ]{3,30})", n)
    if m:
        objetivo = re.sub(r"^(?:(?:my|the|your)(?: |$))+", "", re.sub(r"\bbluetooth\b", "", m.group(2)).strip()).strip()
        if objetivo and not re.search(r"\b(?:wifi|wi fi|network|internet|vpn|ethernet|server|computer|pc|database|session|account)\b", objetivo) and len(objetivo.split()) <= 4 \
                and not set(objetivo.split()) & _CORTA_NOMBRE:
            return ("bluetooth", {"accion": "bluetooth_" + ("desconectar" if m.group(1) == "disconnect" else "conectar"), "objetivo": objetivo})
    m = re.fullmatch(r"(?:open|launch|start|run) " + _ARTICULOS_EN + r"(.+?)(?: app| application| program)?", n)
    if m and _nombre_valido(m.group(1)):
        return ("abrir_app", {"nombre": m.group(1)})
    return None


def entender(texto):
    """(id, datos) si la frase ES una orden directa clara; None en cualquier otro caso (preguntas, negaciones, órdenes encadenadas, dudas)."""
    original = str(texto or "")
    if not original.strip() or len(original) > 80:
        return None                                              # frases largas: las entiende la IA
    n = normalizar(original)
    en = IDI.actual() == "en"
    cortesia, final = (_CORTESIA_EN, _FINAL_EN) if en else (_CORTESIA_ES, _FINAL_ES)
    n = re.sub(r"^" + cortesia + "+", "", n)
    n = re.sub(final + r"$", "", n).strip()
    if re.match(r"^(?:no|nunca|jamas|sin|don t|dont|do not|never)\b", n):
        return None
    return _en(n) if en else _es(n)                              # (cada idioma descarta las preguntas, salvo «qué hora es» y similares)


def frase_de_volumen(salida):
    """Lo que dice Lina tras tocar el volumen, a partir de lo que devuelve wpctl («Volume: 0.85» o «Volume: 0.85 [MUTED]»). None si no se pudo leer."""
    m = re.search(r"Volume:\s*([0-9.]+)(\s*\[MUTED\])?", str(salida))
    if not m:
        return None
    if m.group(2):
        return T("Está silenciado.")
    return T("Volumen al {n} %.", n=round(float(m.group(1)) * 100))


def frase_de_hora(ahora):
    """«Son las 16:58.» (o «Es la 1:05.»): la hora la dice el código, no la IA."""
    if IDI.actual() != "en" and ahora.hour == 1:
        return T("Es la {hora}.", hora=f"1:{ahora.minute:02d}")
    return T("Son las {hora}.", hora=ahora.strftime("%H:%M"))


def frase_de_fecha(ahora):
    en = IDI.actual() == "en"
    dia, mes = (TXT._DAYS, TXT._MONTHS) if en else (TXT._DIAS, TXT._MESES)
    return T("Hoy es {dia} {n} de {mes}.", dia=dia[ahora.weekday()], n=ahora.day, mes=mes[ahora.month - 1])


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
