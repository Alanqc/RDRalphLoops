---
name: run-rd-ralph-loop
description: Orchestrate evidence-gated research and development work as a three-role Ralph loop using proposal.md, design.md, plan.md, and verify.md. Use when Codex must run one or more isolated R&D loops, create dedicated Git worktrees and branches, checkpoint Planner/Implementer/Reviewer changes, obtain independent acceptance, archive the four-document task pack, or prepare a user-controlled manual-merge handoff; also trigger for Ralph loop, 研发闭环, 四件套, iterative implementation/review, and acceptance-gated archival.
---

# Run an R&D Ralph Loop

Use one interactive Controller and three isolated roles: Planner, Implementer, and Reviewer. Make
the Planner mandatory at initialization and conditional later; run the Implementer and Reviewer in
every iteration. Treat Reviewer acceptance as the only successful exit.

The Controller owns orchestration, Git state, checkpoints, status updates, and user interaction.
Role agents edit only their authorized files and never commit, merge, push, rebase, cherry-pick,
stash, switch branches, reset, or remove worktrees.

Read [references/protocol.md](references/protocol.md) before starting. Read
[references/role-prompts.md](references/role-prompts.md) immediately before dispatching roles.
Resolve `<skill-root>` as the directory containing this `SKILL.md`; run bundled paths from there.

## Keep the Controller interactive

- Dispatch every role as a background subagent with a fresh role context.
- Keep the main task open while roles run. Use bounded waits, report meaningful progress at least
  every 60 seconds, and continue accepting user messages.
- Treat a message intended for the current run as steering. Forward ordinary clarifications to the
  active role when safe. If it changes the goal, scope, an AC, a design invariant, path ownership,
  or the candidate under review, interrupt or invalidate the current candidate and route through
  Planner -> Implementer -> Reviewer again.
- Treat a queued follow-up as next-run work unless it changes the current contract.
- Preserve role dependencies: do not start Implementer before Planner returns, and do not start
  Reviewer before the Implementer checkpoint and snapshot exist. Controller interactivity does not
  authorize concurrent writers in one worktree.
- Do not send the final response while a required role is still running. Finalize only after
  acceptance, archival, closure checkpoint, and handoff.

## Isolate every Git loop

For a Git repository, use one task ID, one linked worktree, and one branch per loop. Multiple loops
may run on the same machine and share the Git object database, but they must not share a checkout,
branch, Git index, or write-owned external resource.

Create each worktree before dispatching its Planner:

```bash
python3 <skill-root>/scripts/ralph_loop.py worktree-create \
  --repo-root <integration-checkout> \
  --worktree-path <dedicated-worktree-path> \
  --task-id <unique-task-id> \
  --base <full-base-commit-or-ref>
```

This creates `ralph/<task-id>` without `--force` and never removes it. If the user or Codex app
already created a dedicated worktree, validate it instead:

```bash
python3 <skill-root>/scripts/ralph_loop.py git-context \
  --workspace-root <worktree> \
  --task-id <unique-task-id> \
  --require-git \
  --require-clean
```

Pass the same absolute worktree root, branch, base commit, task directory, and run ID to every role.
Choose globally unique task IDs. Declare exclusive ownership for deliverable paths, generated
directories, databases, ports, caches, devices, and external publication targets. If active loops
overlap on any mutable resource, mark the dependency and serialize those Implementer passes or
pause as `BLOCKED`.

For a non-Git workspace, skip worktree and checkpoint commands and retain the content-snapshot
workflow.

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

4. Keep deliverables outside the task-pack directory and use workspace-relative paths. Archival
   moves the four-pack; it must not move or delete deliverables.
5. Register the active task in the branch-local index. The helper updates only its marker-managed
   index; update a project-specific index according to that repository's contract.

The helper's lifecycle schema is normative only for the bundled templates. With a project-specific
four-pack, keep repository-native gates, pass nonstandard deliverables through repeated
`--artifact <path>` arguments, and enforce the same role, Git, and evidence invariants manually.

## Initialize with the Planner

Dispatch a fresh Planner. Require it to complete all four files before implementation:

- `proposal.md`: freeze the goal, scope, non-goals, constraints, and stable `AC-*` criteria.
- `design.md`: define the approach, interfaces, risks, decisions, exact deliverable paths, owners,
  formats, retention, and concurrent resource ownership.
- `plan.md`: map every `DEL-*` and `ITEM-*` to `AC-*`, include dependencies and executable
  verification methods, and record worktree, branch, base commit, and manual merge mode.
- `verify.md`: create only the empty review schema. Do not pre-fill evidence or a verdict.

The Planner owns `proposal.md`. A material goal, scope, or AC change requires explicit user
authorization and a recorded re-baseline; never weaken criteria to fit the implementation.

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

The checkpoint refuses a dirty staging area, out-of-role paths, detached or wrong branches, and
primary-worktree use unless an explicitly serialized single-loop run passes
`--allow-primary-worktree`. It pins Base to the parent of Planner iteration 0 and authenticates
every later commit as the same task's linear Ralph checkpoint chain.

