"""Recetas aprendidas: cómo se consiguió algo que FUNCIONÓ en este equipo, para probarlo primero la próxima vez (y no gastar minutos y
tokens descubriéndolo otra vez).

  - Las apunta el código cuando algo queda COMPROBADO (probar_ajuste_kde) o la IA con guardar_receta, que solo acepta comandos que se
    ejecutaron bien en esa petición y que se comprobaron después.
  - Son PISTAS, nunca órdenes: al pedir algo parecido, la IA las recibe como «esto funcionó», las prueba primero y comprueba como siempre;
    cada comando pasa por las mismas reglas de seguridad. Nada se ejecuta solo por estar apuntado.
  - Viven en ~/.local/share/lina/recetas.json, que la IA no puede editar (solo por guardar_receta/olvidar_receta).
  - Una receta que falla dos veces se borra; si descubres una nueva para lo mismo, sustituye a la vieja.
"""
import json
import os
import re
import threading
import time

from lina.nucleo import comandos
from lina.nucleo import rutas as RUT

ARCHIVO = RUT.DATOS / "recetas.json"
MAX_RECETAS = 100
FALLOS_PARA_OLVIDAR = 2
_lock = threading.RLock()

_TONTAS = set("""los las una uno unos unas del que como esto esta este estos estas hay hazlo haz dime oye ahora otra vez mas menos muy todo toda sobre entre
desde hasta cuando donde quien por para con sin favor quiero puedes puede podrias asistente porfa venga vale gracias algo cosa cosas mi mis tu tus su sus
nos les mismo misma tambien pero aunque porque pues ahi aqui""".split())
_GENERICAS = set("""pantalla sistema ajuste ajustes configuracion configura panel ventana modo valor nivel activa activar activado desactiva desactivar enciende
apaga cambia cambiar sube subir baja bajar quita quitar pon poner aumenta reduce pones cambio ponlo ponla quitalo""".split())
_GEN = {t[:6] for t in _GENERICAS}


def log(mensaje):
    print(f"[{time.strftime('%H:%M:%S')}] {mensaje}", flush=True)


# ======================= texto limpio y palabras =======================
def _limpio(texto, n=300):
    """Una sola línea, sin caracteres de control (esto acabará dentro de una nota para la IA)."""
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(texto or ""))).strip()[:n]


