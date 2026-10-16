"""Cuándo se puede mirar la pantalla: permiso de capturas, decisión de la IA y motivo si no se ve."""
from lina.nucleo import ajustes as AJ
from lina.nucleo import comandos as C
from lina.nucleo import herramientas as H
from lina.nucleo.constantes import MODELOS_GEMINI
from lina.nucleo.constantes import MODELOS_PROFUNDO
from lina.nucleo.constantes import NO_VE_PANTALLA
from lina.nucleo.constantes import PANTALLA_SESION_SEG
from lina.nucleo.ia import nivel_razonamiento
from lina.nucleo.ia import parece_promesa
from lina.nucleo.registro import log
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
        if (self.contexto or {}).get("tipo") == "juego":
            motivo = "estás en un juego"
        elif C.pide_mirar(pregunta):
            motivo = "hablas de lo que ves"
        elif time.time() - self.ultima_pantalla_t < PANTALLA_SESION_SEG:
            motivo = "seguías pidiendo ayuda con la pantalla"
        else:
            log("Captura de pantalla: no enviada (no hace falta; la IA la pedirá si la necesita)")
            return None
        self.pantalla_adjunta, self.ultima_pantalla_t = True, time.time()
        log(f"Captura de pantalla: enviada ({motivo})")
        return imagen

    def _con_pantalla_si_la_pide(self, respuesta, modelo, modo, pregunta, herramientas, sistema):
        """Si la IA ha pedido ver la pantalla (o ha dicho que no la ve), se repite la petición CON la captura. La frase corta del primer paso se
        descarta: jamás se entrega como respuesta."""
        if (not self.pedir_pantalla and not self.pantalla_adjunta and self.captura_guardada and not self.modo_privado
                and NO_VE_PANTALLA.search(H._sin_acentos(str(respuesta).lower()))):
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
        for m in (MODELOS_PROFUNDO if modo == "profundo" else MODELOS_GEMINI):
            self.paso_guion = 0
            r = self._gemini(grupo, m, pregunta + nota, self.captura_guardada, self.historial, herramientas=herr, ejecutar_herramienta=self.ejecutar_herramienta,
                             sistema=sistema, nivel=nivel_razonamiento(m, modo), revisor=self.revisar_respuesta)
            if r and not parece_promesa(r):
                self.pantalla_adjunta, self.ultima_pantalla_t = True, time.time()
                return r, f"{m} (con la captura)"
        return "No he conseguido mirar la pantalla ahora mismo. Vuelve a pedírmelo dentro de un momento.", "código (sin respuesta)"
