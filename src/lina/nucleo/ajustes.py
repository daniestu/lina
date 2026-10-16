"""Los ajustes de Lina, en un único sitio: ~/.config/lina/config.toml

Secciones: asistente, voz, activacion, autonomia, gasto, privacidad e interfaz. Cada ajuste tiene valor de fábrica y se valida: si algo
está mal escrito se usa el valor de fábrica y se avisa en el registro (nunca se cae). El archivo se relee solo cuando cambia.
Las listas editables de política, comandos y vocabulario se mantienen aparte (politica.txt, comandos.txt, vocabulario.txt).

Se puede editar a mano o con `lina config`. Al guardar un valor se conservan los comentarios y el orden del archivo.
"""
import json
import os
import re
import tomllib
from pathlib import Path

from lina.nucleo import rutas as RUT

NOMBRE_ARCHIVO = "config.toml"

# ----------------------------------------------------------------------------------------------------------------------
# Esquema: sección -> clave -> (defecto, tipo, restricción, explicación)
#   tipos: texto · bool · int (restricción = (mín, máx)) · float (mín, máx) · opcion (restricción = valores válidos) · lista · color
# ----------------------------------------------------------------------------------------------------------------------
PERFILES = ("autonomo", "equilibrado", "prudente")
CATEGORIAS = ("borrado", "software_de_fuera", "red_expuesta", "sesion", "persistencia", "archivos_de_paquetes")
MODOS_CATEGORIA = ("perfil", "confirmar", "libre")
# Estas categorías se confirman siempre con el atajo, en todos los perfiles y sin interruptor: tocar discos, arranque, cuentas, dinero y gasto.
SIEMPRE_CONFIRMAN = ("discos_y_particiones", "arranque", "cuentas_y_credenciales", "dinero", "gasto_del_asistente")

