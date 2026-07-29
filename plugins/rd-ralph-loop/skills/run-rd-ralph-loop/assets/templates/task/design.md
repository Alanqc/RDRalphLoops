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

| Deliverable | Path | Format / interface | Owner | ACs | Retention |
|---|---|---|---|---|---|
| `DEL-001` | `path/to/output` | [[PLANNER: exact form]] | [[PLANNER: owner]] | `AC-001` | Retain after four-pack archival |

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

| Iteration | Author | Reason | Changed invariant / interface | Affected ACs |
|---|---|---|---|---|
| INIT | Planner | Initial design | Initial design | All |
