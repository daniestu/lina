"""C2: recordatorios guardados en disco (sobreviven a reiniciar el equipo). Aquí solo está la lógica: entender la hora, guardar y decir cuáles tocan.
Quien los hace sonar por voz es el asistente (un hilo que mira cada pocos segundos y, al arrancar, avisa de los que se pasaron mientras estaba apagado).

La hora se entiende en español natural («dentro de 20 minutos», «mañana a las 9», «el viernes a las 18:30», «el 15 de octubre a las 5 de la tarde»)
o como AAAA-MM-DD HH:MM. Si no se entiende, se dice cuál es la hora de ahora para que la IA dé una exacta.
"""
import json
import os
import re
import threading
import unicodedata
from datetime import datetime, timedelta
from lina.nucleo import idioma as IDI
from lina.nucleo import rutas as RUT

RUTA = RUT.DATOS / "recordatorios.json"
MAX_PENDIENTES = 100
MAX_TEXTO = 200
CONSERVAR_SONADOS = 30            # cuántos ya sonados se guardan para poder contestar «¿qué se me pasó?»
MIN_REPETICION_MIN = 5            # «cada 1 minuto» sería un despertador loco
_lock = threading.RLock()

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def ahora():
    return datetime.now().replace(microsecond=0)


def _plano(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


# ======================= entender la hora =======================
_NUM = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
        "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "treinta": 30,
        "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "noventa": 90}
_N = r"(\d{1,3}|" + "|".join(sorted(_NUM, key=len, reverse=True)) + r")"
_DIA_SEM = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_MES = {_plano(m): i + 1 for i, m in enumerate(MESES)}


def _n(s):
    s = str(s)
    return int(s) if s.isdigit() else _NUM[s]


def _sumar_meses(dt, meses):
    m = dt.month - 1 + meses
    anio, mes = dt.year + m // 12, m % 12 + 1
    dia = dt.day
    while True:
        try:
            return dt.replace(year=anio, month=mes, day=dia)
        except ValueError:
            dia -= 1


def _relativo(t, ref):
    """«en 20 minutos», «dentro de media hora», «en una hora y media»... → datetime o None."""
    m = re.search(r"\b(?:dentro de|en|de aqui a)\s+(?:un\s+)?(media hora|cuarto de hora)\b", t)
    if m:
        return ref + timedelta(minutes=30 if m.group(1).startswith("media") else 15)
    m = re.search(r"\b(?:dentro de|en|de aqui a)\s+" + _N + r"\s*(segundos?|seg|minutos?|min|horas?|h|dias?|semanas?|meses|mes)\b"
                  r"(?:\s+y\s+(media|cuarto|" + _N + r"\s*(?:minutos?|min)))?", t)
    if not m:
        m2 = re.search(r"\b(?:dentro de|en)\s+(?:una\s+)?hora y (media|cuarto)\b", t)
        if m2:
            return ref + timedelta(minutes=90 if m2.group(1) == "media" else 75)
        return None
    cantidad, unidad, extra = _n(m.group(1)), m.group(2), m.group(3)
    if unidad.startswith("seg"):
        d = timedelta(seconds=cantidad)
    elif unidad.startswith("min"):
        d = timedelta(minutes=cantidad)
    elif unidad.startswith("h"):
        d = timedelta(hours=cantidad)
        if extra:
            d += timedelta(minutes=30 if extra == "media" else 15 if extra == "cuarto" else _n(re.match(_N, extra).group(1)))
    elif unidad.startswith("dia"):
        d = timedelta(days=cantidad)
    elif unidad.startswith("semana"):
        d = timedelta(weeks=cantidad)
    else:
        return _sumar_meses(ref, cantidad)
    return ref + d


def _hora(t):
    """(hora, minuto, ambigua, parte_del_dia, medianoche) de lo que se dice, o None. `ambigua`: sin am/pm y ≤ 12."""
    parte = None
    if re.search(r"\b(?:de la |por la |en la |esta )?(?:tarde)\b", t):
        parte = "tarde"
    if re.search(r"\b(?:de la |por la |esta )noche\b", t):
        parte = "noche"
    if re.search(r"\b(?:de la |por la |esta )manana\b|\bpor la manana\b", t):
        parte = "manana"
    if re.search(r"\bmadrugada\b", t):
        parte = "madrugada"
    if re.search(r"\b(?:a|al) ?medio ?dia\b|\bmediodia\b", t):
        return 12, 0, False, parte, False
    if re.search(r"\b(?:a )?medianoche\b|\bmedia noche\b", t):
        return 0, 0, False, parte, True
    h = mi = None
    m = re.search(r"\b(?:a las?|sobre las?|las?)\s*" + _N + r"\s*(?::|\.|h)\s*(\d{2})\b", t) or re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m and m.re.groups == 2 and m.group(1).isdigit():
        h, mi = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(?:a|sobre)\s+las?\s+" + _N + r"(?:\s*(?:horas|h))?"
                      r"(?:\s+(y media|y cuarto|menos cuarto|en punto|y " + _N + r"|menos " + _N + r"))?\b", t)
        if not m:
            m = re.search(r"\blas\s+" + _N + r"\s+(y media|y cuarto|menos cuarto|en punto|y " + _N + r"|menos " + _N + r")\b", t)
        if m:
            h = _n(m.group(1))
            ajuste = m.group(2) or ""
            if ajuste == "y media":
                mi = 30
            elif ajuste == "y cuarto":
                mi = 15
            elif ajuste == "menos cuarto":
                h, mi = h - 1, 45
            elif ajuste.startswith("y "):
                mi = _n(ajuste[2:])
            elif ajuste.startswith("menos "):
                h, mi = h - 1, 60 - _n(ajuste[6:])
            else:
                mi = 0
    if h is None:
        if re.search(r"\bmanana por la manana\b", t):
            return None
        return None
    pm = bool(re.search(r"\bpm\b|\bp\.m\b", t)) or parte in ("tarde", "noche")
    am = bool(re.search(r"\bam\b|\ba\.m\b", t)) or parte in ("manana", "madrugada")
    if h < 0:
        h += 24
    if not (0 <= h <= 24 and 0 <= mi <= 59):
        raise ValueError("Esa hora no existe.")
    if h == 24:
        h = 0
    ambigua = h <= 12 and not pm and not am
    if pm and h < 12:
        h += 12
    elif am and h == 12:
        h = 0
    medianoche = parte == "noche" and h == 12
    if medianoche:
        h = 0
    return h, mi, ambigua, parte, medianoche


