# Práctica Calificada de Laboratorio N° 05 — Semana 05

**Asignatura:** Agentes Inteligentes (VIII Ciclo) · **Unidad II:** Agentes Basados en LLMs y Paradigmas

Motor agéntico **ReAct** (Reasoning + Acting) implementado a bajo nivel con el SDK oficial `google-genai` de Gemini. Incluye:

* **Ejercicio 1 — Bucle ReAct y Self-Healing:** ciclo Thought → Action → Action Input → Observation → Final Answer, con `stop\_sequences=\["Observation:"]` y captura de errores de herramientas para que el modelo pueda corregirse.
* **Ejercicio 2 — Parseo robusto y Failsafe:** extracción de etiquetas con expresiones regulares (tolerante a cercados ````` y comillas), inyección del reloj del sistema (`reloj\_sistema`) en el System Prompt y límite de `max\_pasos = 5` con respuesta de degradación elegante.

No se usan frameworks de alto nivel como LangChain o CrewAI.

\---

## Estructura del proyecto

```
practica\_semana05\_react/
├── practica\_semana05\_react.py   # Script principal (ambos ejercicios)
├── requirements.txt             # Dependencias (google-genai)
├── .gitignore                   # Excluye .venv, caché y archivos con secretos
├── README.md                    # Este archivo
└── salida\_gemini\_real.txt       # Ejemplo de ejecución real con la API de Gemini
```

\---

## Requisitos

* Python **3.10** o superior
* Una cuenta de Google para obtener una API key de Gemini (opcional si solo usas `--mock`)

\---

## Instalación

Desde la carpeta del proyecto:

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Sabrás que el entorno está activo porque aparece `(.venv)` al inicio de la línea de la terminal.

\---

## Configuración de la API key

El script **no contiene ninguna clave**. Lee la clave de la variable de entorno `GEMINI\_API\_KEY`.

1. Obtén una clave en **Google AI Studio** (aistudio.google.com) → *Get API key* → *Create API key*.
2. Defínela en la misma terminal donde vas a ejecutar el script:

**Windows (PowerShell):**

```powershell
$env:GEMINI\_API\_KEY="TU\_CLAVE\_AQUI"
```

**macOS / Linux:**

```bash
export GEMINI\_API\_KEY="TU\_CLAVE\_AQUI"
```

> Esta variable dura solo mientras la terminal esté abierta. Si la cierras, hay que definirla de nuevo.

**Importante:** no escribas la clave en el código ni la subas al repositorio.

\---

## Ejecución

### Modo 1: con la API de Gemini (requiere `GEMINI\_API\_KEY`)

```bash
python practica\_semana05\_react.py
```

### Modo 2: simulador local (sin API ni clave)

```bash
python practica\_semana05\_react.py --mock
```

Usa respuestas predefinidas para recorrer el flujo completo: un nombre de herramienta incorrecto, un argumento inválido, la corrección y la respuesta final. Sirve para verificar la lógica sin consumir la API.

### Modo 3: forzar el Failsafe

```bash
python practica\_semana05\_react.py --mock --failsafe
```

El modelo simulado nunca da una respuesta final, así que el bucle se detiene en el paso 5 y muestra `\[FAILSAFE ACTIVADO]`.

### Cambiar el modelo (opcional)

Por defecto se usa `gemini-2.5-flash`. Para usar otro modelo, define la variable `GEMINI\_MODEL`:

**Windows (PowerShell):**

```powershell
$env:GEMINI\_MODEL="nombre-del-modelo"
```

**macOS / Linux:**

```bash
export GEMINI\_MODEL="nombre-del-modelo"
```

\---

## Cómo funciona

1. **Reloj del sistema:** antes de empezar, se obtiene la fecha y hora actual y se inserta en el System Prompt como `\[ESTADO\_SISTEMA]: Timestamp actual = ...`.
2. **Bucle ReAct:** en cada paso, el modelo recibe el historial y responde con `Thought`, `Action` y `Action Input`. La opción `stop\_sequences=\["Observation:"]` hace que el modelo se detenga antes de inventar un resultado.
3. **Ejecución de herramientas:** el script ejecuta la herramienta indicada y devuelve el resultado como `Observation:`:

   * Si tiene éxito: `Observation: \[ÉXITO] ...`
   * Si falla (herramienta inexistente, `KeyError`, `ValueError`, firma inválida): `Observation: \[ERROR DE EJECUCIÓN] ...`. El modelo lee el error y puede corregirse en el siguiente paso.
4. **Respuesta final:** cuando el modelo responde con `Final Answer:`, el bucle termina.
5. **Failsafe:** si se llega a 5 pasos sin respuesta final, el bucle se detiene y devuelve `\[FAILSAFE ACTIVADO]`.

### Herramientas disponibles

|Herramienta|Argumentos|Descripción|
|-|-|-|
|`consultar\_inventario`|`producto\_id` (texto)|Devuelve stock y precio de un producto. Ejemplos: `PROD-001`, `PROD-002`.|
|`calcular\_descuento`|`precio`, `porcentaje`|Calcula el precio final con descuento. El porcentaje debe estar entre 0 y 100.|

\---

## Ejemplo de salida

Ejecución real con la API de Gemini (también guardada en `salida\_gemini\_real.txt`):

```
--- PASO 1 de 5 ---
Thought: El usuario pregunta por el stock y precio del producto PROD-001. ...
Action: consultar\_inventario
Action Input: PROD-001
Observation: \[ÉXITO] Producto: Laptop Gamer | Stock: 5 | Precio: $1200.0

--- PASO 2 de 5 ---
Thought: ... Ahora necesito calcular el precio con un 15% de descuento. ...
Action: calcular\_descuento
Action Input: 1200.0, 15
Observation: \[ÉXITO] Precio original: $1200.00 | Descuento: 15.0% | Precio final: $1020.00

--- PASO 3 de 5 ---
Thought: ... Ahora puedo formular la respuesta final al usuario.
Final Answer: El producto PROD-001 (Laptop Gamer) tiene un stock de 5 unidades ...
```

Como el modelo de lenguaje no es determinista, la redacción de cada ejecución puede variar, aunque el flujo debe ser similar.

\---

## Solución de problemas

|Problema|Causa probable|Solución|
|-|-|-|
|`Define la variable GEMINI\_API\_KEY`|La variable no está definida en esta terminal|Vuelve a ejecutar el comando `$env:GEMINI\_API\_KEY=...` o `export GEMINI\_API\_KEY=...`|
|`Falta el SDK` / `No module named 'google'`|Las dependencias no están instaladas o el entorno virtual no está activo|Activa `.venv` y ejecuta `pip install -r requirements.txt`|
|`400 INVALID\_ARGUMENT ... api version v1`|Versión de API incorrecta para la instrucción de sistema|Usa la versión actual del script, que crea el cliente con `api\_version="v1beta"`|
|`404 NOT\_FOUND` con el nombre del modelo|El modelo no existe o ya no está disponible|Define otro modelo con `GEMINI\_MODEL`|
|`PermissionError` al activar `.venv` en Windows|Política de ejecución de PowerShell|Ejecuta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y confirma con `S`|

\---

## Autor

Nombre: LUIS GUSTAVO REGALADO CONDOR · Código: 0202314046

