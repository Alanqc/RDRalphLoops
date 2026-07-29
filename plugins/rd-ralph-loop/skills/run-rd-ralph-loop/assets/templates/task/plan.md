# {{TASK_TITLE}} Plan

## Loop Control

| Field | Value |
|---|---|
| Run ID | `{{RUN_ID}}` |
| Worktree root | `{{WORKTREE_ROOT}}` |
| Branch | `{{GIT_BRANCH}}` |
| Base commit | `{{BASE_COMMIT}}` |
| Merge mode | {{MERGE_MODE}} |
| Merge owner | User |
| State | Proposed |
| Current iteration | 0 |
| Next actor | Implementer |
| Planner required next | No |
| Planner re-entry reason | N/A |
| Last Reviewer verdict | PENDING |
| Soft / hard threshold | 3 / 8 |
| Last updated | {{DATE}} |

## Next Step

- [[PLANNER: Give one executable next action or an exact blocker.]]

## Deliverables

Paths are relative to the workspace root. Do not encode a temporary worktree's absolute path.

| ID | ACs | Path | Required | Status | Evidence target |
|---|---|---|---|---|---|
| `DEL-001` | `AC-001` | `path/to/output` | Yes | Pending | [[PLANNER: command, review, or artifact identity]] |

## Delivery Items

| Done | ID | Deliverable / ACs | Depends | Owner | Target | Action |
|---|---|---|---|---|---|---|
| [ ] | `ITEM-001` | `DEL-001`; `AC-001` | None | Implementer | `path/to/output` | [[PLANNER: one executable action]] |

## AC Verification Plan

| AC | Method | Command / review step | Expected evidence |
|---|---|---|---|
| `AC-001` | [[PLANNER: unit/integration/e2e/manual/link/command]] | [[PLANNER: exact command or step]] | [[PLANNER: pass condition and evidence location]] |

## Iteration Log

Append one row per role pass. Do not rewrite history.

| Iteration | Role | Changed paths | Commands and results | Finding disposition | Next action |
|---|---|---|---|---|---|
| 0 | Planner | Four-pack | Planning only | N/A | Implementer |