def _fecha(t, ref):
    """La fecha (date) que se nombra, o None. Entiende hoy/mañana/pasado mañana, días de la semana, «15 de octubre», 15/10."""
    d0 = ref.date()
    t2 = re.sub(r"\b(?:de la|por la|esta|en la)\s+manana\b", " ", t)
    if re.search(r"\bpasado manana\b", t2):
        return d0 + timedelta(days=2)
    if re.search(r"\bmanana\b", t2):
        return d0 + timedelta(days=1)
    if re.search(r"\bhoy\b|\besta (?:tarde|noche|manana)\b", t):
        return d0
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    m = re.search(r"\b(\d{1,2})\s+de\s+(" + "|".join(_MES) + r")(?:\s+(?:de|del)\s+(\d{4}))?\b", t)
    if m:
        dia, mes, anio = int(m.group(1)), _MES[m.group(2)], m.group(3)
        if anio:
            return datetime(int(anio), mes, dia).date()
        for a in (d0.year, d0.year + 1):
            try:
                c = datetime(a, mes, dia).date()
            except ValueError:
                continue
            if c >= d0:
                return c
        raise ValueError("Esa fecha no existe.")
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        dia, mes, anio = int(m.group(1)), int(m.group(2)), m.group(3)
        if anio:
            a = int(anio) + (2000 if int(anio) < 100 else 0)
            return datetime(a, mes, dia).date()
        for a in (d0.year, d0.year + 1):
            try:
                c = datetime(a, mes, dia).date()
            except ValueError:
                continue
            if c >= d0:
                return c
        raise ValueError("Esa fecha no existe.")
    m = re.search(r"\b(proximo |este |el |del )?(" + "|".join(_DIA_SEM) + r")\b", t)
    if m:
        objetivo = _DIA_SEM[m.group(2)]
        dif = (objetivo - d0.weekday()) % 7
        return d0 + timedelta(days=dif if dif else (7 if (m.group(1) or "").strip() == "proximo" else 0)), objetivo
    m = re.search(r"\bel (?:dia )?(\d{1,2})\b(?! de )", t)
    if m and 1 <= int(m.group(1)) <= 31:
        dia = int(m.group(1))
        c = d0
        for _ in range(14):
            if c.day == dia and c >= d0:
                return c
            c += timedelta(days=1)
    return None


