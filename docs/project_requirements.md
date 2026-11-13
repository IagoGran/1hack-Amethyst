# AI Coding Agent — Project Requirements

## 1. Project Overview

The project aims to develop an AI-powered coding agent that can generate, inspect, and improve source code while using external resources—including SQL databases, web search, and vector stores—to support its work. Users interact with the agent through a chat interface and retain control over resource connections, local access, file modifications, and reusable skills.

## 2. Scope and Conventions

- **System** refers to the complete application; **agent** refers to the LLM-driven component that plans tasks and uses tools.
- **MVP** identifies functionality for the initial usable release; **Later** identifies an enhancement that can follow. These classifications remain recommendations except where explicitly approved in section 5.
- **Origin** distinguishes **Original** requirements (retained or clarified from the initial list) from **Added** requirements proposed in this revision.
- All requirements use **shall** for mandatory behavior *within their approved release scope*. Section 5 records approved acceptance criteria; remaining technology and implementation choices are to be agreed during design.

## 3. Functional Requirements

### 3.1 User Interface and Interaction

| ID | Requirement | Release | Origin |
|---|---|---|---|
| FR-01 | **Interactive chat:** The system shall allow users to exchange messages with the agent through a chat interface. | MVP | Original |
| FR-02 | **Streaming output:** The system shall display the agent's response incrementally as it is generated when supported by the selected model. | MVP | Added |
| FR-03 | **Unified settings interface:** The system shall provide an interface for configuring models, resource connections, permissions, and skills. | MVP | Original |
| FR-04 | **Conversation history:** The system shall persist conversations until deleted and allow users to view, resume, and delete them. | MVP | Added |
| FR-05 | **Task cancellation:** The system shall allow users to stop an active agent task and prevent further tool calls after cancellation takes effect. | MVP | Added |

### 3.2 Agent Reasoning and Task Management

| ID | Requirement | Release | Origin |
|---|---|---|---|
| FR-06 | **Task-state assessment:** Before beginning work, the agent shall inspect relevant available context and determine whether the requested task has already been started or partially completed. | MVP | Original |
| FR-07 | **Task planning:** For multi-step requests, the agent shall identify the steps needed to complete the task before performing consequential actions. | MVP | Added |
| FR-08 | **Progress reporting:** The system shall indicate whether a task is running, paused awaiting a budget increase, completed, cancelled, or failed and display meaningful progress updates for multi-step tasks. | MVP | Added |
| FR-09 | **Tool orchestration:** The agent shall be able to select and invoke enabled tools when they are relevant to a user request. | MVP | Added |
| FR-10 | **Result validation:** After a tool call, the agent shall inspect its result and determine whether additional actions or corrections are necessary. | MVP | Added |
| FR-11 | **Failure recovery:** When a tool call fails, the agent shall report the failure and either retry within configured limits, choose an authorized alternative, or stop safely. | MVP | Added |

### 3.3 Code Generation and Development

| ID | Requirement | Release | Origin |
|---|---|---|---|
| FR-12 | **Code generation:** The agent shall generate source code in response to user requests. | MVP | Original |
| FR-13 | **Existing-code inspection:** With appropriate authorization, the agent shall read project files to understand an existing codebase before proposing changes. | MVP | Added |
| FR-14 | **Code modification:** With required approvals, the agent shall create or modify project files to implement requested changes. | MVP | Added |
| FR-15 | **Change preview:** Before modifying an existing file, the system shall present the proposed change or a meaningful diff for user review. | MVP | Added |
| FR-16 | **Command execution:** The agent shall be able to run explicitly authorized development commands inside a container sandbox restricted to the approved workspace, with network access disabled by default. | MVP | Added |
| FR-17 | **Test execution:** Where a project provides a runnable test suite and execution is authorized, the agent shall be able to run tests inside the approved container sandbox and report their results. | MVP | Added |
| FR-18 | **Debugging support:** The agent shall be able to analyze supplied error messages, logs, or test failures and suggest or implement fixes subject to permission checks. | MVP | Added |

### 3.4 External Tools and Data Sources

