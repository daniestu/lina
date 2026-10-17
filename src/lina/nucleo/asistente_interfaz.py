"""Control de programas por la interfaz (accesibilidad y visión) y las recetas que se aprenden de ello."""
from lina.nucleo import herramientas as H
from lina.nucleo import ia_activa as IAC
from lina.nucleo.ia import _abortar
from lina.nucleo.registro import log
from lina.nucleo.turnos import peticion_de_receta
import re


class MixinInterfaz:
    def _paso_hecho(self, paso):
        """Apunta un paso de interfaz que SÍ se hizo (con el nombre del control, no su id) por si luego se guarda como receta."""
        self.pasos_receta = (getattr(self, "pasos_receta", []) + [paso])[-20:]

    def _fallo_interfaz(self, motivo):
        """Una acción de interfaz que no pudo hacerse: si la petición acaba sin cumplirse, se reintenta a fondo con este motivo."""
        self.obstaculo = f"usar la interfaz del programa: {str(motivo)[:150]}"

    def herramienta_interfaz(self, args):
        """Leer ventanas es libre; pulsar/escribir/teclear pasan por topes, comprobación de juego, de terminales y de riesgo (confirmar solo con el atajo)."""
        _A.INT.activar_accesibilidad(log)
        accion = str(args.get("accion") or "elementos").strip().lower()
        if accion in ("clic", "senalar"):
            return self.interfaz_por_vision(args, accion)
        if accion not in ("pulsar", "escribir", "tecla", "accionar"):
            r = _A.INT.herramienta(args)
            log("Interfaz: " + r.splitlines()[0][:160])
            self.ultima_tecla = None                                 # mirar el estado «reinicia» el control de teclas repetidas
            if (accion == "elementos" and not r.startswith(("No veo", "Falta"))) or (accion == "acciones" and r.startswith("Acciones de")):
                self.ejecutor.efecto_sin_comprobar = False          # se han mirado los controles de verdad
            return r
        if _abortar.is_set():
            return "Tarea parada: no hago nada más con la interfaz."
        if self.en_juego():
            return "Hay un juego en primer plano: no toco su ventana con la interfaz."
        tope = getattr(_A.INT, "MAX_PASOS", 15)
        if getattr(self, "pasos_interfaz", 0) >= tope:
            return f"Ya he hecho {tope} acciones de interfaz en esta petición: paro aquí. Cuenta al usuario qué queda por hacer y que te lo pida de nuevo si quiere seguir."
        if accion == "accionar" and not str(args.get("nombre") or "").strip():
            return "Para accionar necesito el «nombre» (id o texto) de la acción: míralo antes con interfaz(acciones, filtro=…)."
        if accion == "tecla" and getattr(self, "ultima_tecla", None) == (str(args.get("combo") or "").lower(), str(args.get("ventana") or "").lower()):
            return ("Ya mandaste esa misma tecla y no has mirado el estado desde entonces. Si ALTERNA algo (como ctrl+h), repetirla lo deshace. Comprueba el estado "
                    "(interfaz elementos/acciones o mirar_pantalla) antes de volver a mandarla.")
        if accion in ("pulsar", "escribir") and not (str(args.get("nombre") or "").strip() and (str(args.get("elemento") or "").strip() or str(args.get("ventana") or "").strip())):
            return "Para pulsar o escribir necesito el «nombre» del control tal como salió en interfaz(elementos), y su «elemento» (id) o al menos la «ventana». Pide la lista primero."
        ctx = _A.INT.contexto(args) if accion in ("pulsar", "escribir") else {}
        args_riesgo = args
        if accion == "accionar":
            servicio, ident, acc, error = _A.INT.resolver_accion(args)
            if error:
                self._fallo_interfaz(error)
                return error
            ctx = {"app": servicio, "ventana": servicio, "textos": []}
            args_riesgo = {**args, "nombre": f"{ident} {acc['texto']}"}
        objetivo = f"{ctx.get('app', '')} {ctx.get('ventana', '')} {_A.ventana_activa()} {args.get('ventana', '')}"
        if re.search(H._PROPIO, objetivo, re.I):
            return "Esa ventana es de los archivos del propio asistente: no los toco por la interfaz."
        riesgo = _A.INT.riesgo(args_riesgo, _A.ventana_activa(), ctx)
        if riesgo and riesgo[0] == "negar":
            log("Interfaz: denegado — " + riesgo[1])
            return riesgo[1]
        resumen = {"pulsar": f"Pulsar «{args.get('nombre')}»", "escribir": f"Escribir en «{args.get('nombre')}»",
                   "tecla": f"Mandar la tecla {args.get('combo')} a «{args.get('ventana') or 'la ventana con foco'}»",
                   "accionar": f"Accionar «{args.get('nombre')}»" + (f" ({args.get('estado')})" if args.get("estado") else "")}[accion]
        if accion == "escribir":
            resumen += f" el texto «{str(args.get('texto') or '')[:60]}»"
        if ctx.get("ventana"):
            resumen += f" (ventana «{ctx['ventana'][:50]}»)"

        def hacer(a=dict(args)):  # noqa: B006 (copia a propósito: la acción se ejecuta más tarde)
            self.pasos_interfaz = getattr(self, "pasos_interfaz", 0) + 1
            H.anotar("[interfaz] " + resumen)
            r = _A.INT.herramienta(a)
            u = dict(getattr(_A.INT, "ULTIMO", {}) or {})
            if accion == "tecla":
                self.ultima_tecla = (str(a.get("combo") or "").lower(), str(a.get("ventana") or "").lower())
            if u.get("accion") == accion and (r.startswith(("Pulsado", "Escrito", "Mandado", "Accionado"))):
                self._paso_hecho({"accion": accion, "ventana": (u.get("ventana") or str(a.get("ventana") or "") if accion == "accionar" else (u.get("app") or u.get("ventana") or str(a.get("ventana") or ""))),
                                  "nombre": u.get("nombre", ""), "rol": u.get("rol", ""), "texto": u.get("texto", ""), "combo": u.get("combo", ""), "estado": u.get("estado", "")})
                if accion == "tecla" or (accion == "pulsar" and u.get("sin_cambios")) or (accion == "accionar" and "Verificado" not in r):
                    self.ejecutor.efecto_sin_comprobar = True           # no consta que haya pasado algo: que se mire
                if accion == "accionar" and "Verificado por el estado" in r:
                    self.ejecutor.efecto_sin_comprobar = False          # lo ha comprobado el propio programa: un comando fallido anterior ya no importa
                    self.ejecutor.duda = ""
                if str(getattr(self, "obstaculo", "")).startswith("usar la interfaz"):
                    self.obstaculo = ""
            elif accion == "pulsar" and "no tiene una acción de pulsar" in r and _A.VIS is not None:
                log("Interfaz: el control no se puede pulsar por accesibilidad; pruebo con la visión")
                desc = f"{args.get('rol') or 'control'} «{args.get('nombre')}»" + (f" en la ventana «{ctx.get('ventana')}»" if ctx.get("ventana") else "")
                return self.interfaz_por_vision({"accion": "clic", "descripcion": desc, "ambito": "ventana"}, "clic")
            elif "no he tocado nada" in r:
                pass                                                    # ya estaba como se pedía: no es un fallo
            elif not r.startswith(("Pulsado", "Escrito", "Mandado", "Esperado", "Accionado")):
                self._fallo_interfaz(r.splitlines()[0])
            return r
        if riesgo and riesgo[0] == "confirmar":
            log("Interfaz: pide confirmación — " + riesgo[1])
            return self.ejecutor.preparar_accion(resumen + " con la interfaz de un programa", hacer, "usar la interfaz", razon=riesgo[1])
        r = hacer()
        log(f"Interfaz ({self.pasos_interfaz}/{tope}): {resumen} → " + r.splitlines()[0][:140])
        return r

    def _guardar_receta_interfaz(self, args):
        """Apunta como receta lo que se hizo con la interfaz en ESTA petición. Los pasos los pone el código (lo ejecutado de verdad), no la IA;
        hace falta que algo haya comprobado el resultado después del último paso."""
        ajuste, comprobar = str(args.get("ajuste", "")).strip(), str(args.get("comprobar", "")).strip()
        pasos = list(getattr(self, "pasos_receta", []))
        if not ajuste or not comprobar:
            return "No guardo la receta: faltan el nombre de lo que se consigue o cómo lo comprobaste."
        if not pasos:
            return "No guardo la receta: en esta petición no se ha hecho ningún paso de interfaz que haya funcionado."
        if self.ejecutor.duda:
            return f"No guardo la receta: lo último que se hizo sigue con una duda sin resolver ({self.ejecutor.duda_corta()})."
        if self.ejecutor.efecto_sin_comprobar:
            return "No guardo la receta: nadie ha comprobado el resultado después del último paso. Mira los controles (interfaz elementos) o la pantalla (mirar_pantalla) y vuelve a llamar."
        if any(n in {"pulsar", "escribir"} and not p.get("nombre") for p in pasos for n in [p.get("accion")]):
            return "No guardo la receta: algún paso no tiene nombre de control."
        if not _A.REC.aprender_interfaz(ajuste, "", "", pasos, "", comprobar, solo_comprobar=True):
            return "No puedo guardar esa receta (el nombre debe tener alguna palabra concreta y los pasos ser de pulsar, escribir, tecla o clic)."
        self.receta_interfaz_pendiente = (ajuste, args.get("palabras", ""), getattr(self, "pregunta_pura", ""), pasos, args.get("valor_usado", ""), comprobar)
        return (f"Receta anotada: «{ajuste}» ({len(pasos)} pasos). Se guardará cuando la respuesta se dé por buena; si resulta que no funcionó, se descarta. "
                "Contesta al usuario normalmente.")

    def _cerrar_receta_interfaz(self, aceptada):
        """Al terminar la petición: la receta pendiente se guarda solo si la respuesta se dio por buena (sin duda, sin objeción del revisor, sin reintento)."""
        self.turno_aceptado = bool(aceptada)
        diferidas = list(getattr(self.ejecutor, "recetas_diferidas", None) or [])
        if aceptada and diferidas:
            self.ejecutor.guardar_diferidas(self._peticion_de_receta())
        elif diferidas:
            log(f"Receta descartada ({len(diferidas)}): la petición no se dio por cumplida")
        self.ejecutor.recetas_diferidas = []
        pendiente, self.receta_interfaz_pendiente = getattr(self, "receta_interfaz_pendiente", None), None
        if not pendiente or not aceptada:
            if pendiente:
                log("Receta de interfaz descartada: la petición no se dio por buena a la primera")
            return
        receta = _A.REC.aprender_interfaz(*pendiente)
        if receta:
            self.ejecutor.receta_turno = True

    def _peticion_de_receta(self):
        return peticion_de_receta(self.historial, getattr(self, "pregunta_pura", ""))

    def interfaz_por_vision(self, args, accion):
        """Clic donde la accesibilidad no llega: se mira la ventana con la visión, se comprueba el punto y se pulsa. Mismos topes y confirmaciones que pulsar."""
        if _A.VIS is None:
            return "Falta interfaz_vision.py: no puedo hacer clic por visión."
        if _abortar.is_set():
            return "Tarea parada: no hago nada más con la interfaz."
        if self.en_juego():
            return "Hay un juego en primer plano: no toco su ventana con la interfaz."
        tope = getattr(_A.INT, "MAX_PASOS", 15)
        if accion == "clic" and getattr(self, "pasos_interfaz", 0) >= tope:
            return f"Ya he hecho {tope} acciones de interfaz en esta petición: paro aquí. Cuenta al usuario qué queda por hacer."
        if not str(args.get("descripcion") or "").strip():
            return "Describe qué hay que pulsar (por ejemplo «el botón Reproducir» o «el icono de la lupa»)."
        motivo_no = self._motivo_sin_pantalla(_A.ventana_activa(), _A.clase_activa())
        if motivo_no:
            return self._permiso_de_capturas() or f"No miro la ventana para hacer clic: {motivo_no}. Díselo al usuario; que lo pulse él."
        if re.search(H._PROPIO, _A.ventana_activa(), re.I):
            return "Esa ventana es de los archivos del propio asistente: no los toco por la interfaz."
        riesgo_previo = _A.INT.riesgo({"accion": "clic", "nombre": args.get("descripcion", "")}, _A.ventana_activa())
        if riesgo_previo and riesgo_previo[0] == "negar":
            log("Interfaz: denegado — " + riesgo_previo[1])
            return riesgo_previo[1]
        claves = self._claves("mini")
        # Tres miradas por clic: la general (solo hace falta la zona) y la comprobación van con el modelo barato (Flash gratis solo da 20 al día);
        # el modelo más fuerte se reserva para la ampliación, que es donde se decide la precisión.
        visor = lambda imagen, texto, sistema: _A.visor_gemini(claves, imagen, texto, sistema, json_salida=True,
                                                            modelos=IAC.modelos("profundo" if sistema == _A.VIS.PROMPT_REFINAR else "rapido"))
        loc = _A.VIS.localizar(args, visor)
        if loc.get("error"):
            log("Interfaz (visión): " + loc["error"][:160])
            self._fallo_interfaz(loc["error"])
            return loc["error"]
        H.anotar(f"[interfaz-visión] {accion} «{loc['etiqueta']}»")
        log(f"Interfaz (visión): «{loc['etiqueta']}» en ({loc['x']},{loc['y']}), seguridad {loc['confianza']:.0%}")
        if accion == "senalar":
            return _A.VIS.hacer_clic(loc, solo_mover=True)
        riesgo = _A.INT.riesgo({"accion": "clic", "nombre": f"{args.get('descripcion', '')} {loc['etiqueta']}"}, _A.ventana_activa())
        if riesgo and riesgo[0] == "negar":
            return riesgo[1]
        resumen = f"Hacer clic en «{loc['etiqueta']}» ({args.get('descripcion', '')[:60]})"
        boton, veces = args.get("boton", "izquierdo"), args.get("veces", 1)

        def hacer():
            self.pasos_interfaz = getattr(self, "pasos_interfaz", 0) + 1
            H.anotar("[interfaz-visión] " + resumen)
            r = _A.VIS.hacer_clic(loc, boton, veces)
            if r.startswith("Clic"):
                self._paso_hecho({"accion": "clic", "ventana": loc.get("ventana", ""), "descripcion": str(args.get("descripcion", "")), "boton": boton, "veces": veces})
                self.ejecutor.efecto_sin_comprobar = True               # un clic a ciegas: que se compruebe con la pantalla o los controles
                if str(getattr(self, "obstaculo", "")).startswith("usar la interfaz"):
                    self.obstaculo = ""
            else:
                self._fallo_interfaz(r)
            return r
        if riesgo and riesgo[0] == "confirmar":
            log("Interfaz (visión): pide confirmación — " + riesgo[1])
            return self.ejecutor.preparar_accion(resumen + " con el ratón", hacer, "usar la interfaz", razon=riesgo[1])
        r = hacer()
        log(f"Interfaz ({self.pasos_interfaz}/{tope}): {resumen} → " + r.splitlines()[0][:140])
        return r


# Al final a propósito: asistente.py importa este módulo y este importa a asistente.py; así vale importar cualquiera de los dos primero.
from lina.nucleo import asistente as _A  # se usa al llamar (no al importar): así valen los parches de pruebas