# ======================= inglés =======================
_DIAS_EN_TXT = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MESES_EN_TXT = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_NUM_EN = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
           "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
           "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}
_N_EN = r"(\d{1,3}|" + "|".join(sorted(_NUM_EN, key=len, reverse=True)) + r")"
_DIA_SEM_EN = {d.lower(): i for i, d in enumerate(_DIAS_EN_TXT)}
_MES_EN = {m.lower(): i + 1 for i, m in enumerate(_MESES_EN_TXT)}
_MES_EN.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})
_MES_EN_RE = "|".join(sorted(_MES_EN, key=len, reverse=True))


def _n_en(s):
    s = str(s)
    return int(s) if s.isdigit() else _NUM_EN[s]


def _hora12(dt):
    h = dt.hour % 12 or 12
    return f"{h}{'' if dt.minute == 0 else f':{dt.minute:02d}'} {'am' if dt.hour < 12 else 'pm'}"


def _humano_en(dt, ref):
    delta = dt - ref
    if timedelta(0) <= delta < timedelta(minutes=90):
        mins = max(1, round(delta.total_seconds() / 60))
        return "in 1 minute" if mins == 1 else f"in {mins} minutes"
    dias = (dt.date() - ref.date()).days
    hora = "at " + _hora12(dt)
    if dias == 0:
        dia = "today"
    elif dias == 1:
        dia = "tomorrow"
    elif dias == 2:
        dia = "the day after tomorrow"
    elif 0 < dias < 7:
        dia = f"on {_DIAS_EN_TXT[dt.weekday()]}"
    else:
        dia = f"on {_MESES_EN_TXT[dt.month - 1]} {dt.day}" + (f", {dt.year}" if dt.year != ref.year else "")
    return f"{dia} {hora}"


def _relativo_en(t, ref):
    """«in 20 minutes», «in half an hour», «in an hour and a half», «in 2 hours 30 minutes»... → datetime o None."""
    m = re.search(r"\b(?:in|within)\s+(?:a\s+)?(half an hour|half hour|quarter of an hour|quarter hour)\b", t)
    if m:
        return ref + timedelta(minutes=30 if m.group(1).startswith("half") else 15)
    m = re.search(r"\b(?:in|within)\s+(?:an?|one)\s+hour\s+and\s+(?:a\s+)?(half|quarter)\b", t)
    if m:
        return ref + timedelta(minutes=90 if m.group(1) == "half" else 75)
    m = re.search(r"\b(?:in|within)\s+" + _N_EN + r"\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\b"
                  r"(?:\s+(?:and\s+)?(?:a\s+)?(half|quarter|" + _N_EN + r"\s*(?:minutes?|mins?)))?", t)
    if not m:
        return None
    cantidad, unidad, extra = _n_en(m.group(1)), m.group(2), m.group(3)
    if unidad.startswith("sec"):
        return ref + timedelta(seconds=cantidad)
    if unidad.startswith("min"):
        return ref + timedelta(minutes=cantidad)
    if unidad.startswith(("hour", "hr")):
        d = timedelta(hours=cantidad)
        if extra:
            d += timedelta(minutes=30 if extra == "half" else 15 if extra == "quarter" else _n_en(re.match(_N_EN, extra).group(1)))
        return ref + d
    if unidad.startswith("day"):
        return ref + timedelta(days=cantidad)
    if unidad.startswith("week"):
        return ref + timedelta(weeks=cantidad)
    return _sumar_meses(ref, cantidad)


def _parte_en(t):
    if re.search(r"\b(?:in the |this )?(?:evening)\b|\btonight\b|\bat night\b|\bin the night\b", t):
        return "noche"
    if re.search(r"\b(?:in the |this )?afternoon\b", t):
        return "tarde"
    if re.search(r"\b(?:in the |this )?morning\b", t):
        return "manana"
    return None


