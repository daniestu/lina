"""Cambiar ajustes hablando: «habla más rápido», «quita el resplandor», «pasa al perfil prudente», «cuál es el tope de gasto».

Las frases las entiende este código, sin llamar a la IA (así la IA no puede cambiar sus propios ajustes, ni una web o una voz de fuera
colarle una orden). Reglas:
  · Los ajustes normales (velocidad, resplandor) se cambian desde el atajo o desde el manos libres.
  · Lo que da MÁS permisos o MÁS gasto (perfil más permisivo, el tope más alto lo cambia presupuesto.py con la misma regla) solo se hace si pulsas el atajo y lo dices tú:
    por «Oye Lina» no, porque cualquier voz cercana (un vídeo, otra persona) podría decirlo.
  · Lo que aprieta (perfil más prudente, tope más bajo) se puede pedir de cualquier forma.
"""
import re
import unicodedata

from lina.nucleo import ajustes as AJ

_VERBOS_HABLA = r"(?:habla|hables|hablame|hablar|dime|contesta|responde|responder)"
PERFILES_HABLADOS = {"autonomo": "autonomo", "autonoma": "autonomo", "equilibrado": "equilibrado", "equilibrada": "equilibrado",
                     "prudente": "prudente", "prudencia": "prudente"}


def _normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9ñ,. ]", " ", t.replace("ñ", "n"))
    return re.sub(r"\s+", " ", t).strip()


def entender(texto):
    """Devuelve None o una tupla:  ('poner', sección, clave, valor, descripción) · ('mover', sección, clave, paso, descripción) · ('ver', 'perfil'|'tope')."""
    n = _normalizar(texto)
    if not n or len(n.split()) > 10:                          # son órdenes cortas: una petición larga que mencione «más rápido» es otra cosa
        return None
    # --- preguntas sobre cómo se cambia algo de Lina: se contestan aquí, sin buscar en internet
    if re.search(r"\b(como|donde|que)\b.*\b(cambio|cambiar|cambias|puedo cambiar|se cambia|configuro|configurar|elijo|elegir|pongo|poner)\b.*\b(voz|voces)\b", n) \
            or re.search(r"\b(que|cuantas|cuales) voces\b", n) or re.search(r"\b(cambia|cambiate|cambiame)\b.*\b(tu|la|otra) voz|\bponte otra voz\b", n):
        return ("ayuda", "voz")
    if re.search(r"\b(como|donde)\b.*\b(cambio|cambiar|cambias|se cambia|configuro|configurar|ajusto|ajustar)\b.*\b(ajustes|configuracion|tu nombre|perfil)\b", n):
        return ("ayuda", "ajustes")
    # --- velocidad de la voz
    if re.search(rf"\b{_VERBOS_HABLA}\b[^.]*\b(mas rapido|mas deprisa|mas aprisa|rapido|deprisa)\b", n) or re.search(r"\bsube la velocidad de (?:la )?voz\b", n):
        return ("mover", "voz", "velocidad", +0.15, "más rápido")
    if re.search(rf"\b{_VERBOS_HABLA}\b[^.]*\b(mas despacio|mas lento|despacio|lento|mas tranquilo)\b", n) or re.search(r"\bbaja la velocidad de (?:la )?voz\b", n):
        return ("mover", "voz", "velocidad", -0.15, "más despacio")
    if re.search(rf"\b{_VERBOS_HABLA}\b[^.]*\bvelocidad normal\b", n) or re.search(r"\bvelocidad (?:de (?:la )?voz )?(?:normal|por defecto|de fabrica)\b", n):
        return ("poner", "voz", "velocidad", 1.0, "a velocidad normal")
    m = re.search(r"\bvelocidad de (?:la )?voz (?:a|en|de) ([0-9][0-9.,]*)", n)
    if m:
        return ("poner", "voz", "velocidad", float(m.group(1).replace(",", ".").rstrip(".")), "a esa velocidad")
    # --- resplandor / indicador
    if re.search(r"\b(resplandor|indicador|brillo de los bordes|luz de los bordes)\b", n):
        for color in ("azul", "rojo", "verde", "morado", "violeta", "naranja", "amarillo", "rosa", "cian", "blanco"):
            if re.search(rf"\b{color}\b", n):
                return ("poner", "interfaz", "indicador_color", color, f"de color {color}")
        if re.search(r"\b(desactiva|desactivar|apaga|apagar|quita|quitar|deshabilita|sin|no quiero)\b", n):
            return ("poner", "interfaz", "indicador", False, "apagado")
        if re.search(r"\b(activa|activar|enciende|encender|pon|poner|habilita|vuelve|quiero)\b", n):
            return ("poner", "interfaz", "indicador", True, "encendido")
        if re.search(r"\b(mas grueso|mas ancho|mas grande|mas gordo)\b", n):
            return ("mover", "interfaz", "indicador_grosor", +10, "más grueso")
        if re.search(r"\b(mas fino|mas estrecho|mas delgado|mas pequeno)\b", n):
            return ("mover", "interfaz", "indicador_grosor", -10, "más fino")
        if re.search(r"\b(mas fuerte|mas brillante|mas intenso)\b", n):
            return ("mover", "interfaz", "indicador_intensidad", +0.25, "más fuerte")
        if re.search(r"\b(mas suave|mas tenue|menos brillante|menos intenso)\b", n):
            return ("mover", "interfaz", "indicador_intensidad", -0.25, "más suave")
    # --- perfil de autonomía
    m = re.search(r"\b(?:perfil|modo|ponte|pasa|cambia|usa)\b[^.]*\b(autonomo|autonoma|equilibrado|equilibrada|prudente|prudencia)\b", n)
    if m and re.search(r"\b(pon|ponte|pasa|pasate|cambia|cambiate|usa|activa|quiero|vuelve|deja)\b", n):
        return ("poner", "autonomia", "perfil", PERFILES_HABLADOS[m.group(1)], f"con el perfil {PERFILES_HABLADOS[m.group(1)]}")
    if re.search(r"\b(que|cual) (?:perfil|modo) (?:de autonomia )?(?:tienes|usas|llevas|tengo)\b|\bcual es tu (?:perfil|modo)( de autonomia)?\b", n):
        return ("ver", "perfil")
    # --- tope de gasto
    if re.search(r"\b(tope|limite)\b", n) and re.search(r"\b(gasto|gastar|mensual|mes|pago)\b", n):
        if re.search(r"\b(cual|cuanto|que)\b.*\b(tope|limite)\b|\b(tope|limite)\b.*\b(actual|tengo|tienes|llevo)\b", n) and not re.search(r"\b(sube|baja|pon|cambia|fija|establece|ponlo|subelo|bajalo|aumenta|reduce)\b", n):
            return ("ver", "tope")
    return None


