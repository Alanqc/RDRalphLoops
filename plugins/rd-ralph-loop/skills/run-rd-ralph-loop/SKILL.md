---
name: run-rd-ralph-loop
description: Orchestrate evidence-gated research and development work as a three-role Ralph loop using proposal.md, design.md, plan.md, and verify.md. Use when Codex must run one or more isolated R&D loops, create dedicated Git worktrees and branches, checkpoint Planner/Implementer/Reviewer changes, obtain independent acceptance, archive the four-document task pack, or prepare a user-controlled manual-merge handoff; also trigger for Ralph loop, 研发闭环, 四件套, iterative implementation/review, and acceptance-gated archival.
---

# Run an R&D Ralph Loop

Use one interactive Controller and three isolated roles: Planner, Implementer, and Reviewer. Make
the Planner mandatory at initialization and conditional later. Run the Implementer in every
implementation iteration and an independent Reviewer for every immutable candidate. An
Implementer plan consultation stays inside the same iteration and creates no candidate or review.
Treat Reviewer acceptance as the only successful exit.

The Controller owns orchestration, Git state in the workspace/control repository and every
registered participant repository, checkpoints, status updates, and user interaction. Role agents
edit only their authorized files and never commit, merge, push, rebase, cherry-pick, stash, switch
branches, reset, or remove worktrees.

Read [references/protocol.md](references/protocol.md) before starting. Read
[references/role-prompts.md](references/role-prompts.md) immediately before dispatching roles.
Resolve `<skill-root>` as the directory containing this `SKILL.md`; run bundled paths from there.

## Keep the Controller interactive

- Dispatch every role as a background subagent with a fresh role context.
- Keep the main task open while roles run. Use bounded waits, report meaningful progress at least
  every 60 seconds, and continue accepting user messages.
- Treat the 60-second interval as a Controller reporting cadence, not a role or first-write
  deadline. Fresh context isolates roles; it does not justify restarting a role that is still
  running. File mtimes, sizes, and absent or partial writes do not establish a stall. For apparent
  inactivity, request one status update and wait through two more bounded status cycles; continue
  waiting if the role replies or shows observable role/tool progress. Confirm the old role has
  stopped before dispatching at most one fresh replacement. If that replacement also meets this
  stall test, stop and ask the user instead of restarting again.
- Treat a message intended for the current run as steering. Forward ordinary clarifications to the
  active role when safe. If it changes the goal, scope, an AC, a design invariant, path ownership,
  or the candidate under review, interrupt or invalidate the current candidate and route through
  Planner -> Implementer -> Reviewer again.
- Treat a queued follow-up as next-run work unless it changes the current contract.
- Preserve role dependencies: do not start Implementer before Planner returns, and do not start
  Reviewer before the Implementer checkpoint and snapshot exist. Controller interactivity does not
  authorize concurrent writers in one worktree.
- Treat pause, resume, abandon, split, plan-query, and plan-response as Controller-owned
  append-only events. In Git mode, use empty Control checkpoints that leave current WIP unstaged
  and untouched.
- Do not send the final response while a required role is still running. Finalize only after
  acceptance, archival, closure checkpoint, and handoff.

## Isolate every Git loop

Use one workspace/control Git worktree for the four-pack, index, lifecycle chain, review evidence,
archive, and final candidate seal. A task may also register zero or more participant Git
worktrees for Implementer deliverables. Every repository uses the same task ID and its own
`ralph/<task-id>` branch, index, immutable Base, write scopes, and manual-merge handoff.
Multiple loops may run on the same machine, but they must not share a checkout, branch, Git index,
write scope, or mutable external resource.

Create the control worktree before dispatching its Planner. Create each known participant
worktree the same way, against that repository's own integration checkout and Base:

```bash
python3 <skill-root>/scripts/ralph_loop.py worktree-create \
  --repo-root <integration-checkout> \
  --worktree-path <dedicated-worktree-path> \
  --task-id <unique-task-id> \
  --base <full-base-commit-or-ref>
```

