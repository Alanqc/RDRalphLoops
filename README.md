# R&D Ralph Loops for Codex

An evidence-gated Codex plugin for running research and development work through a
three-role Ralph loop:

```text
Planner? -> Implementer -> Reviewer
               |             |
               |             +-- ACCEPTED --------> archive + manual-merge handoff
               |             +-- CHANGES_REQUIRED -> guard -> Implementer or PAUSED
               |             +-- NEEDS_REPLAN ----> guard -> Planner or PAUSED
               |             `-- BLOCKED ---------> PAUSED[EXTERNAL]
               `-- PLAN_FEEDBACK_REQUIRED -> fresh Planner consultation
```

The Planner is mandatory during initialization and conditional in later iterations. The
Implementer is mandatory in every implementation iteration, and an independent Reviewer is
mandatory for every immutable candidate. Plan consultation happens before candidate creation. A
loop finishes only after the Reviewer accepts the exact candidate.

## What it provides

- A bundled four-document task pack: `proposal.md`, `design.md`, `plan.md`, and `verify.md`.
- Dedicated Git worktree and `ralph/<task-id>` branch isolation for each loop.
- Controller-owned, path-scoped checkpoint commits after each role finishes.
- Typed Reviewer findings that separate subject defects, assurance defects, contract gaps, and
  external blockers.
- Simple line-count/`git diff --numstat` budgets for explicitly guarded deliverable paths; the
  guard does not build semantic validators.
- Append-only Control events for pause, resume, plan feedback, abandon, and child-task splits while
  preserving unstaged WIP.
- Immutable candidate commits and content snapshots for independent review.
- Evidence-gated acceptance, four-pack archival, retained deliverables, and index updates.
- A manual-merge handoff. The plugin does not merge, push, rebase, cherry-pick, or delete
  worktrees.
- Multiple concurrent loops in the same repository when each loop has a unique worktree, branch,
  task ID, and non-overlapping mutable resources.

The plugin bundle is self-contained: its templates, protocol, role prompts, and helper script are
all stored under [`plugins/rd-ralph-loop`](plugins/rd-ralph-loop).

## Requirements

- Codex with plugin marketplace support.
- Python 3.10 or newer.
- Git with linked-worktree support.

Version `0.2.0` is validated on macOS and uses a POSIX-oriented test suite. Windows support has not
yet been verified. Configure a Git author identity before starting a Git-mode loop.

## Install

Add this Git repository as a Codex marketplace:

```bash
codex plugin marketplace add Alanqc/RDRalphLoops --ref main
```

Then install the plugin:

```bash
codex plugin add rd-ralph-loop@rd-ralph-loops
```

Start a new Codex task after installation so the skill is loaded.

To refresh an existing installation after a new release:

```bash
codex plugin marketplace upgrade rd-ralph-loops
codex plugin add rd-ralph-loop@rd-ralph-loops
```

## Start a loop

In a new Codex task, ask:

```text
Run this R&D task with the R&D Ralph Loop plugin. Use a dedicated worktree,
iterate until independent acceptance, archive the four-document pack, and leave
the resulting branch for me to merge manually:

<your task>
```

The main Controller remains available for conversation while a role subagent runs, but role
dependencies still block lifecycle advancement: Implementer waits for Planner when planning is
required, and Reviewer waits for the Implementer candidate checkpoint. If Implementer finds the
plan infeasible, it can request a fresh read-only Planner consultation before creating a candidate.

## Current limitations

- An active run records its absolute worktree path and should not be moved to another checkout.
- Automated checkpoint, archive, and handoff validation targets the bundled four-pack schema.
  Repository-specific schemas may require manual lifecycle enforcement.
- Protocol-v1 review history remains immutable. Legacy runs must append typed findings in new
  reviews instead of rewriting old blocks.
- Repository Git hooks, signing rules, attributes, clean filters, and line-ending configuration
  apply normally and can affect checkpoint creation or byte-for-byte snapshot checks.

## Role and commit model

| Actor | Required | May edit | Commits |
|---|---|---|---|
| Planner | Initialization; later on replan or plan-query triggers | Four-pack initially; controlled plan/design changes later; consultation is read-only over WIP | No |
| Implementer | Every implementation iteration | Declared deliverables, `plan.md`, and necessary `design.md` amendments | No |
| Reviewer | Every immutable candidate | Append-only typed `verify.md` evidence and verdict | No |
| Controller | Entire run | Orchestration and lifecycle state | Creates scoped role and empty Control checkpoints |
| User | Manual integration | Conflict resolution and final integration | Merges manually |

See the full [skill instructions](plugins/rd-ralph-loop/skills/run-rd-ralph-loop/SKILL.md),
[protocol](plugins/rd-ralph-loop/skills/run-rd-ralph-loop/references/protocol.md), and
[role prompts](plugins/rd-ralph-loop/skills/run-rd-ralph-loop/references/role-prompts.md).

## Test

```bash
python3 plugins/rd-ralph-loop/tests/test_git_flow.py -v
```

The test suite exercises checkpoint authority, two-worktree isolation, typed verdict routing,
explicit pause/resume transitions, dirty-WIP preservation, line-budget boundaries, Planner
consultation, legacy compatibility, archival rollback, retained deliverables, and manual-merge
handoff behavior.

## Repository layout

```text
.agents/plugins/marketplace.json       Codex marketplace catalog
plugins/rd-ralph-loop/
  .codex-plugin/plugin.json            Plugin manifest
  skills/run-rd-ralph-loop/            Skill, protocol, prompts, templates, helper
  tests/test_git_flow.py                Regression and end-to-end tests
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

This is an independent community plugin and is not an official OpenAI project.
