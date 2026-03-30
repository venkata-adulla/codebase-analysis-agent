# Temporal Drift Monitor — Integration Guide

## What this feature does (the pitch)

Every competitor (CodeRabbit, Greptile, Qodo) analyzes your codebase as it is **right now**.
None of them ask: *"How fast is this codebase deteriorating, and which services will break
down in the next 30 days?"*

The Temporal Drift Monitor fills that gap by treating your git history as a time-series
dataset and computing **drift velocity** per service — a composite score that measures:

| Metric | What it means | Weight |
|---|---|---|
| **Churn rate** | How often files in this service change (high = unstable, tightly coupled, or over-engineered) | 40% |
| **Complexity drift** | Is cyclomatic complexity growing faster than LOC? | 35% |
| **Bus factor decay** | Is the number of contributors to this service shrinking? | 25% |

From these three velocities it produces a **drift score (0–100)** per service, projects it
forward 30 days using linear regression, and alerts you *before* the threshold is crossed.

---

## File placement

```
backend/
  agents/
    temporal_drift_agent.py          ← drop here
  services/
    temporal_drift_analyzer.py       ← drop here
  models/
    drift.py                         ← drop here
  api/
    routes/
      drift.py                       ← drop here

frontend/
  app/
    drift/
      page.tsx                       ← drop here
  components/
    drift/
      DriftHotspots.tsx              ← drop here
      DriftVelocityTable.tsx         ← contains DriftTimeline too
```

---

## Backend wiring

### 1. Register the DB models

In `backend/models/__init__.py` (or wherever you import models for Alembic):

```python
from models.drift import DriftSnapshot, DriftReport  # add this
```

### 2. Create the migration

```bash
cd backend
alembic revision --autogenerate -m "add temporal drift tables"
alembic upgrade head
```

Or, if you're using the direct Base.metadata.create_all approach documented in AGENTS.md:

```python
from models.drift import DriftSnapshot, DriftReport
from core.database import Base, engine
Base.metadata.create_all(engine)
```

### 3. Mount the router

In `backend/main.py`:

```python
from api.routes.drift import drift_router

app.include_router(drift_router, prefix="/api/drift", tags=["Temporal Drift"])
```

### 4. Plug into the agent chain

In your `OrchestratorAgent` or `PlanningAgent`, add `TemporalDriftAgent` after
`DependencyMapperAgent`:

```python
# Existing chain:
# planning → code_browser → dependency_mapper → documentation → impact → human_review

# New chain:
# planning → code_browser → dependency_mapper → temporal_drift ← ADD HERE
#                                             → documentation → impact → human_review

from agents.temporal_drift_agent import TemporalDriftAgent

# Inside your orchestration loop, after dependency_mapper completes:
drift_agent = TemporalDriftAgent(db_session, neo4j_driver, redis_client)
drift_result = await drift_agent.run(
    repository_id=repository_id,
    repo_path=str(repo_local_path),
    lookback_days=90,
    snapshots=12,
)
```

---

## Frontend wiring

### 1. Add the nav link

In your sidebar/nav component, add:

```tsx
<Link href="/drift">Temporal Drift</Link>
```

### 2. Import the DriftTimeline export correctly

`DriftVelocityTable.tsx` exports two named exports:
- `DriftVelocityTable` (default export + named)
- `DriftTimeline` (named export)

Import in the page as:
```tsx
import DriftTimeline from "@/components/drift/DriftTimeline";
// But since it's a named export from DriftVelocityTable.tsx, import it as:
import { DriftTimeline } from "@/components/drift/DriftVelocityTable";
```

Or rename the file to `DriftTimeline.tsx` and re-export from an index.

---

## Environment variables

No new env vars required. The feature degrades gracefully:
- Without `OPENAI_API_KEY`: uses the fallback rule-based narrative instead of LLM summary
- Without a Neo4j connection: skips coupling metrics (uses 0 as baseline)
- Without git history (< 3 commits): returns a warning, does not fail the pipeline

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/drift/analyze` | Run drift analysis (params: repository_id, repo_path, lookback_days, snapshots) |
| GET | `/api/drift/reports/{repository_id}` | Most recent full reports |
| GET | `/api/drift/snapshots/{repository_id}` | Time-series data for charts |
| GET | `/api/drift/hotspots/{repository_id}` | Filtered hotspot list |
| GET | `/api/drift/velocity/{repository_id}` | Per-service velocity scores |

---

## How drift_score is computed

```
drift_score = clamp(0, 100,
  churn_slope     × 40 +
  complexity_slope × 35 +
  (-bus_factor_slope) × 25   ← negative bus slope = declining contributors = bad
)
```

`*_slope` = linear regression slope across the N time slices (normalized to [0, n-1]).
A positive churn slope means more files are being changed per window over time.
A negative bus factor slope means fewer people are touching the service — silo risk.

---

## Competitive differentiation summary

| Capability | Your agent | CodeRabbit | Greptile | Sourcegraph |
|---|---|---|---|---|
| Current-state dependency graph | ✓ | Partial | Partial | ✓ |
| Tech debt scoring | ✓ | ✓ | Partial | — |
| **Temporal drift velocity** | ✓ (new) | ✗ | ✗ | ✗ |
| **Drift prediction (30-day)** | ✓ (new) | ✗ | ✗ | ✗ |
| **Bus factor tracking** | ✓ (new) | ✗ | ✗ | ✗ |
| Human-in-the-loop checkpoints | ✓ (unique) | — | — | — |
| Vector search (Qdrant) | ✓ | — | Partial | ✓ |

The Temporal Drift Monitor, combined with your existing human-in-the-loop checkpoints and
Neo4j dependency graph, creates a defensible differentiation: you're the only tool that
tells teams *where their codebase is heading*, not just where it is.