This creates `ralph/<task-id>` without `--force` and never removes it. If the user or Codex app
already created a dedicated control or participant worktree, validate it instead:

```bash
python3 <skill-root>/scripts/ralph_loop.py git-context \
  --workspace-root <worktree> \
  --task-id <unique-task-id> \
  --require-git \
  --require-clean
```

Pass the same control root, task directory, run ID, and complete repository mapping to every role.
For Protocol v3, append one `--repo REPO-NNN=/absolute/participant-worktree` for every participant
to every `guard`, `control`, `snapshot`, `validate`, `checkpoint`, `archive`, and `handoff`
invocation. The mapping is machine-local; accepted documents identify repositories by stable
`REPO-NNN`, logical identity, branch, and Base rather than temporary worktree paths. V3 command
examples below omit these repeated arguments for readability; append the complete mapping to each
one. A Protocol-v3 task with an `N/A` participant row is the CONTROL-only compatibility profile:
pass no `--repo`, retain the legacy snapshot shape, and record candidate-vector fields as `N/A`.

Choose globally unique task IDs. Declare exclusive ownership for deliverable paths, generated
directories, databases, ports, caches, devices, and external publication targets. If active loops
overlap on any mutable resource, mark the dependency and serialize those Implementer passes or
pause as `BLOCKED`. Never map two repository IDs to one worktree or nest a participant worktree
inside another registered repository.

A readiness child task must reference its paused parent, parent Base/candidate, transferred paths,
returned deliverables, and parent resume predicate. The child has exclusive write ownership of
transferred paths until handback; the parent stays paused and must not compete for them. A child
cannot claim the parent's live acceptance.

For a non-Git workspace with no participant repositories, skip worktree and checkpoint commands
and retain the content-snapshot workflow. A multi-repository candidate vector requires `CONTROL`
to be a Git worktree because its final checkpoint is the authoritative seal for all participant
commits.

## Establish the local contract

1. Inspect repository instructions and existing task conventions before writing.
2. If the repository already has four-pack templates or an index protocol, use them as
   authoritative and preserve required sections, names, states, IDs, link style, promotion rules,
   and archive layout. Add loop history without replacing local verification records.
3. Otherwise run:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py init \
     --workspace-root <worktree-or-workspace> \
     --tasks-root <workspace>/tasks \
     --task-id <unique-id> \
     --title "<task title>"
   ```

4. Keep deliverables outside the task-pack directory and use paths relative to their named
   repository. Archival moves the four-pack in `CONTROL`; it must not move or delete participant
   deliverables.
5. Register the active task in the branch-local index. The helper updates only its marker-managed
   index; update a project-specific index according to that repository's contract.

The helper's lifecycle schema is normative only for the bundled templates. With a project-specific
four-pack, keep repository-native gates, pass nonstandard control deliverables through repeated
`--artifact <path>` arguments and participant deliverables as
`--artifact REPO-NNN=<path>`, and enforce the same role, Git, and evidence invariants manually.

## Initialize with the Planner

Dispatch a fresh Planner. Require it to complete all four files before implementation:

- `proposal.md`: freeze the goal, scope, non-goals, constraints, and stable `AC-*` criteria;
  register every blocking external dependency and immutable unblock proof plus guarded deliverable
  path budgets.
- `design.md`: define the approach, minimum verification boundary, interfaces, risks, decisions,
  exact deliverable paths, classes, owners, formats, retention, concurrent resource ownership, and
  the immutable Repository Participants registry.
- `plan.md`: map every `DEL-*` and `ITEM-*` to `AC-*`, include dependencies and executable
  verification methods, and record worktree, branch, base commit, and manual merge mode.
- `verify.md`: create only the empty review schema. Do not pre-fill evidence or a verdict.

The Planner owns `proposal.md`. A material goal, scope, or AC change requires explicit user
authorization and a recorded re-baseline; never weaken criteria to fit the implementation.
Adding a repository, repository write scope, deliverable/path, budget, schema generation, provider,
phase, public interface, or assurance surface after initialization also requires explicit user
authorization. An Implementer may inspect a user-identified repository read-only when needed to
justify `PLAN_FEEDBACK_REQUIRED`, but must not modify it or include it in a candidate until a fresh
Planner checkpoint registers it. The executable order is: user authorizes the proposed logical
identity and scopes; Controller creates or validates its dedicated worktree; Planner records its
ID, identity, branch, Base, scopes, ACs, merge order, and authorization; Controller creates the
fresh CONTROL Planner checkpoint; only then may Implementer mutate it. An authorization
token/reference is a non-secret audit identifier, not an authentication credential.

Guard measurement is intentionally limited to physical line counts and
`git diff --numstat --no-renames` for proposal-listed deliverable paths. Never add AST, call-graph,
schema, execution, or semantic validation to the guard itself. Use the CODE/DOCUMENT defaults in
the proposal template unless the user approves task-specific initialization values. Every
deliverable must be covered by a guarded prefix or a reasoned `path :: reason` exclusion.

Validate the bundled planning pack, then let the Controller create the checkpoint:

```bash
python3 <skill-root>/scripts/ralph_loop.py validate \
  --workspace-root <workspace> \
  --task-dir <task-dir> \
  --phase planned

