# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""Bajar lo que suena mientras Lina te escucha y devolverlo siempre."""
import os

from lina.voz import atenuador as AT


def bloque(ident, pct, app="Firefox", corked="no", mute="no", binario="firefox", pid="999"):
    return (f'Sink Input #{ident}\n\tDriver: PipeWire\n\tCorked: {corked}\n\tMute: {mute}\n'
            f'\tVolume: front-left: {pct * 655} /  {pct}% / -10.00 dB,   front-right: {pct * 655} /  {pct}% / -10.00 dB\n'
            f'\tProperties:\n\t\tapplication.name = "{app}"\n\t\tapplication.process.id = "{pid}"\n\t\tapplication.process.binary = "{binario}"\n')


class Pactl:
    def __init__(self, *bloques):
        self.vol = {}
        self.texto = {}
        for ident, pct, kw in bloques:
            self.vol[ident] = pct
            self.texto[ident] = kw
        self.ordenes = []

    def __call__(self, *args, tiempo=4):
        if args[0] == "list":
            return "\n".join(bloque(i, self.vol[i], **self.texto[i]) for i in self.vol)
        self.ordenes.append(args)
        if args[0] == "set-sink-input-volume":
            self.vol[args[1]] = int(args[2].rstrip("%"))
        return ""


def hacer(tmp_path, *bloques, nivel=20):
    p = Pactl(*bloques)
    return p, AT.Atenuador(nivel=nivel, ejecutar=p, archivo=tmp_path / "bajado.json", log=lambda m: None)


def test_baja_a_una_fraccion_y_devuelve(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}), ("6", 50, {"app": "mpv", "binario": "mpv"}))
    assert a.bajar() == 2
    assert p.vol == {"5": 16, "6": 10} and (tmp_path / "bajado.json").exists()
    assert a.subir() == 2
    assert p.vol == {"5": 80, "6": 50} and not (tmp_path / "bajado.json").exists()


def test_no_toca_pausados_silenciados_ni_los_de_lina(tmp_path):
    p, a = hacer(tmp_path, ("1", 70, {"corked": "yes"}), ("2", 70, {"mute": "yes"}), ("3", 70, {"binario": "piper", "app": "piper"}),
                 ("4", 70, {"pid": str(os.getpid())}), ("5", 70, {}))
    a.bajar()
    assert p.vol == {"1": 70, "2": 70, "3": 70, "4": 70, "5": 14}


def test_si_tocas_el_volumen_en_medio_no_se_pisa(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}))
    a.bajar()
    p.vol["5"] = 55                                     # el usuario lo ha movido a mano
    a.subir()
    assert p.vol["5"] == 55


def test_un_programa_que_se_cierra_no_da_error(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}), ("6", 60, {}))
    a.bajar()
    del p.vol["5"]
    assert a.subir() == 1 and p.vol == {"6": 60}


def test_dos_duenos_se_devuelve_cuando_acaba_el_ultimo(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}))
    a.bajar("atajo"); a.bajar("manos libres")
    assert a.subir("atajo") == 0 and p.vol["5"] == 16
    assert a.subir("manos libres") == 1 and p.vol["5"] == 80


def test_bajar_dos_veces_no_baja_dos_veces(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}))
    a.bajar(); a.bajar()
    a.subir()
    assert p.vol["5"] == 80


def test_si_lina_se_cierra_a_medias_se_devuelve_al_arrancar(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}))
    a.bajar()
    nuevo = AT.Atenuador(ejecutar=p, archivo=tmp_path / "bajado.json", log=lambda m: None)
    assert nuevo.recuperar() == 1 and p.vol["5"] == 80 and not (tmp_path / "bajado.json").exists()


def test_el_temporizador_lo_devuelve_si_la_escucha_se_alarga(tmp_path):
    p = Pactl(("5", 80, {}))
    a = AT.Atenuador(ejecutar=p, archivo=tmp_path / "b.json", log=lambda m: None, segundos=0.2)
    a.bajar()
    import time; time.sleep(0.8)
    assert p.vol["5"] == 80


def test_sin_pactl_no_pasa_nada(tmp_path):
    a = AT.Atenuador(ejecutar=lambda *x, **k: "", archivo=tmp_path / "b.json", log=lambda m: None)
    assert a.bajar() == 0 and a.subir() == 0


def test_nivel_cero_lo_deja_en_silencio_y_vuelve(tmp_path):
    p, a = hacer(tmp_path, ("5", 80, {}), nivel=0)
    a.bajar()
    assert p.vol["5"] == 0
    a.subir()
    assert p.vol["5"] == 80


def test_manos_libres_baja_al_oir_el_nombre_y_devuelve_con_la_orden():
    from lina.voz import manos_libres as ML
    hechos = []

    class Falso:
        def _bajar_sonido(self, dueno="atajo"): hechos.append(("baja", dueno))
        def _subir_sonido(self, dueno="atajo"): hechos.append(("sube", dueno))
    ml = ML.ManosLibres.__new__(ML.ManosLibres)
    ml.a, ml.modo = Falso(), None
    ml._sonido_en_espera_de_orden(); ml._sonido_en_espera_de_orden()
    assert hechos == []
    ml.modo = "orden"
    ml._sonido_en_espera_de_orden(); ml._sonido_en_espera_de_orden()
    assert hechos == [("baja", "manos libres")]
    ml.modo = None
    ml._sonido_en_espera_de_orden()
    assert hechos == [("baja", "manos libres"), ("sube", "manos libres")]
