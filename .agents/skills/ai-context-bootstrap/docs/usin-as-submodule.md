# Guía rápida: trabajar con el submódulo `ai-context-bootstrap`

Esta guía explica **cómo usar y mantener el submódulo** del skill `.ai-context`  
sin romper nada y sin perder tiempo.

---

## 1️⃣ Añadir el skill a un proyecto (cuando NO está)

Desde la **raíz del proyecto**:

```bash
git submodule add https://github.com/egrandal-org/ai-context-standards .github/skills/ai-context-bootstrap
git commit -m "Add ai-context-bootstrap skill as submodule"
git push
````

👉 El proyecto ahora usa el estándar.
👉 VS Code detecta la skill automáticamente.

---

## 2️⃣ Clonar un proyecto que YA tiene el submódulo

Después de clonar el repo:

```bash
git submodule update --init --recursive
```

⚠️ Si no haces esto, el submódulo estará vacío.

---

## 3️⃣ Actualizar TODOS los proyectos cuando cambia el repo origen

### Paso A — Actualizar el repo del skill

En el **repo central del skill**:

```bash
git commit -m "Cambios en el estándar"
git push
```

### Paso B — En cada proyecto que lo use

Desde la raíz del proyecto:

```bash
git submodule update --remote --merge
git commit -m "Update ai-context-bootstrap skill"
git push
```

👉 Esto actualiza el **puntero del submódulo** al último commit del skill.

---

## 4️⃣ Cambiar el skill DESDE un proyecto que lo incluye

### Paso A — Commit en el submódulo

Desde la raíz del proyecto:

```bash
cd .github/skills/ai-context-bootstrap
git add .
git commit -m "Cambios en la skill"
git push
```

### Paso B — Commit del puntero en el proyecto

Vuelve al proyecto:

```bash
cd ../../..
git add .github/skills/ai-context-bootstrap
git commit -m "Update ai-context-bootstrap skill submodule"
git push
```

⚠️ **Este orden es obligatorio**.

---

## 5️⃣ Ver si un proyecto está usando una versión antigua del skill

Desde la raíz del proyecto:

```bash
git status
```

Si ves algo como:

```
modified: .github/skills/ai-context-bootstrap (new commits)
```

👉 El proyecto **no está actualizado** al último commit del skill.

---

## 6️⃣ Errores comunes (y qué hacer)

### ❌ “He cambiado la skill pero no se refleja en otros proyectos”

➡️ No has actualizado el submódulo en esos proyectos
→ ver sección **3️⃣**

---

### ❌ “He hecho commit en el proyecto pero no en la skill”

➡️ El cambio **no existe en el repo central**
→ entra al submódulo y haz commit allí

---

### ❌ “Cloné el repo y no veo la skill”

➡️ Falta ejecutar:

```bash
git submodule update --init --recursive
```

---

### ❌ “Git dice que el submódulo está sucio”

➡️ Entra al submódulo y:

* o haces commit
* o descartas cambios

```bash
cd .github/skills/ai-context-bootstrap
git status
```

---

## 7️⃣ Regla de oro (léela dos veces)

* **La skill es un repo independiente**
* **El proyecto solo apunta a un commit**
* Cambias la skill → commit en la skill
* El proyecto se entera → commit del puntero

Si dudas, **NO hagas commit a ciegas**.

---

## 8️⃣ TL;DR (versión vaga pero correcta)

* Añadir skill: `git submodule add`
* Clonar: `git submodule update --init`
* Actualizar todos: `git submodule update --remote`
* Cambiar skill desde proyecto:

  1. commit dentro del submódulo
  2. commit del puntero en el proyecto

Fin. No hay más magia.

---

Siguiente paso natural 'pendiente' (cuando te apetezca sufrir un poco más) es:
- un **script / agente updater** que recorra todos los repos de la org y abra PRs actualizando el submódulo

Pero ahora mismo ya tienes algo mejor que el 95 % de los equipos:  
**un estándar vivo, centralizado y documentado sin ruido**.