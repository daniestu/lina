import sys, os, tempfile, pathlib, threading
from unittest.mock import MagicMock
casa = pathlib.Path(tempfile.mkdtemp()); os.environ["HOME"] = str(casa)
for m in ("sounddevice","faster_whisper"): sys.modules[m]=MagicMock()
from lina.nucleo import asistente as A; from lina.nucleo import herramientas as H
f=0
def ok(c,m):
    global f
    if not c: f+=1; print("FALLO:",m)
SI=["Formátame el ordenador.","formatea el disco","formatéame el PC por favor","oye formatea el disco principal","formatea todo el sistema","formatea mis discos",
    "borra todas las particiones","borra el disco duro","elimina el sistema operativo","borra windows","borra todo el sistema","destruye el disco",
    "deja el ordenador de fábrica","restablece el equipo de fábrica","deja el pc como nuevo","reinstala el sistema","reinstálame windows","resetea el ordenador","vacía el disco de datos",
    "Voy a borrar todas las particiones y formatear el disco principal, ¿lo hago?","wipefs -a /dev/nvme0n1"]
NO=["formatea el texto del documento","formatea esta memoria usb","formatea la tabla de excel","borra el archivo prueba.txt","borra todo lo de la carpeta descargas",
    "limpia la caché del sistema","limpia el sistema","pon el ordenador en suspensión","reinicia el ordenador","reinicia el escritorio","borra la nota de la compra","elimina el programa vlc",
    "restaura el fondo de pantalla","restablece los ajustes del panel","cuánto espacio queda en el disco","formatea las fechas del informe","el disco está lleno, qué ocupa más","apaga el pc"]
for t in SI: ok(H.destruccion_total(t),"debería detectar: "+t)
for t in NO: ok(not H.destruccion_total(t),"NO debería detectar: "+t)

# integración: petición directa → no llega a la IA
a=A.Asistente.__new__(A.Asistente)
a.cerrojo=threading.Lock(); a.estado="pensando"; a.interrumpiendo=False
dichos=[]; a.decir=lambda t:dichos.append(t)
llamadas=[]
a.quiere_reiniciar=lambda p:False
a.responder=lambda *x,**k:(llamadas.append(1) or ("x","m"))
a.ejecutor=MagicMock(); a.ejecutor.pendientes=[]
A.PRES.entender_tope=lambda t:None; A.C.entender_alias=lambda t:None
a._atender("Formátame el ordenador.",0)
ok(dichos and "bloqueado" in dichos[0] and not llamadas,"la petición no llega a la IA y se dice que está bloqueado: %s"%dichos)

# red sobre la respuesta de la IA
resp="Voy a borrar todas las particiones y formatear el disco principal, ¿lo hago?"
ok(A.PIDE_CONFIRMACION.search(resp) and H.destruccion_total(resp),"el ejemplo real se detecta")
ok(not (H.destruccion_total("No lo hago: formatear discos está bloqueado.") and A.PIDE_CONFIRMACION.search("No lo hago: formatear discos está bloqueado.")),"una negativa no se toca")

# el «sí» a una propuesta de destrucción
b=A.Asistente.__new__(A.Asistente)
b.ejecutor=MagicMock(); b.ejecutor.pendientes=[]
b.historial=[{"rol":"model","texto":resp}]
nota,hecho=b.resolver_pendientes("sí")
ok("BLOQUEADO" in nota and not hecho,"un sí a la destrucción no la empuja a ejecutarse: %s"%nota[:60])
b.historial=[{"rol":"model","texto":"¿Quieres que abra Firefox?"}]
nota,hecho=b.resolver_pendientes("sí"); ok("no hay ninguna acción preparada" in nota,"un sí normal sigue como antes")

# revisor: no empuja a preparar algo bloqueado
c=A.Asistente.__new__(A.Asistente)
c.ejecutor=MagicMock(); c.ejecutor.pendientes=[]; c.acciones_turno=[]
r=c.revisar_respuesta(resp); ok(r and "BLOQUEADO" in r and not c.ejecutor.solo_preparar is True,"no pide preparar la destrucción")
c.acciones_turno=[("ejecutar_comando",{},"BLOQUEADO: formatearía un disco")]
r=c.revisar_respuesta("¿Lo hago?"); ok(r and "BLOQUEADO" in r,"si ya hubo un bloqueo, tampoco")
c.acciones_turno=[]; c.ejecutor.solo_preparar=False
r=c.revisar_respuesta("Voy a instalar vlc, ¿lo hago?"); ok(r and "preparado" in r and c.ejecutor.solo_preparar,"lo normal sigue pidiendo preparar")
# los comandos duros siguen bloqueados
for cmd in ["sudo mkfs.ext4 /dev/nvme0n1","sudo wipefs -a /dev/nvme0n1","sudo parted /dev/nvme0n1 mklabel gpt","sudo dd if=/dev/zero of=/dev/nvme0n1","sudo rm -rf --no-preserve-root /"]:
    ok(H._bloqueado(cmd),"sigue bloqueado: "+cmd)
print("FALLOS:",f)
