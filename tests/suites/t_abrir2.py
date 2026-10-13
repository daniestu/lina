import sys, tempfile, pathlib
from lina.nucleo import comandos as C; from lina.nucleo import herramientas as H
d = pathlib.Path(tempfile.mkdtemp())
def ap(stem, name, exe, extra=""):
    (d/f"{stem}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec={exe} %U\n{extra}")
ap("com.anthropic.Claude", "Claude", "/usr/bin/claude-desktop")
ap("claude-code", "Claude Code", "claude-code")
ap("org.kde.konsole", "Konsole", "konsole")
ap("kate", "Kate", "kate"); ap("kwrite", "KWrite", "kwrite")
ap("htop", "Htop", "htop", "Terminal=true\n")
ap("org.fp.App", "Flatty", "/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=flatty org.fp.App @@u %U @@")
C.DIRS_APPS = lambda: [d]; C._cache_apps["firma"] = None
e = H.Ejecutor.__new__(H.Ejecutor)
lanzados = []
e.herramienta = lambda a: (lanzados.append(a["comando"]) or "Lanzado.")
f = 0
def ok(c, m):
    global f
    print(("OK  " if c else "FALLA ") + m); f += (not c)
r = e.abrir_app("Claude"); ok(r.startswith("Abierto «Claude»") and lanzados[-1] == "/usr/bin/claude-desktop", r)
r = e.abrir_app("la consola"); ok("Abierto «Konsole»" in r and "entendí" in r and lanzados[-1] == "konsole", r)
n = len(lanzados); r = e.abrir_app("whatsapp"); ok("No hay ningún programa INSTALADO" in r and len(lanzados) == n, r[:80])
n = len(lanzados); r = e.abrir_app("k"); ok(len(lanzados) == n, r[:80])
r = e.abrir_app("Flatty"); ok(lanzados[-1] == "flatpak run org.fp.App", lanzados[-1])
n = len(lanzados); r = e.abrir_app("htop"); ok("terminal" in r and len(lanzados) == n, r)
r = e.abrir_app("org.kde.konsole"); ok("Konsole" in r and lanzados[-1] == "konsole", r)
e.herramienta = lambda a: "BLOQUEADO: no"
r = e.abrir_app("kate"); ok(r.startswith("Intenté abrir") and "BLOQUEADO" in r, r)
r = e.abrir_app(""); ok("Falta" in r, r)
print("fallos", f)