python3 <skill-root>/scripts/ralph_loop.py checkpoint \
  --workspace-root <worktree> \
  --task-dir <task-dir> \
  --task-id <task-id> \
  --role planner-init \
  --iteration 0 \
  --index <task-index>
```

The checkpoint refuses a dirty staging area, out-of-role paths, detached or wrong branches,
unmapped or mismatched participant repositories, and primary-worktree use unless an explicitly
serialized single-loop run passes `--allow-primary-worktree`. It pins the control Base to the
parent of Planner iteration 0, validates every participant Base/branch/write scope, and
authenticates every later control commit as the same task's linear Ralph checkpoint chain.

## Run one iteration

For iteration `N`:

1. Run Planner first only for initialization or a re-entry trigger. After re-entry, checkpoint with
   `--role planner-replan --iteration N`. Add `--allow-contract-change` and
   `--authorization-token <non-secret-user-reference>` only after the user explicitly authorizes
   a proposal/AC re-baseline, repository-registry change, scope expansion, or other controlled
   contract change. Require a disposition for every triggering `F-*`/`PQ-*`, what was removed or
   replaced, the budget delta, and the next direct subject evidence. New deliverables/paths,
   budgets, schema generations, providers, phases, interfaces, or assurance layers require
   explicit user authorization, not merely Controller preference.

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py guard \
     --role planner-replan \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --task-id <task-id>
   ```

   Checkpoint the Planner only when the guard returns `CONTINUE`.
2. Run Implementer. Require it to update deliverables in `CONTROL` and registered participant
   repositories plus `plan.md`, run declared checks, and record changed paths, commands, results,
   and unresolved issues. It may amend `design.md` only when necessary and must log why, but may
   not add/remove a repository or expand its write scopes. It must not edit `proposal.md` or
   `verify.md`.
   - If it discovers an ambiguous, contradictory, infeasible, ownership-breaking, new-repository,
     or expansion-requiring plan, stop before touching the undeclared scope or creating a candidate
     with `PLAN_FEEDBACK_REQUIRED`.
     Require a stable `PQ-NNN`, affected `ITEM-*`/`DEL-*`/`AC-*`, whether WIP exists, continue-risk,
     and a recommendation.
   - Record a plan-query Control event and dispatch a fresh Planner for read-only consultation.
     The Planner must answer each query with `ACCEPT`, `MODIFY`, `REJECT`, or `ESCALATE`, plus
     exactly one outcome: `CLARIFIED`, `REPLAN_REQUIRED`, `CONTRACT_CHANGE_REQUIRED`, or
     `EXTERNAL_BLOCKER`. Record a plan-response Control event. These events are not Reviewer
     verdicts.
   - `CLARIFIED` returns to the same Implementer. A formal `REPLAN_REQUIRED` file edit requires a
     clean role-scoped tree. Preserve dirty WIP and pause as `PLAN_CONFLICT` rather than stashing,
     discarding, or letting Planner edit over it. Contract changes pause for user authorization;
     external blockers pause as `EXTERNAL`.
   - A second consultation in the same implementation iteration pauses as `PLAN_CONFLICT` before
     more planning churn is allowed.