| ID | Requirement | Release | Origin |
|---|---|---|---|
| FR-19 | **SQL connectivity:** The system shall allow users to configure connections to supported SQL databases. | MVP | Original |
| FR-20 | **Database queries:** The agent shall be able to execute authorized read-only SQL queries and use the returned results in its response. | MVP | Added |
| FR-21 | **Web search:** The agent shall be able to submit search-engine queries and retrieve results. | MVP | Original |
| FR-22 | **Vector retrieval:** The agent shall be able to query a configured vector store for relevant content to support retrieval-augmented generation (RAG). | MVP | Original |
| FR-23 | **Source attribution:** When the response draws on retrieved external information, the system shall show the corresponding source or resource identifier when available. | MVP | Added |
| FR-24 | **Tool configuration:** Users shall be able to add, edit, enable, disable, and test supported resource connections. | MVP | Original |
| FR-25 | **Extensible integrations:** The system shall support registering additional tools or connectors without redesigning the chat interface. | Later | Added |

### 3.5 Security and Permission Management

| ID | Requirement | Release | Origin |
|---|---|---|---|
| FR-26 | **Local environment inspection:** The agent shall inspect the user's machine or local files only when the user has granted permission for the requested scope. | MVP | Original |
| FR-27 | **File modification approval:** Before changing any existing file, the agent shall obtain explicit user approval of the displayed diff, individually or within an explicitly listed batch. Changed proposals shall require renewed approval. | MVP | Original |
| FR-28 | **Scoped permissions:** Users shall be able to grant, inspect, and revoke permissions for tools and local resources. | MVP | Added |
| FR-29 | **High-impact action approval:** The agent shall request explicit approval before performing destructive actions, database writes, or other actions designated as high impact. | MVP | Added |
| FR-30 | **Approval enforcement:** The system shall prevent tool execution if the required approval has not been granted or has been revoked. | MVP | Added |
| FR-31 | **Action history:** The system shall record tool invocations, their outcomes, and relevant approval decisions for later inspection. | Later | Added |

### 3.6 Skills and Customization

| ID | Requirement | Release | Origin |
|---|---|---|---|
| FR-32 | **Skill creation and storage:** Users shall be able to create and save reusable agent skills. | MVP | Original |
| FR-33 | **Skill management:** Users shall be able to view, edit, enable, disable, and delete saved skills. | MVP | Original (expanded) |
| FR-34 | **Skill application:** The agent shall be able to apply enabled skills when explicitly selected by the user or when their configured conditions are met. | MVP | Added |
| FR-35 | **Model configuration:** Users shall be able to choose from supported language models and configure available model parameters. | Later | Added |

## 4. Non-Functional Requirements

### 4.1 Performance and Efficiency

| ID | Requirement | Release | Origin |
|---|---|---|---|
| NFR-01 | **Token efficiency:** The agent shall avoid unnecessary prompts, repeated context, and redundant tool calls while preserving response correctness and completeness. | MVP | Original |
| NFR-02 | **Responsiveness:** The interface shall remain usable during model generation and tool execution, with visible status feedback for long-running operations. | MVP | Added |
| NFR-03 | **Resource limits:** The system shall enforce configurable limits on task and tool execution time, tokens, retries, retrieval size, and output size as defined in section 5. | MVP | Added |

### 4.2 Security and Privacy

| ID | Requirement | Release | Origin |
|---|---|---|---|
| NFR-04 | **Credential protection:** The system shall protect stored credentials and shall not expose secrets in ordinary chat messages, application logs, or error output. | MVP | Added |
| NFR-05 | **Least privilege:** Tools and connectors shall operate with no more access than required for the approved task. | MVP | Added |
| NFR-06 | **Isolation:** Agent-executed commands shall run inside a container sandbox restricted to the approved workspace, with network access disabled by default. | MVP | Added |
| NFR-07 | **Data minimization:** The system shall minimize the transmission and retention of local files, database content, and other sensitive material not required for the active request. | MVP | Added |

### 4.3 Reliability and Robustness

| ID | Requirement | Release | Origin |
|---|---|---|---|
| NFR-08 | **Graceful degradation:** The application shall remain usable when an external model, database, search provider, or vector store is unavailable, and shall communicate the limitation. | MVP | Added |
| NFR-09 | **Recoverable failures:** Tool failures shall not cause silent data loss or leave the interface indefinitely in a running state. | MVP | Added |
| NFR-10 | **State consistency:** The system shall keep task state, permission state, and displayed tool results consistent with actual execution outcomes. | MVP | Added |

### 4.4 Maintainability and Extensibility

| ID | Requirement | Release | Origin |
|---|---|---|---|
| NFR-11 | **Modularity:** Model providers, external connectors, and skill management shall be implemented behind clearly defined interfaces. | MVP | Added |
| NFR-12 | **Testability:** Core permission checks, tool execution paths, and task-state transitions shall be covered by automated tests. | MVP | Added |
| NFR-13 | **Configuration portability:** Application configuration shall be exportable and importable without including plaintext secrets. | Later | Added |