ESQUEMA: dict = {
    "asistente": {
        "nombre": ("Lina", "texto", None, "Cómo se llama el asistente. Es también la palabra de activación («Oye Lina»)."),
    },
    "voz": {
        "voz": ("es_MX-claude-high", "texto", None, "Voz de Piper. Mira las que hay con:  lina voz"),
        "velocidad": (1.0, "float", (0.5, 2.0), "Velocidad al hablar: 1 normal, 1.2 más rápida, 0.8 más lenta."),
    },
    "activacion": {
        "activo": (True, "bool", None, "false: apaga el manos libres (el atajo sigue funcionando siempre)."),
        "alias": ("", "texto", None, "Otros nombres que también valen, separados por comas."),
        "prefijos": ("oye, escucha, hey, ey, eh, hola, oiga, atiende, despierta, ok, vale, oie", "texto", None, "Palabras que van delante del nombre."),
        "sin_prefijo": (True, "bool", None, "true: basta con «Lina, …» al principio de la frase."),
        "seguimiento": (8, "int", (0, 60), "Segundos tras contestarte en los que puedes seguir hablando sin repetir el nombre (0 = nunca)."),
        "espera_orden": (6, "int", (1, 60), "Segundos que espera tu orden si solo dices «Oye Lina» y callas."),
        "en_juegos": (False, "bool", None, "true: escucha también con un juego en primer plano."),
        "sensibilidad": (0.012, "float", (0.001, 0.5), "Volumen mínimo para considerar que hablas. Mídelo con:  lina manos-libres nivel"),
        "eco": ("auto", "opcion", ("auto", "no"), "auto: cancela el eco si está instalado. no: apagado."),
        "parecido": (0.78, "float", (0.3, 1.0), "Lo parecido que tiene que sonar el nombre (0-1). Más bajo = acepta más variantes (y más falsos avisos)."),
    },
    "autonomia": {
        "perfil": ("autonomo", "opcion", PERFILES, "autonomo: actúa solo salvo lo crítico · equilibrado: además frena los cambios tras leer contenido "
                   "de internet · prudente: pide confirmación para casi todo lo que cambie algo."),
        "borrado": ("perfil", "opcion", MODOS_CATEGORIA, "Borrar de verdad o muchos archivos de golpe."),
        "software_de_fuera": ("perfil", "opcion", MODOS_CATEGORIA, "Instalar o ejecutar software de fuera de las fuentes de confianza (AUR, pip, npm…)."),
        "red_expuesta": ("perfil", "opcion", MODOS_CATEGORIA, "Cortafuegos, SSH y todo lo que expone tu PC a la red."),
        "sesion": ("perfil", "opcion", MODOS_CATEGORIA, "Apagar, reiniciar o cerrar sesión."),
        "persistencia": ("perfil", "opcion", MODOS_CATEGORIA, "Crear servicios o tareas automáticas."),
        "archivos_de_paquetes": ("perfil", "opcion", MODOS_CATEGORIA, "Modificar archivos de programas instalados (/usr…)."),
    },
    "gasto": {
        "tope_mensual_eur": (10.0, "float", (0.0, 100000.0), "Lo máximo que gastas al mes con la clave de pago, en euros."),
        "eur_por_usd": (0.92, "float", (0.01, 100.0), "Cuántos euros vale un dólar (los precios de Google están en dólares)."),
        "avisos_porcentaje": ([50, 80, 100], "lista", None, "Te aviso al llegar a estos porcentajes del tope. Al 100 % la clave de pago deja de usarse."),
    },
    "privacidad": {
        "capturas": ("preguntar", "opcion", ("preguntar", "si", "no"), "Enviar capturas de tu pantalla a la IA cuando haga falta. preguntar: aún no has decidido, no se envía ninguna "
                     "(decídelo con:  lina privacidad) · si: se envían cuando hacen falta, nunca en modo privado ni con ventanas sensibles · no: nunca."),
        "registrar_preguntas": (True, "bool", None, "true: lo que dices y lo que contesto queda en el registro del sistema (journalctl), útil para depurar. false: se omite."),
        "registro_ruido": (False, "bool", None, "true: se apunta en el registro lo que oye y descarta (solo para depurar)."),
        "almacen_claves": ("auto", "opcion", ("auto", "archivo"), "auto: las claves van al llavero del sistema si lo hay (y si no, a un archivo solo tuyo). archivo: siempre archivo."),
    },
    "interfaz": {
        "indicador": (True, "bool", None, "Resplandor en los bordes: te escucha (azul), piensa (ámbar), habla (verde)."),
        "indicador_color": ("azul", "color", None, "Color al escucharte: azul, rojo, verde, morado, naranja, amarillo, rosa, cian, blanco o #rrggbb."),
        "indicador_grosor": (40, "int", (12, 300), "Píxeles que entra el resplandor desde el borde."),
        "indicador_intensidad": (1.0, "float", (0.1, 2.0), "Lo fuerte que brilla: 0.1 casi invisible … 1 normal … 2 muy fuerte."),
        "indicador_juegos": (False, "bool", None, "true: también se dibuja con un juego en primer plano."),
        "indicador_instalar": (True, "bool", None, "true: si faltan paquetes para dibujarlo, los instala solo (repositorios oficiales)."),
    },
}
TITULOS = {"asistente": "Identidad", "voz": "Voz", "activacion": "Manos libres", "autonomia": "Autonomía: qué hace solo y qué te pregunta",
           "gasto": "Gasto con la clave de pago", "privacidad": "Privacidad", "interfaz": "Interfaz"}

# Nombres planos que usa el manos libres desde siempre (activacion.txt) → ajuste nuevo
PLANAS = {
    "nombre": ("asistente", "nombre"), "activo": ("activacion", "activo"), "alias": ("activacion", "alias"), "prefijos": ("activacion", "prefijos"),
    "sin_prefijo": ("activacion", "sin_prefijo"), "seguimiento": ("activacion", "seguimiento"), "espera_orden": ("activacion", "espera_orden"),
    "en_juegos": ("activacion", "en_juegos"), "sensibilidad": ("activacion", "sensibilidad"), "eco": ("activacion", "eco"),
    "parecido": ("activacion", "parecido"), "registro_ruido": ("privacidad", "registro_ruido"),
    **{k: ("interfaz", k) for k in ESQUEMA["interfaz"]},
}

# Ajustes que dan más permisos o más gasto: solo se suben con el atajo (o a mano en el archivo / con `lina config` en la terminal)
SENSIBLES = {("autonomia", "perfil"), ("gasto", "tope_mensual_eur")} | {("autonomia", c) for c in CATEGORIAS}