3. After the Implementer returns, inspect every registered worktree and create the immutable
   multi-repository candidate:

   First run the Implementer guard. If it returns a pause decision, record an empty Control pause
   checkpoint, preserve all tracked and untracked WIP unstaged, and do not create a candidate or
   dispatch Reviewer.

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py guard \
     --role implementer \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --task-id <task-id>

   python3 <skill-root>/scripts/ralph_loop.py participant-checkpoint \
     --workspace-root <control-worktree> \
     --task-dir <task-dir> \
     --task-id <task-id> \
     --repo REPO-001=<participant-worktree> \
     --repo-id REPO-001 \
     --iteration N

   # Repeat participant-checkpoint in REPO-NNN order for each changed participant,
   # then seal the candidate in CONTROL.
   python3 <skill-root>/scripts/ralph_loop.py checkpoint \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --task-id <task-id> \
     --role implementer \
     --iteration N
   ```

   The Controller stages only validated paths in one repository at a time. Never use
   repository-wide `git add -A` or `git commit -a`. Participant commits are recoverable prepared
   commits, not candidates by themselves. The final control checkpoint seals their full commit
   map and the global content snapshot; only that control commit is the candidate root. If a later
   participant commit fails, preserve earlier prepared commits and WIP—never reset or amend them—and
   do not dispatch Reviewer until the control seal succeeds. All prepared commits share the
   CONTROL HEAD used by the first participant as their preparation anchor. An audited
   configuration pause/resume may add only Control-event descendants before sealing; any
   intervening substantive checkpoint makes the prepared batch stale and requires user handling.

   If an authorized design amendment introduces a new deliverable path in an already registered
   repository, inspect it and pass one repository-qualified
   `--allow-new-deliverable REPO-NNN=<path>`; otherwise the checkpoint refuses it. New repositories
   and write-scope expansions require Planner re-entry, not this flag. A declared or explicit
   deliverable may not overlap the four-pack directory. Snapshot members with non-default Git
   index flags are refused, and every candidate-tree blob must match the filesystem bytes exactly.
4. Reproduce the candidate snapshot from the clean commit:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py snapshot \
     --workspace-root <worktree> \
     --task-dir <task-dir>
   ```

5. Run a fresh independent Reviewer. Give it the task pack, repository registry, declared
   deliverables, implementation evidence, exact control candidate commit, full participant commit
   map, candidate-vector digest, and snapshot; never give it a desired verdict.
6. The Reviewer may inspect files and run checks but may modify only `verify.md`. It appends exactly
   one review record, maps every finding to `AC-*`, classifies it as `SUBJECT_DEFECT`,
   `ASSURANCE_DEFECT`, `CONTRACT_GAP`, or `EXTERNAL_BLOCKER`, records independently observed
   evidence, direct subject evidence delta, external blocker delta, assurance surface delta,
   `Candidate commit`, `Candidate branch`, the Candidate Repositories matrix, candidate-vector
   digest, and snapshot, then emits exactly one verdict:
   `ACCEPTED`, `CHANGES_REQUIRED`, `NEEDS_REPLAN`, or `BLOCKED`.
   `NEEDS_REPLAN` requires an open `CONTRACT_GAP`; `BLOCKED` requires an open
   `EXTERNAL_BLOCKER` preventing a required AC. An `ASSURANCE_DEFECT` must have a concrete reachable
   false result or unsafe side effect. Its action is limited to assurance contraction, Reviewer
   recomputation from immutable evidence, or a minimum local repair within existing interfaces.
   Record one action class: `SUBJECT_FIX`, `SHRINK_ASSURANCE`, `DIRECT_RECOMPUTE`,
   `MINIMAL_LOCAL_FIX`, `REPLAN`, `UNBLOCK_EXTERNAL`, `CLOSE`, or `ESCALATE`. Open assurance
   findings may use only the three assurance-specific classes or `ESCALATE`. Normalize
   machine-local roots in durable Reviewer environment/command evidence to `<CONTROL_WORKTREE>`
   and `<REPO-NNN_WORKTREE>` without changing argv structure, exit codes, or relevant output.