### 4.5 Usability and Transparency

| ID | Requirement | Release | Origin |
|---|---|---|---|
| NFR-14 | **Clarity:** Permission requests, error messages, and tool results shall be understandable to the intended users. | MVP | Added |
| NFR-15 | **Action transparency:** The interface shall distinguish between proposed actions, actions awaiting approval, actions completed, and actions that failed. | MVP | Added |
| NFR-16 | **Accessibility:** The primary interface shall support keyboard navigation and accessible labels for interactive controls. | MVP | Added |

## 5. Approved Acceptance Criteria

The project owner approved the following decisions on 2026-11-13. They define the acceptance baseline for the MVP and take precedence over conflicting release recommendations. Approval of these criteria does not mean they are implemented or validated, and does not approve unrelated recommendations elsewhere in this document.

### 5.1 Supported Platforms and Deployment

- The system shall support Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2.
- The system shall run locally as a single-user desktop application with its own standalone window, rather than requiring a browser interface.
- Acceptance shall include launching the desktop application and exercising its primary workflows on both supported platform configurations, including GUI operation through WSL2.
- Configured external model and data services may be accessed from the local application. Server and hybrid application deployment are outside the approved initial deployment scope.
- The desktop framework and packaging technology remain design decisions; these acceptance criteria do not select them.

### 5.2 Supported Providers and Data Sources

The MVP shall support each integration below through the modular provider and connector interfaces.

| Category | Approved integrations | Acceptance expectations |
|---|---|---|
| Language models | OpenAI API, Gemini API, DeepSeek API, and local Ollama models | Configure the provider and model ID, generate a response, stream when supported, and report connection/authentication failures without leaving the application unusable. |
| External read-only SQL | SQLite 3 and PostgreSQL 16+ | Configure and test connections, execute authorized read-only queries, and reject writes. These choices do not select the application's internal persistence engine. |
| Vector retrieval | Locally hosted Qdrant, Milvus, and ChromaDB | Configure and test each connection, retrieve relevant content within the selected limits, and preserve available source/resource identifiers. |
| Web search | Brave Search API | Configure and test the connection, retrieve search results within the selected limits, and preserve available source URLs. |

Exact SDK versions and model IDs are implementation configuration choices. Broader model-parameter controls in FR-35 and extensible registration in FR-25 remain later-release recommendations.

### 5.3 Command and Test Execution

- Authorized development commands and project test suites shall run in the MVP (FR-16 and FR-17).
- Execution shall occur inside a container sandbox restricted to the approved workspace; host-local command execution is outside the approved scope.
- Sandbox network access shall be disabled by default. Enabling it requires explicit authorization for the requested scope.
- Acceptance tests shall verify workspace boundaries, default network denial, permission enforcement, timeouts, cancellation, and result reporting. Command execution shall not bypass file-modification approval.
- NFR-06 isolation is an MVP requirement alongside these execution capabilities.

### 5.4 Approval Scope and Lifetime

- A protected-action approval shall cover one action or an explicitly listed batch of actions and diffs. A task-level request alone shall not authorize unspecified future protected actions.
- Existing-file edits require approval of the displayed diff. Changed proposals, including changes to the file state that invalidate the reviewed diff, require renewed approval.
- Approval is consumed by execution of its listed actions and expires no later than task completion. Unused approvals shall not carry into a new task or app session.
- Read-only access grants may last for the current application session and shall expire on app exit.
- Users shall be able to inspect and revoke granted permissions. Revocation shall block further protected actions, including unexecuted actions in a previously approved batch.
- Acceptance shall verify individual and batch approval, denial, expiry, revocation, and changed-diff invalidation (FR-15 and FR-26 through FR-30).

### 5.5 Responsiveness and Timeouts

Performance acceptance shall measure p95 over at least 30 runs for each tested reference configuration, recording the machine, operating system, model/provider, and network conditions. A typical task has at most three tool calls and 1,000 generated tokens. Time waiting for user approval is excluded; local-model cold starts shall be measured and reported separately.

| Metric | Approved p95 target |
|---|---|
| First visible model token, measured from model-request dispatch for streaming-capable models | At most 10 seconds |
| Typical task duration, from submission to completion | At most 120 seconds |
| Visible UI status feedback following a user action | At most 200 milliseconds |

The following execution limits shall be configurable and applied by default:

| Operation | Default timeout |
|---|---|
| SQL, web-search, or vector-retrieval call | 30 seconds per call |
| Model request inactivity | 60 seconds without progress |
| Model request total duration | 300 seconds |
| Sandbox command | 120 seconds |
| Entire task | 10 minutes, excluding approval waits |

A timeout shall end the operation's running state and report its outcome; the application shall remain usable. Retries shall respect the remaining task deadline.

### 5.6 Token, Retrieval, Output, and Retry Limits

All limits below shall be configurable. The system shall enforce the lower of its configured limits and the selected model's capacity; input and reserved output together must fit that capacity.

| Resource | Default limit |
|---|---|
| Cumulative model input plus output per task, including retries | 100,000 tokens |
| Model input per request | 32,000 tokens |
| Model output per request | 8,000 tokens |
| Retrieval per call | 8 chunks, each at most 1,000 tokens |
| SQL result per call | 1,000 rows |
| Tool output per call | 1 MiB (1,048,576 bytes) |
| Automatic retries after the initial attempt | At most 2 |

- Reaching the task token budget shall pause work until the user explicitly increases it; the system shall not silently start another model request beyond the remaining budget.
- Both row/chunk limits and the tool-output byte limit apply to the same result. The interface shall identify truncated results.
- Automatic retries shall apply only to transient failures, use exponential backoff with jitter, and respect provider retry delays within the remaining deadline and token budget.
- Permission, authentication, and invalid-input failures require correction instead of automatic retry.
- File mutations and commands with uncertain outcomes shall never be repeated automatically.

### 5.7 Data Retention, Credentials, and Logs

- Conversations shall persist locally until the user deletes them. Viewing, resuming, and deleting conversations are MVP capabilities (FR-04).
- Settings and saved skills shall remain until deleted.
- Retrieved content and copied workspace data shall be discarded after the task unless explicitly saved. User project files and source databases are unaffected. Content incorporated into a retained conversation follows that conversation's retention policy; separate raw retrieval and workspace copies shall not be retained by default.
- Redacted diagnostic logs shall expire after seven days. Users shall have an explicit option to save selected logs permanently; saved copies remain until deleted and shall retain the same redaction rules.
- Credentials shall be stored in the operating system's credential store. If unavailable, including in WSL setups, credentials shall remain in memory only and be requested again after restart. There shall be no plaintext disk fallback.
- Configuration exports, ordinary chat messages, logs, and error output shall not expose secrets.
- Normal diagnostic logs shall contain operational metadata, excluding prompts, source code, query results, and tool-result bodies. Diagnostic logging does not bring the richer action-history interface in FR-31 into the MVP.
- Acceptance shall verify conversation persistence/resumption/deletion, seven-day log expiry and explicit permanent saving, temporary-data cleanup, credential-store fallback, and secret redaction.

### 5.8 MVP Automated Testing Gate

- All critical-path tests shall pass. Required paths are approval denial/revocation, approval lifetime and batch scope, changed-diff invalidation, read-only SQL, sandbox boundaries and default network denial, cancellation, timeouts/retries, budget enforcement, secret redaction, and task-state consistency.
- Automated tests shall achieve at least 80% aggregate branch coverage across the domain, application, and security modules.
- Every selected model provider and connector in section 5.2 shall have adapter contract tests.
- Desktop smoke tests shall cover Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2, including chat, settings, approvals, conversation history, and sandboxed execution workflows.
- Deterministic automated checks shall run without live credentials. Tests that exercise live services and performance measurements shall be explicitly configured and report their environment separately.
- The functional checks in sections 5.1 through 5.7 form part of acceptance; the coverage percentage does not replace them.

## 6. MVP Boundary and Remaining Recommendations

The approved decisions in section 5 include the standalone desktop deployment and selected integrations, conversation viewing/resumption/deletion, sandboxed command and test execution, scoped approvals, operational limits, retention and credential handling, and the automated testing gate. FR-04, FR-16, FR-17, and NFR-06 therefore belong to the MVP.

The remaining suggested MVP boundary includes chat, code generation and inspection, task-state checks, database read access, web search, vector retrieval, basic skills, explicit approval workflows, and configurable connections, as constrained by the approved decisions above. Richer action history, extensible connector registration, broader model-parameter controls, and portable configuration remain later-release recommendations.

> **Note:** Section 5 records project-owner decisions. Other MVP/Later classifications and **Added** requirements remain recommendations unless explicitly adopted there. The **Origin** column records provenance, not approval status.
