# {{TASK_TITLE}} Proposal

| Field | Value |
|---|---|
| Protocol version | 2 |
| Task ID | `{{TASK_ID}}` |
| Run ID | `{{RUN_ID}}` |
| Contract owner | Planner |
| Contract status | Draft |
| Created | {{DATE}} |

## What & Why

[[PLANNER: State the problem, trigger, and why it matters now.]]

## Scope

In scope:

- [[PLANNER: State included work.]]

Out of scope:

- [[PLANNER: State excluded work.]]

## Global Spec References

- [[PLANNER: Link long-term owners, or write N/A with a reason.]]

## References

- [[PLANNER: Link authoritative inputs and prior work.]]

## External Dependency Registry

Register every asset, device, permission, service, or decision that can block a required AC before
implementation starts. Keep one `N/A` row when no external dependency exists. A required dependency
with `BLOCKED` status is not replaceable by simulated or self-generated evidence.

| Dependency | Blocking ACs | Required immutable evidence | Owner | Initial status | Unblock proof |
|---|---|---|---|---|---|
| `DEP-001` | `AC-001` | [[PLANNER: exact real evidence or N/A]] | [[PLANNER: user/team/system]] | READY / BLOCKED | [[PLANNER: observable proof required to proceed]] |

## Guard Budget Defaults

Guard measurements apply only to explicit workspace-relative deliverable paths declared below.
Line measurement is limited to physical line counts and `git diff --numstat --no-renames`; the
guard must not add AST, call-graph, schema, execution, or other semantic analysis.

When no task-specific value is approved during initialization, use these defaults:

| Profile | Per-iteration warning | Per-iteration pause | Cumulative pause | Per-path pause |
|---|---:|---:|---:|---:|
| CODE | 3000 lines | 5000 lines | 12000 lines | 6000 lines |
| DOCUMENT | 10000 lines | 20000 lines | 50000 lines | 30000 lines |

## Guard Budgets

Declare the task's effective budgets below. The four-pack, its required lifecycle updates, and
Reviewer evidence do not consume Implementer deliverable budgets. Generated, vendor, or binary
paths may be excluded only when the exclusion and reason are explicit. Every declared deliverable
must be covered by a guarded path prefix or a reasoned exclusion. Format exclusions as
`path :: reason`, separated by semicolons or `<br>`; use `N/A` when none.

| Budget | Profile | Guarded deliverable paths | Warning | Iteration pause | Cumulative pause | Per-path pause | Exclusions | User authorization |
|---|---|---|---:|---:|---:|---:|---|---|
| `BUD-001` | CODE / DOCUMENT | `path/to/output` | [[PLANNER: lines or default]] | [[PLANNER: lines or default]] | [[PLANNER: lines or default]] | [[PLANNER: lines or default]] | [[PLANNER: `path :: reason`, or N/A]] | Initial task request / explicit initialization approval |

## Acceptance Criteria

Use stable IDs and one objectively verifiable result per criterion.

- `AC-001`: THE [[PLANNER: system or capability]] SHALL [[PLANNER: verifiable result]].

## Contract Change Log

| Iteration | Change | Affected ACs | User authorization |
|---|---|---|---|
| INIT | Initial contract | All | Initial task request |
