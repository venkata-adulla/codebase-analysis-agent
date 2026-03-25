# Codebase Analysis Agent Project Reference

This document is the deep-dive reference for the `codebase-analysis-agent` project. It is written to help an operator, developer, reviewer, or demo owner explain:

- what the product does
- what each UI page means
- what each control on those pages does
- which backend code powers each feature
- how data moves through the system
- where the important calculations and heuristics live
- what is implemented today vs. partially implemented vs. stubbed

If someone asks "How does this feature work?" or "Where is that logic implemented?", this document should be your first reference.

## 1. What this project is

The project is a two-tier monorepo with:

- a FastAPI backend in `backend/`
- a Next.js frontend in `frontend/`

Its purpose is to analyze source repositories and present several views of the analysis:

- repository intake and analysis orchestration
- recent analyses dashboard
- dependency graph visualization
- service inventory
- impact analysis
- technical debt analysis
- human review checkpoints

At a high level, the system clones or links a repository, runs a multi-agent analysis workflow, stores structured results, and exposes those results to the UI through REST APIs.

## 2. High-level architecture

### Frontend

The frontend lives in `frontend/` and uses:

- Next.js App Router
- React
- React Query for API calls and caching
- React Flow for graph visualization
- Recharts for charts on the tech-debt page

Frontend entry points are mostly under `frontend/app/`.

### Backend

The backend lives in `backend/` and uses:

- FastAPI for HTTP APIs
- SQLAlchemy for PostgreSQL models
- Neo4j for graph storage
- Alembic migrations on startup
- a custom agent orchestrator for multi-step analysis

Backend entry point:

- `backend/main.py`

### Data stores

The project is designed to use multiple backing services:

- PostgreSQL: canonical metadata and reports
- Neo4j: dependency graph and impact traversal
- Redis: available for caching, but not central to the current UI flows
- Qdrant: available for vector search, but not central to the current UI flows

In the current implementation, PostgreSQL and Neo4j matter most for visible product features.

## 3. Repository structure

### Important frontend locations

- `frontend/app/` - page routes
- `frontend/components/` - reusable UI and feature components
- `frontend/lib/` - API client and display helpers

### Important backend locations

- `backend/api/routes/` - REST endpoints used by the frontend
- `backend/agents/` - workflow agents
- `backend/services/` - main business logic and calculations
- `backend/models/` - database models
- `backend/core/` - configuration, DB setup, security
- `backend/parsers/` - static code parsing logic

## 4. Runtime startup and configuration

### Backend application startup

File:

- `backend/main.py`

What happens on startup:

- FastAPI app is created
- CORS is configured
- rate limiting is configured
- all route modules are registered
- `init_db()` runs at startup
- Neo4j driver is closed on shutdown

### Configuration

File:

- `backend/core/config.py`

Important settings:

- Neo4j connection: `neo4j_uri`, `neo4j_user`, `neo4j_password`
- PostgreSQL connection: `postgres_*`, `postgres_url`
- Qdrant and Redis connection settings
- OpenAI settings for optional documentation generation
- GitHub token for GitHub mode cloning
- API host, port, and `api_key`
- file storage paths such as `repositories_dir`
- `orchestrator_pause_on_checkpoints`

Important behavior:

- `orchestrator_pause_on_checkpoints` controls whether analysis stops when a human-review checkpoint is opened
- default API key is `dev-local-key`

### Database setup

File:

- `backend/core/database.py`

What it does:

- creates the SQLAlchemy engine and session factory
- creates the Neo4j driver lazily
- exposes Qdrant and Redis clients
- runs Alembic migrations through `init_db()`

## 5. End-to-end analysis flow

This is the most important product flow.

### Step 1: user starts analysis from the UI

Frontend page:

- `frontend/app/analyze/page.tsx`

API called:

- `POST /api/repositories/analyze`

Backend file:

- `backend/api/routes/repositories.py`

What the backend does:

