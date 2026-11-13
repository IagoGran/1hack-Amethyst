# Alignment rules (v1)

# Cómo alinear .ai-context con el estándar SIN romper nada

## Principios

- NO borrar contenido existente del usuario
- NO reescribir texto existente
- NO inventar información
- Cambios mínimos y reversibles

## Alineación estructural

- Verificar que todos los encabezados normativos existen
- Si falta un encabezado:
  - añadirlo en la sección correcta
  - si no está claro, añadirlo al final del archivo
- No modificar encabezados existentes aunque el texto sea distinto

## Contenido desconocido

- Si una sección aplica pero no hay información:
  - usar `N/A` si no aplica
  - usar `Pending` si se desconoce
- Nunca inferir decisiones técnicas no explícitas

## Versionado del contexto

- No cambiar `context_standard` si existe
- Si no existe, sugerir añadirlo (no forzar)

## Orden de lectura

- Respetar siempre el orden definido en `.ai-context/README.md`
- No leer código antes de consumir el contexto

## Conflictos

- Si el contenido existente contradice el estándar:
  - NO corregir automáticamente
  - Señalar el conflicto en el resumen final

## Instrucciones para agentes IA

- Si existe .github/copilot-instructions.md o AGENTS.md:
  - Verificar consistencia con .ai-context/README.md
  - No modificar sin autorización explícita
- Si no existen, crear usando como referencia las plantillas en .github/skills/ai-context-bootstrap/templates/agents_instructions/
