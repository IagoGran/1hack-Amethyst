# Environments

## Supported Environments

- Approved MVP platforms: Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2.
- Deployment: local, single-user, standalone desktop window. Desktop framework and packaging: `Pending`.
- Product commands and project tests: Docker Engine/runc on a local Linux daemon, restricted to a read-only approved workspace, with network disabled by default. The selected profile requires cgroup v2, resource controllers, and built-in seccomp; it remains disabled until host validation. See `docs/sandbox_runtime.md`.

## Environment Differences

Desktop smoke tests must cover both supported platform configurations, including GUI operation through WSL2. Credential-store availability must be handled explicitly: use memory-only credentials when the store is unavailable, including in WSL setups. S0 uses Python 3.13+ and credential-free fakes; development checks do not require a container runtime or desktop display. These developer checks are distinct from product command execution, which remains container-only. Other development/release environment differences: `Pending`.

## Environment Variables

The repository contains `.env` and `.env.example`. Names, example values, and purposes: `Pending` until relevant references are reviewed. Never copy secret values into context.

The live sandbox acceptance suite recognizes `AMETHYST_LIVE_SANDBOX=1`, `AMETHYST_SANDBOX_IMAGE` (a pre-provisioned repository digest), `AMETHYST_DOCKER_SOCKET` (default `/var/run/docker.sock`), and optional `AMETHYST_WINDOWS_BUILD` for the WSL2 report. These are test configuration, not production application settings. Opted-in misconfiguration fails rather than skips; the default test run never contacts Docker. See `docs/sandbox_runtime.md` for commands and the acceptance record.

## External Services by Environment

- Model providers: OpenAI API, Gemini API, DeepSeek API, and local Ollama models.
- External read-only SQL: SQLite 3 and PostgreSQL 16+.
- Locally hosted vector stores: Qdrant, Milvus, and ChromaDB.
- Web search: Brave Search API.
- Model connections use stdlib HTTP and do not add a runtime dependency. Install optional drivers with `uv sync --extra integrations` (or one of `--extra postgresql`, `--extra qdrant`, `--extra chroma`, `--extra milvus`). Exact model IDs and context windows remain `Pending`; endpoints and credentials are supplied through validated connection settings and opaque credential references. These selections do not choose the internal application database.

## Approved Operational Defaults

Requirements sections 5.5 and 5.6 are normative. Workstream B implements these controls through `configuration.limits.Limits` and the application/security services. Desktop settings and live adapter wiring remain Pending.

| Setting | Default |
|---|---|
| SQL/search/vector call timeout | 30 seconds |
| Model request timeout | 60 seconds idle; 300 seconds total |
| Sandbox command timeout | 120 seconds |
| Task timeout | 10 minutes, excluding approval waits |
| Task token budget | 100,000 cumulative input/output tokens, including retries |
| Per-request model limits | 32,000 input tokens; 8,000 output tokens, also constrained by model capacity |
| Retrieval limit | 8 chunks, at most 1,000 tokens each |
| SQL result limit | 1,000 rows |
| Tool-output limit | 1 MiB per call |
| Automatic retries | At most 2 after the initial attempt, only for transient failures |

Limits are configurable. Budget exhaustion pauses work until explicitly increased. Retries use exponential backoff with jitter and respect provider delays within the remaining deadline/budget. Do not automatically repeat file mutations or commands with uncertain outcomes; permission, authentication, and invalid-input failures require correction.

## Data Retention and Credentials

- Persist conversations locally until deleted, with MVP viewing, resumption, and deletion.
- Keep settings and saved skills until deleted.
- Discard raw retrieved content and copied workspace data after the task unless explicitly saved. Content incorporated into a retained conversation follows conversation retention; project files and source databases are unaffected.
- Expire redacted diagnostic logs after seven days. Provide an explicit option to save selected logs permanently until deleted, preserving redaction.
- Store credentials in the OS credential store. If unavailable, keep them only in memory and request them again after restart. Never fall back to plaintext disk storage.
- Normal logs contain operational metadata, excluding prompts, source code, query results, and tool-result bodies. Keep secrets out of ordinary chat, logs, errors, and configuration exports.
- The internal database uses SQLite at `$XDG_DATA_HOME/amethyst/amethyst.sqlite3`, falling back to `~/.local/share/amethyst/amethyst.sqlite3`. Repository values persist across process restarts. Encryption, backup, migration beyond schema version 1, and cleanup scheduling remain `Pending`. S0 memory repositories and credentials remain explicit development doubles and do not survive restart. See requirements section 5.7 for acceptance checks.

## Security Considerations

Do not commit secrets or expose them in conversations, logs, or errors. Use `.env.example` to document variable names without real credentials, and minimize each connection's permissions.
