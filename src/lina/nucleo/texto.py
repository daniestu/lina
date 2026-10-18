# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Texto del asistente: fecha y hora para la IA, números a palabras y limpieza de lo que se va a decir en voz alta."""
import re
import unicodedata
from datetime import datetime

from lina.nucleo import comandos as C
from lina.nucleo import idioma as IDI
from lina.nucleo.registro import log


def _plano_simple(texto):
    t = unicodedata.normalize("NFD", str(texto or "").strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")




_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_es(d):
    return (f"Ahora mismo son las {d.strftime('%H:%M')} del {_DIAS[d.weekday()]} {d.day} de {_MESES[d.month - 1]} de {d.year} (hora del equipo). "
            "Úsala tal cual para la hora, la fecha y los cálculos con ellas; no la inventes ni repitas una de antes.")


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _fecha_en(d):
    return (f"It is now {d.strftime('%H:%M')} on {_DAYS[d.weekday()]}, {_MONTHS[d.month - 1]} {d.day}, {d.year} (the computer's time). "
            "Use it as is for the time, the date and any calculation with them; do not make one up or reuse an earlier one.")


_FECHA_POR_IDIOMA = {"es": _fecha_es, "en": _fecha_en}


def texto_fecha_hora(ahora=None):
    """La fecha y la hora de este momento, para que la IA no las invente ni reutilice una de antes."""
    return IDI.segun(_FECHA_POR_IDIOMA)(ahora or datetime.now())


def log_nueva_peticion():
    """Línea de separación en el registro: así se ve dónde empieza cada petición."""
    log("")
    log("=" * 22 + " NUEVA PETICIÓN " + "=" * 22)


# ----- Números a palabras (para que la voz los lea bien) -----
_UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
             "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
             "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
             "veintiocho", "veintinueve"]
_DECENAS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
_CENTENAS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos",
             6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos"}


def _apocope(texto):
    """'veintiuno' -> 'veintiún', 'treinta y uno' -> 'treinta y un' (delante de mil o millones)."""
    if texto.endswith("veintiuno"):
        return texto[:-9] + "veintiún"
    if texto.endswith("uno"):
        return texto[:-3] + "un"
    return texto


def _menor_mil(n):
    if n == 100:
        return "cien"
    partes = []
    centenas, resto = divmod(n, 100)
    if centenas:
        partes.append(_CENTENAS[centenas])
    if resto:
        if resto < 30:
            partes.append(_UNIDADES[resto])
        else:
            decena, unidad = divmod(resto, 10)
            partes.append(_DECENAS[decena] + (f" y {_UNIDADES[unidad]}" if unidad else ""))
    return " ".join(partes)


def numero_a_texto(n):
    """Número entero a palabras en español: 15103 -> 'quince mil ciento tres'."""
    if n < 30:
        return _UNIDADES[n]
    if n < 1000:
        return _menor_mil(n)
    if n < 1_000_000:
        miles, resto = divmod(n, 1000)
        texto = "mil" if miles == 1 else f"{_apocope(_menor_mil(miles))} mil"
        return texto + (f" {_menor_mil(resto)}" if resto else "")
    if n < 10**12:
        millones, resto = divmod(n, 10**6)
        texto = "un millón" if millones == 1 else f"{_apocope(numero_a_texto(millones))} millones"
        return texto + (f" {numero_a_texto(resto)}" if resto else "")
    return str(n)


_PALABRAS_SUELTAS = {"de", "del", "en", "al", "por", "con", "para", "que", "entre", "sin", "y", "o", "si", "no", "como", "pero"}
_FEMENINAS_EN_A = {"día", "días"}
_MASCULINAS_EN_A = {"mapa", "mapas", "planeta", "planetas", "problema", "problemas", "sistema", "sistemas",
                    "tema", "temas", "idioma", "idiomas", "programa", "programas", "clima", "climas"}


def _concordar(texto, palabra):
    """Si el número acaba en 'uno' y va seguido de un sustantivo, usa un/una: 21 años -> veintiún años, 1 vez -> una vez."""
    if not texto.endswith("uno") or palabra in _PALABRAS_SUELTAS or len(palabra) < 3:
        return texto
    femenino = (palabra not in _MASCULINAS_EN_A and palabra not in _FEMENINAS_EN_A
                and palabra.endswith(("a", "as", "ción", "ciones", "dad", "dades", "vez", "veces")))
    return texto[:-1] + "a" if femenino else _apocope(texto)


_PATRON_NUMERO = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+|\d+)(?:[.,](\d+))?(\s?%)?(?![\w])")


def numeros_a_palabras(texto):
    """Cambia las cifras por palabras: '162%' -> 'ciento sesenta y dos por ciento'. Deja igual lo que no sea un número solo.
    Solo en español: la voz de otros idiomas lee las cifras sola."""
    if IDI.actual() != "es":
        return texto
    def convertir(m):
        entero, decimales, porcentaje = m.group(1), m.group(2), m.group(3)
        digitos = entero.replace(".", "")
        if len(digitos) > 1 and digitos.startswith("0") and not decimales:
            return m.group(0)  # códigos como 007: se leen tal cual
        if len(digitos) > 12:
            return m.group(0)
        resultado = numero_a_texto(int(digitos))
        siguiente = re.match(r"\s+([a-záéíóúñü]+)", m.string[m.end():], re.IGNORECASE)
        if siguiente and not decimales and not porcentaje:
            resultado = _concordar(resultado, siguiente.group(1).lower())
        if decimales:
            if decimales.startswith("0") or len(decimales) > 3:
                resultado += " coma " + " ".join(_UNIDADES[int(d)] for d in decimales)
            else:
                resultado += " coma " + numero_a_texto(int(decimales))
        if porcentaje:
            resultado += " por ciento"
        return resultado
    return _PATRON_NUMERO.sub(convertir, texto)