_COLORES = ("azul", "rojo", "verde", "morado", "violeta", "naranja", "amarillo", "rosa", "cian", "blanco")


# ----------------------------------------------------------------------------------------------------------------------
# Validación y formato
# ----------------------------------------------------------------------------------------------------------------------
def _si_no(v):
    if isinstance(v, bool):
        return v
    t = str(v).strip().lower()
    if t in ("si", "sí", "yes", "true", "1", "on", "verdadero"):
        return True
    if t in ("no", "false", "0", "off", "falso"):
        return False
    raise ValueError("debe ser true o false")


def validar(seccion, clave, valor):
    """Devuelve el valor ya con su tipo y comprobado, o lanza ValueError con la razón en español."""
    try:
        defecto, tipo, restr, _ = ESQUEMA[seccion][clave]
    except KeyError:
        raise ValueError(f"no existe el ajuste «{seccion}.{clave}»")
    if tipo == "bool":
        return _si_no(valor)
    if tipo in ("int", "float"):
        try:
            n = float(str(valor).replace(",", ".")) if not isinstance(valor, (int, float)) or isinstance(valor, bool) else float(valor)
        except ValueError:
            raise ValueError("debe ser un número")
        if tipo == "int":
            if n != int(n):
                raise ValueError("debe ser un número entero")
            n = int(n)
        if restr and not restr[0] <= n <= restr[1]:
            raise ValueError(f"debe estar entre {restr[0]:g} y {restr[1]:g}")
        return n
    if tipo == "opcion":
        t = str(valor).strip().lower()
        if t not in restr:
            raise ValueError("debe ser una de: " + ", ".join(restr))
        return t
    if tipo == "color":
        t = str(valor).strip().lower()
        if t in _COLORES or re.fullmatch(r"#?[0-9a-f]{6}", t):
            return t
        raise ValueError("debe ser un color (azul, rojo…) o #rrggbb")
    if tipo == "lista":
        if isinstance(valor, str):
            valor = re.findall(r"\d+(?:[.,]\d+)?", valor) if clave == "avisos_porcentaje" else [x.strip() for x in valor.split(",") if x.strip()]
        try:
            lista = sorted({int(float(str(x).replace(",", "."))) for x in valor})
        except (TypeError, ValueError):
            raise ValueError("debe ser una lista de números, por ejemplo [50, 80, 100]")
        if not lista or not all(0 < x <= 100 for x in lista):
            raise ValueError("debe tener porcentajes entre 1 y 100")
        return lista
    texto = str(valor).strip()
    if "\n" in texto or "\r" in texto:
        raise ValueError("no puede tener saltos de línea")
    if seccion == "asistente" and clave == "nombre" and not texto:
        raise ValueError("el nombre no puede quedar vacío")
    if seccion == "voz" and clave == "voz" and not re.fullmatch(r"[A-Za-z0-9_.\-]+", texto):
        raise ValueError("nombre de voz no válido")
    return texto