## Run one iteration

For iteration `N`:

1. Run Planner first only for initialization or a re-entry trigger. After re-entry, checkpoint with
   `--role planner-replan --iteration N`. Add `--allow-contract-change` only after the user
   explicitly authorizes a proposal/AC re-baseline.
2. Run Implementer. Require it to update deliverables and `plan.md`, run declared checks, and record
   changed paths, commands, results, and unresolved issues. It may amend `design.md` only when
   necessary and must log why. It must not edit `proposal.md` or `verify.md`.
3. After the Implementer returns, inspect all worktree changes and create the immutable candidate:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py checkpoint \
     --workspace-root <worktree> \
     --task-dir <task-dir> \
     --task-id <task-id> \
     --role implementer \
     --iteration N
   ```

   The Controller stages only the validated explicit paths. Never use repository-wide
   `git add -A` or `git commit -a`. The checkpoint returns the full candidate commit and content
   snapshot and records both in commit trailers. If an authorized Implementer design amendment
   introduces a new deliverable path that was not present in the preceding checkpoint, inspect it
   and pass one `--allow-new-deliverable <path>` per new path; otherwise the checkpoint refuses it.
   Prefer Planner re-entry when the ownership change is material. A declared or explicit
   deliverable may not overlap the four-pack directory. Snapshot members with non-default Git
   index flags are refused, and candidate-tree blobs must match the filesystem bytes exactly.
4. Reproduce the candidate snapshot from the clean commit:

   ```bash
   python3 <skill-root>/scripts/ralph_loop.py snapshot \
     --workspace-root <worktree> \
     --task-dir <task-dir>
   ```

5. Run a fresh independent Reviewer. Give it the task pack, declared deliverables, implementation
   evidence, exact candidate commit, branch, and snapshot; never give it a desired verdict.
6. The Reviewer may inspect files and run checks but may modify only `verify.md`. It appends exactly
   one review record, maps every finding to `AC-*`, records independently observed evidence,
   `Candidate commit`, `Candidate branch`, and snapshot, then emits exactly one verdict:
   `ACCEPTED`, `CHANGES_REQUIRED`, `NEEDS_REPLAN`, or `BLOCKED`.
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

   The Reviewer checkpoint accepts only `verify.md` changes, preserves every prior review block,
   and verifies that the recorded candidate equals the pre-review HEAD and its Implementer
   trailers.
8. Route the verdict:

   - `ACCEPTED`: run the accepted gate, close, archive, and hand off.
   - `CHANGES_REQUIRED`: carry stable finding IDs into the next mandatory Implementer pass.
   - `NEEDS_REPLAN`: run Planner before the next Implementer.
   - `BLOCKED`: record the external decision or state change needed and pause.

Planner re-entry is also mandatory when one finding survives two reviews, two consecutive
iterations have materially identical changes or failures, an Implementer changes a design
invariant or public interface, ACs prove ambiguous or contradictory, or three iterations complete.
At eight iterations, pause for user direction; never relabel exhaustion as acceptance.

## Accept, archive, and prepare manual merge

Accept only when every `AC-*` is `PASS`, required deliverables exist at declared paths, checks were
independently reproduced, required items are complete, no blocking finding remains, and the latest
review records the current snapshot and immutable candidate commit.

Any post-review change to `proposal.md`, `design.md`, `plan.md`, or a deliverable invalidates
acceptance and requires another Implementer candidate plus fresh Reviewer. Never amend or rewrite a
reviewed candidate commit.

After exact archive-ready bytes are accepted:

1. Preserve deliverables at their owner paths.
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

The handoff reports base, branch, candidate, closure commit, accepted snapshot, commits, paths,
deliverables, and checks. It never merges, pushes, rebases, cherry-picks, deletes a worktree, or
creates an integration queue. Leave the branch and worktree for the user to merge and clean up
manually. Branch-local index conflicts are resolved by the user. If conflict resolution changes an
accepted snapshot member, run a new Implementer -> Reviewer pass on the merged bytes.

Use `<skill-root>/scripts/ralph_loop.py archive` only for the bundled marker-managed index. For a
custom index/archive protocol, perform repository-native closure before the same closure checkpoint
and handoff.

## Preserve role and evidence boundaries

- Only Reviewer can emit `ACCEPTED`; only Controller can create Git checkpoints.
- Bind acceptance to proposal, design, plan, declared deliverables, candidate commit, and snapshot.
  Exclude `verify.md` from the content snapshot so Reviewer can append evidence.
- Keep Reviewer history append-only and failed candidates reachable; never amend reviewed commits.
- Make each rejection actionable with stable `F-*` IDs and `AC-*` mappings.
- Do not archive `BLOCKED`, `CHANGES_REQUIRED`, or `NEEDS_REPLAN`.
- Do not treat plan status, Implementer claims, or a commit alone as acceptance evidence.
- Preserve unrelated user changes and obey repository instructions throughout.
