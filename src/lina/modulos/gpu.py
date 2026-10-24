# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Fase 15: la tarjeta gráfica (módulo opcional: solo aparece si hay una GPU que sepa leer).

  · Solo LECTURA por defecto: frecuencias, temperatura, consumo, memoria de vídeo usada, límite de potencia y el motivo de la limitación si la hay.
    NVIDIA con `nvidia-smi`; AMD (amdgpu) e Intel leyendo sysfs, sin instalar nada.
  · LACT (si está): ver sus perfiles. Cambiar de perfil es una acción que PIDE CONFIRMACIÓN, nunca directa (la decide el clasificador de órdenes).
  · Registro de métricas a un CSV en una carpeta de Lina («cada 2 segundos durante 15 minutos»): un proceso aparte con límites de frecuencia, duración y tamaño,
    que se ve en la lista de procesos y se cancela con la propia herramienta. No se queda corriendo sin que se sepa.
Nada de lo que hay aquí sube frecuencias, quita límites ni toca ventiladores."""
import csv
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from lina.nucleo import rutas as RUT

SYS = Path("/sys")
CARPETA_REGISTROS = RUT.DATOS / "gpu"
ARCHIVO_REGISTRO = RUT.EJECUCION / "gpu_registro.json"
INTERVALO_MIN, INTERVALO_MAX = 1, 60            # segundos entre muestras
MINUTOS_MAX = 60                                  # lo más que puede durar un registro
TAMANO_MAX = 2_000_000                            # bytes: al llegar, el registro se detiene solo
FABRICANTES = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
CAMPOS = ["hora", "temp_c", "uso_pct", "vram_usada_mb", "vram_total_mb", "potencia_w", "limite_w", "frec_gpu_mhz", "frec_mem_mhz", "limitacion"]
_MOTIVOS_NVIDIA = {0x2: "frecuencias fijadas por una aplicación", 0x4: "límite de potencia (software)", 0x8: "ralentización por hardware",
                   0x20: "temperatura (software)", 0x40: "temperatura (hardware)", 0x80: "freno de potencia (hardware)"}      # 0x1 = inactiva y 0x10/0x100 no son limitaciones


def _ej(argv, timeout=8):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, errors="replace")
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)


def _leer(ruta, por_defecto=None):
    try:
        return Path(ruta).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return por_defecto


def _num(ruta, escala=1.0):
    v = _leer(ruta)
    try:
        return float(v) / escala if v is not None else None
    except ValueError:
        return None


# ======================= detección =======================
def detectar(raiz=None):
    """Las GPU que se saben leer: [{'id', 'fabricante', 'nombre', 'ruta'}]. Vacío si no hay ninguna (entonces la herramienta ni se ofrece)."""
    raiz = Path(raiz) if raiz else SYS
    gpus = []
    if shutil.which("nvidia-smi"):
        rc, out = _ej(["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"], timeout=10)
        if rc == 0:
            for linea in out.splitlines():
                indice, _, nombre = linea.partition(",")
                if indice.strip().isdigit() and nombre.strip():
                    gpus.append({"id": f"nvidia{indice.strip()}", "fabricante": "nvidia", "nombre": nombre.strip(), "ruta": indice.strip()})
    for tarjeta in sorted((raiz / "class/drm").glob("card[0-9]*")):
        if "-" in tarjeta.name:
            continue                                                          # card0-DP-1 es una salida de vídeo, no una tarjeta
        dispositivo = tarjeta / "device"
        fab = FABRICANTES.get((_leer(dispositivo / "vendor") or "").lower())
        if fab in ("amd", "intel"):
            nombre = _leer(dispositivo / "product_name") or {"amd": "GPU AMD", "intel": "GPU Intel"}[fab]
            gpus.append({"id": f"{fab}{tarjeta.name[4:]}", "fabricante": fab, "nombre": f"{nombre} ({tarjeta.name})", "ruta": str(tarjeta)})
    return gpus


_cache = {"t": 0.0, "gpus": []}


def hay(raiz=None):
    """¿Hay alguna GPU que leer? (con un minuto de memoria, para no consultar a cada petición)."""
    if raiz is None and time.time() - _cache["t"] < 60:
        return bool(_cache["gpus"])
    gpus = detectar(raiz)
    if raiz is None:
        _cache.update(t=time.time(), gpus=gpus)
    return bool(gpus)


# ======================= lectura =======================
def _leer_nvidia(gpu):
    consultas = ["temperature.gpu", "utilization.gpu", "memory.used", "memory.total", "power.draw", "power.limit", "clocks.gr", "clocks.mem"]
    for campo in ("clocks_event_reasons.active", "clocks_throttle_reasons.active"):        # el nombre cambió entre versiones del controlador
        rc, out = _ej(["nvidia-smi", f"--id={gpu['ruta']}", f"--query-gpu={','.join(consultas + [campo])}", "--format=csv,noheader,nounits"], timeout=10)
        if rc == 0 and out:
            break
    else:
        return {"error": f"nvidia-smi no ha contestado ({out[:100] if out else 'sin mensaje'})"}
    v = [x.strip() for x in out.splitlines()[0].split(",")]
    if len(v) < 9:
        return {"error": f"nvidia-smi ha devuelto algo inesperado: {out[:100]}"}

    def f(x):
        try:
            return float(x)
        except ValueError:
            return None
    mascara = 0
    try:
        mascara = int(v[8], 16)
    except ValueError:
        pass
    motivos = [t for bit, t in _MOTIVOS_NVIDIA.items() if mascara & bit]
    return {"temp_c": f(v[0]), "uso_pct": f(v[1]), "vram_usada_mb": f(v[2]), "vram_total_mb": f(v[3]), "potencia_w": f(v[4]), "limite_w": f(v[5]),
            "frec_gpu_mhz": f(v[6]), "frec_mem_mhz": f(v[7]), "limitacion": ", ".join(motivos) if motivos else "ninguna"}


def _hwmon(dispositivo):
    carpetas = sorted((Path(dispositivo) / "hwmon").glob("hwmon*"))
    return carpetas[0] if carpetas else None


def _leer_amd(gpu):
    d = Path(gpu["ruta"]) / "device"
    h = _hwmon(d)
    r = {"uso_pct": _num(d / "gpu_busy_percent")}
    usada, total = _num(d / "mem_info_vram_used", 1e6), _num(d / "mem_info_vram_total", 1e6)
    r["vram_usada_mb"], r["vram_total_mb"] = usada, total
    temp = potencia = limite = critica = None
    r["frec_gpu_mhz"] = r["frec_mem_mhz"] = None
    if h:
        temps = [t for t in (_num(h / "temp2_input", 1000), _num(h / "temp1_input", 1000)) if t is not None]
        temp = max(temps) if temps else None                                # la mayor: la del punto más caliente (junction) si existe
        critica = _num(h / "temp2_crit", 1000) or _num(h / "temp1_crit", 1000)
        potencia = _num(h / "power1_average", 1e6) or _num(h / "power1_input", 1e6)
        limite = _num(h / "power1_cap", 1e6)
        r["frec_gpu_mhz"], r["frec_mem_mhz"] = _num(h / "freq1_input", 1e6), _num(h / "freq2_input", 1e6)
    for clave, archivo in (("frec_gpu_mhz", "pp_dpm_sclk"), ("frec_mem_mhz", "pp_dpm_mclk")):
        if r[clave] is None:
            m = re.search(r"(\d+)\s*Mhz\s*\*", _leer(d / archivo, ""), re.I)
            r[clave] = float(m.group(1)) if m else None
    r.update(temp_c=temp, potencia_w=potencia, limite_w=limite)
    motivos = []                                                            # amdgpu no dice por qué baja: se deduce (y se avisa de que es una deducción)
    if potencia and limite and potencia >= 0.97 * limite:
        motivos.append("límite de potencia (probable: consume casi todo lo que le dejan)")
    if temp is not None and ((critica and temp >= critica - 3) or (not critica and temp >= 95)):
        motivos.append("temperatura (probable: está en su límite térmico)")
    r["limitacion"] = ", ".join(motivos) if motivos else "ninguna detectada"
    return r


def _leer_intel(gpu):
    t = Path(gpu["ruta"])
    r = {"temp_c": None, "uso_pct": None, "vram_usada_mb": None, "vram_total_mb": None, "potencia_w": None, "limite_w": None, "frec_mem_mhz": None}
    r["frec_gpu_mhz"] = _num(t / "gt_act_freq_mhz") or _num(t / "gt_cur_freq_mhz") or _num(t / "gt/gt0/rps_act_freq_mhz")
    maxima = _num(t / "gt_max_freq_mhz") or _num(t / "gt/gt0/rps_max_freq_mhz")
    motivos = []
    estado = _num(t / "gt/gt0/throttle_reason_status")
    if estado:
        for archivo in sorted((t / "gt/gt0").glob("throttle_reason_*")):
            if archivo.name != "throttle_reason_status" and _leer(archivo) == "1":
                motivos.append(archivo.name.removeprefix("throttle_reason_"))
    r["limitacion"] = ", ".join(motivos) if motivos else ("ninguna detectada" if maxima else "no se puede saber en esta GPU")
    return r


def leer(gpu):
    return {"nvidia": _leer_nvidia, "amd": _leer_amd, "intel": _leer_intel}[gpu["fabricante"]](gpu)


def memoria_libre(raiz=None):
    """Para decidir si cabe un modelo local: ('sin_tarjeta', None) si no hay ninguna GPU (Ollama usaría la CPU); ('medible', MB libres) con la tarjeta que
    más memoria libre tiene; o ('ilegible', None) si hay tarjeta pero no se puede saber cuánta memoria le queda (p. ej. una Intel integrada)."""
    gpus = detectar(raiz)
    if not gpus:
        return "sin_tarjeta", None
    libres = []
    for g in gpus:
        try:
            m = leer(g)
        except Exception:
            continue
        usada, total = m.get("vram_usada_mb"), m.get("vram_total_mb")
        if usada is not None and total:
            libres.append(total - usada)
    return ("medible", max(libres)) if libres else ("ilegible", None)


def _fmt(valor, unidad, decimales=0):
    return "?" if valor is None else f"{valor:.{decimales}f} {unidad}"


def describir(gpu, m):
    if m.get("error"):
        return f"{gpu['nombre']}: {m['error']}"
    vram = "?" if m.get("vram_usada_mb") is None else (f"{m['vram_usada_mb']:.0f} de {m['vram_total_mb']:.0f} MB" if m.get("vram_total_mb") else f"{m['vram_usada_mb']:.0f} MB")
    return (f"{gpu['nombre']}\n  Uso: {_fmt(m.get('uso_pct'), '%')} · Temperatura: {_fmt(m.get('temp_c'), '°C')} · Memoria de vídeo: {vram}\n"
            f"  Frecuencia: {_fmt(m.get('frec_gpu_mhz'), 'MHz')} (memoria {_fmt(m.get('frec_mem_mhz'), 'MHz')}) · "
            f"Consumo: {_fmt(m.get('potencia_w'), 'W', 0)} de un límite de {_fmt(m.get('limite_w'), 'W', 0)}\n  Limitación: {m.get('limitacion', '?')}")


# ======================= LACT =======================
def _lact_instalado():
    return shutil.which("lact") is not None


def lact_perfiles():
    """(lista de perfiles, perfil actual, error). Solo lee."""
    if not _lact_instalado():
        return [], "", "LACT no está instalado (paquete «lact»)."
    rc, out = _ej(["lact", "cli", "profile", "list"], timeout=10)
    if rc != 0:
        return [], "", f"LACT no contesta: {out[:150] or 'sin mensaje'}. ¿Está el servicio lactd en marcha?"
    perfiles = [re.sub(r"^[-*•\s]+", "", l).strip() for l in out.splitlines() if l.strip()]
    rc, actual = _ej(["lact", "cli", "profile", "get"], timeout=10)
    return perfiles, (actual.strip() if rc == 0 else ""), ""


# ======================= registro a archivo =======================
def _muestra(gpu):
    m = leer(gpu)
    return [time.strftime("%Y-%m-%d %H:%M:%S")] + [("" if m.get(c) is None else (round(m[c], 1) if isinstance(m.get(c), float) else m[c])) for c in CAMPOS[1:]]


def registrar(ruta, intervalo, duracion_s, indice=0, tam_max=TAMANO_MAX, dormir=time.sleep, reloj=time.time):
    """El bucle del proceso aparte: una fila cada `intervalo` s hasta `duracion_s` o hasta que el archivo llegue al tope de tamaño."""
    gpus = detectar()
    if not gpus:
        return 1
    gpu = gpus[min(indice, len(gpus) - 1)]
    fin = reloj() + duracion_s
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CAMPOS)
        while reloj() < fin:
            w.writerow(_muestra(gpu))
            f.flush()
            if os.path.getsize(ruta) >= tam_max:
                break
            dormir(intervalo)
    ARCHIVO_REGISTRO.unlink(missing_ok=True)
    return 0


def _registro_activo():
    try:
        d = json.loads(ARCHIVO_REGISTRO.read_text(encoding="utf-8"))
        os.kill(int(d["pid"]), 0)
        if "lina.modulos.gpu" not in (_leer(f"/proc/{int(d['pid'])}/cmdline", "") or "").replace("\x00", " "):
            return None                                                      # el pid lo ocupa ya otro programa
        return d
    except (OSError, ValueError, KeyError, TypeError):
        return None


def iniciar_registro(intervalo=2, minutos=15):
    intervalo, minutos = int(intervalo), float(minutos)
    if not INTERVALO_MIN <= intervalo <= INTERVALO_MAX:
        return {"error": f"El intervalo va de {INTERVALO_MIN} a {INTERVALO_MAX} segundos."}
    if not 0 < minutos <= MINUTOS_MAX:
        return {"error": f"Un registro dura como mucho {MINUTOS_MAX} minutos."}
    if _registro_activo():
        return {"error": "Ya hay un registro en marcha; páralo antes de empezar otro (registro_parar)."}
    ruta = CARPETA_REGISTROS / f"gpu-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    ARCHIVO_REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen([sys.executable, "-m", "lina.modulos.gpu", "--registrar", str(ruta), str(intervalo), str(int(minutos * 60))],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    ARCHIVO_REGISTRO.write_text(json.dumps({"pid": p.pid, "csv": str(ruta), "inicio": time.time(), "intervalo": intervalo, "minutos": minutos}), encoding="utf-8")
    return {"texto": f"Registro en marcha: una muestra cada {intervalo} s durante {minutos:g} min en {ruta} (se para solo; puedes cancelarlo con registro_parar). "
                     "Cuando termine, ese CSV se puede convertir en una hoja de cálculo."}


def estado_registro():
    d = _registro_activo()
    if not d:
        recientes = sorted(CARPETA_REGISTROS.glob("gpu-*.csv")) if CARPETA_REGISTROS.is_dir() else []
        return {"texto": "No hay ningún registro en marcha." + (f" El último archivo es {recientes[-1]}." if recientes else "")}
    restante = max(0, d["inicio"] + d["minutos"] * 60 - time.time())
    return {"texto": f"Registro en marcha (pid {d['pid']}): cada {d['intervalo']} s, quedan unos {restante / 60:.1f} min, en {d['csv']}."}


def parar_registro():
    d = _registro_activo()
    if not d:
        return {"texto": "No había ningún registro en marcha."}
    try:
        os.killpg(int(d["pid"]), signal.SIGTERM)
    except OSError:
        try:
            os.kill(int(d["pid"]), signal.SIGTERM)
        except OSError:
            pass
    ARCHIVO_REGISTRO.unlink(missing_ok=True)
    return {"texto": f"Registro parado. Lo recogido hasta ahora está en {d['csv']}."}


# ======================= la herramienta =======================
ACCIONES = ["estado", "lact", "perfil", "registro_iniciar", "registro_estado", "registro_parar"]


def planificar(args):
    accion = str(args.get("accion", "estado") or "estado").strip().lower()
    if accion not in ACCIONES:
        return {"error": f"Acción de GPU desconocida «{accion}». Las hay: {', '.join(ACCIONES)}."}
    objetivo = str(args.get("objetivo", "") or "").strip()
    if accion == "registro_estado":
        return estado_registro()
    if accion == "registro_parar":
        return parar_registro()
    gpus = detectar()
    if not gpus:
        return {"error": "No detecto ninguna tarjeta gráfica que sepa leer (NVIDIA con nvidia-smi, AMD o Intel)."}
    if accion == "estado":
        elegidas = [g for g in gpus if objetivo and objetivo.lower() in (g["nombre"] + g["id"]).lower()] or gpus
        return {"texto": "\n".join(describir(g, leer(g)) for g in elegidas)}
    if accion == "registro_iniciar":
        try:
            return iniciar_registro(args.get("intervalo_s") or 2, args.get("minutos") or 15)
        except (TypeError, ValueError):
            return {"error": "intervalo_s y minutos deben ser números."}
    perfiles, actual, error = lact_perfiles()
    if accion == "lact":
        if error:
            return {"error": error}
        return {"texto": f"LACT: perfil actual «{actual or '?'}». Perfiles: " + (", ".join(f"«{p}»" for p in perfiles) or "(ninguno)") + ". Cambiar de perfil pide confirmación."}
    if error:                                                               # accion == "perfil"
        return {"error": error}
    exacto = [p for p in perfiles if p.lower() == objetivo.lower()] or [p for p in perfiles if objetivo and objetivo.lower() in p.lower()]
    if len(exacto) != 1:
        return {"error": (f"No encuentro un perfil de LACT que encaje con «{objetivo}»" if not exacto else f"Encajan varios perfiles: {', '.join(exacto)}")
                         + f". Perfiles: {', '.join(perfiles)}."}
    nombre = exacto[0]
    return {"comando": f"lact cli profile set {shlex.quote(nombre)}", "motivo": f"cambiar el perfil de la tarjeta gráfica a «{nombre}» (LACT)", "espera": 2.0,
            "comprobar": lambda: "Perfil de LACT ahora: " + lact_perfiles()[1]}


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--registrar":
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
        sys.exit(registrar(sys.argv[2], int(sys.argv[3]), int(sys.argv[4])))