- generates a new repository UUID
- clones from GitHub or generic Git URL, or links/copies a local repo path
- inserts a `Repository` row in PostgreSQL
- queues background analysis with `run_analysis_task`

### Step 2: repository is acquired

Backend file:

- `backend/services/repository_manager.py`

Modes:

- `clone_from_github(owner, repo, branch)`
- `clone_from_url(url, branch)`
- `use_local_path(path)`

Important note:

- On Windows, local repositories are copied into the managed repository folder instead of symlinked.

### Step 3: orchestrator creates a run

Backend file:

- `backend/services/agent_orchestrator.py`

What it tracks:

- run id
- repository id
- current agent
- completed agents
- shared `AgentState`
- checkpoint list

### Step 4: workflow agents run in order

The registered workflow in `backend/api/routes/repositories.py` is:

1. `planning_agent`
2. `code_browser_agent`
3. `dependency_mapper_agent`
4. `tech_debt_agent`
5. `documentation_agent`
6. `impact_agent`
7. `human_review_agent`

### Step 5: workflow results are persisted

After workflow completion:

- tech-debt state is saved to PostgreSQL via `save_tech_debt_report`
- services and documentation snippets are saved via `persist_services_and_docs`

### Step 6: status is exposed to the UI

Frontend polls:

- `GET /api/repositories/{repository_id}/status`

Backend status logic lives in:

- `backend/api/routes/repositories.py`

That endpoint merges:

- in-memory active analysis state
- orchestrator progress
- stored repository status from PostgreSQL

## 6. Agent-by-agent explanation

### `planning_agent`

File:

- `backend/agents/planning_agent.py`

Purpose:

- early repository inspection
- collect file/language information
- build an analysis plan for downstream steps

Why it exists:

- gives the pipeline a structured starting point before deeper parsing

### `code_browser_agent`

File:

- `backend/agents/code_browser_agent.py`

Purpose:

- parse code files with `CodeParserService`
- extract code elements such as classes/functions/methods
- extract imports

Output stored in state:

- `parsed_files`
- `code_elements`
- `imports`

Why it matters:

- tech-debt analysis depends on `code_elements`
- documentation agent uses discovered elements to infer service-level context

### `dependency_mapper_agent`

File:

- `backend/agents/dependency_mapper_agent.py`

Purpose:

- run repository dependency discovery
- create service nodes and dependency edges in Neo4j
- populate service metadata such as classification and entry points

Important collaborator files:

- `backend/services/dependency_analyzer.py`
- `backend/services/graph_service.py`

Important logic:

- clears the previous graph for the repository before rewriting it
- resolves import targets to known services with `_resolve_target_service`
- skips self-loop dependencies

### `tech_debt_agent`

File:

- `backend/agents/tech_debt_agent.py`

Purpose:

- run static debt analysis during the pipeline

Important behavior:

- reuses `code_elements`
- reuses discovered `services`
- loads dependency graph if needed

### `documentation_agent`

File:

- `backend/agents/documentation_agent.py`

Purpose:

- generate service descriptions using OpenAI when `OPENAI_API_KEY` is configured

Important note:

- if no OpenAI key is configured, this feature degrades gracefully
- the visible documentation in the Services UI is stored as `Service.description`, not served by a fully implemented standalone documentation API

### `impact_agent`

File:

- `backend/agents/impact_agent.py`

Purpose:

- prepare impact-related state during the main pipeline

Important note:

- the real user-facing impact calculation happens later in `ImpactEngine` when the user runs impact analysis on demand

### `human_review_agent`

File:

- `backend/agents/human_review_agent.py`

Purpose:

- identify ambiguous or unclear analysis situations
- create checkpoints for operator review

Current checkpoint types:

- ambiguous dependencies
- unclear service boundaries

Important logic:

- compares dependency targets against known service names and module names
- stores detailed explanation context for display in the UI

## 7. Core service layer and where logic lives

### Repository intake

File:

- `backend/services/repository_manager.py`

Main jobs:

