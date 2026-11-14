# Amethyst Tool Inventory

This inventory distinguishes code that implements a tool, connection kinds that
can be constructed by configuration, and tools available in a particular task.
Runtime availability depends on the selected session, enabled connection,
optional adapter dependencies, workspace selection, and sandbox host validation.

## Configured connector tools

Connector tools receive a unique `kind_<connection-hash>` name. Read-only
connectors require a matching session permission grant or a one-action approval.

| Internal name | Function and implementation | Arguments | Access and authorization | Status / agent availability |
|---|---|---|---|---|
| `sqlite_<hash>` | Read-only query; `SQLiteReadOnlyTool` in `adapters/tools/sql.py` via `ReadOnlySQLTool` | `query: string` | Read-only; session grant or one-action approval; query admission and SQLite read-only connection | Implemented and covered by offline adapter tests; requires a valid enabled connection; registered only when configured for the task |
| `postgresql_<hash>` | Read-only query; `PostgreSQLReadOnlyTool` in `adapters/tools/sql.py` via `ReadOnlySQLTool` | `query: string` | Read-only; session grant or one-action approval; query admission and database-enforced read-only transaction | Implemented; requires connection settings and the optional `postgresql` extra; live server behavior is not verified by deterministic tests; registered only when configured |
| `brave_<hash>` | Web search; `BraveSearchTool` in `adapters/tools/web_search.py` | `query: string`, optional `count: integer` | Read-only; session grant or one-action approval; bounded result count and bytes | Implemented; requires an enabled connection and stored API key; live-service behavior is pending; registered only when configured |
| `qdrant_<hash>` | Vector retrieval; `QdrantTool` in `adapters/tools/vector.py` | `vector: number[]`, optional `limit: integer` | Read-only; session grant or one-action approval; bounded chunks and bytes | Implemented; requires endpoint, collection, and optional `qdrant` extra; live service is not verified; registered only when configured |
| `chroma_<hash>` | Vector retrieval; `ChromaTool` in `adapters/tools/vector.py` | `vector: number[]`, optional `limit: integer` | Read-only; session grant or one-action approval; bounded chunks and bytes | Implemented; requires endpoint, collection, and optional `chroma` extra; live service is not verified; registered only when configured |
| `milvus_<hash>` | Vector retrieval; `MilvusTool` in `adapters/tools/vector.py` | `vector: number[]`, optional `limit: integer` | Read-only; session grant or one-action approval; bounded chunks and bytes | Implemented; requires endpoint, collection, and optional `milvus` extra; live service is not verified; registered only when configured |

## Workspace and sandbox tools

These names are reserved and appear only when their runtime dependencies are
selected. They are registered per task and all calls still pass through
`ToolDispatcher`.

| Internal name | Function and implementation | Arguments | Access and authorization | Status / agent availability |
|---|---|---|---|---|
| `workspace.read` | Read permitted UTF-8 files; `Workspace.read` in `security/workspace.py` | `path: string` | Read-only; explicit workspace read grant or one-action approval; path and file safety checks | Implemented; available only after workspace selection; task registration does not itself grant permission |
| `workspace.edit` | Propose and apply a reviewed diff; `Workspace.propose/apply` in `security/workspace.py` | `path: string`, `content: string \| null` | Modifies files; explicit approval bound to the exact diff and current file state | Implemented; available only after workspace selection and only executes after approval |
| `sandbox.run` | Run a command in the container; `DockerSandbox.run` in `security/sandbox.py` | `argv: string[]`, optional `working_directory: string`, optional `network_enabled: boolean` | Command execution; explicit approval bound to the exact request; container-only, read-only workspace, network denied by default | Implemented but runtime disabled until image/host validation; available only when the validated sandbox is configured and enabled |

## Session availability rules

- `configuration/catalog.py` and `configuration/tools.py` define built-in
  connection kinds and adapter factories. A configured connection is not proof
  that its service is reachable or its optional client is installed.
- `DesktopRuntime.configure()` includes enabled connectors whose adapter
  construction succeeds. Failed or unavailable connectors are omitted and
  reported as runtime warnings.
- `AgentService` registers only currently enabled connector bindings and the
  workspace/sandbox tools whose dependencies are present. The dispatcher
  rechecks authorization and enabled state when each call executes.
- Live provider, connector, and real-container acceptance remains pending unless
  separately reported as completed in the test and environment records.