def _hora_en(t):
    """(hora, minuto, ambigua, parte, medianoche) o None, como _hora pero para inglés."""
    parte = _parte_en(t)
    if re.search(r"\bnoon\b|\bmidday\b", t):
        return 12, 0, False, parte, False
    if re.search(r"\bmidnight\b", t):
        return 0, 0, False, parte, True
    h = mi = None
    ampm = None
    m = re.search(r"\bhalf past " + _N_EN + r"\b", t)
    if m:
        h, mi = _n_en(m.group(1)), 30
    m2 = re.search(r"\bquarter past " + _N_EN + r"\b", t)
    if h is None and m2:
        h, mi = _n_en(m2.group(1)), 15
    m3 = re.search(r"\bquarter to " + _N_EN + r"\b", t)
    if h is None and m3:
        h, mi = _n_en(m3.group(1)) - 1, 45
    if h is None:
        m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", t)
        if m:
            h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    if h is None:
        m = re.search(r"\b(?:at|around|by|for)\s+" + _N_EN + r"(?:\s+o\s?clock)?\s*(am|pm)?\b(?!\s*(?:minutes?|mins?|hours?|days?|weeks?))", t) \
            or re.search(r"\b(\d{1,2})\s*(am|pm)\b", t)
        if m:
            h, mi, ampm = _n_en(m.group(1)), 0, m.group(2)
    if h is None:
        return None
    pm = ampm == "pm" or parte in ("tarde", "noche")
    am = ampm == "am" or parte in ("manana",)
    if h < 0:
        h += 24
    if not (0 <= h <= 24 and 0 <= mi <= 59):
        raise ValueError("Esa hora no existe.")
    if h == 24:
        h = 0
    ambigua = h <= 12 and not pm and not am
    if pm and h < 12:
        h += 12
    elif am and h == 12:
        h = 0
    medianoche = parte == "noche" and h == 12
    if medianoche:
        h = 0
    return h, mi, ambigua, parte, medianoche


def _fecha_en(t, ref):
    """La fecha (date) que se nombra en inglés, o None; con día de la semana devuelve (fecha, día)."""
    d0 = ref.date()
    if re.search(r"\bday after tomorrow\b", t):
        return d0 + timedelta(days=2)
    if re.search(r"\btomorrow\b", t):
        return d0 + timedelta(days=1)
    if re.search(r"\btoday\b|\btonight\b|\bthis (?:morning|afternoon|evening)\b", t):
        return d0
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    m = re.search(r"\b(?:(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MES_EN_RE + r")|(" + _MES_EN_RE + r")\s+(\d{1,2})(?:st|nd|rd|th)?)(?:\s+(\d{4}))?\b", t)
    if m:
        dia = int(m.group(1) or m.group(4))
        mes = _MES_EN[m.group(2) or m.group(3)]
        if m.group(5):
            return datetime(int(m.group(5)), mes, dia).date()
        for a in (d0.year, d0.year + 1):
            try:
                c = datetime(a, mes, dia).date()
            except ValueError:
                continue
            if c >= d0:
                return c
        raise ValueError("Esa fecha no existe.")
    m = re.search(r"\b(next |this |on )?(" + "|".join(_DIA_SEM_EN) + r")\b", t)
    if m:
        objetivo = _DIA_SEM_EN[m.group(2)]
        dif = (objetivo - d0.weekday()) % 7
        return d0 + timedelta(days=dif if dif else (7 if (m.group(1) or "").strip() == "next" else 0)), objetivo
    m = re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", t)
    if m and 1 <= int(m.group(1)) <= 31:
        dia = int(m.group(1))
        c = d0
        for _ in range(40):
            if c.day == dia and c >= d0:
                return c
            c += timedelta(days=1)
    return None


