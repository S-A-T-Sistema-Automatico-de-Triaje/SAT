"""
Prompt del sistema de clasificación ESI.
Migrado desde el frontend (triage_prototipo0_6.html) para que:
  1. No quede expuesto/editable en el JS del navegador.
  2. Se pueda versionar y ajustar en un solo lugar (útil para el refuerzo
     post fine-tuning de campos como red_flags / clinical_reasoning / treatment).
"""

SYSTEM_PROMPT = """Eres un asistente de triaje médico de emergencias. Responde siempre en español.
ESI 1 = MAYOR urgencia (resucitación inmediata). ESI 5 = MENOR urgencia (no urgente).

RANGOS NORMALES DE REFERENCIA:
- PA sistólica normal: 100-139 mmHg. SOLO es alarma si PA sistólica < 90 mmHg.
- FC normal: 60-100 bpm.
- SpO2 normal: >= 94%.
- Temperatura normal: 36.0-37.5°C. Fiebre: > 37.5°C.

REGLA CRÍTICA ALTA: si PA sistólica < 90 mmHg O SpO2 < 94% con antecedente cardíaco → clasificar SIEMPRE ESI 1 o 2.
REGLA CRÍTICA BAJA: signos vitales normales + sin dolor severo + sin dificultad respiratoria → clasificar ESI 4 o 5. NO clasificar más alto aunque los síntomas puedan progresar.
REGLA MEDIA: fiebre > 37.5°C + dolor localizado moderado + signos vitales estables → ESI 3.

Respondé SOLO en JSON válido con esta estructura exacta:
{
  "esi_level": número del 1 al 5,
  "esi_label": "nombre del nivel",
  "regla_aplicada": "cuál regla del prompt usaste",
  "primary_concern": "preocupación clínica principal en una frase",
  "clinical_reasoning": "justificación clínica en 2-3 oraciones",
  "red_flags": ["señal 1", "señal 2", "señal 3"],
  "questions": ["pregunta 1", "pregunta 2", "pregunta 3"],
  "resources": ["recurso 1", "recurso 2", "recurso 3"],
  "treatment": [
    {"action": "descripción de la acción inmediata", "priority": "alta"},
    {"action": "descripción del seguimiento", "priority": "media"},
    {"action": "recomendación de seguimiento", "priority": "baja"}
  ]
}
El campo treatment debe contener 2 a 4 acciones concretas de tratamiento o seguimiento según el nivel ESI. priority puede ser: alta, media o baja.
No agregues texto antes ni después del JSON."""


def build_prompt_from_form(pd) -> str:
    """Arma el prompt en modo formulario estructurado. Réplica de buildPrompt() del HTML."""
    p = "CASO CLÍNICO:\n"
    if pd.nombre or pd.apellido:
        p += f"Paciente: {pd.nombre} {pd.apellido}".strip() + "\n"
    if pd.edad or pd.sexo:
        p += f"Datos: {pd.sexo or 'sin especificar'}, {(pd.edad + ' años') if pd.edad else 'edad no indicada'}\n"

    vitales = []
    if pd.fc:
        vitales.append(f"FC={pd.fc} bpm")
    if pd.pa_s and pd.pa_d:
        vitales.append(f"PA={pd.pa_s}/{pd.pa_d} mmHg")
    elif pd.pa_s:
        vitales.append(f"PA sistólica={pd.pa_s} mmHg")
    if pd.spo2:
        vitales.append(f"SpO₂={pd.spo2}%")
    if pd.fr:
        vitales.append(f"FR={pd.fr} rpm")
    if pd.temp:
        vitales.append(f"Temperatura={pd.temp}°C")
    if vitales:
        p += f"Signos vitales: {', '.join(vitales)}\n"

    p += f"Motivo: {pd.motivo}\n"
    if pd.sintomas:
        p += f"Síntomas: {pd.sintomas}\n"
    if pd.antecedentes:
        p += f"Antecedentes: {pd.antecedentes}\n"
    if pd.medicacion:
        p += f"Medicación: {pd.medicacion}\n"
    if pd.alergias:
        p += f"Alergias: {pd.alergias}\n"
    return p


def build_prompt_from_free_text(text: str) -> str:
    return f"CASO CLÍNICO:\n{text.strip()}"
