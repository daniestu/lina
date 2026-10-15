"""`lina doctor`: comprueba que todo lo que Lina necesita está en su sitio y, si no, dice qué falta y el comando que lo arregla.

Solo lee: no cambia nada ni instala nada. `--red` además prueba la conexión y la clave de Gemini. `--informe` imprime lo mismo sin datos
personales (carpeta personal, usuario, nombre del equipo, claves, correos, direcciones IP) para pegarlo en una incidencia.
"""
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

from lina import __version__
from lina.escritorio import atajo as ATAJO
from lina.nucleo import ajustes as AJ
from lina.nucleo import bienvenida as BIEN
from lina.nucleo import claves as CL
from lina.nucleo import modelos as MOD
from lina.nucleo import plataforma as PL
from lina.nucleo import rutas as RUT

OK, AVISO, MAL = "ok", "aviso", "mal"
SIMBOLO = {OK: "✔", AVISO: "!", MAL: "✘"}


class Sondas:
    """Todo lo que se mira del equipo, en un sitio, para poder sustituirlo en las pruebas."""

    def sistema(self):
        return PL.detectar()

    def python(self):
        return sys.version_info[:3]

    def base_que_falta(self):
        return PL.faltan(PL.PAQUETES_BASE)

    def audio(self):
        return PL.detectar_audio()

    def microfonos(self):
        import sounddevice as sd
        return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]

    def modelos(self):
        return MOD.estado()

    def clave(self):
        return CL.donde_esta("gemini")

    def llavero(self):
        return CL.llavero_disponible()

    def servicio(self):
        """'activo' | 'inactivo' | 'sin_systemd'."""
        if PL.detectar_init() != "systemd":
            return "sin_systemd"
        r = subprocess.run(["systemctl", "--user", "is-active", "lina.service"], capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip() or "inactivo"

    def proceso(self):
        try:
            os.kill(int(RUT.PID.read_text().strip()), 0)
            return True
        except (OSError, ValueError):
            return False

    def atajo(self):
        return ATAJO.ya_hay_atajo(ATAJO.escritorio(), Path.home())

    def ajustes(self):
        return AJ.solo_lectura()

    def enlace(self):
        return (Path.home() / ".local" / "bin" / "lina").exists()

    def red(self):
        socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=6).close()
        return True

    def probar_clave(self):
        from lina.nucleo import claves
        return BIEN.validar_clave(claves.obtener("gemini"))


def _seguro(f, defecto=None):
    try:
        return f()
    except Exception as e:
        return defecto if defecto is not None else e