def aplicar(orden, aj=None, voz_libre=False):
    """Hace el cambio y devuelve lo que Lina dice. voz_libre=True si la orden llegó por «Oye Lina» (y no con el atajo)."""
    aj = aj or AJ.actuales(log=lambda m: None)
    if orden[0] == "ayuda":
        if orden[1] == "voz":
            from lina.voz import voces
            nombres = ", ".join(v["descripcion"].split(" · ")[0] + " " + v["descripcion"].split(" · ")[1] for g in voces.CATALOGO.values() for v in g.values())
            return (f"Tengo {sum(len(g) for g in voces.CATALOGO.values())} voces en español: {nombres}. Para cambiarla, en una terminal escribe lina voz, "
                    "y después el nombre de la que quieras; luego reinicia a Lina. La velocidad sí te la cambio ahora: dime habla más rápido o más despacio.")
        return ("Mis ajustes se cambian con el comando lina config en una terminal. Algunos puedes pedírmelos hablando: la velocidad, el resplandor, el perfil y el tope de gasto.")
    if orden[0] == "ver":
        if orden[1] == "perfil":
            return f"Voy con el perfil {aj.get('autonomia', 'perfil')}."
        return f"El tope de gasto mensual con la clave de pago es de {aj.get('gasto', 'tope_mensual_eur'):g} euros."
    tipo, seccion, clave, dato, descripcion = orden
    try:
        if tipo == "mover":
            actual = float(aj.get(seccion, clave))
            _, kind, (minimo, maximo), _ = AJ.ESQUEMA[seccion][clave]
            nuevo = AJ.validar(seccion, clave, round(min(maximo, max(minimo, actual + dato)), 3))      # se queda en el límite si se pasa
            if nuevo == actual:
                return "Ya no puedo ir más allá en esa dirección."
        else:
            nuevo = AJ.validar(seccion, clave, dato)
    except ValueError as e:
        if tipo == "mover":
            return "Ya no puedo ir más allá en esa dirección."
        return f"Eso no vale: {e}."
    if AJ.cambio_sensible(seccion, clave, nuevo, aj) and voz_libre:
        return ("Eso me da más permisos o más gasto, y por seguridad solo lo cambio si pulsas el atajo y me lo dices tú. "
                "Con «Oye Lina» no, por si lo dijera otra voz.")
    aj.establecer(seccion, clave, nuevo)
    if clave == "velocidad":
        return f"Vale, hablo {descripcion}."
    if seccion == "interfaz":
        return f"Vale, el resplandor queda {descripcion}."
    if clave == "perfil":
        return f"Vale, ahora voy {descripcion}."
    return f"Vale, el tope {descripcion}."
