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
- [Loop control](#loop-control)
- [Snapshot contract](#snapshot-contract)
- [Closure and archival](#closure-and-archival)
- [Manual integration boundary](#manual-integration-boundary)

## State machine

Use this transition graph:

```text
INIT -> PLANNED -> PLANNER_CHECKPOINT -> IMPLEMENTING -> CANDIDATE_CHECKPOINT -> REVIEWING
REVIEWING -> REVIEW_CHECKPOINT
              | ACCEPTED         -> READY_TO_ARCHIVE -> ARCHIVED -> CLOSURE_CHECKPOINT
              | CHANGES_REQUIRED -> IMPLEMENTING
              | NEEDS_REPLAN     -> PLANNED
              ` BLOCKED          -> PAUSED
CLOSURE_CHECKPOINT -> MANUAL_MERGE_HANDOFF
```

Initialization always uses Planner -> Implementer -> Reviewer. Later iterations use
Planner? -> Implementer -> Reviewer. The question mark is conditional; the other two roles are
mandatory.

`BLOCKED` is a pause, not a terminal success. Resume only after the stated external state changes.
`MANUAL_MERGE_HANDOFF` is the plugin boundary, not proof that the user merged the branch.

## Authority

| Concern | Authority |
|---|---|
| Goal, scope, non-goals, ACs | `proposal.md`, Planner-owned |
| Technical approach and output shape | `design.md`; Implementer may amend with rationale |
| Progress, tasks, commands, handoff | `plan.md`, Implementer-owned after initialization |
| Evidence, findings, verdict | `verify.md`, Reviewer-owned and append-only |
| Current/archived task registration | Project task index |
| Stable deliverable body | Declared owner path outside the task pack |
| Role dispatch, user steering, Git staging and commits | Controller |
| Merge, cherry-pick, push, conflict resolution, worktree cleanup | User |

Repository-local instructions and templates override the bundled defaults. Do not duplicate a
stable deliverable body into the task pack; link it and preserve its identity instead.
When a local Verify schema has AC records and a Final Review instead of `ITER-NNN` sections, retain
those required sections and append an equivalent round ledger; do not replace the local contract to
make the bundled validator happy.

## Required traceability

- Give each acceptance criterion a stable `AC-NNN` ID and one objectively testable result.
- Give each deliverable a stable `DEL-NNN` ID, declared path, format, owner, retention rule, and
  one or more AC links.
- Give each execution item a stable `ITEM-NNN` ID, dependency list, owner, target path, and AC/DEL
  links.
- Give each reviewer finding a stable `F-NNN` ID and one or more AC links.
- Never reuse an ID for a different meaning. Preserve superseded history.

Every proposal AC must appear in the plan's verification matrix and in every complete reviewer
decision matrix. A summary is not a substitute for AC-level evidence.

## Worktree and concurrency contract

- For Git work, allocate one globally unique task ID, one linked worktree, and one
  `ralph/<TASK-ID>` branch per loop. Record the absolute worktree root, full base commit, branch,
  and manual merge mode before planning.
- Give every role the same absolute worktree root and require all tools to use it as cwd.
- Never run two write-capable roles concurrently in one worktree.
- Declare exclusive write ownership for repository paths and non-repository mutable resources.
  Shared databases, ports, caches, generated directories, devices, and publication targets count
  as conflicts even when worktree paths differ.
- If active loops have overlapping ownership, establish an explicit dependency and serialize their
  Implementer passes or pause one as `BLOCKED`.
- Worktree creation must refuse existing paths/branches and must not use `--force`. The loop never
  removes its worktree or branch.
- Branch-local copies of a shared index may conflict during manual integration. Do not solve that
  with concurrent writes or an integration queue; leave conflict resolution to the user.

## Interactive Controller contract

- Spawn one fresh background role at a time for a loop and remain available in the main thread.
- Use bounded waits and send meaningful status updates at least every 60 seconds.
- Accept user steering while a role runs. Forward non-material clarifications when safe.
- A change to goal, scope, AC, design invariant, path ownership, or reviewed bytes invalidates the
  current candidate. Interrupt or let the role stop safely, record the change, and route through
  Planner -> Implementer -> Reviewer.
- Do not advance a dependency gate until the required role returns. Main-thread interactivity does
  not make Planner, Implementer, and Reviewer parallel within one loop.
- Do not issue a final response while a mandatory role, checkpoint, archival validation, or
  handoff remains incomplete.

## Git checkpoint contract

Roles never mutate Git history or shared Git control state. They must not stage, commit, amend,
merge, rebase, cherry-pick, push, stash, switch branches, reset, run repository maintenance, or
remove worktrees. The Controller creates every checkpoint after verifying the role's filesystem
changes.

| Checkpoint | Allowed paths | Required identity |
|---|---|---|
| Planner initialization | Four-pack plus active index entry | Task, Planner, iteration 0 |
| Planner re-entry | `plan.md`, necessary `design.md`; `proposal.md` only with explicit user authorization | Task, Planner, iteration |
| Implementer candidate | `plan.md`, necessary `design.md`, declared deliverables | Task, Implementer, iteration, content snapshot |
| Reviewer evidence | `verify.md` only | Task, Reviewer, iteration, candidate, snapshot, verdict |
| Closure | Active four-pack deletion, archived four-pack addition, index | Task, Closure, iteration, accepted candidate/snapshot |

Before each checkpoint, require the staging area to be empty and reject unmerged files or any
dirty/untracked path outside the role allowlist. Stage only the validated explicit path set with a
path-scoped command. Repository-wide `git add -A`, `git commit -a`, and blanket pathspecs are
forbidden. Require a non-empty commit, verify its actual path set, and require a clean worktree
afterward. A required path that is ignored or otherwise absent from both the index and validated
change set is an error; a local file alone is never proof that manual integration will retain it.

Treat the parent of Planner iteration 0 as the immutable Base. Before every later checkpoint,
authenticate every commit from that Base to HEAD as a linear Ralph chain for the same task and
valid role/iteration sequence. Reject merges, ordinary commits without matching trailers,
rewritten Base fields, Reviewer commits not parented by their exact Implementer candidate, and
Closure commits not parented by their exact accepted Reviewer.

For an Implementer checkpoint, derive the path allowlist from both the preceding committed plan and
the current plan. A newly declared deliverable path requires explicit Controller approval after
inspection; prefer Planner re-entry for material ownership changes. This prevents an Implementer
from expanding its own write authority merely by editing `plan.md`. Required, optional, and
explicit deliverable paths must not be inside the four-pack directory or be an ancestor that
contains it.

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

Reviewer and Closure checkpoints additionally record `Ralph-Candidate` and `Ralph-Verdict`.
Never write a commit's own SHA into a snapshot member such as `plan.md`; that creates a
self-reference. Candidate SHA belongs in `verify.md`, the index archive record, Git history, and
the final handoff.

## Planner contract

At initialization:

1. Read user intent, repository instructions, existing owners, prior tasks, and templates.
2. Create the complete four-pack.
3. Freeze scope and EARS-style or equivalently objective ACs in `proposal.md`.
4. Specify deliverables precisely in `design.md` and trace them in `plan.md`.
5. Leave `verify.md` as an empty schema with `Final decision: PENDING`.
6. Do not implement deliverables.

On re-entry:

- Diagnose the failure as implementation defect, design gap, goal ambiguity, or external blocker.
- Amend only what the diagnosis requires.
- Record the reason, affected ACs, and replacement text in the change log.
- Obtain explicit user authorization before materially changing goal, scope, or ACs.
- Never delete or weaken an AC merely because it failed.

## Implementer contract

The Implementer runs once in every iteration and may:

- edit declared deliverables;
- update `plan.md`;
- amend `design.md` when implementation reveals a real design issue.

It may not edit `proposal.md`, reviewer history in `verify.md`, or claim final acceptance. For every
iteration, record either a substantive change or a precise blocker. Record changed paths, commands,
exit codes, relevant output, remaining failures, and any design amendment.

Before review, set the plan to `In Review` or the repository-equivalent and make the next step
"Independent review."

## Reviewer contract

Use a fresh agent that did not implement the candidate. The Reviewer is read-only except for
appending one review record to `verify.md`.

The Reviewer must:

1. Inspect actual diffs and declared deliverables, not only the Implementer's summary.
2. Re-run proportionate tests/checks independently.
3. Compare the candidate to every proposal AC and the design.
4. Record environment, inputs, commands, exit codes, relevant output, paths, full candidate commit,
   candidate branch, snapshot, and residual risk.
5. Preserve finding IDs across iterations and state whether each is Open or Closed.
6. Record the exact snapshot SHA-256 produced by `snapshot`.
7. Emit only `ACCEPTED`, `CHANGES_REQUIRED`, `NEEDS_REPLAN`, or `BLOCKED`.

Before review starts, the Controller must create the Implementer candidate checkpoint. During
review, that commit is immutable and is the worktree HEAD; Reviewer may leave only `verify.md`
dirty. The Reviewer checkpoint verifies the candidate's task, role, iteration, and snapshot
trailers before committing the review record, and rejects any rewrite or deletion of a prior
review block.

The Reviewer may emit `ACCEPTED` only when all ACs pass with evidence, all required outputs exist,
all required items are done, the implementation and design agree, scope is respected, and no
unresolved P0/P1 or otherwise blocking finding exists. "Looks good," an Implementer report, or an
unrun command is not evidence.

## Loop control

Mandatory Planner re-entry triggers:

- Reviewer emits `NEEDS_REPLAN`.
- The same finding remains open for two reviews.
- Two consecutive iterations have the same candidate snapshot or materially identical failure.
- A public interface, scientific claim, data contract, security boundary, or other design invariant
  changes.
- ACs are ambiguous, contradictory, or untestable.
- The soft threshold of three iterations is reached.

At a hard threshold of eight iterations, pause and ask the user whether to re-scope, unblock an
external dependency, or continue. Preserve the active task and evidence. Never convert exhaustion
into acceptance.

## Snapshot contract

The acceptance snapshot contains:

- `proposal.md`;
- `design.md`;
- `plan.md`;
- every required deliverable path declared in the standard plan table.

It excludes `verify.md` to avoid a self-referential hash when the Reviewer appends evidence. Any
post-review mutation of a snapshot member invalidates acceptance and requires another review.

In Git mode, required repository deliverables must be tracked by the Implementer candidate. The
snapshot digest remains content-based and does not include Git metadata. Reviewer acceptance binds
that digest to the full candidate commit through `verify.md` and commit trailers.

For project-specific plan formats, pass each deliverable explicitly to `snapshot` with
`--artifact <path>`.

## Closure and archival

Close only from `ACCEPTED`.

1. Before final acceptance, complete any authorized promotion/publication and record its identity.
   If this changes a snapshot member, keep the task active and run another
   Implementer -> Reviewer iteration.
2. Prepare final status fields and links before final acceptance. Prefer root-relative links; when
   final bytes depend on archive depth, stage those exact bytes outside active/archive and review
   the staged candidate before the atomic move.
3. Ensure deliverables live outside the task directory and remain in place.
4. Before moving, require the active four-pack and task index in the Reviewer commit and reject an
   ignored archive destination. After the exact archive-ready snapshot is accepted, move all four
   files together without changing their bytes; do not discard failed review history.
5. Update the index in the same transaction: remove the active row, add an archived row with task
   link, deliverable links, final verdict, iteration count, full accepted snapshot, and
   promotion/commit identity when applicable.
6. Confirm the task ID exists in exactly one of active or archive locations.
7. Run `git diff --check`; include untracked files in whitespace checks; check Markdown links after
   the move; record commands and results.
8. Run `validate --phase archived`.
9. Create the Closure checkpoint and require it to contain all four active deletions, all four
   archived additions, and the index update; then require a clean loop worktree.
10. Run the read-only `handoff` gate and return its exact branch, base, candidate, closure commit,
    snapshot, changed paths, deliverables, and validation evidence to the user.

If the move or index update changes an accepted byte or fails integrity checks, roll back to active
state. Fix and re-review before another archive attempt; never review an already-marked archive as
though it were accepted.

The bundled `archive` command supports only indexes containing the Ralph marker blocks from the
bundled `index.md` template. It refuses custom indexes rather than guessing their structure.

## Manual integration boundary

The plugin ends with a manual-merge handoff. It must not create an integration queue or execute
merge, rebase, cherry-pick, push, branch deletion, or worktree deletion. The user owns integration
order and conflict resolution.

A clean merge that preserves every accepted snapshot member preserves the branch review evidence,
but repository-level integration checks should still be run. If conflict resolution or another
integrated change alters proposal, design, plan, or a declared deliverable, the old acceptance no
longer covers the merged bytes; run a new Implementer -> Reviewer pass before treating them as
accepted. Index-only conflict resolution requires the repository's archive/index validation but
does not by itself change the content snapshot.
