# {{TASK_TITLE}} Design

## Context

[[PLANNER: Describe relevant current state and known facts without repeating the proposal.]]

## Spec Alignment

- [[PLANNER: Explain alignment with each global owner or identify a required owner update.]]

## Goals

- [[PLANNER: State technical design goals.]]

## Non-goals

- [[PLANNER: State rejected or deferred technical choices.]]

## Output Design

Keep retained deliverables outside this four-pack directory. Use paths relative to the workspace
root so a temporary worktree path is never embedded in an accepted deliverable identity.

Classify each output as `SUBJECT`, `ASSURANCE`, or `EVIDENCE`. `ASSURANCE` includes task-specific
harnesses, validators, simulators, evidence generators, and their tests.

| Deliverable | Class | Path | Format / interface | Owner | ACs | Guard budget | Retention |
|---|---|---|---|---|---|---|---|
| `DEL-001` | SUBJECT / ASSURANCE / EVIDENCE | `path/to/output` | [[PLANNER: exact form]] | [[PLANNER: owner]] | `AC-001` | `BUD-001` / EXCLUDED | Retain after four-pack archival |

## Verification Boundary

- Direct subject evidence: [[PLANNER: name the immutable outputs or live observations that decide the ACs.]]
- Reviewer direct recomputation: [[PLANNER: state what the Reviewer can recompute without trusting a task-specific validator.]]
- Allowed assurance surface: [[PLANNER: list the minimum harnesses or write None.]]
- Prohibited substitutions: [[PLANNER: state which external/live evidence cannot be replaced by simulation, metadata, or self-attestation.]]
- Expansion rule: adding a deliverable, schema generation, provider, phase, interface, assurance
  layer, or budget requires explicit user authorization after initialization.

## Concurrent Resource Ownership

Declare every shared mutable resource, including generated directories, databases, services,
ports, caches, devices, and external publication targets. Concurrent loops must not have overlapping
write ownership.

| Resource | Location / identity | Access | Owner | Collision avoidance |
|---|---|---|---|---|
| Repository files for `DEL-001` | `path/to/output` | Exclusive write | `{{TASK_ID}}` | Dedicated worktree and `{{GIT_BRANCH}}` branch |

## Constraints

- [[PLANNER: Record compatibility, safety, data, repository, runtime, and authority constraints.]]

## Approach

1. [[PLANNER: Describe the technical path.]]

## Key Decisions

- [[PLANNER: Record each decision and rationale.]]

## Risks

- [[PLANNER: Record each risk and mitigation.]]

## Design Amendment Log

| Iteration | Author | Trigger findings / queries | Reason | Removed or replaced | Changed invariant / interface | Budget delta | User authorization | Affected ACs |
|---|---|---|---|---|---|---|---|---|
| INIT | Planner | Initial request | Initial design | N/A | Initial design | Initial budgets | Initial task request | All |
