"""Módulos que el asistente usa si existen y, si no, funciona sin ellos (una actualización a medias no lo deja inservible)."""

PRESUPUESTO_OK = True
try:
    from lina.nucleo import presupuesto as PRES
except ImportError:                   # actualización a medias: sin presupuesto NO se usa la clave de pago (lo seguro) y el asistente arranca igual
    PRESUPUESTO_OK = False

    class _SinPresupuesto:
        def configurar_claves(self, gratis, pago): pass
        def hay_clave_de_pago(self): return False
        def una_sola_clave(self): return True
        def nombre_de(self, clave): return "gratis"
        def claves_para(self, modo): return []
        def registrar(self, *a, **k): pass
        def avisos_pendientes(self): return []
        def notificar(self, texto): pass
        def estado(self): return {"tope_eur": 0.0}
        def resumen(self): return "Falta presupuesto.py: no hay control de gasto y no uso la clave de pago."
        def subir_tope(self, euros, voz_libre=False): return "Falta presupuesto.py: no puedo cambiar el tope."
        def entender_tope(self, texto): return None
    PRES = _SinPresupuesto()
    print("Aviso: falta presupuesto.py; arranco sin la clave de pago", flush=True)