def _cuando_en(t, ref, original):
    """(datetime, ¿relativo?) de una hora dicha en inglés. ValueError con un mensaje para la IA si no se entiende."""
    t = re.sub(r"p\.m\.?", "pm", re.sub(r"a\.m\.?", "am", t)).replace(",", " ")
    t = re.sub(r"\s+", " ", t).strip()
    dt = _relativo_en(t, ref)
    if dt is not None:
        return dt, True
    fecha = _fecha_en(t, ref)
    semana = None
    if isinstance(fecha, tuple):
        fecha, semana = fecha
    hora = _hora_en(t)
    parte = _parte_en(t)
    partes = {"manana": (9, 0), "tarde": (17, 0), "noche": (21, 0)}
    if fecha is None and hora is None:
        if parte is None:
            raise ValueError(f"No entiendo cuándo es «{original}».")
        hora = (*partes[parte], False, parte, False)
    if hora is None:
        hh = partes.get(parte, (9, 0))
        hora = (hh[0], hh[1], False, None, False)
    h, mi, ambigua, _p, medianoche = hora
    if fecha is None:                                              # solo hora: la próxima vez que sea
        base = ref.replace(hour=0, minute=0, second=0)
        candidatas = [(h, mi)] + ([(h + 12, mi)] if ambigua and h < 12 else [])
        futuras = sorted(base.replace(hour=hh, minute=mm) for hh, mm in candidatas if base.replace(hour=hh, minute=mm) > ref)
        dt = futuras[0] if futuras else base.replace(hour=candidatas[0][0], minute=candidatas[0][1]) + timedelta(days=1)
    else:
        if ambigua and 1 <= h <= 6:                                # «at 5» con fecha y sin más: la tarde
            h += 12
        dt = datetime(fecha.year, fecha.month, fecha.day, h, mi)
        if medianoche:
            dt += timedelta(days=1)
        if semana is not None and dt <= ref and re.search(r"\b(?:this|on)\b", t) and not re.search(r"\bnext\b", t):
            dt += timedelta(days=7)
    return dt, False


def _repetir_en(t, texto):
    if not t or t in ("no", "none", "never", "once", "just once", "only once", "does not repeat", "do not repeat", "no repeat", "dont repeat", "don t repeat"):
        return ""
    m = re.search(r"\bevery\s+" + _N_EN + r"\s*(minutes?|mins?|hours?|hrs?)\b", t)
    if m:
        n = _n_en(m.group(1))
        if m.group(2).startswith(("h")):
            return f"cada:{n}:h" if n >= 1 else ""
        if n < MIN_REPETICION_MIN:
            raise ValueError(f"No repito cada menos de {MIN_REPETICION_MIN} minutos.")
        return f"cada:{n}:min"
    if re.search(r"\bhourly\b|\bevery hour\b", t):
        return "cada:1:h"
    if re.search(r"weekday|workday|monday (?:to|through) friday|business day", t):
        return "laborables"
    if re.search(r"\bdaily\b|\bevery day\b|\beach day\b|\bevery (?:morning|evening|night|afternoon)\b", t):
        return "diario"
    if re.search(r"\bweekly\b|\bevery week\b|\beach week\b|\bevery (?:" + "|".join(_DIA_SEM_EN) + r")\b", t):
        return "semanal"
    if re.search(r"\bmonthly\b|\bevery month\b|\beach month\b", t):
        return "mensual"
    raise ValueError(f"No entiendo cómo se repite «{texto}»: puede ser diario, laborables, semanal, mensual o «cada N minutos/horas».")


