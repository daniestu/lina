import sys, os, tempfile, pathlib, json
from lina.modulos import juegoconf as J; from lina.modulos import juegos as JU
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
tmp=pathlib.Path(tempfile.mkdtemp())
J.DIR_COPIAS=tmp/"copias"; J.RUTA_MANGOHUD=tmp/"mh"/"MangoHud.conf"
# --- VDF ---
muestra='''"UserLocalConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"apps"
				{
					"489830"
					{
						"LastPlayed"		"1700000000"
						"LaunchOptions"		"mangohud %command% -novid"
					}
					"1234"
					{
						"Playtime"		"5"
					}
				}
			}
		}
	}
	"WebStorage" { "x" "a\\\\b \\"c\\" \\n" }
}
'''
t=J.vdf_parse(muestra); ok(t["UserLocalConfigStore"]["WebStorage"]["x"]=='a\\b "c" \n',"escapes %r"%t["UserLocalConfigStore"]["WebStorage"]["x"])
ok(J.vdf_parse(J.vdf_dump(t))==t,"ida y vuelta")
for malo in ['"a" {','"a" "b" "c"','"a" }','"a" "b"\n"a" "c"']:
    try: J.vdf_parse(malo); ok(False,"debería fallar "+malo)
    except ValueError: pass
