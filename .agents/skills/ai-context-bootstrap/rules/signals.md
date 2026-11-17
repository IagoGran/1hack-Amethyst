# Signals (v1)
# Señales para inferir estructura del proyecto SIN leer código

## Señales generales
- README.md existente -> proyecto documentado parcialmente
- docker-compose.yml OR Dockerfile -> proyecto dockerizado
- .env OR .env.* -> uso de variables de entorno
- .github/workflows/* -> existe CI/CD

## Frontend
- package.json -> frontend presente (posible Node-based)
- pnpm-lock.yaml OR yarn.lock -> frontend moderno
- astro.config.* -> Astro
- vite.config.* -> Vite
- next.config.* -> Next.js
- public/ OR src/components/ -> frontend estructurado

## Backend
- composer.json -> backend PHP
- pom.xml -> backend Java
- requirements.txt OR pyproject.toml -> backend Python
- package.json con frameworks server -> backend Node
- api/ OR src/api/ -> backend con endpoints

## Base de datos
- prisma/schema.prisma -> base de datos gestionada con Prisma
- migrations/ OR database/migrations/ -> base de datos con migraciones
- schema.sql -> base de datos SQL
- supabase/ -> Supabase (DB + Auth)
- firebase.json -> Firebase (DB/Auth)

## API
- openapi.yaml OR openapi.json
- swagger.yaml OR swagger.json
- docs/api.* -> API documentada
- backend expuesto + frontend consumidor -> API implícita

## Despliegue
- Dockerfile OR docker-compose.yml -> DEPLOYMENT.md requerido
- vercel.json OR netlify.toml -> despliegue gestionado
- terraform/ OR infra/ -> infraestructura como código
- render.yaml OR fly.toml -> plataforma PaaS

## Arquitectura
- frontend + backend detectados -> ARCHITECTURE.md requerido
- múltiples servicios -> ARCHITECTURE.md requerido
- uso de servicios externos relevantes -> ARCHITECTURE.md recomendado
