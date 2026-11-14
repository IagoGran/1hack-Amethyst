# Model and tool architecture

Models generate text and request tool calls through `ports/model_provider.py`. PydanticAI `Agent` owns the iterative sequence of model requests and tool calls. `application/pydantic_agent.py` bridges each request to the existing model-provider port and registers configured tools as schema-backed PydanticAI functions. Tool functions call `ToolDispatcher`, which retains responsibility for authorization, approvals, budgets, deadlines, redaction, and connector execution. A model adapter never executes a tool itself. `ModelRunner` still enforces and reports input/output usage for each provider request; the UI shows cumulative used and remaining task tokens.

## Adapter superclasses

- `adapters/models/base.py`: `ModelAdapter` shares credential/endpoint setup, model-capacity discovery, stream deadlines, and function declarations. `chat_completions.py` implements OpenAI, DeepSeek, and Ollama; `gemini.py` implements Gemini. `providers.py` preserves public provider imports.
- `adapters/tools/base.py`: `Tool` defines the abstract definition/execution role and shares bounded retrieval results with aligned sources. `ReadOnlySQLTool` shares SQL schemas, query admission, result formatting, and attribution; each driver retains its own enforcement. The vector family retains its shared retrieval implementation. Structural `AgentTool` implementations remain supported for injected tools and test doubles.
- `application/pydantic_agent.py`: translates persisted chat history to and from PydanticAI messages, registers the enabled `ToolDefinition` schemas as PydanticAI tools, and routes their execution through `ToolDispatcher`. `ProviderModel` adapts PydanticAI model requests to existing provider adapters and `ModelRunner`.
- `application/tools.py`: `NamedTool` wraps a configured connector with a stable alias and translates retrieval output to the agent's chunk contract. It preserves sources, call IDs, and truncation metadata. `application/runtime.py` retains its previous `NamedTool` import for compatibility.

## Connection configuration

- `configuration/catalog.py` contains immutable category, field, and result-shape metadata. The desktop and validation code consume this catalog rather than maintaining independent field lists.
- `configuration/models.py` validates model settings and constructs providers through `PROVIDER_FACTORIES`.
- `configuration/tools.py` validates resource settings and constructs tool adapters through `TOOL_FACTORIES`. Optional vendor clients load only when constructing their connector.
- `configuration/connection_validation.py` handles shared endpoint validation, required text, and recursive inline-secret rejection.
- `configuration/connections.py` preserves the existing validation, factory, kind, and secret-free export entry points. Existing connection records and credential references require no database migration.

The catalog and factories are explicit built-in registries. Dynamic plugin registration remains Pending; these internal boundaries do not introduce a plugin installation mechanism.

## Desktop settings

Connections contains independent **Models** and **Tools** tabs. `ModelConnectionPage` and `ToolConnectionPage` share `ConnectionEditor`; each filters its records and type choices and creates only its category's option widgets. Secrets remain masked and separate from persisted options. Blank replacement secrets preserve existing credential references. A name already used by the other category cannot be overwritten through the form. Operational limits remain a separate settings tab.

## Available agent tools

PydanticAI receives only tools enabled for the current task. Configured connectors expose read-only SQLite and PostgreSQL queries, Brave web search, and Qdrant, Milvus, or Chroma vector retrieval. When configured for the session, `workspace.read` reads permitted UTF-8 files, `workspace.edit` proposes a reviewed change, and `sandbox.run` runs an approved command in the container. The latter two protected operations remain subject to exact approval. Each configured connector receives a unique name derived from its connection kind and ID.

## Adding a built-in integration

1. Implement a model provider or tool behind its corresponding port; use the appropriate adapter superclass for shared behavior.
2. Add its `ConnectionKind` and `ConnectionSpec` to the catalog. For list-shaped retrieval results, specify the record field that becomes chunk content. SQL tools retain the `rows` contract.
3. Add settings validation and a factory to the matching model or tool configuration module. Keep secrets in the credential store and optional clients inside their factory. Tools become available to PydanticAI through their existing `ToolDefinition`; all execution must continue through `ToolDispatcher`.
4. Add deterministic contract tests for execution, health feedback, limits, sources, and invalid configuration. Verify the settings-to-runtime path. Do not change chat rendering or bypass application authorization to introduce an adapter.

## Validation

The broader refactor and removal of unused previews are documented in [code structure](code_structure.md). Test-only fake services and vendor fixtures are isolated in `tests/support/`.

`tests/integration/test_connection_page.py` covers category separation, saved-record loading, numeric options, credential-reference preservation, separate replacement secrets, and cross-category name protection. Existing adapter, runtime, and desktop tests cover provider streaming, aliases, source/result handoff, and task controls. Live services and visible desktop acceptance remain Pending.