- clone repos
- validate local paths
- list repository files
- collect repo metadata

### Static parsing

File:

- `backend/services/code_parser.py`

Delegates to parsers in:

- `backend/parsers/python_parser.py`
- `backend/parsers/javascript_parser.py`
- `backend/parsers/java_parser.py`

Purpose:

- parse files
- extract code elements
- extract imports and dependencies

### Dependency discovery

File:

- `backend/services/dependency_analyzer.py`

This is one of the most important files in the project.

What it does:

- identifies service boundaries using repository indicators
- falls back to code-cluster discovery if needed
- switches to Python module-level analysis for Python library repos
- detects module classifications
- detects entry points
- extracts dependency candidates per service/module

Important outputs:

- `services`
- `modules`
- `dependencies`
- `api_endpoints`
- `databases`
- `message_queues`
- `entry_points`
- `classification_summary`

Important heuristics:

- service indicators include files like `main.py`, `app.py`, `package.json`, `pyproject.toml`, `Dockerfile`, and more
- if the repository looks like a Python package/library, it analyzes Python files as module-level services
- classifies Python files into categories like `test`, `example`, `documentation`, `entrypoint`, `package_root`, `core_library`, and `application_module`

### Graph storage and analytics

File:

- `backend/services/graph_service.py`

Purpose:

- create Neo4j nodes and edges
- query service dependencies
- compute direct and indirect graph views
- compute architecture summaries
- support impact traversal

Main write operations:

- `create_service_node`
- `create_file_node`
- `create_function_node`
- `create_dependency`
- `create_api_call`
- `create_database_connection`

Important graph safeguards:

- metadata is JSON-serialized because Neo4j properties cannot store Python dicts directly
- self-loop dependencies are blocked
- dependencies with empty endpoints are blocked

Important read/analysis methods:

- `get_service_dependencies`
- `get_dependency_graph`
- `find_impacted_services`

Important calculations:

- `_compute_indirect_edges`: BFS-based transitive dependency edges up to a depth limit
- `_compute_cycle_count`: counts detected cycles
- `_build_architecture_summary`: computes service counts, direct/indirect counts, isolation, entry-point counts, classification counts, top fan-in/fan-out, cycles

### Graph fallback

File:

- `backend/services/dependency_graph_fallback.py`

Purpose:

- provide at least a basic graph response from Postgres services when Neo4j is unavailable or empty

Why it exists:

- lets the Dependency Graph page still render nodes even if graph edges are missing

### Impact analysis

File:

- `backend/services/impact_engine.py`

Purpose:

- estimate blast radius of a proposed change

Input modes:

- selected services
- changed file paths
- change-description-only heuristics

Important calculations:

- `_heuristic_surface_impact`: estimates direct risk based on language, keywords, classification, and entry points
- `_match_services_from_files`: maps changed file paths to persisted services
- `_calculate_impact_score`: reduces score as graph depth increases and adjusts for keywords like `breaking`, `remove`, `delete`, `add`, `optimize`
- `_calculate_risk_level`: aggregates service impacts into overall risk
- `_generate_recommendations`: produces response guidance based on risk and impact profile

Important graph usage:

- reads the dependency graph from Neo4j
- finds transitive downstream dependents with `find_impacted_services`
- includes architecture summary data in the result

### Technical debt analysis

File:

- `backend/services/tech_debt_analyzer.py`

Purpose:

- orchestrate debt analysis across categories

Sub-analyzers:

- `CodeQualityAnalyzer`
- `ArchitectureAnalyzer`
- `DependencyVulnerabilityScanner`
- `DocumentationDebtAnalyzer`

Important calculations:

- `_calculate_category_scores`
- `calculate_debt_score`
- `prioritize_debt`
- debt density based on issue count per 1000 lines

Important behavior:

- category scores are weighted by severity and impact
- overall debt score is a weighted average of category scores
- `assessment_coverage` explains whether a category is fully assessed or only partially supported

