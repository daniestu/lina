# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
"""El paquete del AUR y los documentos de publicación: comprobaciones baratas para que no se desincronicen (sin makepkg ni red)."""
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AUR = RAIZ / "packaging" / "aur"


def test_el_pkgbuild_tiene_sintaxis_valida_y_lo_imprescindible():
    ruta = AUR / "PKGBUILD"
    assert subprocess.run(["bash", "-n", str(ruta)], capture_output=True).returncode == 0
    texto = ruta.read_text(encoding="utf-8")
    for imprescindible in ("pkgname=lina-asistente", "license=('AGPL-3.0-or-later')", "portaudio", "libnotify", "usr/bin/lina-instalar", "install.sh",
                           "LICENSE", "install=lina-asistente.install"):
        assert imprescindible in texto, imprescindible
    assert (AUR / "lina-asistente.install").is_file() and (RAIZ / "install.sh").is_file()


def test_el_pkgbuild_apunta_al_repositorio_del_proyecto():
    texto = (AUR / "PKGBUILD").read_text(encoding="utf-8")
    assert "github.com/daniestu/lina" in texto


def test_los_documentos_nuevos_estan_enlazados_desde_el_readme():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    for doc in ("docs/uso.md", "docs/publicacion.md", "docs/idiomas.md", "docs/proveedores-ia.md"):
        assert doc in readme and (RAIZ / doc).is_file(), doc


def test_la_licencia_es_la_agpl_y_todos_los_archivos_llevan_su_cabecera():
    texto = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    assert texto.startswith("GNU AFFERO GENERAL PUBLIC LICENSE") and "Version 3, 19 November 2007" in texto
    assert 'license = { text = "AGPL-3.0-or-later" }' in (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    sin_cabecera = [str(p.relative_to(RAIZ)) for carpeta in ("src", "tests") for p in (RAIZ / carpeta).rglob("*.py")
                    if "SPDX-License-Identifier: AGPL-3.0-or-later" not in p.read_text(encoding="utf-8")[:300]]
    assert sin_cabecera == []
