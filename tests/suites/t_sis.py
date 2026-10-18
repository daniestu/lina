# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lina contributors
import sys, json, os
from lina.modulos import sistema as S
fallos = 0
def ok(c, m):
    global fallos
    if not c:
        fallos += 1; print("FALLO:", m)

U1="{11111111-1111-1111-1111-111111111111}"; U2="{22222222-2222-2222-2222-222222222222}"; U3="{33333333-3333-3333-3333-333333333333}"
WIN={U1:("Mozilla Firefox","firefox",100),U2:("~ : fish — Konsole","org.kde.konsole",200),U3:("Skyrim Special Edition","steam_app_489830",300)}
WPCTL="""PipeWire 'pipewire-0' [1.4.0, usuario@pc, cookie:1]
 └─ Clients:
        33. WirePlumber                         [1.4.0, usuario@pc, pid:1000]

Audio
 ├─ Devices:
 │      46. Built-in Audio                      [alsa]
 │
 ├─ Sinks:
 │  *   47. Built-in Audio Analog Stereo        [vol: 0.40]
 │      48. HDMI / DisplayPort 1                [vol: 1.00 MUTED]
 │
 ├─ Sources:
 │  *   50. Micrófono interno                   [vol: 0.80]
 │
 └─ Streams:
        85. Firefox
             88. output_FL > Built-in Audio:playback_FL   [active]
             89. output_FR > Built-in Audio:playback_FR   [active]
        90. Discord
             91. output_FL > Built-in Audio:playback_FL   [active]
"""
KS={"outputs":[
 {"id":1,"name":"DP-1","enabled":True,"connected":True,"priority":1,"currentModeId":"2","pos":{"x":0,"y":0},"scale":1.0,"rotation":1,
  "modes":[{"id":"1","size":{"width":2560,"height":1440},"refreshRate":60.0},{"id":"2","size":{"width":2560,"height":1440},"refreshRate":165.0},{"id":"3","size":{"width":1920,"height":1080},"refreshRate":144.0}]},
 {"id":2,"name":"HDMI-A-1","enabled":True,"connected":True,"priority":2,"currentModeId":"4","pos":{"x":2560,"y":0},"scale":1.0,"rotation":1,
  "modes":[{"id":"4","size":{"width":1920,"height":1080},"refreshRate":60.0}]}]}
llamadas=[]
estado={"vol":"Volume: 0.40"}
def ej(argv, timeout=8):
    llamadas.append(argv)
    a=argv; b=a[0]
    if b=="kdotool":
        if a[1]=="search":
            if a[-1]=="%@":
                cmd=a[-2]; idx={"getwindowname":0,"getwindowclassname":1,"getwindowpid":2}[cmd]
                return 0,"\n".join(str(v[idx]) for v in WIN.values())
            return 0,"\n".join(WIN)
        if a[1]=="getactivewindow": return 0,U3
        if a[1]=="getwindowgeometry": return 0,"Position: 0,0\nGeometry: 1920x1080"
        if a[1]=="get_desktop": return 0,"1"
    if b=="ps":
        if "--sort=-pcpu" in a:
            return 0,"""  1 root 0.0 0.1 12000 5000 systemd systemd
 500 usuario 55.0 5.0 2000000 3000 steam /usr/lib/steam/steam
 600 usuario 30.0 2.0 800000 3000 firefox /usr/lib/firefox/firefox
 601 usuario 1.0 2.0 300000 3000 Web Content /usr/lib/firefox/firefox -contentproc
 700 usuario 0.1 0.1 100000 3000 plasmashell /usr/bin/plasmashell
 800 root 0.5 0.1 100000 3000 NetworkManager /usr/bin/NetworkManager"""
        return 0,"  600 S"
    if b=="wpctl":
        if a[1]=="status": return 0,WPCTL
        if a[1]=="get-volume": return 0,estado["vol"]
    if b=="kscreen-doctor": return 0,json.dumps(KS)
    if b=="systemctl":
        if "list-unit-files" in a:
            return 0,("sshd.service enabled\nbluetooth.service enabled\nasistente.service enabled" if "--user" not in a else "pipewire.service enabled\nasistente.service enabled")
        if "is-active" in a: return 0,"active"
        if "is-enabled" in a: return 0,"enabled"
        if "--failed" in a: return 0,"foo.service failed"
    if b=="nmcli":
        if "connection" in a and "show" in a: return 0,"Casa 5G:802-11-wireless\nWired connection 1:802-3-ethernet\nlo:loopback"
        if "device" in a and "status" in a: return 0,"enp5s0:ethernet:connected:Wired connection 1\nlo:loopback:unmanaged:"
        if "connectivity" in a: return 0,"full"
        if "radio" in a: return 0,"enabled"
    if b=="ip": return 0,"enp5s0 UP 192.168.1.5/24"
    if b=="bluetoothctl":
        if a[1:]==["devices"]: return 0,"Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\nDevice 11:22:33:44:55:66 Mando Xbox"
        if a[1:]==["devices","Connected"]: return 0,"Device 11:22:33:44:55:66 Mando Xbox"
        if a[1]=="show": return 0,"Controller X\n\tPowered: yes\n\tPairable: yes"
    if b=="powerprofilesctl": return 0,"balanced"
    if b=="busctl":
        if "tree" in a: return 0,"└─ /org/kde/ScreenBrightness\n   └─ /org/kde/ScreenBrightness/display0"
        if "get-property" in a: return 0,("i 40" if "Brightness" == a[-1] else "i 100")
        if "list" in a: return 0,"org.kde.KWin 1 kwin\n:1.5 2 x\norg.kde.plasmashell 3 p"
    return None,f"{b}: no simulado"