def parse_cuando(texto, ref=None):
    """datetime (hora local, sin segundos) de lo que dice el usuario. ValueError con un mensaje para la IA si no se entiende o ya pasó."""
    ref = ref or ahora()
    original = str(texto or "").strip()
    t = _plano(original)
    if not t:
        raise ValueError("Falta cuándo.")
    en = IDI.actual() == "en"
    if re.search(r"\b(ayer|anteayer|anoche|hace \d+|la semana pasada|el mes pasado)\b", t) or (en and re.search(r"\b(yesterday|last night|last week|last month|\d+ (?:minutes?|hours?|days?|weeks?) ago)\b", t)):
        raise ValueError(f"«{original}» es del pasado. Ahora son las {ref:%H:%M} del {DIAS[ref.weekday()]} {ref.day} de {MESES[ref.month - 1]} de {ref.year}.")
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})[ t]+(\d{1,2}):(\d{2})\b", t)
    relativo = False
    if m:
        dt = datetime(*[int(x) for x in m.groups()])
    elif en:
        dt, relativo = _cuando_en(t, ref, original)
    else:
        dt = _relativo(t, ref)
        relativo = dt is not None
        if dt is None:
            fecha = _fecha(t, ref)
            semana = None
            if isinstance(fecha, tuple):
                fecha, semana = fecha
            hora = _hora(t)
            if fecha is None and hora is None:
                partes = {"manana": (9, 0), "tarde": (17, 0), "noche": (21, 0)}
                for clave, hm in partes.items():
                    if re.search(r"\b(?:esta|por la|de la)\s+" + clave + r"\b", t):
                        hora = (hm[0], hm[1], False, clave, False)
                        break
                if hora is None:
                    raise ValueError(f"No entiendo cuándo es «{original}».")
            if hora is None:
                partes = {"tarde": (17, 0), "noche": (21, 0), "manana": (9, 0)}
                hh = next((v for k, v in partes.items() if re.search(r"\b(?:esta|por la|de la|en la)\s+" + k + r"\b", t)), (9, 0))
                hora = (hh[0], hh[1], False, None, False)
            h, mi, ambigua, parte, medianoche = hora
            if fecha is None:                                    # solo hora: la próxima vez que sea
                base = ref.replace(hour=0, minute=0, second=0)
                candidatas = [(h, mi)] + ([(h + 12, mi)] if ambigua and h < 12 else [])
                futuras = sorted(base.replace(hour=hh, minute=mm) for hh, mm in candidatas if base.replace(hour=hh, minute=mm) > ref)
                dt = futuras[0] if futuras else base.replace(hour=candidatas[0][0], minute=candidatas[0][1]) + timedelta(days=1)
            else:
                if ambigua and 1 <= h <= 6:                      # «a las 5» con fecha y sin más: la tarde
                    h += 12
                dt = datetime(fecha.year, fecha.month, fecha.day, h, mi)
                if medianoche:
                    dt += timedelta(days=1)
                if semana is not None and dt <= ref and re.search(r"\b(?:el|este)\b", t) and not re.search(r"\bproximo\b", t):
                    dt += timedelta(days=7)                      # «el lunes a las 9» dicho el lunes a las 10: el siguiente
    dt = dt.replace(microsecond=0) if (m is None and relativo) else dt.replace(second=0, microsecond=0)
    if dt <= ref - timedelta(minutes=1):
        raise ValueError(f"Esa hora ({humano(dt, ref)}) ya ha pasado. Ahora son las {ref:%H:%M} del {DIAS[ref.weekday()]} {ref.day} de {MESES[ref.month - 1]} de {ref.year}.")
    if dt > ref + timedelta(days=366 * 2):
        raise ValueError("Eso queda demasiado lejos (más de dos años).")
    return max(dt, ref + timedelta(seconds=1)) if dt < ref else dt


def completo(dt):
    """«viernes 9 de octubre a las 18:30» (para que el usuario compruebe lo que se ha entendido)."""
    if IDI.actual() == "en":
        return f"{_DIAS_EN_TXT[dt.weekday()]}, {_MESES_EN_TXT[dt.month - 1]} {dt.day} at {_hora12(dt)}"
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} a las {dt:%H:%M}"


def ahora_texto(ref=None):
    ref = ref or ahora()
    if IDI.actual() == "en":
        return f"{_DIAS_EN_TXT[ref.weekday()]}, {_MESES_EN_TXT[ref.month - 1]} {ref.day}, {ref.year}, {ref:%H:%M}"
    return f"{DIAS[ref.weekday()]} {ref.day} de {MESES[ref.month - 1]} de {ref.year}, {ref:%H:%M}"


def parse_repetir(texto):
    """'' (no se repite), 'diario', 'laborables', 'semanal', 'mensual' o 'cada:N:min|h'. ValueError si no se entiende."""
    t = _plano(texto)
    if IDI.actual() == "en":
        return _repetir_en(t, texto)
    if not t or t in ("no", "ninguno", "nunca", "una vez", "solo una vez", "no se repite"):
        return ""
    m = re.search(r"\bcada\s+" + _N + r"\s*(minutos?|min|horas?|h)\b", t)
    if m:
        n = _n(m.group(1))
        if m.group(2).startswith("h"):
            return f"cada:{n}:h" if n >= 1 else ""
        if n < MIN_REPETICION_MIN:
            raise ValueError(f"No repito cada menos de {MIN_REPETICION_MIN} minutos.")
        return f"cada:{n}:min"
    if re.search(r"laborable|entre semana|lunes a viernes|dias de diario", t):
        return "laborables"
    if re.search(r"diari|todos los dias|cada dia|a diario|cada manana|cada noche|cada tarde", t):
        return "diario"
    if re.search(r"seman|cada (" + "|".join(_DIA_SEM) + r")|todos los (" + "|".join(_DIA_SEM) + r")", t):
        return "semanal"
    if re.search(r"mensual|cada mes|todos los meses", t):
        return "mensual"
    raise ValueError(f"No entiendo cómo se repite «{texto}»: puede ser diario, laborables, semanal, mensual o «cada N minutos/horas».")


