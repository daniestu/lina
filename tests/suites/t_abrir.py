import sys, os, tempfile, pathlib
from lina.nucleo import comandos as C
d = pathlib.Path(tempfile.mkdtemp())
def ap(stem, name, exe, extra=""):
    (d/f"{stem}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec={exe} %U\n{extra}")
ap("com.anthropic.Claude", "Claude", "/usr/bin/claude-desktop")
ap("org.kde.konsole", "Konsole", "konsole", "GenericName[es]=Terminal\nKeywords=terminal;consola;shell\n")
ap("firefox", "Firefox", "firefox")
ap("code", "Visual Studio Code", "code")
ap("kate", "Kate", "kate")
ap("kwrite", "KWrite", "kwrite")
ap("org.foo.Edit", "Editor de texto", "edit")
ap("steam", "Steam", "/usr/bin/steam")
C.DIRS_APPS = lambda: [d]
C._cache_apps["firma"] = None
n = lambda q: [(p, a["nombre"]) for p, a in C.buscar_app(q)]
fallos = 0
def ok(c, m):
    global fallos
    print(("OK  " if c else "FALLA ") + m)
    fallos += (not c)
ok(n("Claude")[0] == (100, "Claude"), "exacto Claude")
ok(n("abre Claude")[0][1] == "Claude", "con verbo")
ok(n("claude desktop")[0][1] == "Claude", "claude desktop")
ok(n("consola")[0][1] == "Konsole", f"consola -> Konsole {n('consola')}")
ok(n("terminal")[0][1] == "Konsole", f"terminal por generico {n('terminal')}")
ok(n("code")[0][1] == "Visual Studio Code" and n("code")[0][0] == 88, f"code {n('code')}")
ok(n("cait")[0][1] == "Kate" if n("cait") else False, f"cait~Kate {n('cait')}")
ok(n("whatsapp") == [], f"whatsapp inexistente {n('whatsapp')}")
ok(n("") == [] and n("abre el") == [], "vacío")
ok(n("blender") == [], f"blender {n('blender')}")
# ambiguo
ok(len(n("edit")) >= 1, f"id edit {n('edit')}")
print("fallos", fallos)
