# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, os, json, sqlite3, tempfile, pathlib
from lina.modulos import juegos as J
H = pathlib.Path(tempfile.mkdtemp()); J._HOME = H
fallos = 0
def ok(c, m):
    global fallos
    print(("OK  " if c else "FALLA ") + m); fallos += (not c)
# Steam
sa = H/".local/share/Steam/steamapps"; (sa/"common/Skyrim Special Edition").mkdir(parents=True)
otra = H/"disco2/SteamLibrary/steamapps"; (otra/"common/Sifu").mkdir(parents=True)
(sa/"libraryfolders.vdf").write_text('"libraryfolders" { "0" { "path" "%s" } "1" { "path" "%s" } }' % (H/".local/share/Steam", H/"disco2/SteamLibrary"))
def acf(d, appid, name, inst, flags=4, last=0):
    (d/f"appmanifest_{appid}.acf").write_text(f'"AppState"\n{{\n"appid" "{appid}"\n"name" "{name}"\n"installdir" "{inst}"\n"StateFlags" "{flags}"\n"LastPlayed" "{last}"\n}}')
acf(sa, 489830, "The Elder Scrolls V: Skyrim Special Edition", "Skyrim Special Edition", last=1700000000)
acf(sa, 611670, "The Elder Scrolls V: Skyrim VR", "Skyrim VR", last=1600000000)
acf(otra, 2138710, "Sifu", "Sifu", last=1650000000)
acf(sa, 1493710, "Proton Experimental", "Proton - Experimental")
acf(sa, 99, "Medio descargado", "x", flags=1026)
# Heroic
hb = H/".config/heroic"; (hb/"legendaryConfig/legendary").mkdir(parents=True); (hb/"store_cache").mkdir(parents=True); (hb/"gog_store").mkdir(parents=True)
(hb/"legendaryConfig/legendary/installed.json").write_text(json.dumps({"Fortnite": {"app_name": "Fortnite", "title": "Fortnite", "install_path": "/games/Fortnite"}}))
(hb/"gog_store/installed.json").write_text(json.dumps({"installed": [{"appName": "1207658924", "install_path": "/games/witcher3", "platform": "windows"}]}))
(hb/"store_cache/gog_library.json").write_text(json.dumps({"games": [{"app_name": "1207658924", "title": "The Witcher 3: Wild Hunt", "is_installed": True}, {"app_name": "555", "title": "No instalado", "is_installed": False}]}))
# Lutris
(H/".local/share/lutris").mkdir(parents=True)
con = sqlite3.connect(H/".local/share/lutris/pga.db"); con.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, directory TEXT, lastplayed INTEGER, installed INTEGER)")
con.executemany("INSERT INTO games VALUES (?,?,?,?,?)", [(7, "Hades", "/home/x/Games/hades", 1690000000, 1), (8, "Borrado", "/x", 0, 0)]); con.commit(); con.close()
J._cache["t"] = 0
b = J.biblioteca(); nombres = {j["nombre"] for j in b}
ok({"Sifu", "Fortnite", "The Witcher 3: Wild Hunt", "Hades"} <= nombres, str(sorted(nombres)))
ok(not any("Proton" in n or "Medio" in n or "No instalado" in n or "Borrado" in n for n in nombres), "sin herramientas ni no instalados")
r = J.buscar("Skyrim"); ok(len(r) == 2 and r[0][1]["id"] == "489830", f"skyrim -> el más jugado primero {[(p, j['nombre']) for p, j in r]}")
r = J.buscar("abre Sifu"); ok(r and r[0][0] == 100 and r[0][1]["nombre"] == "Sifu", str(r[:1]))
r = J.buscar("el Witcher 3"); ok(r and r[0][1]["origen"] == "heroic", str(r[:1]))
r = J.buscar("witcher tres"); ok(True, "(tres no es 3: ok si no encuentra) " + str(bool(r)))
r = J.buscar("Ades"); ok(r and r[0][1]["nombre"] == "Hades", f"suena parecido {r[:1]}")
r = J.buscar("fortnait"); ok(r and r[0][1]["nombre"] == "Fortnite", f"fortnait {r[:1]}")
ok(J.buscar("Minecraft") == [], "inexistente")
os.environ["PATH"] = "/nonexistent"
import shutil; shutil.which = lambda x: "/usr/bin/" + x if x in ("steam", "lutris", "heroic") else None
cmds = {j["nombre"]: J.comando_de_lanzamiento(j) for j in b}
ok(cmds["Sifu"] == "steam steam://rungameid/2138710", cmds["Sifu"])
ok(cmds["Hades"] == "lutris lutris:rungameid/7", cmds["Hades"])
ok(cmds["Fortnite"] == "heroic heroic://launch/legendary/Fortnite", cmds["Fortnite"])
ok(J.comando_de_lanzamiento({"origen": "steam", "id": "1; rm -rf ~"}) is None, "id con inyección rechazado")
ok(J.comando_de_lanzamiento({"origen": "heroic", "runner": "gog", "id": "a b"}) is None, "id con espacio rechazado")
w = J.nombres_para_whisper(); ok(w[0] == "Skyrim Special Edition" and "Sifu" in w, str(w))
# /proc falso
P = pathlib.Path(tempfile.mkdtemp())
def proc(pid, ppid, cmd, env="", cwd=None):
    d = P/str(pid); d.mkdir(); (d/"cmdline").write_bytes(cmd.replace(" ", "\0").encode()); (d/"stat").write_text(f"{pid} (x y) S {ppid} 1 1")
    (d/"environ").write_bytes(env.encode())
    if cwd: os.symlink(cwd, d/"cwd")
proc(100, 1, "systemd"); proc(200, 100, "lutris-wrapper: Hades"); proc(300, 200, "wine hades.exe")
ok(J.juego_de_proceso(300, str(P), b) == {"nombre": "Hades", "origen": "lutris"}, str(J.juego_de_proceso(300, str(P), b)))
proc(400, 100, "reaper SteamLaunch AppId=2138710 -- proton waitforexitandrun"); proc(500, 400, "Sifu-Win64-Shipping.exe")
ok(J.juego_de_proceso(500, str(P), b)["nombre"] == "Sifu", "steam por AppId del padre")
proc(600, 100, "wine x.exe", env="FOO=1\0SteamGameId=489830\0")
ok(J.juego_de_proceso(600, str(P), b)["nombre"].startswith("The Elder Scrolls V: Skyrim Special"), "steam por entorno")
os.makedirs("/tmp/xx_games/witcher3", exist_ok=True)
proc(700, 100, "wine witcher3.exe", cwd="/games/witcher3/bin/x64")
ok(J.juego_de_proceso(700, str(P), b)["nombre"] == "The Witcher 3: Wild Hunt", "heroic por la carpeta del juego")
proc(800, 100, "firefox"); ok(J.juego_de_proceso(800, str(P), b) is None, "firefox no es un juego")
ok(J.juego_de_proceso(0, str(P), b) is None and J.juego_de_proceso("x", str(P), b) is None, "pid inválido")
print("fallos", fallos)