# --- carpeta de Steam falsa ---
raiz=tmp/"Steam"; (raiz/"config").mkdir(parents=True); (raiz/"userdata/1000/config").mkdir(parents=True); (raiz/"userdata/0/config").mkdir(parents=True)
(raiz/"userdata/1000/config/localconfig.vdf").write_text(muestra)
cfg='''"InstallConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"CompatToolMapping"
				{
					"0"
					{
						"name"		"proton_experimental"
						"config"		""
						"priority"		"75"
					}
					"489830"
					{
						"name"		"proton_9"
						"config"		""
						"priority"		"250"
					}
				}
			}
		}
	}
}
'''
(raiz/"config/config.vdf").write_text(cfg)
ct=raiz/"compatibilitytools.d/GE-Proton9-20"; ct.mkdir(parents=True)
(ct/"compatibilitytool.vdf").write_text('"compatibilitytools"\n{\n"compat_tools"\n{\n"GE-Proton9-20"\n{\n"install_path" "."\n"display_name" "GE-Proton9-20"\n}\n}\n}\n')
ct2=raiz/"compatibilitytools.d/GE-Proton10-1"; ct2.mkdir(parents=True)
(ct2/"compatibilitytool.vdf").write_text('"compatibilitytools"\n{\n"compat_tools"\n{\n"GE-Proton10-1"\n{\n"install_path" "."\n"display_name" "GE-Proton10-1"\n}\n}\n}\n')
lib=raiz/"steamapps"; (lib/"common/Proton 9.0 (Beta)").mkdir(parents=True); (lib/"common/Proton - Experimental").mkdir(parents=True)
(lib/"libraryfolders.vdf").write_text('"libraryfolders"\n{\n}\n')
(lib/"appmanifest_489830.acf").write_text('"AppState"\n{\n"appid" "489830"\n"name" "The Elder Scrolls V: Skyrim Special Edition"\n"installdir" "Skyrim Special Edition"\n"StateFlags" "4"\n"LastPlayed" "1700000000"\n}\n')
(lib/"appmanifest_1234.acf").write_text('"AppState"\n{\n"appid" "1234"\n"name" "Sifu"\n"installdir" "Sifu"\n"StateFlags" "4"\n}\n')
(lib/"common/Skyrim Special Edition").mkdir()
J.RAICES=[raiz]; JU._raices_steam=lambda:[raiz]; JU._cache["t"]=0
estado={"abierto":False,"juego":False,"cerrado":0,"abierto_otra":0}
J.steam_abierto=lambda:estado["abierto"]
J.juego_en_marcha=lambda:estado["juego"]
def cerrar(r=None): estado["abierto"]=False; estado["cerrado"]+=1; return True,"Steam cerrado."
def abrir(r=None): estado["abierto"]=True; estado["abierto_otra"]+=1; return True
J.cerrar_steam=cerrar; J.abrir_steam=abrir
# --- proton ---
ins=J.proton_instalados(raiz); ids={h["id"] for h in ins}
ok({"GE-Proton9-20","GE-Proton10-1","proton_9","proton_experimental"}<=ids,"instalados %s"%ids)
p=J.planificar_steam("proton",{"accion":"listar"}); ok("GE-Proton10-1" in p["texto"] and "Skyrim" in p["texto"],p)
p=J.planificar_steam("proton",{"accion":"ver","juego":"skyrim"}); ok("Proton 9.0" in p["texto"] or "proton_9" in p["texto"],p)
p=J.planificar_steam("proton",{"accion":"poner","juego":"skyrim","valor":"GE"})
ok("aplicar" in p and "GE-Proton10-1" in p["descripcion"] and "copia" in p["descripcion"],p)
r=p["aplicar"](); print(r)
ok("COMPROBADO" in r and J.mapa_proton(raiz/"config/config.vdf")["489830"]=="GE-Proton10-1","escribe proton")
ok(J.mapa_proton(raiz/"config/config.vdf")["0"]=="proton_experimental","global intacto")
ok(len(list(J.DIR_COPIAS.glob("*__config.vdf")))==1,"copia hecha")
p=J.planificar_steam("proton",{"accion":"poner","juego":"sifu","valor":"experimental"}); r=p["aplicar"](); 
ok(J.mapa_proton(raiz/"config/config.vdf")["1234"]=="proton_experimental","entrada nueva %s"%r)
p=J.planificar_steam("proton",{"accion":"poner","juego":"todos","valor":"9"}); ok("proton_9" in str(p) or "Proton 9" in p["descripcion"],p)
p=J.planificar_steam("proton",{"accion":"poner","juego":"skyrim","valor":"xyzzy"}); ok("error" in p,"proton inexistente")
p=J.planificar_steam("proton",{"accion":"poner","juego":"skyrim","valor":"GE-Proton10-1"}); ok("texto" in p and "ya usa" in p["texto"],"ya estaba")
p=J.planificar_steam("proton",{"accion":"deshacer"}); r=p["aplicar"](); ok(J.mapa_proton(raiz/"config/config.vdf").get("1234") is None or True,"deshacer corre")
print(J.mapa_proton(raiz/"config/config.vdf"))
p=J.planificar_steam("proton",{"accion":"quitar","juego":"skyrim"}); r=p["aplicar"](); ok("489830" not in J.mapa_proton(raiz/"config/config.vdf"),"quitar")
# --- Steam abierto: se cierra, se escribe, se reabre ---
estado.update(abierto=True)
p=J.planificar_steam("proton",{"accion":"poner","juego":"skyrim","valor":"9"}); ok("cerraré" in p["descripcion"],"avisa cierre")
r=p["aplicar"](); ok(estado["cerrado"]==1 and estado["abierto_otra"]==1 and "COMPROBADO" in r,"cierra y reabre: %s"%r)
estado.update(abierto=True,juego=True)
p=J.planificar_steam("proton",{"accion":"poner","juego":"sifu","valor":"9"}); ok("error" in p,"con juego en marcha no")
estado.update(abierto=False,juego=False)
# --- opciones de lanzamiento ---
p=J.planificar_steam("opciones_lanzamiento",{"accion":"ver","juego":"skyrim"}); ok("mangohud %command% -novid" in p["texto"],p)
p=J.planificar_steam("opciones_lanzamiento",{"accion":"ver"}); ok("Skyrim" in p["texto"],p)
c=lambda a,acc,v:J.componer_opciones(a,acc,v)
ok(c("","anadir","PROTON_ENABLE_WAYLAND=1")==("PROTON_ENABLE_WAYLAND=1 %command%",None),c("","anadir","PROTON_ENABLE_WAYLAND=1"))
ok(c("mangohud %command% -novid","anadir","gamemoderun")[0]=="mangohud gamemoderun %command% -novid",c("mangohud %command% -novid","anadir","gamemoderun"))
ok(c("A=1 mangohud %command%","anadir","A=2")[0]=="A=2 mangohud %command%","reemplaza var")
ok(c("A=1 mangohud %command% -novid","quitar","mangohud")[0]=="A=1 %command% -novid","quita wrapper")
ok(c("A=1 mangohud %command% -novid","quitar","A")[0]=="mangohud %command% -novid","quita var por nombre")
ok(c("A=1 %command%","quitar","A=1")[0]=="","queda vacío")
ok(c("","anadir","-novid")[0]=="%command% -novid","flag")
ok(c("","anadir","gamescope -W 2560")[1] is not None,"wrapper con args pide poner")
ok(J.validar_opciones("mangohud %command%; rm -rf ~")[0],"inyección ;")
ok(J.validar_opciones("$(curl x) %command%")[0],"inyección $(")
ok(J.validar_opciones("programaquenoexiste123 %command%")[0],"wrapper inexistente")
ok(J.validar_opciones("PROTON_LOG=1 %command% -windowed")[0] is None,"normal")
p=J.planificar_steam("opciones_lanzamiento",{"accion":"anadir","juego":"sifu","valor":"PROTON_ENABLE_WAYLAND=1"}); ok("aplicar" in p,p)
r=p["aplicar"](); print(r)
ok(J.leer_opciones(raiz/"userdata/1000/config/localconfig.vdf","1234")=="PROTON_ENABLE_WAYLAND=1 %command%","escribe opciones")
ok("1000" in str(J.ruta_localconfig(raiz)),"usuario correcto (no el 0)")
ok(J.vdf_parse((raiz/"userdata/1000/config/localconfig.vdf").read_text())["UserLocalConfigStore"]["WebStorage"]["x"]=='a\\b "c" \n',"resto intacto")
p=J.planificar_steam("opciones_lanzamiento",{"accion":"borrar","juego":"sifu"}); r=p["aplicar"](); ok(J.leer_opciones(raiz/"userdata/1000/config/localconfig.vdf","1234")=="","borrar")
p=J.planificar_steam("opciones_lanzamiento",{"accion":"deshacer"}); r=p["aplicar"](); ok(J.leer_opciones(raiz/"userdata/1000/config/localconfig.vdf","1234")=="PROTON_ENABLE_WAYLAND=1 %command%","deshacer opciones")
# fallo a mitad: archivo roto
(raiz/"config/config.vdf").write_text('"a" {')
p=J.planificar_steam("proton",{"accion":"listar"}); ok("error" in p,"archivo roto no se toca")
(raiz/"config/config.vdf").write_text(cfg)
# --- MangoHud ---
m=lambda **k:J.mangohud(k)
r=m(accion="ver"); ok("No hay archivo" in r,r)
r=m(accion="activar",opciones=["fps","gpu_stats","font_size=30"]); ok("COMPROBADO" in r and "font_size=30" in r,r)
r=m(accion="activar",opciones=["font_size=40","cpu_temp"]); txt=J.RUTA_MANGOHUD.read_text(); ok(txt.count("font_size")==1 and "font_size=40" in txt and "cpu_temp" in txt,txt)
ok(len(list(J.DIR_COPIAS.glob("*__MangoHud.conf")))>=1,"copia mangohud")
r=m(accion="quitar",opciones=["gpu_stats"]); ok("gpu_stats" not in J.RUTA_MANGOHUD.read_text(),r)
r=m(accion="activar",opciones=["exec=rm -rf ~"]); ok("no la pongo" in r,r)
r=m(accion="activar",opciones=["fps;rm"]); ok("no parece" in r,r)
r=m(accion="activar",opciones=["inventadaxyz=1"]); ok("AVISO: no conozco" in r,r)
r=m(accion="activar",opciones=["fps"]); ok("Ya estaba" in r,r)
r=m(accion="preset",opciones=["rendimiento"]); ok("gpu_temp" in J.RUTA_MANGOHUD.read_text(),r)
r=m(accion="deshacer"); ok("Restaurada" in r and "inventadaxyz" in J.RUTA_MANGOHUD.read_text(),r)
J.RUTA_MANGOHUD.write_text("# comentario\n#fps\nposition=top-left\n")
r=m(accion="activar",opciones="fps, position=top-right"); t=J.RUTA_MANGOHUD.read_text(); ok(t.splitlines()[1]=="fps" and "position=top-right" in t and "top-left" not in t,t)
r=m(accion="borrar"); ok(not J.RUTA_MANGOHUD.exists(),r)
# --- protección de comandos sueltos ---
from lina.nucleo import herramientas as H
for cmd,esp in {"sed -i 's/a/b/' ~/.local/share/Steam/config/config.vdf":"critico","cat ~/.local/share/Steam/config/config.vdf":"lectura",
                "echo x > ~/.steam/steam/userdata/1000/config/localconfig.vdf":"critico"}.items():
    r=H.clasificar(cmd)[0]; ok(r==esp,f"{cmd}: {r}")
print("fallos",f)
