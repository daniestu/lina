# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Cuándo se puede mirar la pantalla: permiso de capturas, decisión de la IA y motivo si no se ve."""
from lina.nucleo import ajustes as AJ
from lina.nucleo import comandos as C
from lina.nucleo import herramientas as H
from lina.nucleo import ia_activa as IAC
from lina.nucleo.constantes import NO_VE_PANTALLA
from lina.nucleo.constantes import PANTALLA_SESION_SEG
from lina.nucleo.ia import nivel_razonamiento
from lina.nucleo.ia import parece_promesa
from lina.nucleo.registro import log
from lina.nucleo import rutas as RUT
from pathlib import Path
import threading
import time



class MixinPantalla:
    def _permiso_de_capturas(self):
        """Lo que se le dice a la IA cuando necesita ver la pantalla y el usuario no ha dado permiso (o «» si no es ese el problema).
        Sin decidir: se deja PENDIENTE de la confirmación del usuario (solo con el atajo) pedirlo, porque lo ha necesitado ella, no porque él lo pidiera.
        La IA nunca se lo concede sola. Si dijo que NO, se respeta: solo lo cambia él en la terminal."""
        if self.modo_privado:
            return ""
        estado = AJ.actuales(log=lambda m: None).get("privacidad", "capturas")
        if estado == "si":
            return ""
        if estado == "no":
            return ("No puedo ver la pantalla: el usuario decidió que NUNCA envíes capturas. Respétalo: díselo en una frase y que, si cambia de opinión, "
                    "lo decida él en una terminal con «lina privacidad». No adivines lo que hay en ella.")
        if self.ejecutor.contaminado:
            return ("No puedo ver la pantalla: el usuario aún no ha dado permiso para enviar capturas y, como en esta tarea has leído contenido de fuera, "
                    "no lo propongo ahora. Díselo y que lo decida él con «lina privacidad».")
        self.peticion_de_capturas = getattr(self, "pregunta_pura", "")
        r = self.ejecutor.preparar_accion(
            "Dar permiso a Lina para enviar capturas de tu pantalla a la IA (Gemini, de Google) cuando hagan falta, empezando por la petición de ahora. "
            "Nunca en modo privado ni con ventanas sensibles; se revoca con «lina privacidad no»",
            self._conceder_capturas, motivo="permiso para ver la pantalla", razon="es un permiso de privacidad que solo da el usuario")
        return ("Aún no puedes ver la pantalla: el usuario no ha decidido si permite enviar capturas, y lo necesitas para lo que pide. " + r +
                " Explícale en una frase que para esto necesitas ver su pantalla y que la captura se enviaría a Google (Gemini); pregúntale si te deja. "
                "NO describas lo que hay en la pantalla: no lo sabes.")

    def _conceder_capturas(self):
        """Se ejecuta SOLO cuando el usuario confirma con el atajo: guarda el permiso y deja lista la captura para retomar lo que pidió."""
        AJ.actuales(log=lambda m: None).establecer("privacidad", "capturas", "si")
        H.anotar("[privacidad] capturas = si (confirmado por el usuario con el atajo, a petición de la IA)")
        imagen = getattr(self, "imagen_del_turno", None)
        if not imagen and not self._motivo_sin_pantalla():
            imagen = self._capturar_ahora()[0]                   # con el permiso sin decidir no se capturó al pulsar: se hace ahora
        if imagen and not self._motivo_sin_pantalla():
            self.captura_guardada, self.pedir_pantalla = imagen, True
            ya = f" Retoma lo que pidió antes: «{getattr(self, 'peticion_de_capturas', '')[:200]}». La captura se te adjuntará al terminar esta respuesta."
        else:
            ya = " Ahora mismo no hay captura utilizable (ventana sensible o modo privado): díselo; podrá pedírtelo de nuevo."
        return "Permiso concedido por el usuario (se puede quitar con «lina privacidad no»)." + ya

    def _motivo_sin_pantalla(self, titulo=None, clase=None):
        """Por qué NO se puede enviar una captura ahora (o «» si se puede). Esto no lo decide la IA: es privacidad."""
        if self.modo_privado:
            return "estás en modo privado"
        if AJ.actuales(log=lambda m: None).get("privacidad", "capturas") != "si":
            return "no has dado tu permiso para enviar capturas (decídelo con:  lina privacidad)"
        if C.ventana_sensible(self.titulo if titulo is None else titulo, (self.contexto or {}).get("clase", "") if clase is None else clase):
            return "la ventana activa parece sensible (banco, facturación, contraseñas…)"
        return ""

    # ---------- la captura de cada petición, bajo demanda ----------
    def _preparar_captura(self, ventana):
        """Al pulsar (o al llegar una orden por «Oye Lina»): se apunta QUÉ ventana tenías delante y, solo en un juego (donde la captura siempre se envía y
        el momento importa), se captura ya. Fuera de un juego se captura después, y solo si la frase lo pide. Si no se podría usar (modo privado, sin
        permiso, ventana sensible), no se captura nada."""
        self._n_captura = getattr(self, "_n_captura", 0) + 1
        self.ruta_captura = RUT.temporal(f"captura-{self._n_captura}.png")
        self.ventana_al_pulsar = {"id": str(ventana.get("id") or ""), "titulo": ventana.get("titulo") or "", "clase": ventana.get("clase") or ""}
        self.hilo_captura = None
        motivo = self._motivo_sin_pantalla(self.ventana_al_pulsar["titulo"], self.ventana_al_pulsar["clase"])
        if motivo:
            log(f"Captura de pantalla: no la hago ({motivo})")
            return
        sin_identificar = not self._identificable(self.ventana_al_pulsar)
        if sin_identificar:                                  # p. ej. GNOME en Wayland sin xdotool: luego no se podría comprobar que es la misma ventana
            log("Captura de pantalla: no puedo saber qué ventana tienes delante, así que no podré comprobar después que sigue siendo la misma; "
                "la hago ya, al pulsar, como antes (solo miro el modo privado y tu permiso)")
        if sin_identificar or (self.contexto or {}).get("tipo") == "juego":
            from lina.nucleo import asistente as _A
            self.hilo_captura = threading.Thread(target=_A.capturar_pantalla, args=(self.ruta_captura,), daemon=True)
            self.hilo_captura.start()

    @staticmethod
    def _identificable(ventana):
        """¿Se sabe qué ventana es (por su identificador, su título o su clase)?"""
        return bool(ventana.get("id") or ventana.get("titulo") or ventana.get("clase"))

    @staticmethod
    def _misma_ventana(antes, ahora):
        """¿Es la misma ventana que tenías delante al pulsar? Por su identificador; si el escritorio no lo da, por título y clase (y si no se sabe nada, no)."""
        if antes.get("id") and ahora.get("id"):
            return antes["id"] == ahora["id"]
        return bool(antes.get("titulo") or antes.get("clase")) and (antes.get("titulo"), antes.get("clase")) == (ahora.get("titulo"), ahora.get("clase"))

    def _capturar_ahora(self):
        """Captura AHORA la ventana que tenías delante al pulsar → (imagen o None, motivo si no). Se vuelve a comprobar en este momento el modo privado,
        el permiso y si la ventana es sensible (con su título de ahora), y que sigue siendo la misma ventana: si ha cambiado, no se captura otra."""
        from lina.escritorio import sesion as SES
        from lina.nucleo import asistente as _A
        ahora = SES.actual().ventana_activa(vigencia=0)
        motivo = self._motivo_sin_pantalla(ahora.get("titulo", ""), ahora.get("clase", ""))
        if motivo:
            return None, motivo
        antes = getattr(self, "ventana_al_pulsar", None) or {}
        if not self._identificable(antes) and not self._identificable(ahora):
            log("Captura de pantalla: no puedo comprobar que sea la misma ventana (este escritorio no dice cuál está activa); capturo igualmente, como antes")
        elif not self._misma_ventana(antes, ahora):
            return None, "la ventana activa ya no es la que tenía delante el usuario al hablar"
        ruta = getattr(self, "ruta_captura", None) or RUT.temporal("captura-ahora.png")
        self.ruta_captura = ruta
        _A.capturar_pantalla(ruta)
        imagen = _A.preparar_imagen(ruta)
        return imagen, ("" if imagen else "no se ha podido capturar la pantalla")

    def _quiere_pantalla(self, pregunta):
        """(motivo, renovar): por qué esta petición necesita la captura, o ("", False) si no. En un juego, siempre; fuera, si hablas de lo que ves o seguías
        pidiendo ayuda con la pantalla (seguir una ayuda no la alarga: si no, cada pregunta la mandaría para siempre)."""
        if (self.contexto or {}).get("tipo") == "juego":
            return "estás en un juego", True
        if C.pide_mirar(pregunta):
            return "hablas de lo que ves", True
        if time.time() - getattr(self, "ultima_pantalla_t", 0.0) < PANTALLA_SESION_SEG:
            return "seguías pidiendo ayuda con la pantalla", False
        return "", False

    def _captura_de_la_peticion(self, pregunta):
        """La imagen de esta petición, o None. En un juego, la de cuando pulsaste; fuera, se captura ahora solo si hace falta. Si hacía falta y no se pudo
        (cambió la ventana, ahora es sensible…), el motivo queda en `nota_captura` para decírselo a la IA."""
        self.nota_captura = ""
        hilo = getattr(self, "hilo_captura", None)
        if hilo is not None:
            from lina.nucleo import asistente as _A
            hilo.join()
            return _A.preparar_imagen(getattr(self, "ruta_captura", None))
        if not self._quiere_pantalla(pregunta)[0] or self._motivo_sin_pantalla():
            return None
        imagen, motivo = self._capturar_ahora()
        if imagen is None and motivo:
            self.nota_captura = motivo
            log(f"Captura de pantalla: no la hago ({motivo})")
        return imagen

    def _soltar_captura(self):
        """Al terminar la petición, su captura se borra (se haya usado o no); si aún se está haciendo, en cuanto acabe."""
        ruta, hilo = getattr(self, "ruta_captura", None), getattr(self, "hilo_captura", None)
        self.hilo_captura = None
        if not ruta:
            return

        def borrar():
            if hilo is not None:
                hilo.join(15)
            Path(ruta).unlink(missing_ok=True)
        if hilo is not None and hilo.is_alive():
            threading.Thread(target=borrar, daemon=True).start()
        else:
            borrar()

    def _decidir_pantalla(self, imagen, pregunta):
        """¿Va la captura con la pregunta? En un juego, siempre. Fuera, solo si hablas de lo que ves o seguías pidiendo ayuda con la pantalla;
        si no, la IA la pide con ver_pantalla cuando la necesite. En modo privado o con una ventana sensible, NUNCA (ni se guarda).
        Devuelve la imagen a enviar (o None) y deja la captura guardada para cuando se pida."""
        self.captura_guardada, self.pantalla_adjunta, self.imagen_del_turno = imagen, False, imagen
        if not imagen:
            return None
        motivo_no = self._motivo_sin_pantalla()
        if motivo_no:
            self.captura_guardada = None
            log(f"Captura de pantalla: NO enviada ({motivo_no})")
            return None
        motivo, renovar = self._quiere_pantalla(pregunta)
        if not motivo:
            log("Captura de pantalla: no enviada (no hace falta; la IA la pedirá si la necesita)")
            return None
        self.pantalla_adjunta = True
        if renovar:
            self.ultima_pantalla_t = time.time()
        log(f"Captura de pantalla: enviada ({motivo})")
        return imagen

    def _con_pantalla_si_la_pide(self, respuesta, modelo, modo, pregunta, herramientas, sistema):
        """Si la IA ha pedido ver la pantalla (o ha dicho que no la ve), se repite la petición CON la captura. La frase corta del primer paso se
        descarta: jamás se entrega como respuesta."""
        if (not self.pedir_pantalla and not self.pantalla_adjunta and not self.modo_privado
                and NO_VE_PANTALLA.search(H._sin_acentos(str(respuesta).lower()))):
            if not self.captura_guardada and not self._motivo_sin_pantalla():
                self.captura_guardada = self._capturar_ahora()[0]
            if self.captura_guardada:
                log("La IA dice que no ve la pantalla: se la adjunto")
                self.pedir_pantalla = True
        if not self.pedir_pantalla or not self.captura_guardada or self.pantalla_adjunta or self.modo_privado:
            return respuesta, modelo
        self.pedir_pantalla = False
        log("Repito la petición con la captura de pantalla que ha pedido la IA")
        nota = ("\n[SISTEMA: has pedido ver la pantalla: la tienes adjunta (es lo que el usuario veía al preguntar). Respóndele ahora con ella, "
                "con cosas concretas, sin prometer nada.]")
        herr = [h for h in (herramientas or []) if h.get("name") != "ver_pantalla"]
        grupo = "profundo" if modo == "profundo" else "rapido"
        for m in IAC.modelos("profundo" if modo == "profundo" else "rapido"):
            self.paso_guion = 0
            r = self._gemini(grupo, m, pregunta + nota, self.captura_guardada, self.historial, herramientas=herr, ejecutar_herramienta=self.ejecutar_herramienta,
                             sistema=sistema, nivel=nivel_razonamiento(m, modo), revisor=self.revisar_respuesta)
            if r and not parece_promesa(r):
                self.pantalla_adjunta, self.ultima_pantalla_t = True, time.time()
                return r, f"{m} (con la captura)"
        return "No he conseguido mirar la pantalla ahora mismo. Vuelve a pedírmelo dentro de un momento.", "código (sin respuesta)"
