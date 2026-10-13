#!/usr/bin/env python3
"""Deja listo el navegador del asistente (Playwright + Chromium) de una vez, sin hablarle de comandos.
Uso:  python -m lina.mcp.navegador
Instala Chromium si falta (te pedirá la contraseña), quita los servidores de navegador anteriores y añade el bueno."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from lina.nucleo import rutas as RUT

CONFIG = Path(os.environ.get("MCP_CONFIG_PRUEBA") or RUT.CONFIG / "mcp.json")
CHROMIUM = shutil.which("chromium") or "/usr/bin/chromium"

if not Path(CHROMIUM).exists():
    if os.environ.get("SIN_INSTALAR_PRUEBA"):
        sys.exit("(prueba) falta chromium")
    print("Instalando Chromium (pide tu contraseña)...")
    if subprocess.run(["sudo", "pacman", "-S", "--needed", "--noconfirm", "chromium"]).returncode != 0:
        sys.exit("No he podido instalar Chromium. Instálalo a mano (sudo pacman -S chromium) y vuelve a ejecutar esto.")
    CHROMIUM = shutil.which("chromium") or "/usr/bin/chromium"
if not shutil.which("npx"):
    sys.exit("Falta Node.js: sudo pacman -S nodejs npm   y vuelve a ejecutar esto.")

try:
    datos = json.loads(CONFIG.read_text(encoding="utf-8"))
except (OSError, ValueError):
    datos = {}
servidores = datos.setdefault("mcpServers", {})
if CONFIG.exists():
    shutil.copy2(CONFIG, CONFIG.with_name(CONFIG.name + ".copia"))
for viejo in ("browser", "navegador"):
    servidores.pop(viejo, None)
servidores["navegador"] = {
    "command": "npx",
    "args": ["-y", "@playwright/mcp@latest", "--browser", "chromium", "--executable-path", CHROMIUM, "--headless"],
    "palabras": ["navegador", "navegador real"],
    "descripcion": "navegador real (Playwright, Microsoft) para abrir y leer páginas que bloquean a los programas",
}
CONFIG.parent.mkdir(parents=True, exist_ok=True)
CONFIG.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Listo: navegador configurado con {CHROMIUM}.")
print("Reinicia el asistente:  systemctl --user restart lina")
print("La primera vez que lo uses tardará unos segundos en arrancar. Se te pedirá confirmación al usarlo, como siempre.")