S.EJ=ej; S.USUARIO="usuario"
import tempfile as _tf; S.ARCHIVO_PANTALLA_PREVIA=_tf.gettempdir()+"/lina_prueba_prev.json"

from lina.nucleo import comandos
comandos.nombres_de_apps=lambda *a,**k:[{"nombre":"Konsole","es":"Consola","comando":"konsole","id":"org.kde.konsole","generico":"Terminal","claves":"terminal;consola;shell","terminal":False}]
# ventanas
p=S.planificar("ventanas",{"accion":"listar"}); ok("Skyrim" in p["texto"] and "activa" in p["texto"],"listar ventanas")
p=S.planificar("ventanas",{"accion":"cerrar","ventana":"firefox"}); ok(p.get("comando")==f"kdotool windowclose {S._q(U1)}",f"cerrar {p}")
p=S.planificar("ventanas",{"accion":"enfocar","ventana":"la consola"}); ok("windowactivate" in p.get("comando","") and U2 in p["comando"],f"enfocar consola {p}")
p=S.planificar("ventanas",{"accion":"enfocar","ventana":"fairfox"}); ok(U1 in p.get("comando",""),f"parecido fairfox {p}")
p=S.planificar("ventanas",{"accion":"maximizar","ventana":"activa"}); ok("Window Maximize" in p["comando"] and U3 in p["comando"],"maximizar")
p=S.planificar("ventanas",{"accion":"mosaico","ventana":"skyrim","valor":"izquierda"}); ok("Quick Tile Left" in p["comando"],"mosaico")
p=S.planificar("ventanas",{"accion":"mover","ventana":"konsole","valor":"100,50"}); ok("windowmove" in p["comando"] and "100 50" in p["comando"],"mover")
p=S.planificar("ventanas",{"accion":"mover","ventana":"konsole","valor":"; rm -rf /"}); ok("error" in p,"mover valida")
p=S.planificar("ventanas",{"accion":"cerrar","ventana":"zzzzqqq"}); ok("error" in p,"ventana inexistente")
p=S.planificar("ventanas",{"accion":"mover_a_escritorio","ventana":"firefox","valor":"2"}); ok("Window to Desktop 2" in p["comando"],"escritorio")
ok(isinstance(p["comprobar"](),str),"comprobar ventana")

