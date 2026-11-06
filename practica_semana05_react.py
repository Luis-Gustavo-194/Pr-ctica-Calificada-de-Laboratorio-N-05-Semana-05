"""
Práctica Calificada de Laboratorio N° 05 - Semana 05
Motor agéntico ReAct con Self-Healing, parseo robusto con RegEx,
inyección del reloj del sistema y Failsafe por límite de pasos.

Uso:
    python practica_semana05_react.py            # usa Gemini (requiere GEMINI_API_KEY)
    python practica_semana05_react.py --mock     # simulador local, sin API
    python practica_semana05_react.py --mock --failsafe   # fuerza el Failsafe
"""

import os
import re
import sys
import datetime
from typing import Any, Dict, Optional

try:
    from google import genai
    from google.genai import types
except ImportError:  # el script sigue funcionando en modo --mock
    genai = None
    types = None


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_PASOS = 5
STOP_SEQUENCES = ["Observation:"]


# ==========================================
# 1. CATÁLOGO DE HERRAMIENTAS Y SIMULACIÓN
# ==========================================

BD_INVENTARIO = {
    "PROD-001": {"nombre": "Laptop Gamer", "stock": 5, "precio": 1200.0},
    "PROD-002": {"nombre": "Monitor 4K", "stock": 0, "precio": 350.0},
}


def _a_numero(valor: Any, nombre: str) -> float:
    """Convierte a float validando tipo y formato (validación estricta)."""
    if isinstance(valor, bool):
        raise TypeError(f"'{nombre}' debe ser numérico, no booleano.")
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.strip())
        except ValueError:
            raise ValueError(f"'{nombre}' debe ser un número válido, se recibió '{valor}'.")
    raise TypeError(f"'{nombre}' tiene un tipo no soportado: {type(valor).__name__}.")


def consultar_inventario(producto_id: str) -> str:
    """Consulta el stock y precio de un producto por su ID."""
    if not isinstance(producto_id, str):
        raise TypeError("'producto_id' debe ser una cadena de texto.")
    clave = producto_id.strip().upper()
    if not clave:
        raise ValueError("'producto_id' no puede estar vacío.")
    if clave not in BD_INVENTARIO:
        raise KeyError(f"El producto con ID '{clave}' no existe en la base de datos.")
    info = BD_INVENTARIO[clave]
    return f"Producto: {info['nombre']} | Stock: {info['stock']} | Precio: ${info['precio']}"


def calcular_descuento(precio: float, porcentaje: float) -> str:
    """Calcula el precio final aplicando un porcentaje de descuento."""
    p = _a_numero(precio, "precio")
    d = _a_numero(porcentaje, "porcentaje")
    if p < 0:
        raise ValueError("El precio debe ser positivo.")
    if not 0 <= d <= 100:
        raise ValueError("El descuento debe estar entre 0 y 100.")
    precio_final = p * (1 - d / 100)
    return f"Precio original: ${p:.2f} | Descuento: {d}% | Precio final: ${precio_final:.2f}"


HERRAMIENTAS_DISPONIBLES = {
    "consultar_inventario": consultar_inventario,
    "calcular_descuento": calcular_descuento,
}


# ==========================================
# 2. PARSEO TOLERANTE (RegEx)
# ==========================================

PATRON_THOUGHT = re.compile(r"^[\s*_]*Thought:[\s*_]*(.+)$", re.IGNORECASE | re.MULTILINE)
PATRON_ACTION = re.compile(r"^[\s*_]*Action:[\s*_`]*(.+)$", re.IGNORECASE | re.MULTILINE)
PATRON_ACTION_INPUT = re.compile(r"^[\s*_]*Action Input:[\s*_`]*(.+)$", re.IGNORECASE | re.MULTILINE)
PATRON_FINAL = re.compile(r"Final Answer:[\s*_]*(.+)", re.IGNORECASE | re.DOTALL)


def limpiar_formato(texto: str) -> str:
    """Quita los cercados de Markdown (```) y espacios sobrantes."""
    texto = re.sub(r"```[a-zA-Z]*", "", texto)
    return texto.replace("```", "")


def _limpiar_valor(valor: str) -> str:
    """Quita comillas y backticks accidentales alrededor de un valor."""
    return valor.strip().strip("`*'\" ").strip()


def _extraer_argumentos(args_str: str) -> list:
    """Separa argumentos por comas y quita prefijos tipo 'producto_id=' o 'precio:'."""
    args = []
    for a in (args_str or "").split(","):
        a = a.strip().strip("'\"")
        if not a:
            continue
        m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*[=:]\s*(.+)$", a)
        if m:
            a = m.group(1).strip().strip("'\"")
        args.append(a)
    return args


