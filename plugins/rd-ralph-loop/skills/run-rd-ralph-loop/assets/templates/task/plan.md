# {{TASK_TITLE}} Plan

## Loop Control

| Field | Value |
|---|---|
| Protocol version | 2 |
| Run ID | `{{RUN_ID}}` |
| Worktree root | `{{WORKTREE_ROOT}}` |
| Branch | `{{GIT_BRANCH}}` |
| Base commit | `{{BASE_COMMIT}}` |
| Merge mode | {{MERGE_MODE}} |
| Merge owner | User |
| State | Proposed |
| Pause reasons | NONE |
| Guard decision | NOT_EVALUATED |
| Current iteration | 0 |
| Next actor | Implementer |
| Active plan query | NONE |
| Planner required next | No |
| Planner re-entry reason | N/A |
| Last Reviewer verdict | PENDING |
| Consecutive NEEDS_REPLAN | 0 |
| Completed reviews | 0 |
| Last Control event | NONE |
| Last updated | {{DATE}} |

In Git mode, append-only `Ralph-Role: Control` checkpoints are authoritative for pause, resume,
plan-query, and plan-response events. The summary above may lag while preserved WIP is dirty and is
refreshed by the next role that may legitimately edit `plan.md`.

## Next Step

- [[PLANNER: Give one executable next action or an exact blocker.]]

## Deliverables

Paths are relative to the workspace root. Do not encode a temporary worktree's absolute path.

| ID | Class | ACs | Path | Required | Guard budget | Status | Evidence target |
|---|---|---|---|---|---|---|---|
| `DEL-001` | SUBJECT / ASSURANCE / EVIDENCE | `AC-001` | `path/to/output` | Yes | `BUD-001` / EXCLUDED | Pending | [[PLANNER: command, review, or artifact identity]] |

## Delivery Items

| Done | ID | Deliverable / ACs | Depends | Owner | Target | Action |
|---|---|---|---|---|---|---|
| [ ] | `ITEM-001` | `DEL-001`; `AC-001` | None | Implementer | `path/to/output` | [[PLANNER: one executable action]] |

## AC Verification Plan

| AC | Method | Command / review step | Expected evidence |
|---|---|---|---|
| `AC-001` | [[PLANNER: unit/integration/e2e/manual/link/command]] | [[PLANNER: exact command or step]] | [[PLANNER: pass condition and evidence location]] |

## Finding Disposition Ledger

Planner appends one row for every finding that triggers re-entry. Every row must resolve to
`FIX`, `DESCOPE`, `DEFER`, or `ESCALATE`. `DEFER` cannot hide a required AC: it must identify an
external blocker or a user-authorized contract re-baseline.

| Iteration | Finding | Type | Disposition | Changed section / path | Removed or replaced | Budget delta | Expected direct evidence | User authorization |
|---|---|---|---|---|---|---|---|---|
| 0 | N/A | N/A | Initial plan | Four-pack | N/A | Initial budgets | Initial evidence targets | Initial task request |

## Plan Feedback Ledger

`PLAN_FEEDBACK_REQUIRED` is an Implementer-to-Planner consultation before candidate creation. Use a
stable `PQ-NNN` ID. In Git mode, the matching Control plan-query and plan-response checkpoints are
the authoritative append-only events; this table is their next safe projection into `plan.md`.

| Query | Iteration | Related ITEM / DEL / AC | Problem | Existing WIP | Continue-risk | Implementer recommendation | Planner disposition | Planner outcome | Control events |
|---|---:|---|---|---|---|---|---|---|---|
| N/A | 0 | N/A | No query | None | None | N/A | N/A | N/A | N/A |

Planner disposition for each query is `ACCEPT`, `MODIFY`, `REJECT`, or `ESCALATE`. Planner outcome
is exactly one of `CLARIFIED`, `REPLAN_REQUIRED`, `CONTRACT_CHANGE_REQUIRED`, or
`EXTERNAL_BLOCKER`.

## Readiness Child Tasks

A readiness child must reference its paused parent and take exclusive ownership of every
transferred path. The parent must not write those paths until the child returns them. A child
prepares only its declared readiness result and cannot claim the parent's live acceptance.

| Child task | Parent task | Parent base / candidate | Transferred paths | Returned deliverables | Parent resume predicate | Status |
|---|---|---|---|---|---|---|
| N/A | N/A | N/A | None | None | N/A | NONE |

## Control Event Ledger (Non-Git Only)

For Git runs, leave this section unchanged and use Control checkpoints. For non-Git runs, the
Controller appends events here and never rewrites prior rows.

| Event | Date | Action | Reasons | User authorization | Evidence | Resume actor |
|---|---|---|---|---|---|---|
| `CTRL-000` | {{DATE}} | INIT | NONE | Initial task request | Four-pack initialized | Implementer |

## Iteration Log

Append one row per role pass. Do not rewrite history.

| Iteration | Role | Changed paths | Commands and results | Finding disposition | Next action |
|---|---|---|---|---|---|
| 0 | Planner | Four-pack | Planning only | N/A | Implementer |