def _libre(texto, n):
    """Texto libre que escribe la IA (nombre del ajuste, cómo se comprobó…): solo letras, números y puntuación básica, para que no
    pueda colar frases con instrucciones disfrazadas."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w .,;:/+%()'-]", " ", str(texto or ""), flags=re.UNICODE)).strip()[:n]


def _tokens(texto):
    """Las palabras de un texto, sin tildes ni vacías, reducidas a sus 6 primeras letras (así «nocturna» y «nocturno» coinciden)."""
    solo = comandos.normalizar(str(texto or "").replace("_", " "))
    return [t[:6] for t in solo.split() if len(t) >= 3 and t not in _TONTAS]


def _nucleo(ajuste):
    return sorted({t for t in _tokens(ajuste) if t not in _GEN})


# ======================= el archivo =======================
def _cargar():
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(datos, list):
        return []
    return [r for r in datos if isinstance(r, dict) and r.get("ajuste") and r.get("tipo") in {"kde", "comando", "interfaz"} and isinstance(r.get("nucleo"), list)]


def _guardar(recetas):
    try:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARCHIVO.with_name(ARCHIVO.name + ".tmp")
        tmp.write_text(json.dumps(recetas, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(ARCHIVO)
    except OSError as e:
        log(f"No he podido guardar las recetas: {e}")


def _id_nuevo(recetas):
    usados = [int(r["id"][1:]) for r in recetas if re.fullmatch(r"r\d{4}", str(r.get("id", "")))]
    return f"r{(max(usados) + 1 if usados else 1):04d}"


def _parecidas(a, b):
    """¿Hablan de lo mismo? (su núcleo de palabras se solapa al menos un 60 % en los dos sentidos)."""
    na, nb = set(a), set(b)
    if not na or not nb:
        return False
    comun = len(na & nb)
    return comun / len(na) >= 0.6 and comun / len(nb) >= 0.6


def _poner(recetas, nueva, misma_receta):
    """Mete la receta; si ya había una igual o que habla de lo mismo, la sustituye (conserva id, creación y aciertos) en vez de duplicar."""
    previa = next((r for r in recetas if r["tipo"] == nueva["tipo"] and (misma_receta(r) or _parecidas(r["nucleo"], nueva["nucleo"]))), None)
    ahora = time.strftime("%Y-%m-%d")
    if previa:
        # Se conserva el nombre con el que se apuntó (así lo llama el usuario) y se SUMAN las palabras nuevas: «luz nocturna» no se pierde porque la
        # segunda vez la IA llamara al ajuste por el nombre de un control del panel.
        nueva["palabras"] = sorted((set(previa.get("palabras", [])) | set(previa.get("nucleo", [])) | set(nueva["palabras"]) | set(nueva["nucleo"])) - _GEN)[:12]
        if previa.get("nucleo"):
            nueva["ajuste"], nueva["nucleo"] = previa["ajuste"], previa["nucleo"]
        nueva.update(id=previa["id"], creada=previa.get("creada", ahora), exitos=int(previa.get("exitos", 0)) + 1, fallos=0, ultima=ahora)
        if nueva["tipo"] == "kde" and misma_receta(previa):             # el mismo ajuste con otro valor: se suman los ejemplos
            vistos = {e.get("valor") for e in nueva["ejemplos"]}
            nueva["ejemplos"] = (nueva["ejemplos"] + [e for e in previa.get("ejemplos", []) if e.get("valor") not in vistos])[:4]
        recetas[recetas.index(previa)] = nueva
    else:
        nueva.update(id=_id_nuevo(recetas), creada=ahora, exitos=1, fallos=0, ultima=ahora)
        recetas.append(nueva)
        if len(recetas) > MAX_RECETAS:                                  # se olvida lo que hace más tiempo que no se usa
            recetas.sort(key=lambda r: r.get("ultima", ""))
            del recetas[0]
    return nueva


# ======================= aprender =======================
def aprender_kde(ajuste, palabras, pedido, archivo, grupos, clave, valor, panel, control, esperado, recargar="", web=False):
    """Apunta un ajuste de KDE que probar_ajuste_kde dejó COMPROBADO en pantalla."""
    ajuste = _libre(ajuste or control, 60)
    if not ajuste or not archivo or not clave or not panel:
        return None
    nueva = {"tipo": "kde", "ajuste": ajuste, "nucleo": _nucleo(ajuste), "palabras": sorted(set(_tokens(ajuste) + _tokens(palabras) + _tokens(pedido)[:6]) - _GEN),
             "pedido": _limpio(pedido, 120), "web": bool(web), "archivo": _limpio(archivo, 60), "grupos": [_limpio(g, 60) for g in grupos][:6],
             "clave": _limpio(clave, 60), "panel": _limpio(panel, 60), "control": _limpio(control, 80), "recargar": _limpio(recargar, 160),
             "ejemplos": [{"valor": _limpio(valor, 60), "esperado": _limpio(esperado, 80)}]}
    if not nueva["nucleo"]:
        return None
    with _lock:
        recetas = _cargar()
        resultado = _poner(recetas, nueva, lambda r: (r.get("archivo"), r.get("grupos"), r.get("clave")) == (nueva["archivo"], nueva["grupos"], nueva["clave"]))
        _guardar(recetas)
    log(f"Receta aprendida (ajuste de KDE): «{ajuste}» = {nueva['archivo']} {nueva['grupos']} {nueva['clave']}")
    return resultado


def plantilla(cambiar, valor_usado):
    """El comando con el valor concreto sustituido por {valor} (solo si aparece una vez; si no, el comando tal cual)."""
    cambiar, valor_usado = _limpio(cambiar, 300), _limpio(valor_usado, 60)
    if valor_usado and cambiar.count(valor_usado) == 1 and "{valor}" not in cambiar:
        return cambiar.replace(valor_usado, "{valor}")
    return cambiar


def aprender_comando(ajuste, palabras, pedido, cambiar, valor_usado, leer, comprobar, web=False):
    """Apunta un ajuste que se cambió con un comando (ya validado por quien llama: se ejecutó bien y se comprobó)."""
    ajuste = _libre(ajuste, 60)
    cambiar = plantilla(cambiar, valor_usado)
    if not ajuste or not cambiar:
        return None
    nueva = {"tipo": "comando", "ajuste": ajuste, "nucleo": _nucleo(ajuste), "palabras": sorted(set(_tokens(ajuste) + _tokens(palabras) + _tokens(pedido)[:6]) - _GEN),
             "pedido": _limpio(pedido, 120), "web": bool(web), "cambiar": cambiar, "valor_usado": _limpio(valor_usado, 60),
             "leer": _limpio(leer, 300), "comprobar": _libre(comprobar, 160)}
    if not nueva["nucleo"]:
        return None
    with _lock:
        recetas = _cargar()
        resultado = _poner(recetas, nueva, lambda r: r.get("cambiar") == nueva["cambiar"])
        _guardar(recetas)
    log(f"Receta aprendida (comando): «{ajuste}» = {cambiar}")
    return resultado


ACCIONES_INTERFAZ = {"pulsar", "escribir", "tecla", "clic", "accionar"}


def aprender_interfaz(ajuste, palabras, pedido, pasos, valor_usado, comprobar, solo_comprobar=False):
    """Apunta una tarea hecha con la interfaz de un programa: los pasos van POR NOMBRE de control (no por ids, que cambian), tal como se ejecutaron.
    Los pasos los construye el código a partir de lo que se hizo de verdad; aquí solo se limpian."""
    ajuste = _libre(ajuste, 60)
    limpios = []
    for p in pasos or []:
        accion = str(p.get("accion", ""))
        if accion not in ACCIONES_INTERFAZ:
            continue
        paso = {"accion": accion, "ventana": _libre(p.get("ventana", ""), 80)}
        if accion in ("pulsar", "escribir", "accionar"):
            paso["nombre"] = _libre(p.get("nombre", ""), 80)
            paso["rol"] = _libre(p.get("rol", ""), 30)
            if not paso["nombre"]:
                return None
        if accion == "escribir":
            texto, usado = _limpio(p.get("texto", ""), 120), _limpio(valor_usado, 60)
            paso["texto"] = texto.replace(usado, "{valor}") if usado and texto.count(usado) == 1 else texto
        if accion == "accionar":
            paso["estado"] = _libre(p.get("estado", ""), 12)
        if accion == "tecla":
            paso["combo"] = _libre(p.get("combo", ""), 30)
        if accion == "clic":
            paso["descripcion"] = _libre(p.get("descripcion", ""), 120)
            paso["boton"] = "derecho" if str(p.get("boton", "")).startswith("der") else "izquierdo"
            paso["veces"] = 2 if str(p.get("veces", "")) == "2" else 1
            if not paso["descripcion"]:
                return None
        limpios.append(paso)
    if not ajuste or not limpios or len(limpios) > 12:
        return None
    nueva = {"tipo": "interfaz", "ajuste": ajuste, "nucleo": _nucleo(ajuste), "palabras": sorted(set(_tokens(ajuste) + _tokens(palabras) + _tokens(pedido)[:6]) - _GEN),
             "pedido": _limpio(pedido, 120), "web": False, "pasos": limpios, "valor_usado": _limpio(valor_usado, 60), "comprobar": _libre(comprobar, 160), "cambiar": ""}
    if not nueva["nucleo"]:
        return None
    if solo_comprobar:
        return True
    with _lock:
        recetas = _cargar()
        resultado = _poner(recetas, nueva, lambda r: r.get("pasos") == nueva["pasos"])
        _guardar(recetas)
    log(f"Receta aprendida (interfaz): «{ajuste}» en {len(limpios)} pasos")
    return resultado


def _texto_paso(p):
    v = f"ventana=«{p['ventana']}»" if p.get("ventana") else ""
    if p["accion"] == "pulsar":
        return f"interfaz(pulsar, nombre=«{p['nombre']}»{', rol=«' + p['rol'] + '»' if p.get('rol') else ''}, {v})"
    if p["accion"] == "escribir":
        return f"interfaz(escribir, nombre=«{p['nombre']}», texto=«{p.get('texto', '')}», {v})"
    if p["accion"] == "accionar":
        return f"interfaz(accionar, nombre=«{p['nombre']}»{', estado=' + p['estado'] if p.get('estado') else ''}, {v})"
    if p["accion"] == "tecla":
        return f"interfaz(tecla, combo=«{p['combo']}», {v})"
    return f"interfaz(clic, descripcion=«{p['descripcion']}»{', boton=derecho' if p.get('boton') == 'derecho' else ''}{', veces=2' if p.get('veces') == 2 else ''})"


# ======================= usar =======================
def buscar(texto, maximo=2):
    """Las recetas que encajan con lo que acabas de pedir. Encaja si dices las palabras que definen el ajuste (al menos el 60 % de las suyas),
    o dos palabras distintivas cualesquiera suyas. Una palabra suelta y genérica («pantalla») no basta."""
    fuertes = {t for t in _tokens(texto) if t not in _GEN}
    if not fuertes:
        return []
    encajan = []
    with _lock:
        recetas = _cargar()
    for r in recetas:
        nucleo, otras = set(r["nucleo"]), set(r.get("palabras", [])) - set(r["nucleo"])
        en_nucleo, en_otras = nucleo & fuertes, otras & fuertes
        if (nucleo and len(en_nucleo) / len(nucleo) >= 0.6) or len(en_nucleo | en_otras) >= 2:
            encajan.append((len(en_nucleo) * 2 + len(en_otras) + 0.1 * int(r.get("exitos", 0)), r))
    encajan.sort(key=lambda x: -x[0])
    return [r for _, r in encajan[:maximo]]


def _como_se_hace(r):
    web = " (aprendida con ayuda de internet: compruébala igual)" if r.get("web") else ""
    veces = int(r.get("exitos", 1))
    cabecera = f"«{r['ajuste']}» (funcionó {veces} {'vez' if veces == 1 else 'veces'}, la última el {r.get('ultima', '?')}){web}"
    if r["tipo"] == "kde":
        ejemplos = "; ".join(f"{e['valor']} → el panel muestra «{e['esperado']}»" for e in r.get("ejemplos", []))
        recarga = f", recargar=«{r['recargar']}»" if r.get("recargar") else ""
        return (f"{cabecera}: probar_ajuste_kde con archivo=«{r['archivo']}», grupos={json.dumps(r['grupos'], ensure_ascii=False)}, clave=«{r['clave']}», "
                f"panel=«{r['panel']}», control=«{r['control']}»{recarga}. Valor → lo que mostró el panel: {ejemplos}. Con otro valor, adapta valor y esperado.")
    if r["tipo"] == "interfaz":
        pasos = " → ".join(f"({i}) {_texto_paso(p)}" for i, p in enumerate(r.get("pasos", []), 1))
        valor = " (en {valor} va lo que pida el usuario; la última vez " + (r.get("valor_usado") or "?") + ")" if "{valor}" in pasos else ""
        return (f"{cabecera}: pasos con la interfaz{valor}: {pasos}. Se comprobó así: {r.get('comprobar') or '?'}. Los nombres de los controles pueden haber cambiado: si alguno "
                "no aparece, lista los controles y adapta. Cada paso pasa por las mismas protecciones de siempre.")
    texto = f"{cabecera}: cambiar con `{r['cambiar']}`"
    if "{valor}" in r["cambiar"]:
        texto += f" (en {{valor}} va el valor que pida el usuario; la última vez {r.get('valor_usado') or '?'})"
    if r.get("leer"):
        texto += f"; leer el valor actual con `{r['leer']}`"
    if r.get("comprobar"):
        texto += f"; se comprobó así: {r['comprobar']}"
    return texto + "."


def ofrecer(texto, maximo=2, previos=()):
    """(nota para la IA, ids) con las recetas que encajan con lo que se ha pedido; ("", []) si no hay ninguna. Si lo pedido no tiene ninguna palabra
    con contenido («ahora desactívala»), se mira también lo que se pidió justo antes, que es de lo que se habla."""
    if previos and not {t for t in _tokens(texto) if t not in _GEN}:
        texto = " ".join([str(texto)] + [str(p) for p in previos])
    r = buscar(texto, maximo)
    if not r:
        return "", []
    nota = ("Recetas que YA funcionaron en este equipo para algo parecido: pruébalas PRIMERO (y comprueba el resultado como siempre); si no "
            "funcionan, descubre desde cero y apunta la nueva. " + " | ".join(_como_se_hace(x) for x in r))
    return nota[:1500], [x["id"] for x in r]


def indice(maximo_caracteres=900):
    """Una línea con TODAS las recetas (id y nombre), las más usadas recientemente primero, para que la IA decida por significado cuál encaja con lo que se
    pide (aunque el usuario lo diga de otra forma o solo diga «desactívala»). "" si no hay ninguna."""
    with _lock:
        recetas = _cargar()
    recetas.sort(key=lambda r: (r.get("ultima", ""), int(r.get("exitos", 0))), reverse=True)
    trozos, total = [], 0
    for r in recetas:
        t = f"{r['id']}: {r['ajuste']}"
        if total + len(t) + 3 > maximo_caracteres:
            break
        trozos.append(t)
        total += len(t) + 3
    return " | ".join(trozos)


def obtener(referencia):
    """Cómo se hace lo de una receta, por su id (r0001) o por su nombre; None si no existe."""
    ref = str(referencia or "").strip().lower()
    if not ref:
        return None
    with _lock:
        recetas = _cargar()
    for r in recetas:
        if r["id"].lower() == ref or str(r["ajuste"]).lower() == ref:
            return _como_se_hace(r)
    return None


def tipos(referencias):
    """[(tipo, cambiar)] de las recetas con esos ids o nombres (para saber qué herramientas necesitan)."""
    refs = {str(x or "").strip().lower() for x in referencias}
    with _lock:
        recetas = _cargar()
    return [(x["tipo"], x.get("cambiar", "")) for x in recetas if x["id"].lower() in refs or str(x["ajuste"]).lower() in refs]


def para_comando(comando):
    """La receta (de las de comando) cuyo «cambiar» encaja con este comando concreto, si la hay."""
    comando = " ".join(str(comando or "").split())
    with _lock:
        recetas = _cargar()
    for r in recetas:
        if r["tipo"] != "comando" or not r.get("cambiar"):
            continue
        patron = re.escape(r["cambiar"]).replace(re.escape("{valor}"), "(.+?)")
        if re.fullmatch(patron, comando):
            return r
    return None


def probada_kde(archivo, grupos, clave, panel):
    """La receta de KDE ya DEMOSTRADA (se vio cambiar el panel al escribir esta clave) y que no ha fallado desde entonces, o None.
    Con ella no hace falta volver a leer el panel antes de cambiar: ya se sabe que esta clave mueve ese panel."""
    with _lock:
        recetas = _cargar()
    for r in recetas:
        if (r.get("tipo") == "kde" and (r.get("archivo"), r.get("grupos"), r.get("clave")) == (archivo, list(grupos), clave)
                and r.get("panel") == panel and int(r.get("exitos", 0)) >= 1 and int(r.get("fallos", 0)) == 0):
            return r
    return None


# ======================= fallos, olvidar, listar =======================
def fallo_kde(archivo, grupos, clave):
    """Una receta de KDE no funcionó esta vez. A la segunda seguida, se olvida. Devuelve los nombres de las olvidadas."""
    olvidadas = []
    with _lock:
        recetas = _cargar()
        for r in list(recetas):
            if r["tipo"] == "kde" and (r.get("archivo"), r.get("grupos"), r.get("clave")) == (archivo, list(grupos), clave):
                r["fallos"] = int(r.get("fallos", 0)) + 1
                if r["fallos"] >= FALLOS_PARA_OLVIDAR:
                    recetas.remove(r)
                    olvidadas.append(r["ajuste"])
        _guardar(recetas)
    if olvidadas:
        log(f"Receta olvidada por fallar dos veces: {', '.join(olvidadas)}")
    return olvidadas


def olvidar(texto):
    """Borra las recetas de eso («olvida cómo se cambia el volumen»). Devuelve los nombres borrados."""
    claves = _limpio(texto, 80).lower()
    if not claves:
        return []
    ids = {r["id"] for r in buscar(texto, 5)}
    with _lock:
        recetas = _cargar()
        borradas = [r for r in recetas if r["id"] in ids or claves == str(r["ajuste"]).lower()]
        if borradas:
            _guardar([r for r in recetas if r not in borradas])
    return [r["ajuste"] for r in borradas]


def listar():
    with _lock:
        recetas = _cargar()
    if not recetas:
        return "Todavía no he aprendido ninguna receta: cada ajuste nuevo lo descubro desde cero y, cuando queda comprobado, lo apunto."
    return "Recetas aprendidas: " + "; ".join(f"«{r['ajuste']}» ({'ajuste de KDE' if r['tipo'] == 'kde' else 'interfaz' if r['tipo'] == 'interfaz' else 'comando'}, {int(r.get('exitos', 1))} veces, "
                                              f"última {r.get('ultima', '?')})" for r in recetas)
