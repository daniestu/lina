"""Guardar claves de servidores MCP sin escribirlas en pantalla ni dictarlas por voz:  lina clave NOMBRE"""
import getpass
import os
import re
import sys

from lina.nucleo import rutas as RUT


def guardar(nombre, valor):
    """Añade (o sustituye) NOMBRE=valor en mcp_claves.env, con permisos 600."""
    ruta = RUT.asegurar(RUT.CONFIG) / "mcp_claves.env"
    lineas = []
    try:
        lineas = [l for l in ruta.read_text(encoding="utf-8").splitlines() if not l.startswith(nombre + "=")]
    except OSError:
        pass
    lineas.append(f"{nombre}={valor}")
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    os.chmod(ruta, 0o600)
    return ruta


def principal(argv):
    if len(argv) != 1 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", argv[0]):
        print("Uso:  lina clave NOMBRE_DE_LA_CLAVE   (por ejemplo GITHUB_TOKEN)")
        return 2
    nombre = argv[0]
    valor = getpass.getpass(f"Pega aquí {nombre} (no se ve al escribir): ").strip()
    if not valor or "\n" in valor:
        print("No has escrito nada; no se ha guardado.")
        return 1
    guardar(nombre, valor)
    print(f"Guardada {nombre}. Ya puedes decirle a Lina que continúe.")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
