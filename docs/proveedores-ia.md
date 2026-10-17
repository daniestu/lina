# Proveedores de IA intercambiables (fase 7)

Hoy Lina habla con Gemini en cinco sitios del código (el bucle principal con herramientas, el resumen de páginas web, las mini-consultas de
confirmación, interrupción y cumplimiento, y la visión de pantalla), cada uno con su propio manejo de errores. La fase 7 separa **qué le pide
Lina a la IA** de **con quién habla**.

## Principios

- Gemini con clave gratuita sigue siendo lo que viene por defecto: nada cambia para quien no toque nada.
- Ninguna IA se trata como de confianza especial: las capas de seguridad (confirmación por atajo, filtro de órdenes, papelera) no dependen del proveedor.
- Lo que no se puede comprobar se dice (precios desconocidos, modelo sin herramientas o sin visión), no se finge.

## Diseño

Un proveedor es un objeto con un solo método de petición, `turno(...)`, que recibe la conversación en un formato neutro y devuelve una
`Respuesta` (texto, llamadas a herramientas, tokens usados) o un `ErrorIA` con un tipo común (`cuota`, `servidor`, `peticion`, `auth`, `red`,
`vacia`). El bucle de herramientas, los reintentos, la espera de cuota, la cancelación y el plazo se escriben **una vez** y valen para todos.
Cada proveedor traduce a su API y de vuelta, y se encarga de sus propias particularidades (el nivel de razonamiento de Gemini, las firmas de
turno de Gemini 3, el formato de `tool_calls` de OpenAI, los bloques `tool_use` de Anthropic).

| Proveedor | Cubre |
|---|---|
| `gemini` | Gemini (clave gratuita o de pago), como ahora |
| `openai` | cualquier API compatible con OpenAI: OpenAI, OpenRouter, Groq, Mistral, y los servidores locales (Ollama, LM Studio, llama.cpp, vLLM) o de empresa con `url_base` propia |
| `anthropic` | la API de mensajes de Anthropic |

El modelo local que ya existe (para órdenes sencillas sin internet) no cambia.

## Configuración

```toml
[ia]
proveedor = "gemini"          # gemini | openai | anthropic
modelo_rapido = ""            # vacío = el que recomienda Lina para ese proveedor
modelo_profundo = ""
url_base = ""                 # solo para «openai» con servidor propio o local
```

La clave de cada proveedor se guarda aparte (llavero o archivo 600), con `lina clave <proveedor>`. `lina ia` muestra y cambia el proveedor y
`lina ia probar` hace una petición de prueba y dice si el modelo admite herramientas y visión.

## Presupuesto

El tope de gasto en euros necesita saber el precio. Para Gemini viene en la tabla de precios. Para otros proveedores solo se cuenta el gasto si
el usuario indica sus precios; si no, Lina cuenta los tokens, lo dice, y no finge un control de euros que no puede hacer. Los modelos locales
no cuestan nada.

## Entrega por pasos

1. (hecho) Interfaz común y proveedor Gemini; el código actual pasa a usarlos (sin cambios de comportamiento: las mismas pruebas deben seguir pasando).
2. (hecho) Proveedor `openai`.
3. (hecho) Proveedor `anthropic`.
4. Configuración: `[ia]`, `lina ia`, claves por proveedor, asistente de bienvenida, doctor y presupuesto.
5. Documentación y pruebas contra servidores simulados.

Los proveedores 2 y 3 se prueban aquí contra servidores simulados que siguen el formato publicado de cada API; **no contra los servicios
reales**, así que las primeras pruebas con claves reales hay que hacerlas en el equipo de cada uno.
