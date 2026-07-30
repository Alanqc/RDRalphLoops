# {{TASK_TITLE}} Design

## Context

[[PLANNER: Describe relevant current state and known facts without repeating the proposal.]]

## Spec Alignment

- [[PLANNER: Explain alignment with each global owner or identify a required owner update.]]

## Goals

- [[PLANNER: State technical design goals.]]

## Non-goals

- [[PLANNER: State rejected or deferred technical choices.]]

## Repository Participants

`CONTROL` is the workspace/control repository recorded in `plan.md`; it owns the four-pack, index,
Planner/Reviewer/Control history, archive, and candidate seal. Register every other Git worktree
that Implementer may modify as a stable `REPO-NNN`. Use one `N/A` row when no participant
repository is required. Worktree roots are supplied at runtime with
`--repo REPO-NNN=/absolute/worktree` and are not accepted-document identities. Logical identity is
an origin URL or user-approved stable repository label, never a temporary worktree path. CONTROL
is always merged last during manual integration.

| Repository | Logical identity | Branch | Base commit | Write scopes | ACs | Merge order | User authorization |
|---|---|---|---|---|---|---:|---|
| `REPO-001` / N/A | [[PLANNER: origin URL or stable label, or N/A]] | `ralph/{{TASK_ID}}` | [[PLANNER: full immutable base SHA, or N/A]] | [[PLANNER: repository-relative prefixes, or N/A]] | `AC-001` / N/A | 10 | Initial task request / explicit authorization |

An Implementer may inspect a user-identified repository read-only to justify
`PLAN_FEEDBACK_REQUIRED`, but may not modify it or include it in a candidate until the user
authorizes the repository and write scopes and a fresh Planner checkpoint updates this registry.
Repository removal, replacement, or scope expansion follows the same rule.

## Output Design

Keep retained deliverables outside this four-pack directory. Use paths relative to the workspace
or registered participant repository so a temporary worktree path is never embedded in an
accepted deliverable identity.

Classify each output as `SUBJECT`, `ASSURANCE`, or `EVIDENCE`. `ASSURANCE` includes task-specific
harnesses, validators, simulators, evidence generators, and their tests.

| Deliverable | Class | Repository | Path | Format / interface | Owner | ACs | Guard budget | Retention |
|---|---|---|---|---|---|---|---|---|
| `DEL-001` | SUBJECT / ASSURANCE / EVIDENCE | `CONTROL` / `REPO-001` | `path/to/output` | [[PLANNER: exact form]] | [[PLANNER: owner]] | `AC-001` | `BUD-001` / EXCLUDED | Retain after four-pack archival |

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
| Repository files for `DEL-001` | `CONTROL` / `REPO-001`: `path/to/output` | Exclusive write | `{{TASK_ID}}` | Dedicated worktree and `{{GIT_BRANCH}}` branch |

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