def estado_de_resultado(resultado):
    """Traduce el resultado de una herramienta a una frase corta («terminó bien», «falló»...). None si no hay que contarlo."""
    r = str(resultado)
    if r.startswith("código de salida: 0"):
        return "terminó bien"
    if r.startswith("código de salida:"):
        return "terminó con un error"
    if r.startswith("SIGUE EN SEGUNDO PLANO"):
        return "sigue en segundo plano y te avisaré al terminar"
    if r.startswith("BLOQUEADO"):
        return "no se hizo: está bloqueado"
    if r.startswith("PREPARADO"):
        return None                                       # queda pendiente: se cuenta aparte
    if r.startswith(("No se pudo", "No he podido", "La herramienta ha fallado", "Falta ", "No hay ")):
        return "falló"
    return "hecho"


def limpiar_para_voz(texto):
    """Quita lo que no se debe leer en voz alta: bloques de código, enlaces y marcas de formato."""
    sin_codigo = re.sub(r"```.*?```", " ", texto, flags=re.S)
    limpio = re.sub(r"https?://\S+", IDI.T("un enlace"), sin_codigo)
    limpio = re.sub(r"[*#_`]", "", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    if not limpio and texto.strip():
        return IDI.T("Es código y no lo leo en voz alta.")
    return limpio


# Detecta cuándo la IA da algo por hecho (son las redes que impiden que Lina diga «listo» sin haberlo hecho: cada idioma tiene las suyas)
_AFIRMA_HECHO_ES = re.compile(
    r"\b(ya\s+)?(he|hemos|ha|han)\s+(creado|hecho|instalado|configurado|cambiado|borrado|movido|eliminado|desinstalado|abierto|"
    r"activado|desactivado|actualizado|puesto|dejado|quitado|renombrado|copiado|escrito|reiniciado|aplicado|guardado|ajustado)\b"
    r"|\b(esta|queda|ya esta)\s+(hech[oa]|cread[oa]|instalad[oa]|configurad[oa]|list[oa])\b|\b(listo|hecho)\b"
    r"|\b(desactivad|activad|cambiad|puest|quitad|instalad|configurad|ajustad|aplicad|guardad|cread|borrad|abiert|reiniciad|apagad|encendid)[oa]s?\b")


_AFIRMA_HECHO_EN = re.compile(
    r"\b(i\s+have|i\s?ve|we\s+have|we\s?ve|i\s+just|i\s+already)\s+(created|made|installed|configured|changed|deleted|removed|moved|uninstalled|opened|"
    r"enabled|disabled|turned|updated|set|put|renamed|copied|written|restarted|applied|saved|adjusted|switched|fixed)\b"
    r"|\b(it\s+is|it\s?s|that\s+is|that\s?s|is\s+now|has\s+been|have\s+been)\s+(done|created|installed|configured|set|ready|enabled|disabled|"
    r"changed|deleted|removed|moved|updated|applied|saved)\b|\b(all\s+set|done|finished)\b")
AFIRMA_HECHO = IDI.PorIdioma({"es": _AFIRMA_HECHO_ES, "en": _AFIRMA_HECHO_EN})

_ADMITE_DUDA_ES = re.compile(r"no (he|has|pude|puedo|hemos|se ha|ha) (podido|logrado|conseguido|funcionado|comprobado)|no puedo (garantizar|asegurar|confirmar)|"
                         r"sin garantia|no (estoy|estamos) segur|no lo he (conseguido|logrado)|no (ha|han) funcionado|no se ha podido")
_ADMITE_DUDA_EN = re.compile(r"(i|we) (could not|could ?n.?t|cannot|can ?not|can ?t|was not able|wasn.?t able|am not able|haven.?t been able|have not been able) "
                             r"(to )?(do|check|verify|confirm|guarantee|make|get|manage|find)|not sure|no guarantee|(did not|didn.?t|has not|hasn.?t|have not|haven.?t) (work|worked|succeed|succeeded)|"
                             r"unable to")
ADMITE_DUDA = IDI.PorIdioma({"es": _ADMITE_DUDA_ES, "en": _ADMITE_DUDA_EN})


def admite_duda(texto):
    """¿La respuesta ya reconoce que no ha podido comprobarlo o conseguirlo?"""
    return ADMITE_DUDA.search(C.normalizar(texto)) is not None


def afirma_hecho(texto):
    """¿El texto da algo por hecho («ya he creado…», «listo»)? Se mira sin tildes ni mayúsculas."""
    return AFIRMA_HECHO.search(C.normalizar(texto)) is not None


_PIDE_CONFIRMACION_ES = re.compile(r"¿[^?]*\b(lo hago|la hago|los hago|lo confirmas|confirmas|confirmo|procedo|lo ejecuto|"
                               r"lo instalo|lo borro|lo muevo|lo creo)\b[^?]*\?", re.I)
_PIDE_CONFIRMACION_EN = re.compile(r"\b(shall i|should i|do you want me to|want me to|may i|can i go ahead|do you confirm|can you confirm|"
                                   r"shall i proceed|should i proceed|ok to proceed|go ahead and)\b[^?]*\?", re.I)
PIDE_CONFIRMACION = IDI.PorIdioma({"es": _PIDE_CONFIRMACION_ES, "en": _PIDE_CONFIRMACION_EN})
