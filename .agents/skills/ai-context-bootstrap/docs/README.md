# ai-context-standards
Plantilla estándar de estructura para documentar el contexto de proyectos. Todos los poryectos que usen agentes IA deberían tener una carpeta `.ai-context/` con esta estructura.

**Definición del “esqueleto”** de cada archivo: **secciones/títulos**. Esto será la base del *skill global* y permitirá que un agente cree/actualice la carpeta sin inventarse cosas raras.

Propuesta la **v1** de estructura del `.ai-context/`, dejando claro **qué es core, qué es opcional y cuándo se crea cada cosa**. Sin escribir archivos todavía. Solo reglas.

---

## 🧠 `.ai-context/` — Estructura v1 (con opcionales incluidos)

### 🔹 CORE (siempre se crean)

Estos **siempre existen**, aunque sea con contenido mínimo.

**Raíz**

* `README.md`
* `PROJECT.md`
* `TASKING.md`
* `CONVENTIONS.md`

**Por área**

* `frontend/DEV.md`
* `backend/DEV.md`

---

### 🔸 COMUNES (se crean si aplica; muy frecuentes)

Estos el agente los crea **cuando detecta señales claras**.

**Raíz**

* `ARCHITECTURE.md`
  👉 Si hay frontend + backend, o más de un servicio.

* `ENVIRONMENT.md`
  👉 Si hay `.env`, Docker, CI/CD o despliegue.

**Backend**

* `API.md`
  👉 Si hay endpoints / controllers / rutas API.

* `DATABASE.md`
  👉 Si hay DB, ORM, migraciones o SQL.

* `DEPLOYMENT.md`
  👉 Si hay Docker, cloud, VPS, pipelines.

---

### 🔹 OPCIONALES ESTÁNDAR (ya definidos, pero no siempre creados)

Estos **forman parte del estándar**, pero solo aparecen cuando toca.

**Raíz**

* `DECISIONS.md`
  👉 Si hay decisiones técnicas relevantes o cambios de stack.

* `TESTING.md`
  👉 Si existen tests o quieres introducirlos.

* `SECURITY.md`
  👉 Si hay auth, pagos, PII, tokens, cumplimiento legal.

* `OBSERVABILITY.md`
  👉 Si hay despliegue y necesidad de debug en producción.

**Frontend**

* `CONVENTIONS.md`
  👉 Si el frontend no es trivial.

* `UI_UX.md`
  👉 Si el diseño importa (spoiler: casi siempre, pero tú mandas).

**Backend**

* `DATA.md`
  👉 Si hay datasets, ETL, IA, ficheros grandes, pipelines.

---

## 🧩 Regla de oro (para el skill global)

> **El agente NO crea archivos por capricho.**
> Los crea solo cuando:

* detecta señales técnicas claras **en el repo**
* o tú se lo pides explícitamente

Ejemplos de señales:

* Hay `docker-compose.yml` → recomendar `ENVIRONMENT.md` + `DEPLOYMENT.md`
* Hay `/api`, `/routes`, `/controllers` → crear `API.md`
* Hay Stripe, Auth, OAuth → recomendar `SECURITY.md`
* Hay tests → crear `TESTING.md`
* Hay más de un servicio → crear `ARCHITECTURE.md`


---

# `.ai-context/README.md` (SIEMPRE)

**Objetivo:** índice y orden de lectura, y reglas básicas.

Secciones:

* Propósito de `.ai-context/`
* Orden de lectura recomendado (para agentes y humanos)
* Qué NO hay aquí (secretos, credenciales, datos sensibles)
* Cómo actualizar este contexto (cuándo y quién)
* Convenciones de formato (cómo escribir ejemplos, rutas, comandos)

---

# `.ai-context/PROJECT.md` (SIEMPRE)

**Objetivo:** qué es el proyecto y qué no es.

Secciones:

* Resumen (1–3 líneas)
* Objetivo y usuarios
* Alcance (incluye / excluye)
* Stack (alto nivel)
* Entornos (dev/staging/prod si aplica)
* Estado actual / roadmap corto
* Riesgos / puntos delicados (si los hay)

---

# `.ai-context/TASKING.md` (SIEMPRE)

**Objetivo:** cómo quieres que trabajen los agentes contigo.

Secciones:

* Principios de trabajo (antes de tocar código, etc.)
* Qué puede hacer sin preguntar
* Qué debe preguntar siempre
* Formato de entrega (plan → cambios → checklist → próximos pasos)
* Criterios de calidad (tests, lint, docs)
* Política de cambios (pequeños PRs, commits, etc.)

---

# `.ai-context/CONVENTIONS.md` (SIEMPRE)

**Objetivo:** reglas generales del repo (no específicas de front/back).

Secciones:

