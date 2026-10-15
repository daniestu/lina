"""El instalador que corre como administrador, probado contra una raíz falsa (una carpeta temporal): nunca toca el sistema real."""
import hashlib
import os
import subprocess

import pytest

from lina.nucleo import raiz as R

AYUDANTE = b"#!/usr/bin/python3 -I\nprint('hola')\n"


def datos(accion="instalar", usuario="dani", ayudante=AYUDANTE, sha=None):
    return {"accion": accion, "usuario": usuario, "ayudante": ayudante.decode(), "sha256": sha or hashlib.sha256(ayudante).hexdigest()}


def falsa(tmp_path):
    (tmp_path / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (tmp_path / "usr" / "bin" / "python3").write_text("")
    return str(tmp_path)


def bien(ruta):
    return None


def aplicar(tmp_path, d, **kw):
    kw.setdefault("validar_sudoers", lambda temporal: None)
    kw.setdefault("existe_usuario", lambda u: True)
    return R.aplicar(d, raiz=falsa(tmp_path), estricto=False, **kw)


def leer(tmp_path, ruta):
    return (tmp_path / ruta.lstrip("/")).read_bytes()


def test_instalar_deja_ayudante_y_regla_minima(tmp_path):
    aplicar(tmp_path, datos())
    assert leer(tmp_path, R.AYUDANTE) == AYUDANTE
    assert oct((tmp_path / R.AYUDANTE.lstrip("/")).stat().st_mode & 0o777) == "0o755"
    regla = leer(tmp_path, R.SUDOERS_INSTALAR).decode()
    assert f"dani ALL=(root) NOPASSWD: {R.AYUDANTE} instalar *" in regla and "ALL=(root) NOPASSWD: ALL" not in regla
    assert oct((tmp_path / R.SUDOERS_INSTALAR.lstrip("/")).stat().st_mode & 0o777) == "0o440"
    assert b"org.lina.instalar" in leer(tmp_path, R.POLKIT)
    assert not (tmp_path / "etc" / "sudoers.d" / "lina-total").exists()
    assert not [p for p in (tmp_path / "etc" / "sudoers.d").iterdir() if p.name.endswith(".nuevo")]


def test_nivel_total_añade_la_regla_amplia(tmp_path):
    aplicar(tmp_path, datos("total"))
    assert "dani ALL=(root) NOPASSWD: ALL" in leer(tmp_path, R.SUDOERS_TOTAL).decode()


def test_quitar_lo_borra_todo_y_es_repetible(tmp_path):
    aplicar(tmp_path, datos("total"))
    informe = aplicar(tmp_path, {"accion": "quitar"})
    assert all((tmp_path / r.lstrip("/")).exists() is False for r in (R.AYUDANTE, R.SUDOERS_INSTALAR, R.SUDOERS_TOTAL, R.POLKIT))
    assert not (tmp_path / R.DIR_AYUDANTE.lstrip("/")).exists()
    assert len(informe) == 4 and aplicar(tmp_path, {"accion": "quitar"})[0].startswith("No estaba")


@pytest.mark.parametrize("usuario", ["", "Root Admin", "dani; rm -rf /", "dani\nroot ALL=(ALL) ALL", "a" * 40, "-x", "dani ALL=(ALL) NOPASSWD: ALL #"])
def test_usuario_con_trucos_se_rechaza(tmp_path, usuario):
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, datos(usuario=usuario))
    assert not (tmp_path / "etc").exists()


def test_usuario_inexistente_o_de_sistema(tmp_path):
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, datos(), existe_usuario=lambda u: False)
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, datos(usuario="nadie_existe_zz"), existe_usuario=None)


def test_el_ayudante_debe_ser_el_que_se_enseno(tmp_path):
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, datos(sha="0" * 64))
    otro = b"#!/usr/bin/python3 -I\nimport os; os.system('id')\n"
    d = datos()
    d["ayudante"] = otro.decode()                              # contenido cambiado después de enseñar el resumen
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, d)
    assert not (tmp_path / "usr" / "lib").exists()


def test_ayudante_con_otra_primera_linea_o_enorme(tmp_path):
    for malo in (b"#!/bin/sh\nid\n", b"print(1)\n", b"#!/usr/bin/python3 -I\n" + b"x" * 30000):
        with pytest.raises(R.Fallo):
            aplicar(tmp_path, datos(ayudante=malo))


def test_si_visudo_rechaza_no_queda_nada_activo(tmp_path):
    def rechaza(temporal):
        raise R.Fallo("visudo no da por buena la regla")
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, datos(), validar_sudoers=rechaza)
    assert not (tmp_path / R.SUDOERS_INSTALAR.lstrip("/")).exists()
    assert not [p for p in (tmp_path / "etc" / "sudoers.d").iterdir()]


def test_validacion_real_con_visudo_si_existe(tmp_path):
    if not os.path.exists("/usr/sbin/visudo"):
        return
    temporal = tmp_path / "regla"
    temporal.write_text(R.sudoers_instalar("dani"))
    R._validar_sudoers(str(temporal))
    temporal.write_text("dani ALL=(root) NOPASSWD: /x instalar *\nesto no es sudoers {{\n")
    with pytest.raises(R.Fallo):
        R._validar_sudoers(str(temporal))


def test_carpeta_ajena_o_enlace_se_rechazan(tmp_path):
    raiz = falsa(tmp_path)
    destino = tmp_path / "otro"
    destino.mkdir()
    (tmp_path / "usr" / "lib").symlink_to(destino)               # alguien cambió /usr/lib por un enlace
    with pytest.raises(R.Fallo):
        R.aplicar(datos(), raiz=raiz, estricto=False, validar_sudoers=lambda t: None, existe_usuario=lambda u: True)
    assert not list(destino.iterdir())


def test_acciones_desconocidas(tmp_path):
    with pytest.raises(R.Fallo):
        aplicar(tmp_path, {"accion": "ejecutar", "orden": "id"})


def test_solo_biblioteca_estandar():
    import ast
    fuente = open(R.__file__, encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(fuente)):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"hashlib", "json", "os", "pwd", "re", "subprocess", "sys"}, mods