# procesos
p=S.planificar("procesos",{"accion":"listar"}); ok("steam" in p["texto"],"listar procesos")
p=S.planificar("procesos",{"accion":"terminar","proceso":"firefox"}); ok(p.get("comando")=="kill -TERM 600","terminar firefox: %s"%p)
p=S.planificar("procesos",{"accion":"terminar","proceso":"NetworkManager"}); ok("error" in p,"ajeno")
p=S.planificar("procesos",{"accion":"prioridad","proceso":"steam","valor":"-5"}); ok(p["comando"].startswith("sudo -n renice -n -5"),"renice")
p=S.planificar("procesos",{"accion":"terminar","proceso":"nosuchproc"}); ok("texto" in p and "No hay" in p["texto"],"sin proceso")
ok(len(S.procesos_que_encajan("web content"))==1,"con espacio")

# servicios
p=S.planificar("servicios",{"accion":"reiniciar","servicio":"bluetooth"}); ok(p["comando"]=="sudo -n systemctl restart bluetooth.service","reiniciar %s"%p)
p=S.planificar("servicios",{"accion":"reiniciar","servicio":"pipewire"}); ok(p["comando"]=="systemctl --user restart pipewire.service","user %s"%p)
p=S.planificar("servicios",{"accion":"estado","servicio":"blutooth"}); ok("comando" not in p,"estado lectura")
p=S.planificar("servicios",{"accion":"parar","servicio":"xyzxyz"}); ok("error" in p,"servicio inexistente")
p=S.planificar("servicios",{"accion":"listar_fallidos"}); ok("foo.service" in p["texto"],"fallidos")

# red
p=S.planificar("red",{"accion":"estado"}); ok("full" in p["texto"],"red estado")
p=S.planificar("red",{"accion":"conectar","objetivo":"casa"}); ok(p["comando"]=="nmcli connection up id 'Casa 5G'","conectar %s"%p)
p=S.planificar("red",{"accion":"conectar","objetivo":"wifi del vecino"}); ok("error" in p,"red nueva")
p=S.planificar("red",{"accion":"probar","objetivo":"x; rm -rf /"}); ok("error" in p,"host inválido")
p=S.planificar("red",{"accion":"bluetooth_conectar","objetivo":"sony"}); ok(p["comando"]=="bluetoothctl connect AA:BB:CC:DD:EE:FF","bt %s"%p)
p=S.planificar("red",{"accion":"bluetooth_desconectar"}); ok("11:22:33:44:55:66" in p["comando"],"bt desconectar el conectado")
p=S.planificar("red",{"accion":"bluetooth_estado"}); ok("CONECTADO" in p["texto"],"bt estado")

# energia
p=S.planificar("energia",{"accion":"perfil","valor":"rendimiento"}); ok(p["comando"]=="powerprofilesctl set performance","perfil")
p=S.planificar("energia",{"accion":"apagar"}); ok(p["comando"]=="systemctl poweroff","apagar")
p=S.planificar("energia",{"accion":"estado"}); ok("balanced" in p["texto"],"energia estado")

# pantalla
p=S.planificar("pantalla",{"accion":"listar"}); ok("DP-1" in p["texto"] and "165" in p["texto"],"pantalla listar")
p=S.planificar("pantalla",{"accion":"modo","salida":"DP-1","valor":"1920x1080@144"}); ok(p["comando"]=="kscreen-doctor output.DP-1.mode.3","modo %s"%p)
p=S.planificar("pantalla",{"accion":"modo","salida":"DP-1","valor":"144"}); ok("error" in p,"144 sin ese modo en la res actual")
p=S.planificar("pantalla",{"accion":"posicion","salida":"HDMI-A-1","valor":"100,0"}); ok("error" in p and "SOLAPAR" in p["error"],"solape %s"%p)
p=S.planificar("pantalla",{"accion":"posicion","salida":"HDMI-A-1","valor":"2560,200"}); ok("comando" in p,"posición válida")
p=S.planificar("pantalla",{"accion":"escala","salida":"dp1","valor":"125"}); ok("scale.1.25" in p.get("comando",""),"escala %s"%p)
p=S.planificar("pantalla",{"accion":"modo","valor":"60"}); ok("error" in p,"varias pantallas pide salida")
p=S.planificar("pantalla",{"accion":"desactivar","salida":"DP-1"}); ok("comando" in p,"desactivar una de dos")
p=S.planificar("pantalla",{"accion":"brillo","valor":"+10"}); ok("SetBrightness iu 50 0" in p.get("comando",""),"brillo %s"%p)
p=S.planificar("pantalla",{"accion":"brillo"}); ok("40%" in p["texto"],"brillo ver")
KS["outputs"][1]["enabled"]=False
p=S.planificar("pantalla",{"accion":"desactivar","salida":"DP-1"}); ok("error" in p,"no la última")
KS["outputs"][1]["enabled"]=True
S._guardar_previo(S.leer_pantallas()[0]); 
p=S.planificar("pantalla",{"accion":"revertir"}); ok("output.DP-1.mode.2" in p["comando"] and "position.2560,0" in p["comando"],"revertir %s"%p)