* Estructura del repositorio (carpetas clave)
* Naming (archivos, clases, funciones)
* Estilo de commits/ramas (si lo usas)
* Dependencias y gestión de versiones
* Reglas de documentación
* Reglas de seguridad (mínimas) y manejo de secretos (en general)

---

# `.ai-context/ARCHITECTURE.md` (CASI SIEMPRE)

**Objetivo:** visión del sistema.

Secciones:

* Diagrama de alto nivel (texto/ASCII vale)
* Componentes principales (frontend, backend, DB, terceros)
* Flujos clave (login, pagos, etc.)
* Dependencias externas
* Decisiones de arquitectura importantes (link a `DECISIONS` si existe)
* Puntos críticos (rendimiento, concurrencia, límites)

---

# `.ai-context/ENVIRONMENT.md` (CASI SIEMPRE; CORE si Docker/Cloud)

**Objetivo:** mapa de configuración y variables.

Secciones:

* Filosofía (sin secretos aquí)
* Precedencia de configuración (`.env`, secret manager, CI vars, etc.)
* Tabla de variables por componente (front/back)

  * nombre, descripción, tipo, ejemplo (sin credenciales), entornos, dónde se define
* Variables obligatorias vs opcionales
* Configuración por entorno (dev/staging/prod)
* Errores típicos por mala config

---

## Frontend

# `.ai-context/frontend/DEV.md` (CASI SIEMPRE)

Secciones:

* Requisitos (Node/pnpm/etc.)
* Instalación
* Comandos habituales (dev/build/test/lint)
* Variables del frontend (link a `../ENVIRONMENT.md`)
* Estructura (rutas, componentes, estado)
* Problemas frecuentes

---

# `.ai-context/frontend/CONVENTIONS.md` (SEGÚN COMPLEJIDAD; recomendado)

Secciones:

* Convenciones de componentes (estructura, props, hooks)
* Estado (Zustand/Redux/Context) y reglas
* UI library / estilos (MUI/Tailwind/etc.)
* Routing y layouts
* Accesibilidad / i18n (si aplica)
* Testing del frontend (si aplica, link a `TESTING.md` si existe)

---

# `.ai-context/frontend/UI_UX.md` (OPCIONAL)

Secciones:

* Principios de diseño del proyecto
* Componentes base y patrones
* Paleta/typography (si aplica)
* Responsive
* Copy/tono (si aplica)

---

## Backend

# `.ai-context/backend/DEV.md` (CASI SIEMPRE)

Secciones:

* Requisitos (runtime, docker, etc.)
* Instalación / arranque local
* Comandos habituales
* Variables del backend (link a `../ENVIRONMENT.md`)
* Estructura (rutas, controllers, services, etc.)
* Debugging y logs
* Problemas frecuentes

---

# `.ai-context/backend/CONVENTIONS.md` (SEGÚN COMPLEJIDAD; recomendado)

Secciones:

* Arquitectura interna (capas)
* Estilo de endpoints (si hay API)
* Errores y respuestas estándar
* Logging
* Validación
* Manejo de configuración/secretos (referencias)

---

# `.ai-context/backend/API.md` (SI HAY API)

Secciones:

* Autenticación/Autorización
* Endpoints clave (tabla)
* Ejemplos de request/response (mínimos)
* Errores comunes y códigos
* Rate limits / paginación (si aplica)
* Contratos importantes

---

# `.ai-context/backend/DATABASE.md` (SI HAY DB)

Secciones:

* Motor y versión
* Esquema (alto nivel)
* Migraciones (cómo se ejecutan)
* Seed / fixtures
* Accesos/roles (sin credenciales)
* Backups/restauración (si aplica)
* Problemas típicos

---

# `.ai-context/backend/DATA.md` (SI HAY DATA/ETL/IA)

Secciones:

* Fuentes de datos
* Formatos y ubicación (rutas)
* Procesado/pipelines
* Calidad y validaciones
* Privacidad y anonimización
* Cómo regenerar datos / reproducibilidad

---

# `.ai-context/backend/DEPLOYMENT.md` (SI SE DESPLIEGA)

Secciones:

* Entornos y targets (VPS, Cloud Run, etc.)
* Build y artefactos
* Variables/secretos en despliegue (link a `../ENVIRONMENT.md`)
* Pipeline (pasos)
* Rollback
* Observabilidad mínima (logs, healthchecks)

---

# `.ai-context/DECISIONS.md`
  👉 Si hay decisiones técnicas relevantes o cambios de stack.
  _(Secciones por definir)_

# `.ai-context/TESTING.md`
  👉 Si existen tests o quieres introducirlos.
  _(Secciones por definir)_

# `.ai-context/SECURITY.md`
  👉 Si hay auth, pagos, PII, tokens, cumplimiento legal.
  _(Secciones por definir)_

# `.ai-context/OBSERVABILITY.md`
  👉 Si hay despliegue y necesidad de debug en producción.
  _(Secciones por definir)_