def comprobar(s=None, red=False):
    """[(estado, tema, detalle, cómo se arregla)]. Nunca lanza: lo que no se puede mirar sale como aviso."""
    s = s or Sondas()
    r = []

    def a(estado, tema, detalle, arreglo=""):
        r.append((estado, tema, detalle, arreglo))

    sis = _seguro(s.sistema)
    if isinstance(sis, Exception):
        a(AVISO, "Sistema", f"no he podido detectarlo ({sis})")
        sis = {}
    else:
        a(OK if sis.get("familia") else AVISO, "Sistema", f"{sis.get('distro')} · gestor {sis.get('gestor') or 'desconocido'} · escritorio {sis.get('escritorio') or '?'} ({sis.get('sesion') or '?'})",
          "" if sis.get("familia") else "Distribución no reconocida: Lina funciona, pero no instalará paquetes sola. Mira  lina sistema")
    py = _seguro(s.python, (0, 0, 0))
    a(OK if py >= (3, 11) else MAL, "Python", ".".join(map(str, py)) + f" · Lina {__version__}", "" if py >= (3, 11) else "Hace falta Python 3.11 o más reciente")
    falta = _seguro(s.base_que_falta)
    if isinstance(falta, Exception):
        a(AVISO, "Paquetes del sistema", f"no he podido comprobarlos ({falta})")
    elif falta:
        a(MAL, "Paquetes del sistema", "faltan: " + ", ".join(falta), _seguro(lambda: PL.orden_canonica_instalar(falta), "") or "")
    else:
        a(OK, "Paquetes del sistema", "los necesarios están instalados")
    audio = _seguro(s.audio)
    a(OK if audio and not isinstance(audio, Exception) else AVISO, "Sonido", audio if audio and not isinstance(audio, Exception) else "no detecto PipeWire ni PulseAudio",
      "" if audio and not isinstance(audio, Exception) else "Sin servidor de sonido Lina no oye ni habla: instala pipewire (o pulseaudio) y arráncalo")
    mics = _seguro(s.microfonos)
    if isinstance(mics, Exception):
        a(MAL, "Micrófono", f"no puedo consultar los dispositivos ({type(mics).__name__}: {str(mics)[:90]})", "Instala PortAudio (lina preparar o install.sh lo hace) y revisa el sonido")
    elif not mics:
        a(MAL, "Micrófono", "no hay ninguno de entrada", "Enchufa un micrófono o actívalo en los ajustes de sonido")
    else:
        a(OK, "Micrófono", f"{len(mics)} dispositivo(s): {mics[0]}" + (" …" if len(mics) > 1 else ""))
    m = _seguro(s.modelos)
    if isinstance(m, Exception):
        a(AVISO, "Modelos", f"no he podido mirarlos ({m})")
    else:
        a(OK if m["whisper"] else MAL, "Whisper (voz a texto)", "listo" if m["whisper"] else "sin descargar", "" if m["whisper"] else "lina modelos")
        if not m["voz"]:
            a(MAL, "Voz de Lina", "la voz elegida no está instalada", "lina modelos")
        elif m["voz_integra"] is False:
            a(MAL, "Voz de Lina", f"{m['voz']}: los archivos no son los que se descargaron", "Bórrala y vuelve a bajarla:  lina voz  y elige otra vez")
        else:
            a(OK, "Voz de Lina", m["voz"] + ("" if m["voz_integra"] else " (sin huella para verificar)"))
    cl = _seguro(s.clave)
    if isinstance(cl, Exception):
        a(AVISO, "Clave de Gemini", f"no he podido mirarla ({cl})")
    elif cl:
        a(OK, "Clave de Gemini", f"guardada en {cl}")
    else:
        a(MAL, "Clave de Gemini", "no hay ninguna: Lina no puede responder", "lina bienvenida   (la clave es gratuita)")
    if not _seguro(s.llavero, False):
        a(AVISO, "Llavero del sistema", "no disponible: las claves van a un archivo solo tuyo (600)", "Opcional: instala libsecret (secret-tool) y un llavero (GNOME Keyring o KWallet)")
    serv = _seguro(s.servicio)
    if serv == "activo":
        a(OK, "Servicio", "lina.service activo")
    elif serv == "sin_systemd":
        a(OK if _seguro(s.proceso, False) else AVISO, "Servicio", "sin systemd: " + ("Lina está en marcha" if _seguro(s.proceso, False) else "Lina no está en marcha"),
          "" if _seguro(s.proceso, False) else "Arráncala con:  lina  (o cierra y abre sesión si el arranque automático está puesto)")
    elif isinstance(serv, Exception):
        a(AVISO, "Servicio", f"no he podido consultarlo ({serv})")
    else:
        a(MAL, "Servicio", f"lina.service está {serv}", "systemctl --user enable --now lina.service   (o  lina preparar)")
    if serv != "sin_systemd":
        a(OK if _seguro(s.proceso, False) else AVISO, "Proceso", "en marcha" if _seguro(s.proceso, False) else "no veo el proceso de Lina", "" if _seguro(s.proceso, False) else "systemctl --user restart lina")
    a(OK if _seguro(s.atajo, False) else AVISO, "Atajo de teclado", "hay un atajo para Lina" if _seguro(s.atajo, False) else "no encuentro ningún atajo", "" if _seguro(s.atajo, False) else "lina atajo")
    a(OK if _seguro(s.enlace, False) else AVISO, "Comando «lina»", "en ~/.local/bin" if _seguro(s.enlace, False) else "no está en ~/.local/bin", "" if _seguro(s.enlace, False) else "lina preparar")
    aj = _seguro(s.ajustes)
    if isinstance(aj, Exception):
        a(MAL, "Ajustes", f"no se pueden leer ({aj})", "lina config")
    else:
        cap = aj.get("privacidad", "capturas")
        a(OK, "Ajustes", f"perfil {aj.get('autonomia', 'perfil')} · capturas de pantalla: {cap}", "" if cap != "preguntar" else "Aún no has decidido lo de las capturas:  lina privacidad")
    if red:
        try:
            s.red()
        except Exception as e:
            a(MAL, "Red", f"no llego a Google ({type(e).__name__})", "Comprueba tu conexión, el cortafuegos o el proxy")
        else:
            a(OK, "Red", "llego a Google")
            if cl and not isinstance(cl, Exception):
                ok, det = _seguro(s.probar_clave, (None, "no he podido probarla"))
                a(OK if ok else AVISO if ok is None else MAL, "Clave en uso", det, "" if ok is not False else "lina clave gemini")
    return r


