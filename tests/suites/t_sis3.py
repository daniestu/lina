import sys
exec(open("t_sis.py").read().split("# ventanas")[0].replace("fallos = 0","fallos = 0"))  # reutiliza el simulador (S.EJ ya puesto)
from lina.nucleo import herramientas as H
e=H.Ejecutor(avisar=lambda *a,**k:None, confirmar=True)
ejecutados=[]
e.ejecutar=lambda c,m="tarea":(ejecutados.append(c) or "código de salida: 0\n(sin salida)")
H.SNAPSHOT_AUTOMATICA=False; S._nombre_de_pid=lambda p:{700:"plasmashell",600:"firefox"}.get(p,"")
r=e.sistema("audio",{"accion":"volumen","valor":"30"}); print(r)
ok("COMPROBADO AHORA" in r and ejecutados[-1].startswith("wpctl set-volume"),"audio ejecuta y comprueba")
r=e.sistema("energia",{"accion":"apagar"}); print(r[:160])
ok(H.MENSAJE_PREPARADO in r and len(e.pendientes)==1,"apagar queda pendiente")
n=len(ejecutados)
r=e.sistema("procesos",{"accion":"terminar","proceso":"plasmashell"}); print(r[:160])
ok(len(ejecutados)==n and len(e.pendientes)==2,"plasmashell pide confirmación")
r=e.sistema("pantalla",{"accion":"escala","salida":"DP-1","valor":"1.25"}); print(r[-200:])
ok(os.path.exists(S.ARCHIVO_PANTALLA_PREVIA),"guarda previo")
r=e.sistema("ventanas",{"accion":"listar"}); ok("Skyrim" in r,"listar")
r=e.sistema("ventanas",{"accion":"cerrar","ventana":"nada de nada"}); ok("No hay ninguna" in r,"error ventana")
print("fallos",fallos)
