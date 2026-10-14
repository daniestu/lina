from lina.nucleo import herramientas as H
from lina.nucleo.turnos import es_seguimiento, peticion_de_receta, solo_herramientas_meta


def test_solo_herramientas_meta():
    assert solo_herramientas_meta([("mas_herramientas", {}, "Cargado")])
    assert solo_herramientas_meta([("mas_herramientas", {}, "a"), ("pensar_a_fondo", {}, "b")])
    assert not solo_herramientas_meta([])
    assert not solo_herramientas_meta([("mas_herramientas", {}, "a"), ("ejecutar_comando", {}, "b")])


def test_seguimientos_no_son_peticiones():
    for frase in ("No lo has hecho", "Ahora sí, gracias", "Has guardado la receta", "Sigue igual", "Vale"):
        assert es_seguimiento(frase), frase
    for frase in ("Pon las pantallas para que estén extendidas", "Abre el navegador", "Sube el volumen al treinta por ciento",
                  "No quiero que se duplique la pantalla cuando conecto el proyector del salón"):
        assert not es_seguimiento(frase), frase


def test_la_receta_cuenta_la_peticion_original():
    historial = [{"rol": "user", "texto": "Pon las pantallas para que estén extendidas"}, {"rol": "model", "texto": "Hecho"},
                 {"rol": "user", "texto": "Me refiero a que se vea una cosa en una pantalla y otra en la otra, que no estén duplicadas"},
                 {"rol": "model", "texto": "Ya"}]
    assert peticion_de_receta(historial, "No lo has hecho").startswith("Me refiero a que se vea")
    assert peticion_de_receta(historial, "Pon el brillo al cincuenta") == "Pon el brillo al cincuenta"
    assert peticion_de_receta([], "No lo has hecho") == "No lo has hecho"          # sin nada anterior, se queda lo que hay


def test_abrir_un_programa_no_es_una_tarea_que_termine():
    for motivo in ("abrir Firefox", "Abre el navegador", "lanzar Steam", "iniciar el editor", "Abrir Dolphin (entendí «dolfin»)"):
        assert H._es_lanzamiento(motivo), motivo
    for motivo in ("actualizar el sistema", "copiar la carpeta de fotos", "descargar el archivo", "tarea", "cerrar Firefox", ""):
        assert not H._es_lanzamiento(motivo), motivo