7. Validate the review before committing it:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py validate \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --phase reviewed

   python3 <skill-root>/scripts/ralph_loop.py checkpoint \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --task-id <task-id> \
     --role reviewer \
     --iteration N
   ```

   The Reviewer checkpoint accepts only control-repository `verify.md` changes, preserves every
   prior review block, and verifies that the recorded control candidate and every participant
   commit equal the immutable candidate vector and their Implementer trailers.
8. Route the verdict:

   - `ACCEPTED`: run the accepted gate, close, archive, and hand off.
   - `BLOCKED`: record an explicit Control pause with reason `EXTERNAL`; never route it
     mechanically to Planner.
   - `CHANGES_REQUIRED` or `NEEDS_REPLAN`: run the post-review guard before dispatching another
     role. `NEEDS_REPLAN` selects Planner only when the guard returns `CONTINUE`;
     `CHANGES_REQUIRED` otherwise selects Implementer.

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py guard \
     --role post-review \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --task-id <task-id>
   ```

The guard uses a cumulative reason set and pauses on any declared budget limit, an unresolved
external dependency blocking a required AC, two consecutive `NEEDS_REPLAN` reviews, two consecutive
reviews whose open P0/P1 findings are at least half `ASSURANCE_DEFECT`, three completed reviews
without acceptance, an invalid/missing guard or dependency declaration, or an active legacy pack
whose review schema has not been explicitly retained. Reasons are `EXTERNAL`, `BUDGET`,
`ASSURANCE`, `REPLAN_STORM`, `USER_CHECKPOINT`, `PLAN_CONFLICT`, `CONFIGURATION_GAP`, and
`SCHEMA_MIGRATION`.

Every pause/resume is an append-only Controller event. Every resume requires a non-secret user
authorization token/reference, evidence resolving the selected reasons, and an explicit resume
role. Reasons may be resolved in separate Control events, but the eventual resume role must be
legal for the complete pause-reason set. Unresolved reasons remain paused. A new pause revokes any
older resume grant. An authorized historical/external grant lasts only through the next Reviewer;
`BUDGET` never bypasses the Implementer candidate guard, while `CONFIGURATION_GAP` and
`SCHEMA_MIGRATION` can grant Planner entry only and must be corrected before implementation
continues. Never relabel exhaustion as acceptance, discard WIP, or start Reviewer without an
immutable candidate.

The user may instead authorize `abandon` as a terminal non-success that retains the
branch/worktree/WIP, or `split` with a child task ID and transferred paths. Split leaves the parent
paused and gives the child exclusive ownership; it does not merge automatically.

Record Controller events with the helper. Repeat `--reason` when a pause has more than one cause:

```bash
python3 <skill-root>/scripts/ralph_loop.py control \
  --workspace-root <worktree> \
  --task-dir <task-dir> \
  --task-id <task-id> \
  --action pause \
  --reason BUDGET \
  --reason ASSURANCE

python3 <skill-root>/scripts/ralph_loop.py control \
  --workspace-root <worktree> \
  --task-dir <task-dir> \
  --task-id <task-id> \
  --action resume \
  --reason BUDGET \
  --authorization-token <non-secret-user-message-or-change-request-id> \
  --reference <immutable-resolution-evidence> \
  --resume-role planner
```

