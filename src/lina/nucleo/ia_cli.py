"""lina ia: ver con qué IA habla Lina, cambiarla, ver los modelos que ofrece el servicio y comprobar que funciona."""
import base64

from lina.nucleo import ajustes as AJ
from lina.nucleo import ia_activa as IAC
from lina.nucleo import proveedores as P

AYUDA = """lina ia                                  con qué IA habla Lina ahora y si está lista
lina ia usar PROVEEDOR [opciones]        cambia de proveedor: gemini · anthropic · openai (OpenAI y compatibles)
    --modelo NOMBRE       modelo para el día a día
    --profundo NOMBRE     modelo para el modo «a fondo»
    --url DIRECCION       solo openai: servidor propio o local, p. ej. http://localhost:11434/v1
    --razonamiento        solo openai: el modelo es de razonamiento
lina ia volver                           vuelve a Gemini con los modelos de siempre
lina ia modelos                          los modelos que ofrece el servicio ahora configurado
lina ia probar                           hace una petición de prueba y dice si responde, si usa herramientas y si ve imágenes
La clave de cada proveedor se guarda con:  lina clave gemini | anthropic | openai"""

def _imagen_prueba():
    """Un JPEG pequeño en base64 (rojo liso), para comprobar que el modelo acepta imágenes. None si no hay Pillow."""
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    memoria = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 30, 30)).save(memoria, "JPEG")
    return base64.b64encode(memoria.getvalue()).decode()


HERRAMIENTA_PRUEBA = {"name": "anotar", "description": "Anota un número.",
                      "parameters": {"type": "object", "properties": {"numero": {"type": "integer"}}, "required": ["numero"]}}


def estado(leer=None, salida=print):
    a = IAC.actual(leer)
    listo, falta = a.listo()
    salida(f"Proveedor: {a.nombre}" + (f"  ({a.url_base})" if a.url_base else ""))
    salida(f"Modelo rápido:   {', '.join(a.rapido) or '(sin indicar)'}")
    salida(f"Modelo profundo: {', '.join(a.profundo) or '(sin indicar)'}")
    salida("Lista para usar." if listo else f"Todavía no: {falta}.")
    if a.nombre != "gemini":
        salida("Con este proveedor Lina cuenta los tokens pero no controla el gasto en euros: míralo en el panel de tu proveedor.")
    return 0 if listo else 1


def probar(leer=None, salida=print, post=None):
    """Tres peticiones cortas: responde, usa herramientas, ve imágenes. Dice lo que ha pasado, sin dar por bueno lo que no se ha comprobado."""
    a = IAC.actual(leer)
    listo, falta = a.listo()
    if not listo:
        salida(f"No se puede probar: {falta}.")
        return 1
    clave, modelo, prov = a.clave(), a.rapido[0], a.proveedor
    salida(f"Probando {a.nombre} con {modelo}…")
    sistema = "Eres un asistente. Responde siempre muy breve."
    r = prov.turno(clave, modelo, sistema, [{"rol": "user", "texto": "Responde solo: ok"}], post=post, timeout=30)
    if isinstance(r, P.ErrorIA):
        salida(f"  Responde:      NO — {r.resumen or r.tipo}")
        return 1
    salida("  Responde:      sí")
    r = prov.turno(clave, modelo, sistema, [{"rol": "user", "texto": "Usa la herramienta anotar con el número 7."}],
                   herramientas=[HERRAMIENTA_PRUEBA], post=post, timeout=30)
    if isinstance(r, P.ErrorIA):
        herramientas = f"NO — {r.resumen or r.tipo}"
    else:
        herramientas = "sí" if r.llamadas else "NO: respondió con texto en vez de usarla (Lina necesita herramientas para casi todo)"
    salida(f"  Herramientas:  {herramientas}")
    imagen = _imagen_prueba()
    if imagen is None:
        vision = "no comprobado (falta Pillow)"
    else:
        r = prov.turno(clave, modelo, sistema, [{"rol": "user", "texto": "Describe esta imagen en una palabra.", "imagen": imagen}], post=post, timeout=30)
        vision = f"NO — {r.resumen or r.tipo} (no podrá mirar la pantalla)" if isinstance(r, P.ErrorIA) else "sí (acepta imágenes)"
    salida(f"  Imágenes:      {vision}")
    return 0 if herramientas == "sí" else 1


def modelos(leer=None, salida=print, get=None):
    a = IAC.actual(leer)
    clave = a.clave()
    if not clave:
        salida(f"Falta la clave: `lina clave {a.nombre}`.")
        return 1
    lista, motivo = a.proveedor.modelos(clave, get=get)
    if lista is None:
        salida(f"No he podido pedir la lista de modelos: {motivo}")
        return 1
    salida(f"Modelos que ofrece {a.nombre} ({len(lista)}):")
    for m in lista:
        salida(f"  {m}")
    return 0


def usar(args, ajustes=None, salida=print):
    if not args or args[0] not in P.nombres():
        salida("Indica el proveedor: " + " · ".join(P.nombres()) + ".")
        return 2
    nombre, resto, valores = args[0], list(args[1:]), {"proveedor": args[0]}
    opciones = {"--modelo": "modelo_rapido", "--profundo": "modelo_profundo", "--url": "url_base"}
    while resto:
        o = resto.pop(0)
        if o == "--razonamiento":
            valores["razonamiento"] = "true"
        elif o in opciones and resto:
            valores[opciones[o]] = resto.pop(0)
        else:
            salida(f"No entiendo «{o}».\n{AYUDA}")
            return 2
    aj = ajustes or AJ.actuales()
    if nombre != "openai" and ("url_base" in valores or "razonamiento" in valores):
        salida("--url y --razonamiento son solo para openai.")
        return 2
    for clave, defecto in (("modelo_rapido", ""), ("modelo_profundo", ""), ("url_base", ""), ("razonamiento", "false")):
        valores.setdefault(clave, defecto)                # nada del proveedor anterior se arrastra: sus modelos no valen en este
    for clave, valor in valores.items():
        try:
            aj.establecer("ia", clave, valor)
        except ValueError as e:
            salida(f"No vale: ia.{clave} {e}.")
            return 2
    salida(f"Ahora Lina usa {nombre}. Reinicia para aplicarlo:  systemctl --user restart lina")
    return estado(salida=salida)


def principal(argv, salida=print, ajustes=None):
    orden, resto = (argv[0], argv[1:]) if argv else ("estado", [])
    if orden in ("-h", "--help", "ayuda"):
        salida(AYUDA)
        return 0
    if orden == "estado":
        return estado(salida=salida)
    if orden == "usar":
        return usar(resto, ajustes, salida)
    if orden == "volver":
        return usar(["gemini"], ajustes, salida)
    if orden == "modelos":
        return modelos(salida=salida)
    if orden == "probar":
        return probar(salida=salida)
    salida(AYUDA)
    return 2