# audio
a,_=S.leer_audio(); ok(len(a["Sinks"])==2 and a["Sinks"][0]["defecto"] and abs(a["Sinks"][0]["vol"]-0.4)<1e-9,"sinks %s"%a["Sinks"])
ok([x["nombre"] for x in a["Streams"]]==["Firefox","Discord"],"streams %s"%a["Streams"])
ok(a["Sinks"][1]["mudo"],"mudo")
p=S.planificar("audio",{"accion":"volumen","valor":"30"}); ok(p["comando"]=="wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%","vol %s"%p)
p=S.planificar("audio",{"accion":"volumen","valor":"150"}); ok("100%" in p["comando"],"tope")
p=S.planificar("audio",{"accion":"subir"}); ok(p["comando"]=="wpctl set-volume @DEFAULT_AUDIO_SINK@ 10%+ -l 1","subir %s"%p)
p=S.planificar("audio",{"accion":"silenciar","objetivo":"micrófono"}); ok(p["comando"]=="wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1","mic %s"%p)
p=S.planificar("audio",{"accion":"silenciar","objetivo":"discord"}); ok(p["comando"]=="wpctl set-mute 90 1","app %s"%p)
p=S.planificar("audio",{"accion":"salida_por_defecto","objetivo":"hdmi"}); ok(p["comando"]=="wpctl set-default 48","default %s"%p)
p=S.planificar("audio",{"accion":"estado"}); ok("Discord" in p["texto"],"audio estado")

# dbus
p=S.planificar("kde_dbus",{"accion":"servicios","servicio":"kde"}); ok("org.kde.KWin" in p["texto"] and ":1.5" not in p["texto"],"dbus servicios")
p=S.planificar("kde_dbus",{"accion":"llamar","servicio":"org.kde.KWin","ruta":"/KWin","metodo":"reconfigure"}); ok("org.kde.KWin /KWin reconfigure" in p["comando"],"dbus llamar %s"%p)
p=S.planificar("kde_dbus",{"accion":"llamar","servicio":"org.kde.KWin; rm","ruta":"/KWin","metodo":"x"}); ok("error" in p,"dbus validar")

# protecciones
mc=lambda c: S.motivo_critico(c.split())
ok(mc("kill -9 1"),"kill 1")
ok(mc("kill -9 -1"),"kill -1")
ok(mc("pkill plasmashell"),"pkill plasmashell")
ok(mc("killall -9 kwin_wayland"),"killall kwin")
ok(mc("pkill -u usuario"),"pkill -u")
ok(mc("pkill ."),"pkill .")
ok(not mc("kill -TERM 600"),"kill normal")
ok(not mc("pkill firefox"),"pkill firefox ok")
ok(mc("qdbus6 org.kde.Shutdown /Shutdown logout"),"dbus logout")
ok(mc("qdbus6 org.kde.KWin /Scripting loadScript /tmp/x.js"),"dbus script")
ok(not mc("qdbus6 org.kde.KWin /KWin reconfigure"),"dbus reconfigure ok")
ok(not mc("qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut Window Maximize"),"shortcut ok")
ok(mc("busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager PowerOff b true"),"busctl system")
ok(mc("busctl --user call org.freedesktop.login1 /x y z"),"login1 user")
ok(S.motivo_critico(["kill","123"],True),"sudo kill")
ok(S.motivo_critico(["kscreen-doctor","output.DP-1.disable","output.HDMI-A-1.disable"],False,S.leer_pantallas()[0]),"sin pantallas")
ok(not S.motivo_critico(["kscreen-doctor","output.DP-1.disable"],False,S.leer_pantallas()[0]),"una de dos ok")
print("fallos",fallos)
