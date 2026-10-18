# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Las pruebas son de Arch salvo que digan otra cosa (así dan lo mismo en el equipo de cada uno y en la CI, que es Ubuntu).
# Las que prueban otra familia la fijan con monkeypatch.setenv("LINA_DISTRO", ...).
import os  # noqa: E402

os.environ.setdefault("LINA_DISTRO", "arch")
# Y de KDE Plasma con Wayland, que es para lo que están escritas las pruebas de ventanas (las de otros escritorios pasan su propio entorno).
os.environ.setdefault("XDG_CURRENT_DESKTOP", "KDE")
os.environ.setdefault("XDG_SESSION_TYPE", "wayland")
