import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Las pruebas son de Arch salvo que digan otra cosa (así dan lo mismo en el equipo de cada uno y en la CI, que es Ubuntu).
# Las que prueban otra familia la fijan con monkeypatch.setenv("LINA_DISTRO", ...).
import os  # noqa: E402

os.environ.setdefault("LINA_DISTRO", "arch")