# ==========================================
# 3. MOTOR DE PARSEO Y AUTOCORRECCIÓN
# ==========================================

RESPUESTAS_MOCK = [
    # 1) Nombre de herramienta inexistente -> Self-Healing
    "Thought: Necesito el stock del producto PROD-001.\n"
    "Action: consultar_inventario_v2\n"
    "Action Input: PROD-001",
    # 2) Corrige el nombre
    "Thought: El nombre de la herramienta era incorrecto; uso consultar_inventario.\n"
    "Action: consultar_inventario\n"
    "Action Input: PROD-001",
    # 3) Argumento con tipo inválido -> ValueError capturado
    "Thought: Hay stock. Calculo el descuento del 15%.\n"
    "Action: calcular_descuento\n"
    "Action Input: 1200, quince",
    # 4) Corrige el argumento y envuelve la acción en cercado Markdown
    "Thought: El porcentaje debe ser numérico; lo corrijo a 15.\n"
    "```\nAction: calcular_descuento\nAction Input: 1200, 15\n```",
    # 5) Respuesta final
    "Thought: Ya tengo todos los datos.\n"
    "Final Answer: La Laptop Gamer (PROD-001) tiene 5 unidades en stock. "
    "Con un 15% de descuento su precio final es $1020.00.",
]