def a_toml(valor):
    """Valor Python → texto TOML."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, list):
        return "[" + ", ".join(a_toml(x) for x in valor) + "]"
    return json.dumps(str(valor), ensure_ascii=False)


def a_texto_plano(valor):
    """Como lo espera el manos libres: «si»/«no», números y listas con comas."""
    if isinstance(valor, bool):
        return "si" if valor else "no"
    if isinstance(valor, list):
        return ", ".join(str(x) for x in valor)
    return str(valor)


def texto_de_fabrica(valores=None):
    """El archivo completo, comentado, con los valores indicados (por defecto, los de fábrica)."""
    valores = valores or {}
    lineas = ["# Ajustes de Lina. Se relee solo al guardar: no hace falta reiniciar.",
              "# Cámbialos a mano o con:  lina config  (lina config poner SECCION.AJUSTE VALOR)", ""]
    for seccion, claves in ESQUEMA.items():
        lineas += [f"# --- {TITULOS[seccion]} ---", f"[{seccion}]"]
        for clave, (defecto, _tipo, _r, nota) in claves.items():
            lineas.append(f"# {nota}")
            lineas.append(f"{clave} = {a_toml(valores.get((seccion, clave), defecto))}")
        lineas.append("")
    return "\n".join(lineas)


# ----------------------------------------------------------------------------------------------------------------------
# Lectura con recarga en caliente
# ----------------------------------------------------------------------------------------------------------------------
class Ajustes:
    def __init__(self, ruta=None, log=print):
        self.ruta = Path(ruta) if ruta else RUT.CONFIG / NOMBRE_ARCHIVO
        self.log = log
        self.valores = {}
        self.avisos = []
        self.marca = "sin leer"
        self.cargar()

    # --- leer
    def _marca(self):
        try:
            return self.ruta.stat().st_mtime_ns
        except OSError:
            return None

    def cargar(self):
        self.marca = self._marca()
        self.avisos = []
        self.valores = {(s, k): v[0] for s, c in ESQUEMA.items() for k, v in c.items()}
        if self.marca is None:
            return self
        try:
            crudo = tomllib.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            self.avisos.append(f"no he podido leer {self.ruta.name} ({e}): uso los valores de fábrica")
            return self
        for seccion, contenido in crudo.items():
            if seccion not in ESQUEMA or not isinstance(contenido, dict):
                self.avisos.append(f"la sección [{seccion}] no existe (se ignora)")
                continue
            for clave, valor in contenido.items():
                if clave not in ESQUEMA[seccion]:
                    self.avisos.append(f"el ajuste «{seccion}.{clave}» no existe (se ignora)")
                    continue
                try:
                    self.valores[(seccion, clave)] = validar(seccion, clave, valor)
                except ValueError as e:
                    self.avisos.append(f"{seccion}.{clave} = {valor!r}: {e}; uso «{a_texto_plano(ESQUEMA[seccion][clave][0])}»")
        return self

    def recargar_si_cambio(self):
        if self._marca() != self.marca:
            self.cargar()
            for a in self.avisos:
                self.log(f"   Aviso en {self.ruta.name}: {a}")
            return True
        return False

    def get(self, seccion, clave):
        return self.valores[(seccion, clave)]

    def obtener(self, ruta_punto):
        s, _, k = ruta_punto.partition(".")
        return self.get(s, k)

    def plano(self, clave):
        """Un ajuste con el nombre plano de siempre (p. ej. «indicador_color»), como texto."""
        s, k = PLANAS[clave]
        return a_texto_plano(self.get(s, k))

    def planas(self):
        return {c: self.plano(c) for c in PLANAS}

    # --- escribir (conserva comentarios y orden)
    def establecer(self, seccion, clave, valor):
        valor = validar(seccion, clave, valor)
        try:
            lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        except OSError:
            lineas = texto_de_fabrica(self.valores).splitlines()
        nuevo = f"{clave} = {a_toml(valor)}"
        actual, fin_seccion, hecho = None, None, False
        for i, l in enumerate(lineas):
            m = re.match(r"\s*\[([a-z_]+)\]\s*(#.*)?$", l)
            if m:
                actual = m.group(1)
                continue
            if actual == seccion:
                fin_seccion = i
                if re.match(rf"\s*{re.escape(clave)}\s*=", l):
                    comentario = re.search(r"\s+#[^\"']*$", l)
                    lineas[i] = nuevo + (comentario.group(0) if comentario else "")
                    hecho = True
                    break
        if not hecho:
            if fin_seccion is None:
                lineas += ["", f"[{seccion}]", nuevo]
            else:
                lineas.insert(fin_seccion + 1, nuevo)
        escribir_privado(self.ruta, "\n".join(lineas) + "\n")
        self.cargar()
        return valor


def escribir_privado(ruta, texto):
    """Escribe el archivo con permisos 600 (solo tú), de forma atómica."""
    ruta = Path(ruta)
    RUT.asegurar(ruta.parent)
    tmp = ruta.with_name(ruta.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(tmp, ruta)


# ----------------------------------------------------------------------------------------------------------------------
# Migración desde los archivos de antes (activacion.txt, voz.txt, presupuesto.txt, politica.txt)
# ----------------------------------------------------------------------------------------------------------------------
def _leer_pares(ruta):
    pares = {}
    try:
        for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, _, v = linea.partition("=")
            pares[k.strip().lower()] = re.split(r"\s+#", v, maxsplit=1)[0].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return pares


def migrar(carpeta=None, log=print):
    """Crea config.toml con lo que había en los archivos antiguos (si los hay) o con los valores de fábrica. Devuelve (ruta, [qué se migró])."""
    base = Path(carpeta or RUT.CONFIG)
    destino = base / NOMBRE_ARCHIVO
    if destino.exists():
        return destino, []
    valores, migrado = {}, []

    def tomar(seccion, clave, valor, origen):
        try:
            valores[(seccion, clave)] = validar(seccion, clave, valor)
            migrado.append(f"{seccion}.{clave} ← {origen}")
        except ValueError as e:
            log(f"Migración: ignoro «{clave} = {valor}» de {origen} ({e})")

    for clave, valor in _leer_pares(base / "activacion.txt").items():
        if clave in PLANAS and valor != "":
            seccion, k = PLANAS[clave]
            tomar(seccion, k, valor, "activacion.txt")
    try:
        voz = next(l.split("#", 1)[0].strip() for l in (base / "voz.txt").read_text(encoding="utf-8").splitlines() if l.split("#", 1)[0].strip())
        tomar("voz", "voz", voz, "voz.txt")
    except (OSError, StopIteration, UnicodeDecodeError):
        pass
    pres = _leer_pares(base / "presupuesto.txt")
    for origen, clave in (("tope_mensual_eur", "tope_mensual_eur"), ("eur_por_usd", "eur_por_usd"), ("avisos_porcentaje", "avisos_porcentaje")):
        if origen in pres:
            tomar("gasto", clave, pres[origen], "presupuesto.txt")
    try:
        texto = (base / "politica.txt").read_text(encoding="utf-8")
        if re.search(r"^\s*autonomia\s+prudente\b", texto, re.M):
            tomar("autonomia", "perfil", "prudente", "politica.txt")
        elif re.search(r"^\s*frenar_cambios\s+si\b", texto, re.M):
            tomar("autonomia", "perfil", "equilibrado", "politica.txt")
    except (OSError, UnicodeDecodeError):
        pass
    escribir_privado(destino, texto_de_fabrica(valores))
    for viejo in ("activacion.txt", "voz.txt"):                     # para que quede claro cuál manda ahora
        try:
            (base / viejo).rename(base / (viejo + ".antiguo"))
        except OSError:
            pass
    return destino, migrado


# ----------------------------------------------------------------------------------------------------------------------
# Instancia compartida
# ----------------------------------------------------------------------------------------------------------------------
_instancia = {"ajustes": None, "ruta": None}


def solo_lectura():
    """Los ajustes tal como están, SIN crear ni migrar nada (para diagnósticos y simulaciones). Sin archivo, valores de fábrica."""
    return Ajustes(RUT.CONFIG / NOMBRE_ARCHIVO, log=lambda m: None)


def actuales(log=print):
    """Los ajustes del usuario (se crean y migran la primera vez; se releen solos al cambiar el archivo)."""
    ruta = RUT.CONFIG / NOMBRE_ARCHIVO
    if _instancia["ajustes"] is None or _instancia["ruta"] != ruta:
        if not ruta.exists():
            _, migrado = migrar(log=log)
            log(f"Ajustes: creado {ruta.name}" + (f" con lo que había antes ({len(migrado)} valores)" if migrado else " con los valores de fábrica"))
        _instancia["ajustes"], _instancia["ruta"] = Ajustes(ruta, log=log), ruta
        for a in _instancia["ajustes"].avisos:
            log(f"   Aviso en {ruta.name}: {a}")
    else:
        _instancia["ajustes"].recargar_si_cambio()
    return _instancia["ajustes"]


# ----------------------------------------------------------------------------------------------------------------------
# Perfiles de autonomía
# ----------------------------------------------------------------------------------------------------------------------
def politica_efectiva(aj):
    """(modo, frenar_contenido_de_fuera, {sección: 'confirmar'|'libre'}) que resultan del perfil y de los interruptores por categoría.

    · autonomo     actúa solo salvo lo crítico (lo de siempre)
    · equilibrado  igual, pero tras leer contenido de internet frena los cambios libres hasta que confirmes
    · prudente     pide confirmación para casi todo lo que cambie algo
    Los interruptores pueden poner una categoría en «confirmar» o «libre» sea cual sea el perfil, salvo las de SIEMPRE_CONFIRMAN."""
    perfil = aj.get("autonomia", "perfil")
    modo = "prudente" if perfil == "prudente" else "alta"
    frenar = perfil in ("equilibrado", "prudente")
    categorias = {}
    for c in CATEGORIAS:
        v = aj.get("autonomia", c)
        if v != "perfil":
            categorias[c] = v
    return modo, frenar, categorias


def cambio_sensible(seccion, clave, valor_nuevo, aj):
    """¿Este cambio da más permisos o más gasto que el valor actual? (Entonces por voz exige el atajo.)"""
    if (seccion, clave) not in SENSIBLES:
        return False
    actual = aj.get(seccion, clave)
    if (seccion, clave) == ("gasto", "tope_mensual_eur"):
        return float(valor_nuevo) > float(actual)
    if clave == "perfil":
        return PERFILES.index(valor_nuevo) < PERFILES.index(actual)
    orden = {"confirmar": 0, "perfil": 1, "libre": 2}
    return orden[valor_nuevo] > orden[actual]


# ----------------------------------------------------------------------------------------------------------------------
# lina config
# ----------------------------------------------------------------------------------------------------------------------
AYUDA = """lina config                           muestra todos los ajustes y su valor
lina config ver SECCION.AJUSTE        un ajuste, con su explicación
lina config poner SECCION.AJUSTE VALOR   cambia un ajuste (se aplica solo, sin reiniciar)
lina config perfil [autonomo|equilibrado|prudente]   muestra o cambia el perfil de autonomía
lina config comprobar                 revisa el archivo y dice qué está mal
lina config ruta                      dónde está el archivo
Los ajustes de nombre, voz, manos libres e interfaz se aplican al momento; algunos (voz, nombre) piden reiniciar:  systemctl --user restart lina"""


def _nombre_completo(texto):
    s, _, k = texto.partition(".")
    if s in ESQUEMA and k in ESQUEMA[s]:
        return s, k
    if texto in PLANAS:                                   # también vale el nombre de siempre: indicador_color, en_juegos…
        return PLANAS[texto]
    return None


def principal(argv, salida=print, ajustes=None):
    aj = ajustes or actuales(log=lambda m: None)
    if not argv:
        for seccion, claves in ESQUEMA.items():
            salida(f"[{seccion}]  {TITULOS[seccion]}")
            for clave in claves:
                salida(f"  {clave} = {a_toml(aj.get(seccion, clave))}")
        salida(f"\nArchivo: {aj.ruta}\nAyuda:   lina config ayuda")
        return 0
    orden, resto = argv[0], argv[1:]
    if orden in ("ayuda", "-h", "--help"):
        salida(AYUDA)
        return 0
    if orden == "ruta":
        salida(str(aj.ruta))
        return 0
    if orden == "comprobar":
        aj.cargar()
        if not aj.avisos:
            salida(f"{aj.ruta.name}: todo correcto.")
            return 0
        for a in aj.avisos:
            salida("  · " + a)
        return 1
    if orden == "ver" and len(resto) == 1:
        n = _nombre_completo(resto[0])
        if not n:
            salida(f"No existe el ajuste «{resto[0]}». Mira los que hay con:  lina config")
            return 2
        defecto, tipo, restr, nota = ESQUEMA[n[0]][n[1]]
        salida(f"{n[0]}.{n[1]} = {a_toml(aj.get(*n))}\n  {nota}\n  de fábrica: {a_toml(defecto)}")
        return 0
    if orden == "perfil":
        if not resto:
            salida(f"Perfil de autonomía: {aj.get('autonomia', 'perfil')}  (cambiar:  lina config perfil autonomo|equilibrado|prudente)")
            return 0
        resto = ["autonomia.perfil", resto[0]]
        orden = "poner"
    if orden == "poner" and len(resto) >= 2:
        n = _nombre_completo(resto[0])
        if not n:
            salida(f"No existe el ajuste «{resto[0]}». Mira los que hay con:  lina config")
            return 2
        try:
            valor = aj.establecer(*n, " ".join(resto[1:]))
        except ValueError as e:
            salida(f"No vale: {n[0]}.{n[1]} {e}.")
            return 2
        salida(f"{n[0]}.{n[1]} = {a_toml(valor)}")
        return 0
    salida(AYUDA)
    return 2