### Service and documentation persistence

File:

- `backend/services/service_persistence.py`

Purpose:

- upsert service inventory into PostgreSQL
- merge documentation-agent output into `Service.description`
- keep repository service inventory synchronized across reruns

Important behavior:

- stale services from older runs are deleted if they are not present in the latest incoming list

### Tech-debt persistence

File:

- `backend/services/tech_debt_persistence.py`

Purpose:

- save latest debt report and debt items into PostgreSQL

Stored output:

- `TechDebtReport`
- `TechDebtItem`

## 8. Database models and what they mean

### Repository model

File:

- `backend/models/repository.py`

`Repository` stores:

- analysis ID
- repository name/URL
- local path to cloned or linked repo
- branch
- status
- progress
- message

Important meaning:

- the "Analysis ID" shown in the UI is effectively the repository record ID used across the app

### Service-related models

File:

- `backend/models/service.py`

`Service` stores:

- service/module ID
- repository ID
- service name
- language
- description
- file path
- metadata

Metadata currently includes:

- `module_name`
- `classification`
- `entry_points`
- `entry_point_count`

Other models in the same file:

- `Documentation`
- `ImpactAnalysis`
- `HumanReview`

Important note:

- some of these tables exist for broader design intent, but the current UI relies more on orchestrator state and service persistence than on all of these tables being fully used

### Technical debt models

File:

- `backend/models/tech_debt.py`

Models:

- `TechDebtItem`
- `TechDebtReport`
- `DebtRemediationPlan`
- `DebtMetricsHistory`

These support:

- debt reports
- debt item filtering
- remediation planning
- trend views over time

## 9. Frontend shell and navigation

### App shell

File:

- `frontend/components/layout/app-shell.tsx`

What it does:

- defines the left navigation for desktop
- defines a reduced top bar for mobile
- shows the "Workspace ready" badge

Main navigation entries:

- Overview
- Analyze
- Dashboard
- Dependencies
- Services
- Impact
- Tech debt
- Human Review

### Page header

File:

- `frontend/components/layout/page-header.tsx`

Purpose:

- standard page title, description, and actions region

## 10. Frontend feature-by-feature reference

This section describes every user-facing page, its modules/controls, what they mean, and what backend code powers them.

### A. Overview page

Route:

- `/`

Files:

- `frontend/app/page.tsx`

Purpose:

- landing page for the product
- quick launch entry point into major features

Visible modules:

- hero section with product summary
- "Start with a Git URL" action
- feature cards for major product areas

Meaning:

- this page is primarily a navigation and positioning page
- it does not run analysis itself

Backend dependency:

- none directly beyond global app availability

### B. Analyze page

Route:

- `/analyze`

Files:

- `frontend/app/analyze/page.tsx`

Purpose:

- start repository analysis
- track the live status of the multi-agent workflow

Visible modules:

- source mode selector
- repository input form
- branch field
- start analysis button
- status card
- progress bar
- workflow checklist
- links into downstream features

Options and meanings:

- `Git URL`: generic HTTPS Git repository input
- `GitHub`: owner/repo mode, intended to use GitHub API-backed cloning when token is available
- `Local path`: absolute path on the machine where the API server runs
- `Branch`: the branch to clone/analyze
- `Start analysis`: sends repository intake request
- `Clear result`: clears currently shown run result
- `Copy analysis ID`: copies the repository/analysis ID for use in other pages

Status behavior:

- the page polls the status endpoint every second until a terminal state
- the stage list is derived from the known workflow sequence
- failure messages are surfaced from backend status payloads

Backend endpoints:

- `POST /api/repositories/analyze`
- `GET /api/repositories/{id}/status`

Backend code involved:

- `backend/api/routes/repositories.py`
- `backend/services/repository_manager.py`
- `backend/services/agent_orchestrator.py`
- all registered agents

### C. Dashboard page

Route:

- `/dashboard`

Files:

- `frontend/app/dashboard/page.tsx`

Purpose:

- show recent analyses and summary counts

Visible modules:

- repository summary stats
- recent analyses list
- quick links from each analysis to downstream pages

What the stats mean:

- total repositories: count of stored repository rows
- queued/running: analyses still in progress
- completed: analyses with terminal completion state

Backend endpoint:

- `GET /api/repositories/`

Backend code:

- `backend/api/routes/repositories.py`

Important note:

- the page combines current in-memory runs with persisted repository rows, so behavior across restarts depends on what has been written to PostgreSQL

### D. Dependency Graph page

Route:

- `/dependency-graph`

Files:

- `frontend/app/dependency-graph/page.tsx`

Purpose:

- visualize repository service/module relationships

Visible modules:

- legend
- graph filter controls
- architecture stats cards
- module classification badges
- dependency summary text
- repository scope input
- graph canvas with React Flow

Filter options and meanings:

- peripheral toggle: hide/show less central classifications
- core only: focus on central/core modules
- connected only: hide isolated nodes
- indirect edges: reveal computed transitive edges
- edge labels: show edge labels directly in the graph

What the stats mean:

- Services: number of graph nodes
- Direct edges: stored `DEPENDS_ON` edges
- Indirect edges: computed transitive paths
- Entry points: services/modules with entry-point metadata
- Cycles: detected cyclic dependencies
- Isolated: nodes with no direct links

What the summary section means:

- it is a plain-language explanation built from the filtered graph
- it explains how services/modules are linked in the current repository view

Backend endpoint:

- `GET /api/dependencies/graph`

Backend code:

- `backend/api/routes/dependencies.py`
- `backend/services/graph_service.py`
- `backend/services/dependency_graph_fallback.py`

Important note:

- if Neo4j is empty or unavailable, the page can still render a fallback node-only view from PostgreSQL

### E. Services page

Route:

- `/services`

Files:

- `frontend/app/services/page.tsx`

Purpose:

- show the service/module inventory for a repository

Visible modules:

- repository scope behavior based on query string or last-used repository
- toggle for latest repository vs. all repositories
- service cards
- open-graph shortcut

Card contents and meanings:

- service display name: human-friendly name for a service/module
- repo label: repository that the service belongs to
- language: detected service/module language
- classification: inferred category, such as entrypoint or core library
- entry points: count of detected entry surfaces
- description: persisted service description, optionally generated by documentation agent
- view details: drilldown into service detail page

Backend endpoint:

- `GET /api/services/`

Backend code:

- `backend/api/routes/services.py`
- `backend/services/service_persistence.py`

### F. Service detail page

Route:

- `/services/[id]`

Files:

- `frontend/app/services/[id]/page.tsx`

Purpose:

- show a single service/module in more detail

Visible modules:

- heading and repository context
- language
- module classification
- entry-point count
- markdown description
- raw JSON details expander

Backend endpoint:

- `GET /api/services/{id}`

Backend code:

- `backend/api/routes/services.py`

### G. Impact Analysis page

Route:

- `/impact-analysis`

Files:

- `frontend/app/impact-analysis/page.tsx`
- `frontend/app/impact-analysis/impact-client.tsx`

Purpose:

- estimate which services/modules are likely to be affected by a proposed change

Visible modules:

- analysis ID field
- change description field
- run button
- result cards and badges
- impacted services list
- recommendations list

Options and meanings:

- Analysis ID: repository whose service inventory and graph should be used
- Change description: natural language description of the proposed change
- Analyze impact: run on-demand impact scoring

Result meanings:

- Risk badge: overall aggregated risk level
- modules/direct/indirect/entry-point badges: graph summary context
- risk summary: plain-language explanation of the result
- What could break: repository-level warnings
- impacted services: list of direct or transitive effects
- depth: graph distance from the directly changed node
- impact type: whether impact came from direct selection, direct file match, transitive dependency, or repository-wide surface heuristics

Backend endpoint:

- `POST /api/impact-analysis/analyze`

Backend code:

- `backend/api/routes/impact.py`
- `backend/services/impact_engine.py`
- `backend/services/graph_service.py`

### H. Technical Debt page

Route:

- `/tech-debt`

Files:

- `frontend/app/tech-debt/page.tsx`
- `frontend/app/tech-debt/tech-debt-client.tsx`
- `frontend/components/tech-debt/DebtVisualization.tsx`
- `frontend/components/tech-debt/DebtList.tsx`
- `frontend/components/tech-debt/RemediationPlan.tsx`

Purpose:

- analyze and visualize debt findings for a repository

Visible modules:

- repository input card
- run tech-debt pass button
- Overview tab
- Debt items tab
- Remediation tab

Overview tab modules:

- overall debt score
- debt by category chart
- debt by severity chart
- category scores
- top priority list

What the category scores mean:

- each category score is on a 0-100 scale
- the UI now also shows coverage/support notes
- a zero score does not always mean "no risk"; it may mean that a category is only partially supported

Debt items tab modules:

- category filter
- severity filter
- priority filter
- item list with file and line context

Priority meanings:

- Priority 1: quick wins
- Priority 2: strategic work
- Priority 3: fill-ins
- Priority 4: avoid or lower-return work

Remediation tab:

- generates or shows a remediation plan

Backend endpoints:

- `POST /api/tech-debt/analyze`
- `GET /api/tech-debt/reports/{repository_id}`
- `GET /api/tech-debt/metrics/{repository_id}`
- `GET /api/tech-debt/items`
- `POST /api/tech-debt/remediation-plan`
- `GET /api/tech-debt/trends/{repository_id}`

Backend code:

- `backend/api/routes/tech_debt.py`
- `backend/services/tech_debt_analyzer.py`
- `backend/services/code_quality_analyzer.py`
- `backend/services/architecture_analyzer.py`
- `backend/services/dependency_vulnerability_scanner.py`
- `backend/services/documentation_debt_analyzer.py`
- `backend/services/tech_debt_persistence.py`

### I. Human Review page

Route:

- `/agent-status`

Navigation label:

- Human Review

Files:

- `frontend/app/agent-status/page.tsx`

Purpose:

- show pending and resolved human-review checkpoints created by the workflow

Visible modules:

- pending checkpoints
- resolve buttons
- resolved checkpoints
- ambiguity explanations

Checkpoint meanings:

- reason: why the system needs operator input
- question: prompt for the operator
- options: allowed responses
- ambiguous dependency details: source module, unresolved target, file, explanation, and possible candidate matches

Backend endpoints:

- `GET /api/human-review/checkpoints`
- `POST /api/human-review/checkpoints/{id}/resolve`

Backend code:

- `backend/api/routes/human_review.py`
- `backend/agents/human_review_agent.py`
- `backend/services/agent_orchestrator.py`

Important note:

- this page currently focuses on human checkpoints only; there is not a separate autonomous "agent self-review" UI

## 11. API route reference by feature

### Repository APIs

File:

- `backend/api/routes/repositories.py`

Endpoints:

- `POST /api/repositories/analyze`
- `GET /api/repositories/{repository_id}/status`
- `GET /api/repositories/`

### Service APIs

File:

- `backend/api/routes/services.py`

Endpoints:

- `GET /api/services/`
- `GET /api/services/{service_id}`
- `GET /api/services/{service_id}/dependencies`

### Dependency APIs

File:

- `backend/api/routes/dependencies.py`

Endpoints:

- `GET /api/dependencies/graph`

### Impact APIs

File:

- `backend/api/routes/impact.py`

Endpoints:

- `POST /api/impact-analysis/analyze`
- `GET /api/impact-analysis/{analysis_id}`

Important note:

- the `GET` by analysis id path is currently a lightweight stub compared to the main `POST /analyze` flow

### Documentation APIs

File:

- `backend/api/routes/documentation.py`

Important note:

- current standalone documentation retrieval/regeneration endpoints are stubs
- visible documentation in the UI is primarily persisted into `Service.description`

### Human Review APIs

File:

- `backend/api/routes/human_review.py`

Endpoints:

- `GET /api/human-review/checkpoints`
- `GET /api/human-review/checkpoints/{checkpoint_id}`
- `POST /api/human-review/checkpoints/{checkpoint_id}/resolve`

### Tech Debt APIs

File:

- `backend/api/routes/tech_debt.py`

Endpoints:

- `POST /api/tech-debt/analyze`
- `GET /api/tech-debt/reports/{repository_id}`
- `GET /api/tech-debt/items`
- `GET /api/tech-debt/metrics/{repository_id}`
- `POST /api/tech-debt/remediation-plan`
- `GET /api/tech-debt/trends/{repository_id}`

### Metrics API

File:

- `backend/api/routes/metrics.py`

Endpoint:

- `GET /metrics`

Purpose:

- Prometheus-compatible metrics exposure

## 12. Important calculations and heuristics

This section answers the common question: "Why did the system show this result?"

### Why a repository may become many services/modules

Primary logic:

- `backend/services/dependency_analyzer.py`

Reasons:

- service indicators are found in multiple directories
- coarse detection falls back to code clusters
- Python library repositories switch into module-level service modeling

### Why some services are marked as entry points

Primary logic:

- `backend/services/dependency_analyzer.py`

Examples:

- `__main__.py`
- `main.py` or `cli.py` with main-guard patterns
- files inside `bin/` or `scripts/`

### Why the graph shows indirect edges

Primary logic:

- `backend/services/graph_service.py`

Reason:

- indirect edges are computed as transitive paths, not stored direct edges
- they are derived from BFS traversal up to a maximum depth

### Why a node is isolated

Primary logic:

- `backend/services/graph_service.py`

Reason:

- the service exists in the inventory but no direct `DEPENDS_ON` relationship was found for it

### Why impact risk may be high

Primary logic:

- `backend/services/impact_engine.py`

Common causes:

- breaking-change keywords in the description
- graph fan-out into many dependents
- entry-point classification
- core-library classification
- database/schema-related wording

### Why technical debt may be high

Primary logic:

- `backend/services/tech_debt_analyzer.py`

Common causes:

- many code-quality issues
- high-severity findings
- dependency risk findings
- architecture findings
- documentation gaps

### Why a category score may be zero

Primary logic:

- `backend/services/tech_debt_analyzer.py`
- frontend `DebtVisualization`

Possible meanings:

- no issues were found in that category
- the category is only heuristically supported
- the category is not fully implemented yet

The UI now clarifies this with `assessment_coverage`.

### Why human review checkpoints appear

Primary logic:

- `backend/agents/human_review_agent.py`

Current reasons:

- dependency target could not be confidently mapped
- service boundary is unclear due to missing/unknown language

## 13. Display helpers and human-readable naming

Frontend helper files:

- `frontend/lib/repository-display.ts`
- `frontend/lib/service-display.ts`

Purpose:

- replace raw UUID-heavy display with more understandable names where possible
- normalize repository URLs into user-friendly names
- present repository-root-like modules more naturally

## 14. What is fully implemented vs. partial vs. stubbed

### Strongly implemented and visible in the UI

- repository intake and analysis orchestration
- service inventory persistence
- dependency graph visualization with fallback mode
- on-demand impact analysis
- tech-debt reporting and filtering
- human-review checkpoint display

### Partially implemented or heuristic-heavy

- documentation generation depends on OpenAI availability
- architecture analysis depends on graph/service quality
- impact analysis is heuristic when graph or direct file mapping is limited
- documentation debt is currently basic and heuristic

### Present but not fully productized

- standalone documentation API routes
- impact-analysis retrieval by saved analysis id
- deeper test-coverage analysis
- broader use of Qdrant and Redis in visible features

## 15. Operator FAQ

### What is the "Analysis ID"?

