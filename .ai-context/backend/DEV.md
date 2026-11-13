# Backend Development

## Backend Stack

Python is indicated by `pyproject.toml`; the framework, runtime, and concrete dependencies remain `Pending`.

## Directory Structure

The package is `src/1hack_amethyst/`, divided into `application/`, `domain/`, `ports/`, `adapters/`, `security/`, `skills/`, and `configuration/`. Specific adapters remain pending.

## Local Development

Install runtime and development dependencies with `uv sync --group dev`, then start the provisional CLI with `uv run 1hack-amethyst`.

## Build and Packaging

Build the package with `uv build`.

## Environment Variables

See `.ai-context/ENVIRONMENT.md`. Do not include secret values.

## Endpoints and Interfaces

API and internal contracts: `Pending`.

## Data and Persistence

Internal SQL engine and persistence for conversations/skills: `Pending`. User SQL in the requirements refers to an external read-only tool.

## Debugging

Tools and workflow: `Pending`.

## Backend-Specific Conventions

See `.ai-context/CONVENTIONS.md` and `.ai-context/TESTING.md`.

## Backend Change Checklist

- [ ] Keep providers and connectors decoupled through contracts.
- [ ] Check authorization before executing protected tools.
- [ ] Restrict SQL queries to read-only where applicable.
- [ ] Protect credentials and minimize transmitted data.
- [ ] Update context when interfaces, persistence, or configuration change.
