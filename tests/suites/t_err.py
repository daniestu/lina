import sys, types
from lina.nucleo import asistente as A
a = A.Asistente.__new__(A.Asistente); a.ejecutor = object(); a.modo_privado = False
r = A.Asistente.probar_ajuste_kde(a, {"archivo": "kwinrc", "grupos": "NightColor", "clave": "Active", "valor": "false", "panel": "kcm_nightlight"})
print(r)
assert "control" in r and "esperado" in r and "archivo" not in r.split("Falta o está mal:")[1].split(".")[0]
print("OK")