It is the `Repository.id` stored in PostgreSQL. The UI uses it as the main cross-feature identifier. You can use it to open:

- `/services?repo=<id>`
- `/dependency-graph?repo=<id>`
- `/impact-analysis?repo=<id>`
- `/tech-debt?repo=<id>`
- `/agent-status?repo=<id>`

### Where is the graph actually stored?

Primary graph data is stored in Neo4j by `GraphService`. If Neo4j is unavailable or empty, the dependency page can fall back to Postgres service rows for a node-only graph-like response.

### Where do service descriptions come from?

They are saved into `Service.description` by `persist_services_and_docs`. The content may come from discovered service data or the optional `documentation_agent`.

### Why do some pages still work after backend restarts and others may lose detail?

Persisted repository, service, and tech-debt data survives in PostgreSQL. In-memory orchestrator state such as active runs and checkpoints does not survive a restart unless it has already been persisted elsewhere.

### Why does the Human Review page sometimes only show current run checkpoints?

Because the current checkpoint API reads from `AgentOrchestrator.active_runs`, which is in memory.

### Why is the test category on tech debt marked differently?

Because automated test-coverage analysis is not fully implemented, so a zero score should not be interpreted as proof of good test coverage.

## 16. Recommended reading order for new team members

If someone is new to the project, this is the best order to understand it:

1. `README.md`
2. `docs/PROJECT_REFERENCE.md`
3. `frontend/components/layout/app-shell.tsx`
4. `frontend/app/analyze/page.tsx`
5. `backend/main.py`
6. `backend/api/routes/repositories.py`
7. `backend/services/agent_orchestrator.py`
8. `backend/agents/dependency_mapper_agent.py`
9. `backend/services/dependency_analyzer.py`
10. `backend/services/graph_service.py`
11. `backend/services/impact_engine.py`
12. `backend/services/tech_debt_analyzer.py`

## 17. Quick file map for answering questions fast

If you are asked about a topic, start here:

- "How does analysis start?" -> `backend/api/routes/repositories.py`
- "How are repos cloned?" -> `backend/services/repository_manager.py`
- "How are services discovered?" -> `backend/services/dependency_analyzer.py`
- "How is the dependency graph built?" -> `backend/agents/dependency_mapper_agent.py`, `backend/services/graph_service.py`
- "Why is the graph showing that summary?" -> `backend/services/graph_service.py`, `frontend/app/dependency-graph/page.tsx`
- "How is impact scored?" -> `backend/services/impact_engine.py`
- "How is tech debt scored?" -> `backend/services/tech_debt_analyzer.py`
- "Where do debt items come from?" -> sub-analyzers under `backend/services/`
- "Where do service descriptions come from?" -> `backend/agents/documentation_agent.py`, `backend/services/service_persistence.py`
- "Why is human review asking this?" -> `backend/agents/human_review_agent.py`
- "What does this page call?" -> matching file under `frontend/app/` and route under `backend/api/routes/`

## 18. Summary

The project is best understood as:

- a repository ingestion system
- a multi-agent analysis pipeline
- a persistence layer for services, tech debt, and repository state
- a graph-backed dependency and impact engine
- a frontend that presents those results as operational views

The most important backend files to understand first are:

- `backend/api/routes/repositories.py`
- `backend/services/agent_orchestrator.py`
- `backend/services/dependency_analyzer.py`
- `backend/services/graph_service.py`
- `backend/services/impact_engine.py`
- `backend/services/tech_debt_analyzer.py`

The most important frontend files to understand first are:

- `frontend/components/layout/app-shell.tsx`
- `frontend/app/analyze/page.tsx`
- `frontend/app/dependency-graph/page.tsx`
- `frontend/app/services/page.tsx`
- `frontend/app/impact-analysis/impact-client.tsx`
- `frontend/app/tech-debt/tech-debt-client.tsx`
- `frontend/app/agent-status/page.tsx`

Use this document together with the source files above when answering detailed product or implementation questions.
