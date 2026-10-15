"""La clasificación de comandos (nucleo/clasificador.py y clasificar() de herramientas.py)."""
from lina.nucleo import herramientas as H


def test_abrir_un_programa_conocido_con_un_enlace_se_clasifica_como_lanzar():
    # Antes de la fase 6 una segunda función con el mismo nombre tapaba a la buena y esta clase nunca se alcanzaba.
    assert H.clasificar("firefox https://example.com")[0] == "lanzar"
    assert H.clasificar("xdg-open https://example.com")[0] == "lanzar"


def test_lanzar_no_se_cuela_con_argumentos_raros():
    assert H.clasificar("firefox https://example.com; rm -rf ~")[0] != "lanzar"
    assert H.clasificar("firefox --no-remote https://example.com")[0] != "lanzar"
    assert H.clasificar("programa-que-no-existe-xyz https://example.com")[0] != "lanzar"


def test_el_motivo_de_abrir_se_reconoce_sin_acentos():
    assert H._motivo_es_abrir("Abrir Firefox")
    assert H._motivo_es_abrir("lanza steam")
    assert not H._motivo_es_abrir("limpiar la caché")
