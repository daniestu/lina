# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Recetas de pasos (fase 12b): aprender de cualquier petición cumplida la secuencia que funcionó, y repetirla sin IA cuando la misma petición vuelve.

Aprender: al terminar una petición que se dio por cumplida, se guardan SOLO los pasos que cambiaron algo y funcionaron (no las exploraciones ni los intentos
fallidos), más la lectura que lo comprobó. Repetir: si lo que pides es, palabra por palabra, algo que ya se cumplió así, el código repite esos pasos con las
mismas herramientas y las mismas reglas de seguridad (un paso crítico sigue pidiendo tu atajo; una receta no da permisos nuevos), repite la comprobación y
lo dice. Si algo no sale como la vez anterior, la IA toma el relevo contándole lo que pasó."""
import os
import re
import shlex

from lina.nucleo import comandos as C
from lina.nucleo import herramientas as H
from lina.nucleo.idioma import T
from lina.nucleo.registro import log

# Herramientas que solo miran o ayudan a encontrar el camino: no forman parte de la receta
EXPLORACION = {"buscar_ajuste_kde", "mirar_pantalla", "ver_pantalla", "observar_config", "buscar_clave_en_binarios", "ver_recetas", "ver_juegos", "ver_gasto",
               "ver_papelera", "mas_herramientas", "pensar_a_fondo", "usar_receta"}
# Lo que nunca se aprende como receta aunque haya funcionado: borrar, apagar, matar procesos, instalar…
_NO_REPETIR = re.compile(r"\b(?:rm|rmdir|shred|unlink|dd|mkfs\S*|wipefs|fdisk|parted|shutdown|reboot|poweroff|halt|pkill|killall|kill|trash\S*|gio\s+trash)\b"
                         r"|--delete|--purge|\b(?:purge|remove|uninstall|erase)\b|systemctl\s+(?:suspend|hibernate|poweroff|reboot|halt)|loginctl\s+(?:terminate|kill)")
# Frases que dependen del momento o de lo que hay en pantalla: «ciérralo», «abre el último»…
_DEPENDE_DEL_CONTEXTO = set("esto eso esta este esa ese estos esos aqui ahi alli actual activa ultimo ultima anterior siguiente proximo proxima mismo misma".split())
_FECHAS = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b")
_ABIERTO = re.compile(r"(?:Abierto|Abriendo) «")


def _ok(herr, resultado):
    r = str(resultado)
    if H.MENSAJE_PREPARADO in r or r.startswith(("BLOQUEADO", "TOPE ALCANZADO")):
        return False
    if herr == "abrir_app":
        return bool(_ABIERTO.match(r))
    return r.startswith("código de salida: 0")


def _mira_lo_mismo(cambio, lectura):
    """¿Ese comando de lectura mira justo lo que cambió el otro? Comparten alguna palabra concreta (un módulo, un dispositivo, una clave…)."""
    vacias = {"sudo", "true", "false", "enable", "disable", "status", "list", "show", "set", "get", "state", "info", "grep", "echo", "tee", "service",
              "systemctl", "user", "now", "yes", "off", "default", "device", "devices"}

    def palabras(c):
        return {p for p in re.findall(r"[a-z0-9_]{4,}", c.lower()) if p not in vacias}
    return bool(palabras(cambio) & palabras(lectura))


_VERBOS_DE_LEER = {"get", "list", "show", "status", "info", "print", "read", "query", "devices", "paired-devices", "is-active", "is-enabled", "get-volume",
                   "get-mute", "list-sinks", "list-sources", "kreadconfig5", "kreadconfig6"}
_VERBOS_DE_CAMBIAR = {"set", "write", "enable", "disable", "start", "stop", "restart", "block", "unblock", "on", "off", "reset", "add", "remove", "mask", "unmask",
                      "trust", "connect", "disconnect", "pair", "toggle", "load", "unload", "kwriteconfig5", "kwriteconfig6", "set-volume", "set-mute"}


def _parece_lectura(cmd):
    """Un comando que solo mira (gsettings get, rfkill list…), aunque el clasificador lo trate como cambio por prudencia."""
    try:
        palabras = {os.path.basename(t) for t in shlex.split(cmd)}
    except ValueError:
        return False
    return bool(palabras & _VERBOS_DE_LEER) and not (palabras & _VERBOS_DE_CAMBIAR) and not re.search(r"[;&|<>`]|\$\(", cmd.replace("| grep", "").replace("| head", ""))


class MixinPasos:
    def _recetas_de_pasos_activas(self):
        from lina.nucleo import ajustes as AJ
        try:
            return bool(AJ.actuales(log=lambda m: None).get("directas", "recetas"))
        except Exception:
            return False

    # ======================= repetir =======================
    def _intentar_receta_pasos(self, pregunta, crono):
        """Si lo pedido ya se cumplió antes con una receta de pasos fiable, la repite aquí sin llamar a la IA. Devuelve (frase, id) o None (y todo sigue como
        siempre; si la receta empezó y falló, la IA recibe una nota con lo ocurrido)."""
        self._nota_pasos = ""
        REC = self._REC()
        try:
            if REC is None or not self._recetas_de_pasos_activas() or self.ejecutor.pendientes:
                return None
            hallada = REC.para_frase(pregunta)
            if not hallada:
                return None
            receta, valor = hallada
            self.hilo_captura.join()
            self.nueva_tarea()
            self.pregunta_pura = self.ejecutor.pregunta_pura = pregunta
            self.ejecutor.borrado_definitivo = False
            self.ejecutor.continuar = None                       # una receta no espera tareas en segundo plano: si algo tarda, se lo dejo a la IA
            try:
                with crono.medir("herramientas"):
                    frase, nota = self._repetir_pasos(receta, valor)
            finally:
                self.ejecutor.continuar = self._continuar_peticion
            self.ejecutor.recetas_diferidas = []
            if frase is None:
                self.ejecutor.cancelar()
                REC.resultado_pasos(receta["id"], False)
                self._nota_pasos = nota
                log(f"Receta {receta['id']} («{receta['ajuste']}»): {nota or 'no ha salido como la vez anterior'}; se lo dejo a la IA")
                return None
            return frase, "receta"
        except Exception as e:
            if type(e).__name__ == "Cancelado":
                raise
            self.ejecutor.continuar = self._continuar_peticion
            log(f"Receta de pasos: fallo {e!r}; se lo dejo a la IA")
            return None

    @staticmethod
    def _REC():
        from lina.nucleo import asistente as _A
        return _A.REC

    def _repetir_pasos(self, receta, valor):
        """Hace los pasos con las herramientas de siempre. Devuelve (frase, "") si salió bien, o (None, nota para la IA) si no."""
        REC, ej = self._REC(), self.ejecutor
        if valor is not None and not re.fullmatch(r"\d{1,4}", str(valor)):
            return None, ""
        pasos, hechos = receta["pasos"], []
        pendiente = ""
        for i, p in enumerate(pasos, 1):
            args = REC.con_valor(p["args"], valor)
            herr = p["herr"]
            if herr == "ejecutar_comando":
                comando = " ".join(str(args.get("comando", "")).split())
                if H.clasificar(comando)[0] in {"bloqueado", "instalar", "lanzar"} or _NO_REPETIR.search(comando):
                    return None, f"la receta ya no es válida: el paso {i} ahora no se puede repetir tal cual"
                r = str(ej.herramienta(args))
            elif herr == "abrir_app":
                r = str(ej.abrir_app(args.get("nombre", "")))
            else:
                r = str(ej.sistema(herr, dict(args)))
            if H.MENSAJE_PREPARADO in r:                         # paso crítico: lo manda al «sí» del usuario como siempre; es el último o la receta ya no vale
                if i != len(pasos):
                    return None, f"el paso {i} ahora pide confirmación y no es el último"
                pendiente = _limpio_corto(args.get("motivo") or receta["ajuste"])
                hechos.append(f"{i} (pendiente de confirmación)")
                break
            if not _ok(herr, r) or (p.get("comprobado") and "COMPROBADO AHORA" not in r) or ej.duda:
                return None, (f"se repitió la receta «{receta['ajuste']}» (r. {receta['id']}) y falló en el paso {i} ({herr}); pasos ya hechos: "
                              f"{', '.join(hechos) or 'ninguno'}. Comprueba el estado actual antes de seguir y descubre el camino desde cero")
            hechos.append(str(i))
        if pendiente:
            return T("Esto necesita tu confirmación: {motivo}. ¿Lo hago?", motivo=pendiente), ""
        if receta.get("comprobar"):
            r = str(ej.herramienta({"comando": receta["comprobar"], "motivo": "comprobar el resultado"}))
            esperado = receta.get("esperado", "")
            if receta.get("valor_usado") and valor:
                esperado = esperado.replace(receta["valor_usado"], str(valor))
            if not r.startswith("código de salida: 0") or not REC.coincide_salida(esperado, " ".join(r.splitlines()[1:])):
                return None, (f"se repitió la receta «{receta['ajuste']}» (r. {receta['id']}) pero la comprobación no dio lo de la vez anterior "
                              f"(esperaba «{esperado[:80]}», dio «{' '.join(r.splitlines()[1:])[:80]}»); los pasos ya están hechos. Mira el estado y arréglalo si hace falta")
        REC.resultado_pasos(receta["id"], True)
        return T("Hecho."), ""

    # ======================= aprender =======================
    def _frase_para_receta(self):
        """La petición que se cumplió, tal como la dijiste. None si lo último que dijiste es un seguimiento («ahora desactívala») que no la describe."""
        from lina.nucleo.turnos import es_seguimiento, peticion_de_receta
        actual = str(getattr(self, "pregunta_pura", "") or "")
        if es_seguimiento(actual) and not H.es_afirmativo(actual):
            return None
        texto = peticion_de_receta(self.historial, actual)
        m = re.search(r"Pregunta:\s*(.*?)(?:\n\[SISTEMA|$)", str(texto), re.S)
        return (m.group(1) if m else str(texto)).strip()

    def _aprender_pasos(self):
        """Al terminar una petición dada por buena: si hizo algo que se puede repetir, apunta los pasos. Nunca estropea la respuesta."""
        REC, ej = self._REC(), self.ejecutor
        if (REC is None or not self._recetas_de_pasos_activas() or not getattr(self, "turno_aceptado", False) or ej.receta_turno or ej.duda or ej.pendientes
                or ej.contaminado or getattr(self, "insistiendo", False)):
            return
        frase = self._frase_para_receta()
        if not frase:
            return
        palabras = set(C.normalizar(frase).split())
        if palabras & _DEPENDE_DEL_CONTEXTO or any(len(w) >= 6 and re.search(r"[aei](?:lo|la|los|las)$", w) for w in palabras):
            return                                               # «ciérralo», «desactívala»: dependen de a qué se refiera en ese momento
        efectos, lecturas = [], []                               # (posición, herramienta, datos, resultado, comando)
        for i, (n, a, r) in enumerate(self.acciones_turno):
            a, r = a or {}, str(r)
            if n in EXPLORACION:
                continue
            if n not in REC.HERRAMIENTAS_REPETIBLES:
                return                                           # hizo algo que no se sabe repetir (notas, documentos, búsquedas…)
            if n == "ejecutar_comando":
                cmd = " ".join(str(a.get("comando", "")).split())
                clase = H.clasificar(cmd)[0]
                if clase == "lectura" or _parece_lectura(cmd):
                    if _ok(n, r):
                        lecturas.append((i, cmd, r))
                    continue
                if not _ok(n, r):
                    continue                                     # intento fallido: no forma parte de lo que funcionó
                if clase not in {"autonomo", "inocuo", "critico"} or _NO_REPETIR.search(cmd) or _FECHAS.search(cmd) or len(cmd) > 300:
                    return
                try:
                    shlex.split(cmd)
                except ValueError:
                    return
                efectos.append((i, n, {"comando": cmd, "motivo": a.get("motivo", "")}, r, cmd, clase))
            else:
                if not _ok(n, r):
                    continue
                if n == "ventanas":
                    ventana = re.sub(r"\W+", " ", str(a.get("ventana", "")).lower()).strip()
                    if ventana not in ("", "activa") and ventana not in re.sub(r"\W+", " ", frase.lower()):
                        return                                   # actúa sobre una ventana que la frase no nombra: depende de lo que hubiera abierto
                efectos.append((i, n, {k: v for k, v in a.items() if isinstance(v, (str, int, float, bool))}, r, "", "sistema"))
        seguidos = []
        for e in efectos:
            if not seguidos or (seguidos[-1][1], seguidos[-1][2]) != (e[1], e[2]):
                seguidos.append(e)
        efectos = seguidos
        if not efectos or len(efectos) > REC.MAX_PASOS:
            return
        criticos = [e for e in efectos if e[5] == "critico"]
        if len(criticos) > 1 or (criticos and efectos[-1] is not criticos[0]):
            return                                               # un solo paso crítico y al final: lo que sigue a un «sí» no se puede encadenar solo
        ultimo = efectos[-1]
        verificada, comprobar, esperado = False, "", ""
        if ultimo[1] != "ejecutar_comando" and "COMPROBADO AHORA" in ultimo[3]:
            verificada = True                                    # la herramienta de sistema ya comprueba el estado real después de cambiarlo
        else:
            cambio = " ".join(e[4] for e in efectos if e[4])
            lectura = next(((cmd, r) for i, cmd, r in reversed(lecturas) if i > ultimo[0] and _mira_lo_mismo(cambio, cmd)), None)
            if lectura:
                salida = " ".join(lectura[1].splitlines()[1:])[:160]
                if salida.strip():
                    verificada, comprobar, esperado = True, lectura[0], salida
        pasos = [{"herr": e[1], "args": e[2], **({"comprobado": True} if e[1] != "ejecutar_comando" and "COMPROBADO AHORA" in e[3] else {})} for e in efectos]
        receta = REC.aprender_pasos(frase, pasos, comprobar, esperado, verificada)
        if receta:
            ej.receta_turno = True


def _limpio_corto(texto):
    return re.sub(r"\s+", " ", re.sub(r"[^\w .,;:/+%()'-]", " ", str(texto or ""))).strip()[:80] or "una acción"
