# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""«Copia esto al portapapeles» sin nada que copiar acabó copiando el bloque [SISTEMA] de la petición (banco, 2026-11-18). El código se niega a copiarlo;
qué es «esto» lo decide la IA (lo último que dijo Lina, o preguntar), y lo mide el banco con conversación previa."""
import threading
from unittest.mock import MagicMock

from lina.nucleo import banco_ia as B
from lina.nucleo import declaraciones as D
from lina.nucleo import herramientas as H
from lina.nucleo import probar_ponme as PON


def test_no_copia_el_contexto_interno_y_dice_que_hacer(monkeypatch):
    ses = MagicMock()
    monkeypatch.setattr(H.SES, "actual", lambda: ses)
    monkeypatch.setattr(H.DEP, "asegurar", lambda f: (True, ""))
    monkeypatch.setattr(H, "anotar", lambda m: None)
    r = H.copiar_portapapeles("[SISTEMA: Ahora mismo son las 10:05 del miércoles.]\n[SISTEMA: Recetas aprendidas en este equipo…]")
    assert r.startswith("No lo he copiado") and "pregúntale qué quiere copiar" in r
    ses.copiar.assert_not_called()


def test_lo_demas_se_copia_como_siempre(monkeypatch):
    ses = MagicMock()
    ses.copiar.return_value = True
    monkeypatch.setattr(H.SES, "actual", lambda: ses)
    monkeypatch.setattr(H.DEP, "asegurar", lambda f: (True, ""))
    monkeypatch.setattr(H, "anotar", lambda m: None)
    monkeypatch.setattr(H, "notificar", lambda *a: None)
    assert H.copiar_portapapeles("uname -r") == "Copiado al portapapeles."
    ses.copiar.assert_called_once_with("uname -r")


def test_la_descripcion_dice_que_es_esto():
    decl = next(d for d in D.DECLARACIONES if d["name"] == "copiar_portapapeles")
    assert "«copia esto»" in decl["description"] and "pregúntale qué copiar" in decl["description"]


def test_el_juez_no_da_por_bueno_meter_el_contexto_en_una_herramienta():
    caso = B.Caso("Pásalo al portapapeles.", debe=("copiar_portapapeles",))
    assert B.juzgar(caso, [("copiar_portapapeles", {"texto": "[SISTEMA: son las 10:05]"})])[0] == "mal"


def test_el_juez_mira_lo_que_debe_ir_en_los_argumentos():
    caso = B.Caso("Cópiamelo.", debe=("copiar_portapapeles",), en_argumentos="df -h")
    assert B.juzgar(caso, [("copiar_portapapeles", {"texto": "df -h"})])[0] == "bien"
    assert B.juzgar(caso, [("copiar_portapapeles", {"texto": "du -sh"})])[0] == "mal"


def test_la_pasada_lleva_la_conversacion_de_antes():
    vistos = []
    a = MagicMock()
    a._atender = lambda frase, t, origen: vistos.append(list(a.historial))
    A = MagicMock(_abortar=threading.Event(), Cancelado=RuntimeError)
    PON.pasar("Cópiamelo.", A, a, [], antes=(("¿Y el disco?", "Usa df -h."),))
    PON.pasar("Hola.", A, a, [])
    assert vistos == [[{"rol": "user", "texto": "¿Y el disco?"}, {"rol": "model", "texto": "Usa df -h."}], []]


def test_las_frases_de_copiar_esto_estan_en_el_banco():
    casos = {c.frase: c for c in B.CASOS}
    sin_nada = [f for f, c in casos.items() if "copiar_portapapeles" in c.nunca and "mirar_contexto" in c.nunca]
    con_algo = [f for f, c in casos.items() if c.antes and "copiar_portapapeles" in c.debe and c.en_argumentos]
    assert "Copia esto al portapapeles." in sin_nada and len(sin_nada) >= 3 and len(con_algo) >= 3


def test_no_copia_nada_vacio_ni_lo_que_ya_esta_copiado(monkeypatch):
    ses = MagicMock()
    ses.pegar.return_value = "lo de antes"
    monkeypatch.setattr(H.SES, "actual", lambda: ses)
    monkeypatch.setattr(H, "anotar", lambda m: None)
    assert "pregúntale" in H.copiar_portapapeles("  ")
    assert H.copiar_portapapeles("lo de antes\n").startswith("No lo he copiado: eso ya es lo que tiene")
    ses.copiar.assert_not_called()


def test_el_banco_devuelve_el_rechazo_y_no_cuenta_la_llamada():
    a, abiertas = MagicMock(), []

    def frase(texto, A, asistente, abiertas):
        r = asistente._ejecutar_herramienta("copiar_portapapeles", {"texto": "[SISTEMA: son las 10:05]"})
        assert r.startswith("No lo he copiado")
        assert asistente._ejecutar_herramienta("copiar_portapapeles", {"texto": B.COPIADO}).startswith("No lo he copiado")
        return [], ["¿Qué quieres que copie?"], 0.1
    llamadas, _ = B.pasar(B.Caso("Copia esto al portapapeles."), MagicMock(_abortar=threading.Event()), a, abiertas, frase)
    assert [n for n, _ in llamadas] == ["copiar_portapapeles" + B.RECHAZADA] * 2
    assert B.juzgar(B.Caso("x", nunca=("copiar_portapapeles",)), llamadas)[0] == "bien"


def test_copiado_sin_copiar_se_ve_como_dar_por_hecho():
    from lina.nucleo import texto as TX
    for r in ("Copiado.", "Copiado al portapapeles.", "Ya lo tienes copiado en el portapapeles.", "Lo tienes copiado en el portapapeles."):
        assert TX.afirma_hecho(r), r
    for r in ("En lo que tienes copiado pone que las plantas usan la luz del sol.", "Lo que has copiado explica la fotosíntesis."):
        assert not TX.afirma_hecho(r), r