def siguiente(dt, repetir, ref=None):
    """La siguiente vez (después de `ref`) que toca un recordatorio que se repite."""
    ref = ref or ahora()
    n = dt
    for _ in range(100000):
        if repetir == "diario":
            n += timedelta(days=1)
        elif repetir == "laborables":
            n += timedelta(days=1)
            while n.weekday() >= 5:
                n += timedelta(days=1)
        elif repetir == "semanal":
            n += timedelta(weeks=1)
        elif repetir == "mensual":
            n = _sumar_meses(n, 1)
        elif repetir.startswith("cada:"):
            _, cant, unidad = repetir.split(":")
            n += timedelta(minutes=int(cant)) if unidad == "min" else timedelta(hours=int(cant))
        else:
            return None
        if n > ref:
            return n
    return None


def humano(dt, ref=None):
    """«dentro de 20 minutos», «hoy a las 18 y 30», «mañana a las 9», «el viernes a las 18», «el 15 de octubre a las 9»."""
    ref = ref or ahora()
    if IDI.actual() == "en":
        return _humano_en(dt, ref)
    delta = dt - ref
    if timedelta(0) <= delta < timedelta(minutes=90):
        mins = max(1, round(delta.total_seconds() / 60))
        return "dentro de 1 minuto" if mins == 1 else f"dentro de {mins} minutos"
    dias = (dt.date() - ref.date()).days
    hora = f"a las {dt.hour}" + {0: "", 15: " y cuarto", 30: " y media"}.get(dt.minute, f" y {dt.minute}")
    if dias == 0:
        dia = "hoy"
    elif dias == 1:
        dia = "mañana"
    elif dias == 2:
        dia = "pasado mañana"
    elif 0 < dias < 7:
        dia = f"el {DIAS[dt.weekday()]}"
    else:
        dia = f"el {dt.day} de {MESES[dt.month - 1]}" + (f" de {dt.year}" if dt.year != ref.year else "")
    return f"{dia} {hora}"


# ======================= guardar =======================
def _cargar():
    try:
        datos = json.loads(RUTA.read_text(encoding="utf-8"))
        if isinstance(datos, dict) and isinstance(datos.get("recordatorios"), list):
            return datos
    except (OSError, ValueError):
        pass
    return {"siguiente": 1, "recordatorios": []}


def _guardar(datos):
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    datos["recordatorios"] = ([r for r in datos["recordatorios"] if r["estado"] == "pendiente"]
                              + sorted([r for r in datos["recordatorios"] if r["estado"] != "pendiente"], key=lambda r: r.get("sonado_en", ""))[-CONSERVAR_SONADOS:])
    tmp = RUTA.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, RUTA)


def crear(texto, cuando, repetir="", ref=None):
    """Guarda un recordatorio y devuelve el dict (con `cuando` como texto ISO). ValueError con un mensaje para la IA si algo no cuadra."""
    ref = ref or ahora()
    texto = " ".join(str(texto or "").split())[:MAX_TEXTO]
    if not texto:
        raise ValueError("Falta qué quieres que te recuerde.")
    dt = parse_cuando(cuando, ref)
    rep = parse_repetir(repetir)
    with _lock:
        datos = _cargar()
        if sum(1 for r in datos["recordatorios"] if r["estado"] == "pendiente") >= MAX_PENDIENTES:
            raise ValueError("Hay demasiados recordatorios pendientes: cancela alguno antes.")
        for r in datos["recordatorios"]:                         # el mismo dos veces seguidas (la IA reintenta): no se duplica
            if r["estado"] == "pendiente" and r["texto"] == texto and r["cuando"] == dt.isoformat(timespec="seconds") and r.get("repetir", "") == rep:
                return r
        nuevo = {"id": f"rc{datos['siguiente']:04d}", "texto": texto, "cuando": dt.isoformat(timespec="seconds"), "repetir": rep,
                 "estado": "pendiente", "creado": ref.isoformat(timespec="seconds"), "intentos": 0}
        datos["siguiente"] += 1
        datos["recordatorios"].append(nuevo)
        _guardar(datos)
    return nuevo


def _cuando(r):
    return datetime.fromisoformat(r["cuando"])


