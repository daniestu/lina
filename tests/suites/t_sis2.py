import sys
from lina.nucleo import herramientas as H
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
cl=lambda c:H.clasificar(c)[0]
casos={
 "kdotool search --name .":"lectura","kdotool getactivewindow getwindowname":"lectura",
 "kdotool windowclose {11111111-1111-1111-1111-111111111111}":"autonomo",
 "kdotool windowactivate X && qdbus6 org.kde.kglobalaccel /component/kwin invokeShortcut 'Window Maximize'":"autonomo",
 "kill -TERM 600":"autonomo","kill -9 1":"critico","kill -9 -1":"critico","pkill plasmashell":"critico","pkill firefox":"autonomo",
 "sudo -n kill 600":"critico","bash -c 'pkill -u usuario'":"critico",
 "qdbus6 org.kde.Shutdown /Shutdown logout":"critico","qdbus6 org.kde.KWin /KWin reconfigure":"autonomo","qdbus6 org.kde.KWin /KWin":"lectura",
 "busctl --user call org.freedesktop.login1 /x org.freedesktop.login1.Manager PowerOff b true":"critico",
 "systemctl reboot":"critico","systemctl poweroff":"critico","loginctl lock-session":"autonomo","loginctl list-sessions":"lectura",
 "powerprofilesctl set performance":"autonomo","powerprofilesctl get":"lectura",
 "kscreen-doctor -j":"lectura","kscreen-doctor output.DP-1.mode.3":"autonomo",
 "wpctl set-volume 90 30%":"autonomo","wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%":"inocuo","wpctl status":"lectura",
 "nmcli connection up id 'Casa 5G'":"autonomo","nmcli radio wifi off":"autonomo","bluetoothctl connect AA:BB:CC:DD:EE:FF":"autonomo","bluetoothctl devices":"lectura",
 "sudo -n systemctl restart bluetooth.service":"autonomo","systemctl --user restart pipewire.service":"autonomo",
 "brightnessctl set 50%":"autonomo","brightnessctl -m":"lectura","ping -c 3 -W 2 1.1.1.1":"lectura",
 "renice -n 5 -p 600":"autonomo","sudo -n renice -n -5 -p 500":"autonomo",
 "busctl --user call org.kde.ScreenBrightness /org/kde/ScreenBrightness/display0 org.kde.ScreenBrightness.Display SetBrightness iu 50 0":"autonomo",
}
for c,e in casos.items():
    r=cl(c); ok(r==e,f"{c!r}: {r} (esperado {e})")
print("fallos",f)
