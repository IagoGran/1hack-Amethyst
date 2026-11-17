# 1️⃣ Orden de lectura oficial (v1, definitivo)

Este orden es **normativo**: agentes y humanos lo siguen **siempre**.
Se pondrá explícito en el `README.md` de `.ai-context/`.
**IMPORATNTE**: Solo se leeran aquellos necesarios para la tarea encomendada.

### 🔁 Orden de lectura

1. **`.ai-context/README.md`**
   → Qué es esto, reglas, qué leer y en qué orden.

3. **`.ai-context/PROJECT.md`**
   → Qué es el proyecto y qué no es.

4. **`.ai-context/TASKING.md`**
   → Cómo debe trabajar el agente contigo.

5. **`.ai-context/CONVENTIONS.md`**
   → Reglas globales del repo.

6. **`.ai-context/ARCHITECTURE.md`** *(si existe)*
   → Cómo encajan las piezas.

7. **`.ai-context/ENVIRONMENT.md`** *(si existe)*
   → Variables, configuración, entornos.

8. **Área específica según la tarea**

   * Frontend:

     * `.ai-context/frontend/DEV.md`
     * `.ai-context/frontend/CONVENTIONS.md` *(si existe)*
   * Backend:

     * `.ai-context/backend/DEV.md`
     * `.ai-context/backend/API.md` *(si existe)*
     * `.ai-context/backend/DATABASE.md` *(si existe)*

9. **Documentos especializados (solo si existen)**

   * `SECURITY.md`
   * `DEPLOYMENT.md`
   * `TESTING.md`
   * `DATA.md`
   * `OBSERVABILITY.md`
   * `DECISIONS.md`

👉 Regla explícita:

> **Nunca** leer el código antes de consumir `.ai-context/`.
> El código es el último recurso, no el primero.