def listar(ref=None, incluir_sonados=False):
    ref = ref or ahora()
    with _lock:
        datos = _cargar()
    pend = sorted((r for r in datos["recordatorios"] if r["estado"] == "pendiente"), key=lambda r: r["cuando"])
    if not incluir_sonados:
        return pend
    son = [r for r in datos["recordatorios"] if r["estado"] != "pendiente"][-5:]
    return pend, son


def _buscar(datos, referencia):
    ref = _plano(referencia)
    pend = [r for r in datos["recordatorios"] if r["estado"] == "pendiente"]
    exacto = [r for r in pend if r["id"] == ref]
    if exacto:
        return exacto
    palabras = [p for p in re.findall(r"\w{3,}", ref) if p not in ("recordatorio", "recordatorios", "aviso", "sobre", "para", "del", "los", "las")]
    if not palabras:
        return []
    puntos = []
    for r in pend:
        tx = _plano(r["texto"])
        pts = sum(1 for p in palabras if p[:5] in tx)
        if pts:
            puntos.append((pts, r))
    if not puntos:
        return []
    mejor = max(p for p, _ in puntos)
    return [r for p, r in puntos if p == mejor]


def cancelar(referencia):
    """(cancelados, mensaje). `referencia`: id, palabras del texto, o «todos»."""
    with _lock:
        datos = _cargar()
        if _plano(referencia) in ("todos", "todo", "todas"):
            elegidos = [r for r in datos["recordatorios"] if r["estado"] == "pendiente"]
        else:
            elegidos = _buscar(datos, referencia)
        if not elegidos:
            return [], "No encuentro ningún recordatorio pendiente que encaje."
        if len(elegidos) > 1 and _plano(referencia) not in ("todos", "todo", "todas"):
            return [], "Hay varios que encajan: " + "; ".join(f"{r['id']}: {r['texto']}" for r in elegidos[:5]) + ". Pregúntale cuál."
        ids = {r["id"] for r in elegidos}
        datos["recordatorios"] = [r for r in datos["recordatorios"] if r["id"] not in ids]
        _guardar(datos)
    return elegidos, ""


def posponer(referencia, cuando, ref=None):
    """Cambia la hora de uno pendiente. Devuelve (recordatorio, mensaje)."""
    ref = ref or ahora()
    dt = parse_cuando(cuando, ref)
    with _lock:
        datos = _cargar()
        elegidos = _buscar(datos, referencia)
        if not elegidos:
            return None, "No encuentro ningún recordatorio pendiente que encaje."
        if len(elegidos) > 1:
            return None, "Hay varios que encajan: " + "; ".join(f"{r['id']}: {r['texto']}" for r in elegidos[:5]) + ". Pregúntale cuál."
        for r in datos["recordatorios"]:
            if r["id"] == elegidos[0]["id"]:
                r["cuando"] = dt.isoformat(timespec="seconds")
                r["intentos"] = 0
                _guardar(datos)
                return r, ""
    return None, "No he podido cambiarlo."


def vencidos(ref=None):
    """Los pendientes cuya hora ya llegó, los más antiguos primero."""
    ref = ref or ahora()
    with _lock:
        datos = _cargar()
    return sorted((r for r in datos["recordatorios"] if r["estado"] == "pendiente" and _cuando(r) <= ref), key=lambda r: r["cuando"])


def marcar_sonado(identificador, ref=None, perdido=False):
    """Ya ha sonado: si se repite pasa a su siguiente hora; si no, se guarda como sonado."""
    ref = ref or ahora()
    with _lock:
        datos = _cargar()
        for r in datos["recordatorios"]:
            if r["id"] != identificador:
                continue
            sig = siguiente(_cuando(r), r.get("repetir", ""), ref) if r.get("repetir") else None
            if sig:
                r["cuando"] = sig.isoformat(timespec="seconds")
                r["intentos"] = 0
            else:
                r["estado"] = "perdido" if perdido else "sonado"
                r["sonado_en"] = ref.isoformat(timespec="seconds")
            _guardar(datos)
            return r
    return None


def un_intento_mas(identificador):
    with _lock:
        datos = _cargar()
        for r in datos["recordatorios"]:
            if r["id"] == identificador:
                r["intentos"] = int(r.get("intentos", 0)) + 1
                _guardar(datos)
                return r["intentos"]
    return 0
