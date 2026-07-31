# R&D Ralph Loop Protocol

## Contents

- [State machine](#state-machine)
- [Authority](#authority)
- [Required traceability](#required-traceability)
- [Worktree and concurrency contract](#worktree-and-concurrency-contract)
- [Interactive Controller contract](#interactive-controller-contract)
- [Git checkpoint contract](#git-checkpoint-contract)
- [Planner contract](#planner-contract)
- [Implementer contract](#implementer-contract)
- [Reviewer contract](#reviewer-contract)
- [Finding semantics](#finding-semantics)
- [Loop control](#loop-control)
- [Pause and resume](#pause-and-resume)
- [Snapshot contract](#snapshot-contract)
- [Closure and archival](#closure-and-archival)
- [Manual integration boundary](#manual-integration-boundary)

## State machine

Use this transition graph:

```text
INIT -> PLANNED -> PLANNER_CHECKPOINT -> IMPLEMENTING -> CANDIDATE_CHECKPOINT -> REVIEWING

IMPLEMENTING -- PLAN_FEEDBACK_REQUIRED --> PLAN_QUERY_CONTROL --> PLANNER_CONSULT
PLANNER_CONSULT
  | CLARIFIED                -> PLAN_RESPONSE_CONTROL -> IMPLEMENTING
  | REPLAN_REQUIRED          -> PLAN_RESPONSE_CONTROL -> PLANNED
  | CONTRACT_CHANGE_REQUIRED -> PAUSE_CONTROL[USER_CHECKPOINT]
  ` EXTERNAL_BLOCKER         -> PAUSE_CONTROL[EXTERNAL]

REVIEWING -> REVIEW_CHECKPOINT
  | ACCEPTED         -> AWAITING_USER_ARCHIVE_CONFIRMATION
  | BLOCKED          -> PAUSE_CONTROL[EXTERNAL]
  | CHANGES_REQUIRED -> GUARD_EVAL -> CONTINUE | PAUSE_CONTROL[reason set]
  ` NEEDS_REPLAN     -> GUARD_EVAL -> PLANNED  | PAUSE_CONTROL[reason set]

AWAITING_USER_ARCHIVE_CONFIRMATION
  -- explicit post-acceptance USER_CONFIRM --> READY_TO_ARCHIVE -> ARCHIVED -> CLOSURE_CHECKPOINT
  -- no decision --------------------------> AWAITING_USER_ARCHIVE_CONFIRMATION
  `-- authorized USER_REJECT --------------> ABANDONED -> NEW_SUPERSEDING_TASK
PAUSE_CONTROL -> PAUSED
PAUSED -- authorized RESUME_CONTROL --> PLANNED | IMPLEMENTING
CLOSURE_CHECKPOINT -> MANUAL_MERGE_HANDOFF
```

Initialization always starts Planner -> Implementer. Every immutable candidate uses an independent
Reviewer. A plan consultation is inside the same implementation iteration: it is not a candidate,
review, verdict, or completed iteration.

`PAUSED` is one lifecycle state with one or more reasons from `EXTERNAL`, `BUDGET`, `ASSURANCE`,
`REPLAN_STORM`, `USER_CHECKPOINT`, `PLAN_CONFLICT`, `CONFIGURATION_GAP`, or `SCHEMA_MIGRATION`.
`BLOCKED` always becomes `PAUSED[EXTERNAL]`; it must never route mechanically to Planner. Current
unstaged WIP is preserved, and no candidate or Reviewer is created while paused.

`AWAITING_USER_ARCHIVE_CONFIRMATION` is a Controller wait boundary, not an automatic transition
and not a substitute for `PAUSED`. The Controller must show the user the accepted candidate,
participant vector, evidence, residual risks, and retained deliverables. Only a new explicit
confirmation after that report authorizes archive and Closure; an earlier blanket run request
does not. Withholding confirmation leaves the run unchanged. A rejection does not reopen the
accepted checkpoint chain: after explicit user authorization, record `abandon` and create a new
superseding task that references the accepted candidate.

`MANUAL_MERGE_HANDOFF` is the plugin boundary, not proof that the user merged the branch.

## Authority

| Concern | Authority |
|---|---|
| Goal, scope, non-goals, ACs | `proposal.md`, Planner-owned |
| Technical approach, output shape, repository registry | `design.md`; Implementer may amend ordinary design details with rationale, but repository membership/write scopes require Planner plus user authorization |
| Progress, tasks, commands, handoff | `plan.md`, Implementer-owned after initialization |
| Pause, resume, abandon, split, plan-query, plan-response events | Controller-owned append-only Control checkpoints; non-Git fallback ledger in `plan.md` |
| Evidence, findings, verdict | `verify.md`, Reviewer-owned and append-only |
| Current/archived task registration | Project task index |
| Stable deliverable body | Declared owner path outside the task pack |
| Role dispatch, user steering, Git staging and commits in every registered repository | Controller |
| Post-acceptance archive authorization; merge, cherry-pick, push, conflict resolution, worktree cleanup | User |

Repository-local instructions and templates override the bundled defaults. Do not duplicate a
stable deliverable body into the task pack; link it and preserve its identity instead.
When a local Verify schema has AC records and a Final Review instead of `ITER-NNN` sections, retain
those required sections and append an equivalent round ledger; do not replace the local contract to
make the bundled validator happy.

Existing Protocol-v1/v2 runs remain legacy single-repository runs. A Protocol-v3 registry with one
`N/A` row and no participant mappings is the CONTROL-only compatibility profile: it retains the
legacy content snapshot and records participant matrix/vector fields as `N/A`.

## Required traceability

- Give each acceptance criterion a stable `AC-NNN` ID and one objectively testable result.
- Give each deliverable a stable `DEL-NNN` ID, declared path, format, owner, retention rule, and
  one or more AC links.
- Give each execution item a stable `ITEM-NNN` ID, dependency list, owner, target path, and AC/DEL
  links.
- Give each reviewer finding a stable `F-NNN` ID and one or more AC links.
- Give each external dependency a stable `DEP-NNN` ID and every task-specific guard budget a stable
  `BUD-NNN` ID.
- Give every participant repository a stable `REPO-NNN` ID. `CONTROL` is reserved for the
  workspace/control repository and is not a participant ID.
- Give each Implementer plan query a stable `PQ-NNN` ID.
- Never reuse an ID for a different meaning. Preserve superseded history.

Every proposal AC must appear in the plan's verification matrix and in every complete reviewer
decision matrix. A summary is not a substitute for AC-level evidence.

## Worktree and concurrency contract

- For Git work, allocate one globally unique task ID and one workspace/control linked worktree.
  It exclusively owns the four-pack, index, lifecycle checkpoints, Reviewer evidence, archive,
  and control candidate seal.
- Register zero or more participant repositories in `design.md`. Each participant uses one
  dedicated linked worktree, the same task ID, its own `ralph/<TASK-ID>` branch, immutable Base,
  user-approved logical identity, repository-relative write scopes, AC links, and unique numeric
  manual-merge order. Supply machine-local roots at runtime as
  `--repo REPO-NNN=/absolute/worktree`; never treat those roots as accepted identity. CONTROL is
  always the last manual-integration target.
- Give every role the same control root, task directory, run ID, and complete repository mapping.
- Never run two write-capable roles concurrently in any registered worktree.
- Declare exclusive write ownership for repository paths and non-repository mutable resources.
  Shared databases, ports, caches, generated directories, devices, and publication targets count
  as conflicts even when worktree paths differ.
- If active loops have overlapping ownership, establish an explicit dependency and serialize their
  Implementer passes or pause one as `BLOCKED`.
- Reject missing/extra repository mappings, duplicate/nested roots, wrong branches or Bases,
  primary worktrees without explicit serialized-loop authorization, nonempty indexes, unmerged
  operations, and changes outside repository-specific scopes.
- A readiness child task must record its paused parent task, parent Base/candidate, transferred
  paths, returned deliverables, and parent resume predicate. Transferred paths have exactly one
  active write owner: the parent remains paused and must not write them until the child returns
  ownership. A readiness child cannot claim the parent's live acceptance and is handed back for
  user-controlled integration; it does not create an integration queue.
- Worktree creation must refuse existing paths/branches and must not use `--force`. The loop never
  removes its worktree or branch.
- Branch-local copies of a shared index may conflict during manual integration. Do not solve that
  with concurrent writes or an integration queue; leave conflict resolution to the user.

## Interactive Controller contract

- Spawn one fresh background role at a time for a loop and remain available in the main thread.
- Use bounded waits and send meaningful status updates at least every 60 seconds.
- Treat the 60-second interval as a Controller reporting cadence, not a role or first-write
  deadline. Fresh context isolates roles; it does not justify restarting a role that is still
  running. File mtimes, sizes, and absent or partial writes do not establish a stall. For apparent
  inactivity, request one status update and wait through two more bounded status cycles; continue
  waiting if the role replies or shows observable role/tool progress. Confirm the old role has
  stopped before dispatching at most one fresh replacement. If that replacement also meets this
  stall test, stop and ask the user instead of restarting again.
- Accept user steering while a role runs. Forward non-material clarifications when safe.
- A change to goal, scope, AC, design invariant, path ownership, or reviewed bytes invalidates the
  current candidate. Interrupt or let the role stop safely, record the change, and route through
  Planner -> Implementer -> Reviewer.
- Run the guard before a Planner replan checkpoint, before an Implementer candidate checkpoint,
  and after every non-accepted review. A guard pause is authoritative even when a role believes it
  can continue.
- Record pause, resume, abandon, split, plan-query, and plan-response as append-only Controller
  events. In Git mode, use empty Control checkpoints so dirty WIP remains unstaged and
  byte-for-byte untouched. In non-Git mode, append the fallback Control Event Ledger in `plan.md`.
- Do not advance a dependency gate until the required role returns. Main-thread interactivity does
  not make Planner, Implementer, and Reviewer parallel within one loop.
- Do not issue a final response while a mandatory role is running. After `ACCEPTED`, report the
  acceptance result and stop for explicit user archive confirmation. Continue with archive,
  Closure, and handoff only in response to that confirmation.

## Git checkpoint contract

Roles never mutate Git history or shared Git control state. They must not stage, commit, amend,
merge, rebase, cherry-pick, push, stash, switch branches, reset, run repository maintenance, or
remove worktrees. The Controller creates every checkpoint in every registered repository after
verifying the role's filesystem changes.

| Checkpoint | Allowed paths | Required identity |
|---|---|---|
| Planner initialization | Four-pack plus active index entry | Task, Planner, iteration 0 |
| Planner re-entry | `plan.md`, necessary `design.md`; `proposal.md` only with explicit user authorization | Task, Planner, iteration |
| Implementer candidate | `plan.md`, necessary `design.md`, declared deliverables | Task, Implementer, iteration, content snapshot |
| Reviewer evidence | `verify.md` only | Task, Reviewer, iteration, candidate, snapshot, verdict |
| Control event | No staged paths; empty checkpoint | Task, action, lifecycle/reasons or query/response payload, user authorization when required |
| Closure | Active four-pack deletion, archived four-pack addition, index | Task, Closure, iteration, accepted candidate/snapshot, post-acceptance user-authorization hash |

Protocol-v3 Implementer checkpointing is deliberately ordered rather than falsely atomic:

1. Preflight `CONTROL` and every participant before staging anything.
2. In stable `REPO-NNN` order, create an Implementer checkpoint only in each changed participant.
   Each records task, repository ID, iteration, and the control HEAD against which it was prepared.
   An unchanged participant retains its previous candidate/Base without an empty commit.
3. Create the `CONTROL` Implementer checkpoint last. It may be empty when only participants
   changed, and seals the canonical participant commit map plus the global content snapshot.
4. Only the control seal is the immutable candidate root and permits Reviewer dispatch.

If a participant commit fails, keep any earlier prepared commits and all remaining WIP. Do not
reset, amend, manufacture a control seal, or start Reviewer. Retry the remaining preparation when
safe or pause as `CONFIGURATION_GAP`.

The CONTROL HEAD used by the first participant checkpoint is the preparation anchor for that
iteration. On restart, take the previous sealed participant map—or each registered Base when no
seal exists—as the expected parent map. A prepared HEAD is reusable only when it is the direct
child of that expected commit and its task, repository, iteration, and control-parent trailers
match the one shared preparation anchor. The anchor must remain an ancestor of current CONTROL
HEAD, and every intervening CONTROL commit must be a Control event that still leaves the same
Implementer iteration expected; this permits an audited configuration pause/resume without
discarding prepared commits. Continue only the still-unprepared repositories using that same
anchor. Any intervening substantive checkpoint, divergent anchor, extra commit, or ambiguous
participant history pauses as `CONFIGURATION_GAP`; never reset it automatically.

Before each checkpoint, require the staging area to be empty and reject unmerged files or any
dirty/untracked path outside the role allowlist. Stage only the validated explicit path set with a
path-scoped command. Repository-wide `git add -A`, `git commit -a`, and blanket pathspecs are
forbidden. Require a non-empty participant or ordinary role commit, verify its actual path set,
and require a clean worktree afterward. The final CONTROL Implementer seal is the sole exception:
it may be an empty commit when at least one participant advanced. A required path that is ignored
or otherwise absent from both the index and validated change set is an error; a local file alone
is never proof that manual integration will retain it.

Treat the parent of Planner iteration 0 as the immutable Base. Before every later checkpoint,
authenticate every commit from that Base to HEAD as a linear Ralph chain for the same task and
valid role/iteration sequence. Reject merges, ordinary commits without matching trailers,
rewritten Base fields, Reviewer commits not parented by their exact Implementer candidate, and
Closure commits not parented by their exact accepted Reviewer.

Control checkpoints are part of that linear chain but never candidates. They must not stage,
capture, discard, reset, or hide WIP. A plan-query or plan-response Control event is an audit event,
not a Reviewer verdict. A formal Planner file edit still requires a clean, role-scoped worktree.

For an Implementer checkpoint, derive each repository's path allowlist from its registered write
scopes and both the preceding committed plan and current plan. A newly declared deliverable path
inside an existing scope requires explicit user authorization recorded by the Controller after
inspection; prefer Planner re-entry for material ownership changes. A new repository, repository
replacement/removal, or write-scope expansion always requires plan feedback, explicit user
authorization, and a fresh Planner checkpoint. This prevents an Implementer from expanding its own
commit authority merely by editing `plan.md` or `design.md`.
Required, optional, and explicit deliverable paths must not be inside the four-pack directory or be
an ancestor that contains it.

Reject any role, archive, or handoff path carrying `assume-unchanged`, `skip-worktree`, or another
non-default Git index state. After the Implementer commit, compare every current snapshot member
directly with its candidate-tree blob; a clean-looking worktree is not evidence that the candidate
contains those bytes. Reject empty directories and filesystem members Git cannot preserve, such as
FIFOs, sockets, and device nodes.

Use commit trailers as the machine-readable handoff:

```text
Ralph-Task: TASK-A
Ralph-Role: Implementer
Ralph-Iteration: 2
Ralph-Snapshot: <sha256>
```

Each prepared participant additionally records:

```text
Ralph-Repository: REPO-001
Ralph-Control-Parent: <full pre-seal CONTROL HEAD>
```

The final CONTROL Implementer seal records one compact, key-sorted JSON object:

```text
Ralph-Repositories: {"REPO-001":"<full-sha>","REPO-002":"<full-sha>"}
```

Reviewer and Closure checkpoints additionally record `Ralph-Candidate` and `Ralph-Verdict`.
For Protocol v3, the control Implementer seal records one canonical participant map. Reviewer and
Closure bind the SHA-256 of the full vector consisting of the control candidate plus every
participant candidate. Do not use repeated same-name trailers because parsers may collapse them.
Never write a commit's own SHA into a snapshot member such as `plan.md`; that creates a
self-reference. Candidate SHA belongs in `verify.md`, the index archive record, Git history, and
the final handoff.

An authorization token/reference is a non-secret audit identifier, such as a user message or
change-request ID. It proves that the Controller observed explicit user authorization; it is not
authentication and must never contain credentials.

## Planner contract

At initialization:

1. Read user intent, repository instructions, existing owners, prior tasks, and templates.
2. Create the complete four-pack.
3. Freeze scope and EARS-style or equivalently objective ACs in `proposal.md`.
4. Register every blocking external dependency and its required immutable unblock proof.
5. Specify the minimum verification boundary, classify deliverables, and declare guarded path
   budgets in `proposal.md` before implementation. Task-specific budgets require initialization
   authorization; otherwise use the CODE or DOCUMENT defaults.
6. Specify deliverables precisely in `design.md` and trace them in `plan.md`.
7. For Protocol v3, register every participant repository before implementation with stable ID,
   logical identity, branch, full Base, write scopes, AC links, merge order, and authorization.
   `CONTROL` remains defined by the plan's worktree/branch/Base and is integrated last.
8. Leave `verify.md` as an empty schema with `Final decision: PENDING`.
9. Do not implement deliverables.

On re-entry:

- Read every triggering `F-*` and `PQ-*` record. Diagnose it using the protocol finding types.
- Amend only what the diagnosis requires.
- For each finding, append a disposition of `FIX`, `DESCOPE`, `DEFER`, or `ESCALATE`, with the
  changed section/path, removed or replaced surface, budget delta, and next direct subject
  evidence. A `DEFER` on a required AC must become an external blocker or a user-authorized
  contract re-baseline.
- Record the reason, affected ACs, replacement text, and triggering IDs in the change logs.
- Obtain explicit user authorization before changing goal, scope, an AC, deliverable/path
  ownership, repository membership/write scopes, budget, schema generation, provider, phase,
  public interface, or assurance surface.
- For a new participant, follow this order: the user authorizes its logical identity and scopes;
  Controller creates or validates its dedicated worktree; Planner records ID, identity, branch,
  Base, scopes, ACs, merge order, and authorization; Controller checkpoints that registry change
  in CONTROL; only then may Implementer mutate the participant.
- Never delete or weaken an AC merely because it failed.
- Prefer contraction: state what is removed or replaced. Do not answer a failed assurance layer by
  adding another assurance layer without a pause and explicit authorization.

For an Implementer consultation, use a fresh Planner context and answer each `PQ-*` with
`ACCEPT`, `MODIFY`, `REJECT`, or `ESCALATE`, plus exactly one outcome:
`CLARIFIED`, `REPLAN_REQUIRED`, `CONTRACT_CHANGE_REQUIRED`, or `EXTERNAL_BLOCKER`. Consultation over
dirty WIP is read-only. `CLARIFIED` returns to the same Implementer. A formal Planner replan
requires a clean role-scoped tree; preserve dirty WIP and pause as `PLAN_CONFLICT` if no
user-authorized preservation path exists. A second consultation in the same implementation
iteration also pauses as `PLAN_CONFLICT` before more planning churn is allowed.

## Implementer contract

Every implementation iteration has an Implementer. The same Implementer may resume after a
`CLARIFIED` consultation and may:

- edit declared deliverables in `CONTROL` and registered participant repositories;
- update `plan.md`;
- amend `design.md` when implementation reveals a real design issue.

It may not edit `proposal.md`, reviewer history in `verify.md`, or claim final acceptance. For every
iteration, record either a substantive change or a precise blocker. Record changed paths, commands,
exit codes, relevant output, remaining failures, and any design amendment.

If the plan is ambiguous, contradictory, infeasible, outside declared ownership, or would require
an undeclared repository, repository-scope change, unauthorized deliverable, verification surface,
interface, or budget expansion, stop before touching that scope or creating a candidate and return
`PLAN_FEEDBACK_REQUIRED`. Supply a stable `PQ-NNN`, affected
`ITEM-*`/`DEL-*`/`AC-*`, the problem, whether WIP exists, the risk of continuing, and one
recommendation: clarify, replan, descope, or block. The Controller records a plan-query event and
dispatches a fresh Planner consultation. Do not manufacture a candidate merely to obtain Reviewer
feedback.

Continue the same implementation iteration only after a `CLARIFIED` plan-response. A
`REPLAN_REQUIRED` response routes to Planner when the worktree is clean; otherwise preserve WIP
and pause for a safe user decision. `CONTRACT_CHANGE_REQUIRED` pauses for user authorization, and
`EXTERNAL_BLOCKER` pauses as `EXTERNAL`.

Before review, require the guard to return `CONTINUE`, set the plan to `In Review` or the
repository-equivalent, and make the next step "Independent review."

## Reviewer contract

Use a fresh agent that did not implement the candidate. The Reviewer is read-only across every
registered repository except for appending one review record to control-repository `verify.md`.

The Reviewer must:

1. Authenticate the control candidate seal, participant commit map, full candidate-vector digest,
   clean worktrees, and exact HEAD in every repository.
2. Inspect actual diffs and declared deliverables in every repository, not only the Implementer's
   summary.
3. Re-run proportionate tests/checks independently.
4. Compare the candidate vector to every proposal AC and the design.
5. Record environment, inputs, commands, exit codes, relevant output, paths, full control candidate
   commit, Candidate Repositories matrix, vector digest, snapshot, residual risk, direct subject
   evidence delta, external blocker delta, and assurance surface delta.
   Normalize runtime roots in durable evidence to `<CONTROL_WORKTREE>` and
   `<REPO-NNN_WORKTREE>` while preserving argv structure; never archive an absolute participant
   worktree path as repository identity.
6. Give every finding exactly one type, preserve finding IDs across iterations, and state whether
   each is Open or Closed.
7. Record the exact snapshot SHA-256 produced by `snapshot`.
8. Emit only `ACCEPTED`, `CHANGES_REQUIRED`, `NEEDS_REPLAN`, or `BLOCKED`.

Before review starts, the Controller must create the participant checkpoints and final control
candidate seal. During review, every participant commit is immutable and remains its clean
worktree HEAD; the control candidate remains the authenticated ancestor of the sole dirty
`verify.md`. The Reviewer checkpoint verifies the candidate's task, role, iteration, participant
map, vector digest, and snapshot before committing the review record, and rejects any rewrite or
deletion of a prior review block.

The Reviewer may emit `ACCEPTED` only when all ACs pass with evidence, all required outputs exist,
all required items are done, the implementation and design agree, scope is respected, and no
unresolved P0/P1 or otherwise blocking finding exists. "Looks good," an Implementer report, or an
unrun command is not evidence.

`NEEDS_REPLAN` requires an open `CONTRACT_GAP`. `BLOCKED` requires an open `EXTERNAL_BLOCKER` that
prevents a required AC and always routes to `PAUSED[EXTERNAL]`. When a required AC lacks an
authorized real asset, device, permission, service, or live observation, prefer `BLOCKED` over
inventing substitute evidence.

## Finding semantics

Every new finding uses exactly one type:

| Type | Meaning |
|---|---|
| `SUBJECT_DEFECT` | The researched or delivered subject is incorrect or incomplete. |
| `ASSURANCE_DEFECT` | A test, harness, validator, simulator, or evidence generator is incorrect. |
| `CONTRACT_GAP` | The plan or design cannot express a correct implementable path. |
| `EXTERNAL_BLOCKER` | A required asset, device, permission, service, decision, or real observation is absent. |

Never reuse an `F-*` ID for a new mechanism or meaning. An `ASSURANCE_DEFECT` may block only with a
concrete reproducer showing a reachable false pass, false fail, or unsafe side effect. Its required
action is limited to:

- deleting or shrinking the assurance surface;
- direct Reviewer recomputation from immutable source evidence; or
- a minimum local repair that introduces no new schema, provider, phase, interface, simulator, or
  validator layer.

Any broader assurance expansion pauses as `ASSURANCE` and requires explicit user authorization.
The Reviewer must not prescribe "enhance the validator" as an unbounded action.

Each finding also has exactly one machine-readable action class:
`SUBJECT_FIX`, `SHRINK_ASSURANCE`, `DIRECT_RECOMPUTE`, `MINIMAL_LOCAL_FIX`, `REPLAN`,
`UNBLOCK_EXTERNAL`, `CLOSE`, or `ESCALATE`. An open `ASSURANCE_DEFECT` may use only
`SHRINK_ASSURANCE`, `DIRECT_RECOMPUTE`, `MINIMAL_LOCAL_FIX`, or `ESCALATE`; use `ESCALATE` when the
proposed response would expand assurance and therefore needs a pause and user decision. Closed
findings use `CLOSE`.

New tasks require typed findings. When continuing a legacy pack, never rewrite old review blocks to
insert types. Use `--legacy-findings` only while inspecting or controlling that existing pack,
append typed findings in every new review, and remove legacy mode once the latest required
history/schema has migrated.

## Loop control

The guard is a deliberately simple circuit breaker. It may inspect task tables, review types, Git
history, physical file line counts, and `git diff --numstat --no-renames`. It must not grow AST,
call-graph, schema, execution, peer-validation, or other semantic analysis. A guard is not a
validator and does not prove quality.

Count only the repository-relative paths explicitly listed in the proposal's Guard Budgets table.
For Protocol v3, every row names `CONTROL` or one registered `REPO-NNN`, and measurement runs
against that repository's own Base/HEAD.
The four-pack, required lifecycle edits, and Reviewer evidence do not consume Implementer delivery
budgets. If initialization declares no task-specific budget, use:

| Profile | Per-iteration warning | Per-iteration pause | Cumulative pause | Per-path pause |
|---|---:|---:|---:|---:|
| CODE | 3000 lines | 5000 lines | 12000 lines | 6000 lines |
| DOCUMENT | 10000 lines | 20000 lines | 50000 lines | 30000 lines |

Warnings do not block. Reaching a pause limit adds `BUDGET`. Increasing a budget after
initialization is a contract change and requires explicit user authorization; a Planner,
Implementer, or Controller must not silently raise it.

Before any continuation, add the applicable pause reasons:

- `EXTERNAL` when an unresolved dependency prevents a required AC.
- `BUDGET` when a declared iteration, cumulative, or per-path limit is reached.
- `REPLAN_STORM` after two consecutive `NEEDS_REPLAN` reviews.
- `ASSURANCE` after two consecutive reviews in which at least half of open P0/P1 findings are
  `ASSURANCE_DEFECT`.
- `USER_CHECKPOINT` after three completed reviews without acceptance.
- `PLAN_CONFLICT` after two unresolved plan consultations in one implementation iteration, or when
  a required Planner edit cannot safely coexist with preserved WIP.

The reason set is cumulative. One trigger is enough to pause. Do not wait for an iteration limit,
convert exhaustion into acceptance, or continue simply because another role has useful work.

If the guard returns `CONTINUE`, mandatory Planner re-entry still applies when Reviewer emits
`NEEDS_REPLAN`, a design invariant or public interface changes, ACs are ambiguous or
contradictory, or the same non-assurance finding remains open for two reviews. `CHANGES_REQUIRED`
otherwise returns to Implementer.

## Pause and resume

Pause, resume, abandon, split, plan-query, and plan-response are explicit Controller events. In Git
mode, create append-only empty Control checkpoints so all current tracked and untracked WIP remains
unstaged and unchanged. Do not create an Implementer candidate, dispatch a Reviewer, archive,
stash, reset, or discard files while paused. In non-Git mode, append the Controller-owned Control
Event Ledger in `plan.md`.

Every resume requires a user authorization token/reference and records the chosen resume role. The
token/reference is a non-secret audit identifier, not an authentication credential. Reasons may be
resolved by separate Control events; the final resume role must be legal for the intersection of
all reasons in that pause episode, not merely the last reason resolved.

| Pause reason | Required exit evidence | Default resume role |
|---|---|---|
| `EXTERNAL` | User authorization plus the registered immutable unblock proof | Implementer when the contract is unchanged; otherwise Planner |
| `BUDGET` | User-authorized contraction under the unchanged budget, or a budget/scope re-baseline | Implementer for contraction; Planner for re-baseline |
| `ASSURANCE` | User choice to shrink/minimally repair assurance or use direct Reviewer recomputation | Implementer for bounded contraction/repair; otherwise Planner |
| `REPLAN_STORM` | User choice to continue, split, re-scope, or abandon | Planner |
| `USER_CHECKPOINT` | User-selected next action | Role named by the authorization |
| `PLAN_CONFLICT` | User-selected WIP preservation and planning resolution | Planner only after a clean role-scoped tree; otherwise Implementer |
| `CONFIGURATION_GAP` | Corrected guard/dependency declaration plus user-authorized contract disposition | Planner, after the worktree is clean |
| `SCHEMA_MIGRATION` | User-authorized migration to the current typed review schema, or an explicit legacy-findings decision | Planner, after the worktree is clean |

When a pause occurs while Implementer is the only ordinary next actor, the Control state may add a
same-iteration Planner recovery target for reasons that permit or require re-planning. Planner
resume still requires a clean worktree. With dirty WIP, use an authorized Implementer contraction,
an ownership-safe split/preservation path, or abandonment; never let Planner edit over that WIP.

Resume removes only the reasons explicitly resolved by evidence. If any reason remains, lifecycle
stays `PAUSED`. A new pause revokes every older resume grant. A resume event does not itself modify
the contract, approve a budget increase, or make WIP a candidate. It never skips the next candidate
guard. `BUDGET` is not suppressible: over-budget WIP must contract below the unchanged limit, or an
authorized Planner re-baseline must establish a new limit first. `CONFIGURATION_GAP` and
`SCHEMA_MIGRATION` may suppress only the Planner-entry guard and must pass normal lifecycle
validation before the Planner checkpoint. Historical churn reasons and an evidenced `EXTERNAL`
resolution remain suppressed only until the next Reviewer checkpoint; any new pause revokes that
grant, and a later `BLOCKED` verdict reopens the external reason.

The user may instead authorize an `abandon` Control event, which marks the task `ABANDONED` as a
terminal non-success while retaining its branch/worktree/WIP. A `split` Control event requires the
child task ID and transferred paths, leaves the parent paused, and records exclusive child
ownership. Both require non-secret explicit user authorization. A child returns through the
manual-merge boundary; it never auto-merges into the parent.

## Snapshot contract

The acceptance snapshot contains:

- `proposal.md`;
- `design.md`;
- `plan.md`;
- every required deliverable path declared in the standard plan table, namespaced by repository.

It excludes `verify.md` to avoid a self-referential hash when the Reviewer appends evidence. Any
post-review mutation of a snapshot member invalidates acceptance and requires another review.

In single-repository Git mode, required repository deliverables must be tracked by the Implementer
candidate and the legacy content-only snapshot remains unchanged. In Protocol-v3 multi-repository
mode, the snapshot uses a new schema that includes the canonical participant commit map and
repo-qualified entries. Every required deliverable must match the blob/tree in its named candidate
commit. Reviewer acceptance binds the global content digest to the control candidate and full
candidate-vector digest through `verify.md` and commit trailers.

For project-specific plan formats, pass each deliverable explicitly to `snapshot` with
`--artifact <path>`.

## Closure and archival

Close only from `ACCEPTED` plus explicit user confirmation received after the acceptance report.

1. Before final acceptance, complete any authorized promotion/publication and record its identity.
   If this changes a snapshot member, keep the task active and run another
   Implementer -> Reviewer iteration.
2. Prepare final status fields and links before final acceptance. Prefer root-relative links; when
   final bytes depend on archive depth, stage those exact bytes outside active/archive and review
   the staged candidate before the atomic move.
3. Present the exact accepted candidate/vector, checks, residual risks, and retained deliverables
   to the user, then stop. A prior instruction to run through archival does not count as this
   confirmation.
4. After a new explicit user confirmation, derive one non-secret authorization reference for this
   archive decision. Pass that same reference to both `archive --authorization-token` and
   `checkpoint --role closure --authorization-token`; persist only its SHA-256.
5. Ensure deliverables live outside the task directory, remain in their named repositories, and
   every participant worktree is clean at its accepted candidate.
6. Before moving, require the active four-pack and task index in the Reviewer commit and reject an
   ignored archive destination. After the exact archive-ready snapshot is accepted, move all four
   files together without changing their bytes; do not discard failed review history.
7. Update the index in the same transaction: remove the active row, add an archived row with task
   link, deliverable links, final verdict, iteration count, full accepted snapshot, and
   promotion/commit identity when applicable.
8. Confirm the task ID exists in exactly one of active or archive locations.
9. Run `git diff --check`; include untracked files in whitespace checks; check Markdown links after
   the move; record commands and results.
10. Run `validate --phase archived`.
11. Create the Closure checkpoint and require it to contain all four active deletions, all four
    archived additions, the index update, and `Ralph-Authorization-SHA256`; then require a clean
    loop worktree.
12. Run the read-only `handoff` gate and return the exact control branch/Base/candidate/Closure,
    snapshot, vector digest, and every participant's ID, Base, branch, candidate, changed paths,
    merge order, deliverables, Control-event history, authorization hash, and validation evidence
    to the user.

If the move or index update changes an accepted byte or fails integrity checks, roll back to active
state. Fix and re-review before another archive attempt; never review an already-marked archive as
though it were accepted.

Closure is immutable and terminal. A post-Closure change is a new superseding task that references
the archived parent; never silently reopen, move, or rewrite the archived four-pack.

The bundled `archive` command supports only indexes containing the Ralph marker blocks from the
bundled `index.md` template. It refuses custom indexes rather than guessing their structure.
Read-only handoff remains compatible with a pre-0.3.1 Closure that lacks the authorization
trailer, but reports that legacy gap; every newly created archive and Closure must pass the gate
above.

## Manual integration boundary

The plugin ends with a manual-merge handoff. It must not create an integration queue or execute
merge, rebase, cherry-pick, push, branch deletion, or worktree deletion in any repository. The
user owns the Planner-declared integration order and conflict resolution. Cross-repository
candidate creation is ordered and recoverable, not atomic; merging only a subset does not
integrate the accepted vector.

A clean merge that preserves every accepted snapshot member preserves the branch review evidence,
but repository-level integration checks should still be run. If conflict resolution or another
integrated change alters proposal, design, plan, or a declared deliverable, the old acceptance no
longer covers the merged bytes; run a new Implementer -> Reviewer pass before treating them as
accepted. Index-only conflict resolution requires the repository's archive/index validation but
does not by itself change the content snapshot.