class MotorReActEstudiante:
    def __init__(self, max_pasos: int = MAX_PASOS, usar_mock: bool = False, forzar_bucle: bool = False):
        self.max_pasos = max_pasos
        self.usar_mock = usar_mock
        self.forzar_bucle = forzar_bucle  # solo para demostrar el Failsafe en modo mock
        self.historial_contexto: str = ""  # estado interno s_t (ventana de contexto)
        self.system_prompt: str = ""
        self.cliente = None
        self._mock_indice = 0

        if not usar_mock:
            if genai is None:
                raise RuntimeError("Falta el SDK. Instálalo con: pip install google-genai (o usa --mock).")
            if not os.getenv("GEMINI_API_KEY"):
                raise RuntimeError("Define la variable GEMINI_API_KEY (o usa --mock).")
            # v1beta es necesaria para system_instruction (instrucción de sistema)
            self.cliente = genai.Client(
                http_options=types.HttpOptions(api_version="v1beta")
            )  # lee GEMINI_API_KEY del entorno

    # ---------- Reloj del sistema ----------

    def obtener_reloj_sistema(self) -> str:
        """TAREA 1 (Ej 2): Obtener timestamp actual del sistema."""
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def construir_system_prompt(self) -> str:
        timestamp = self.obtener_reloj_sistema()
        return f"""Eres un Agente Autónomo ReAct. Tu deber es resolver consultas respondiendo estrictamente en este formato:

Thought: <tu razonamiento sobre qué hacer>
Action: <nombre de la herramienta a usar>
Action Input: <argumentos para la herramienta>

Reglas:
- Incluye SIEMPRE una línea Thought antes de cada Action.
- En Action Input escribe solo los valores, separados por comas, sin nombres de parámetros (por ejemplo: PROD-001, no producto_id=PROD-001).
- Después de Action Input DETENTE y espera el Observation que te devolverá el entorno. Nunca inventes un Observation.
- Si un Observation es un ERROR DE EJECUCIÓN, analiza el error en tu siguiente Thought, corrige los argumentos o la herramienta y vuelve a intentarlo. No des una respuesta final por un solo error.

Cuando tengas la respuesta final, responde exactamente con:
Final Answer: <respuesta clara y directa al usuario>

Herramientas disponibles:
- consultar_inventario: Argumento (producto_id: str)
- calcular_descuento: Argumentos (precio: float, porcentaje: float)

[ESTADO_SISTEMA]: Timestamp actual = {timestamp}
"""

    # ---------- Parseo ----------

    def parsear_salida_llm(self, texto_salida: str) -> Dict[str, Optional[str]]:
        """TAREA 2 (Ej 2): Parseo mediante RegEx tolerante a Markdown y variaciones."""
        res: Dict[str, Optional[str]] = {
            "thought": None,
            "action": None,
            "action_input": None,
            "final_answer": None,
        }
        if not texto_salida:
            return res

        limpio = limpiar_formato(texto_salida)

        m_final = PATRON_FINAL.search(limpio)
        if m_final:
            res["final_answer"] = m_final.group(1).strip()
            return res

        m_thought = PATRON_THOUGHT.search(limpio)
        m_action = PATRON_ACTION.search(limpio)
        m_input = PATRON_ACTION_INPUT.search(limpio)

        if m_thought:
            res["thought"] = _limpiar_valor(m_thought.group(1))
        if m_action:
            # Solo el identificador: "consultar_inventario (PROD-001)" -> "consultar_inventario"
            ident = re.match(r"[A-Za-z_][A-Za-z0-9_]*", _limpiar_valor(m_action.group(1)))
            res["action"] = ident.group(0) if ident else None
        if m_input:
            res["action_input"] = _limpiar_valor(m_input.group(1))
        return res

    # ---------- Self-Healing ----------

    def ejecutar_herramienta_con_self_healing(self, nombre_herramienta: Optional[str], args_str: Optional[str]) -> str:
        """TAREA 3 (Ej 1): Ejecutar herramienta y capturar excepciones para Self-Healing."""
        if not nombre_herramienta or nombre_herramienta not in HERRAMIENTAS_DISPONIBLES:
            return (
                f"Observation: [ERROR DE EJECUCIÓN] La herramienta '{nombre_herramienta}' no existe. "
                f"Herramientas válidas: {list(HERRAMIENTAS_DISPONIBLES.keys())}. "
                "Por favor corrige los argumentos o intenta otra herramienta."
            )
        try:
            func = HERRAMIENTAS_DISPONIBLES[nombre_herramienta]
            args = _extraer_argumentos(args_str)
            resultado = func(*args)  # firma inválida -> TypeError
            return f"Observation: [ÉXITO] {resultado}"
        except Exception as e:  # KeyError, ValueError, TypeError, etc.
            return (
                f"Observation: [ERROR DE EJECUCIÓN] {type(e).__name__}: {str(e).rstrip('.')}. "
                "Por favor corrige los argumentos o intenta otra herramienta."
            )

    # ---------- LLM ----------

    def _llm_mock(self) -> str:
        if self.forzar_bucle:
            return "Thought: Sigo analizando el problema, aún no tengo certeza."
        idx = self._mock_indice
        self._mock_indice += 1
        if idx < len(RESPUESTAS_MOCK):
            return RESPUESTAS_MOCK[idx]
        return "Thought: Sigo analizando el problema."

    def _llamar_llm(self) -> str:
        if self.usar_mock:
            return self._llm_mock()

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            stop_sequences=STOP_SEQUENCES,  # el modelo se detiene antes de "Observation:"
            temperature=0.2,
        )
        respuesta = self.cliente.models.generate_content(
            model=GEMINI_MODEL,
            contents=self.historial_contexto,
            config=config,
        )
        return respuesta.text or ""

    # ---------- Bucle ReAct ----------

    def ejecutar_bucle_react(self, pregunta_usuario: str) -> str:
        """Bucle Thought -> Action -> Action Input -> Observation -> Final Answer, con Failsafe."""
        print(f"\n=== PROCESANDO PREGUNTA: '{pregunta_usuario}' ===")
        self.system_prompt = self.construir_system_prompt()
        self.historial_contexto = f"Usuario: {pregunta_usuario}\n"

        for paso in range(1, self.max_pasos + 1):
            print(f"\n--- PASO {paso} de {self.max_pasos} ---")

            try:
                salida = self._llamar_llm()
            except Exception as e:
                return f"[ERROR DEL MODELO] No se pudo consultar al LLM: {type(e).__name__}: {e}"

            print(f"LLM:\n{salida}")
            self.historial_contexto += salida.rstrip() + "\n"

            parseo = self.parsear_salida_llm(salida)
            if parseo["final_answer"] is not None:
                return parseo["final_answer"]

            if parseo["action"] is None:
                observacion = (
                    "Observation: [ERROR DE FORMATO] No se encontró 'Action:'. "
                    "Responde con Thought, Action y Action Input, o con Final Answer."
                )
            else:
                observacion = self.ejecutar_herramienta_con_self_healing(
                    parseo["action"], parseo["action_input"]
                )

            print(observacion)
            self.historial_contexto += observacion + "\n"

        # Failsafe: se alcanzó el límite de pasos sin Final Answer
        return (
            f"[FAILSAFE ACTIVADO] Se ha alcanzado el límite máximo de {self.max_pasos} pasos "
            "sin una respuesta final. Intenta reformular la consulta o dividirla en preguntas más simples."
        )


if __name__ == "__main__":
    usar_mock = "--mock" in sys.argv
    forzar_bucle = "--failsafe" in sys.argv

    agente = MotorReActEstudiante(max_pasos=MAX_PASOS, usar_mock=usar_mock, forzar_bucle=forzar_bucle)

    pregunta = (
        "¿Cuál es el stock y precio del PROD-001? "
        "Si hay stock, ¿cuánto costaría con un 15% de descuento?"
    )
    respuesta = agente.ejecutar_bucle_react(pregunta)
    print(f"\n>>> Final Answer: {respuesta}")