def formatear(resultados, color=False):
    lineas = []
    for estado, tema, detalle, arreglo in resultados:
        lineas.append(f" {SIMBOLO[estado]} {tema}: {detalle}")
        if arreglo:
            lineas.append(f"     → {arreglo}")
    mal = sum(e == MAL for e, *_ in resultados)
    av = sum(e == AVISO for e, *_ in resultados)
    lineas.append("")
    lineas.append("Todo en orden." if not mal and not av else f"{mal} problema(s) y {av} aviso(s)." + (" Empieza por los marcados con ✘." if mal else ""))
    return "\n".join(lineas)


_IP4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CLAVE = re.compile(r"\b(?:AIza[\w-]{20,}|sk-[\w-]{20,}|gh[pousr]_\w{20,}|[A-Za-z0-9_-]{32,})\b")
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")


def anonimizar(texto, home=None, usuario=None, equipo=None):
    """Quita del texto lo que identifica a la persona o al equipo."""
    home = str(home if home is not None else Path.home())
    usuario = usuario if usuario is not None else (os.environ.get("USER") or "")
    equipo = equipo if equipo is not None else socket.gethostname()
    if home and home != "/":
        texto = texto.replace(home, "~")
    texto = _CORREO.sub("<correo>", texto)
    texto = _MAC.sub("<mac>", texto)
    texto = _IP4.sub("<ip>", texto)
    texto = _CLAVE.sub("<clave>", texto)
    for dato, marca in sorted(((usuario, "<usuario>"), (equipo, "<equipo>")), key=lambda p: -len(p[0] or "")):    # el más largo primero
        if dato and len(dato) > 2:
            texto = re.sub(rf"(?<![\w]){re.escape(dato)}(?![\w])", marca, texto)
    return texto


def principal(argv, sondas=None, salida=print, **anon):
    if "-h" in argv or "--help" in argv:
        salida("lina doctor [--red] [--informe]\n  Comprueba la instalación y dice cómo arreglar lo que falle. No cambia nada.\n"
               "  --red       prueba también la conexión y la clave de Gemini\n  --informe   lo mismo sin datos personales, para pegar en una incidencia")
        return 0
    res = comprobar(sondas, red="--red" in argv)
    texto = formatear(res)
    if "--informe" in argv:
        texto = anonimizar(f"Lina {__version__} · Python {sys.version.split()[0]}\n" + texto, **anon)
    salida(texto)
    return 1 if any(e == MAL for e, *_ in res) else 0
