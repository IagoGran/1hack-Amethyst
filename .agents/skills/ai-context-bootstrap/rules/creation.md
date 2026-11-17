# Creation rules (v1)

## Create automatically (MUST)
- CORE always:
  - .ai-context/README.md
  - .ai-context/PROJECT.md
  - .ai-context/TASKING.md
  - .ai-context/CONVENTIONS.md
  - .ai-context/frontend/DEV.md
  - .ai-context/backend/DEV.md

## Create automatically when signals apply (MUST if signal)
- ARCHITECTURE.md: if frontend + backend OR multiple services
- ENVIRONMENT.md: if .env* OR multiple environments implied OR external services
- backend/API.md: if OpenAPI/swagger files OR clear API consumer exists
- backend/DATABASE.md: if migrations/schema/prisma/supabase detected
- backend/DEPLOYMENT.md: if Docker / CI-CD / PaaS config / infra-as-code detected

## About optional conventions
- Create by area only if relevant conventions are detected.
- Examples of relevant conventions:
  - Coding style guides (e.g., Airbnb for JS/TS)
  - State management patterns (e.g., Redux, MobX)
  - Architectural patterns (e.g., MVC, MVVM)
  - Testing frameworks and strategies (e.g., Jest, Mocha)
  - Deployment practices (e.g., Docker usage, CI/CD pipelines)
  - UI/UX design systems (e.g., Material UI, Bootstrap)
  - etc...
- Name files as CONVENTIONS.md in each area folder.
  - frontend/CONVENTIONS.md
  - backend/CONVENTIONS.md

## Suggest only (SHOULD NOT auto-create unless asked)
- DECISIONS.md
- TESTING.md
- SECURITY.md
- OBSERVABILITY.md
- frontend/UI_UX.md
- backend/DATA.md

## Notes
- Never create files “just in case”.
- Keep diffs minimal.
- If in doubt: suggest, don’t create.
- Always align headings to v1 templates.