For Implementer feedback, use `--action plan-query --pq-id PQ-NNN --summary ...` plus one repeated
`--reference <item-or-deliverable-or-ac-id>` per affected ID. Record the fresh Planner response
with `--action plan-response --pq-id PQ-NNN --decision <decision> --summary ...`. The decision is
one of `CLARIFIED`, `REPLAN_REQUIRED`, `CONTRACT_CHANGE_REQUIRED`, or `EXTERNAL_BLOCKER`. A
subsequent resume or contract-changing Planner checkpoint requires the user authorization token;
diagnosing that a contract change is required does not.

For legacy packs, never rewrite old review blocks to add finding types. Use `--legacy-findings`
only to inspect/control an existing pack, require typed findings in new reviews, and stop using
legacy mode once the latest required schema/history has migrated.

## Accept, archive, and prepare manual merge

Accept only when every `AC-*` is `PASS`, required deliverables exist at declared paths, checks were
independently reproduced, required items are complete, no blocking finding remains, and the latest
review records the current snapshot and immutable candidate commit.

Any post-review change to `proposal.md`, `design.md`, `plan.md`, or a deliverable invalidates
acceptance and requires another Implementer candidate plus fresh Reviewer. Never amend or rewrite a
reviewed candidate commit.

After exact archive-ready bytes are accepted:

1. Preserve deliverables at their owner paths and keep every participant worktree clean at its
   accepted candidate commit.
2. Move the complete four-pack byte-for-byte to the archive and update the branch-local index in
   the same closure change. With the bundled marker-managed index, run:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py archive \
     --workspace-root <worktree> \
     --task-dir <active-task-dir> \
     --archive-root <tasks-archive-root> \
     --index <task-index>
   ```

   The gate requires the active pack and index in the Reviewer commit and rejects ignored archive
   destinations. A local ignored file is not an integration artifact.
3. Re-run repository, link, whitespace, unique-ID/location, and archived lifecycle checks.
4. Create the closure checkpoint:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py checkpoint \
     --workspace-root <worktree> \
     --task-dir <former-active-task-dir> \
     --archive-task-dir <archived-task-dir> \
     --index <task-index> \
     --task-id <task-id> \
     --role closure \
     --iteration N
   ```

   Closure must capture all four active deletions, all four archived additions, and the index
   update.
5. Produce the read-only manual-merge handoff:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py handoff \
     --workspace-root <worktree> \
     --task-dir <archived-task-dir> \
     --index <task-index>
   ```

The handoff reports the control Base/branch/candidate/closure, accepted content snapshot,
candidate-vector digest, and every participant's repository ID, Base, branch, candidate, changed
paths, and planned manual-merge order. It never merges, pushes, rebases, cherry-picks, deletes a
worktree, or creates an integration queue. Leave every branch and worktree for the user to merge
and clean up manually. Cross-repository commits are not an atomic transaction, and merging only a
subset does not integrate the accepted vector. Branch-local index conflicts are resolved by the
user. If conflict resolution changes an accepted snapshot member, run a new Implementer ->
Reviewer pass on the merged bytes.

Closure is immutable and terminal. Do not reopen or move an archived four-pack after Closure. Any
post-Closure change starts a new superseding task that references the archived parent.

Use `<skill-root>/scripts/ralph_loop.py archive` only for the bundled marker-managed index. For a
custom index/archive protocol, perform repository-native closure before the same closure checkpoint
and handoff.

## Preserve role and evidence boundaries

- Only Reviewer can emit `ACCEPTED`; only Controller can create Git checkpoints.
- Bind acceptance to proposal, design, plan, declared deliverables, the control candidate,
  participant commit vector, vector digest, and content snapshot. Exclude `verify.md` from the
  content snapshot so Reviewer can append evidence.
- Keep Reviewer history append-only and failed candidates reachable; never amend reviewed commits.
- Make each rejection actionable with stable `F-*` IDs and `AC-*` mappings.
- Do not archive `BLOCKED`, `CHANGES_REQUIRED`, or `NEEDS_REPLAN`.
- Do not treat plan status, Implementer claims, or a commit alone as acceptance evidence.
- Preserve unrelated user changes and obey repository instructions throughout.
