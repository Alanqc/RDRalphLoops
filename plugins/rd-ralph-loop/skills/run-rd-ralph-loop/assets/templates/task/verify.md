# {{TASK_TITLE}} Verify

| Field | Value |
|---|---|
| Run ID | `{{RUN_ID}}` |
| Evidence owner | Reviewer |
| Final decision | PENDING |
| Accepted snapshot SHA-256 | PENDING |
| Accepted candidate commit | PENDING |
| Accepted candidate vector SHA-256 | PENDING |

For the Protocol-v3 CONTROL-only compatibility profile, use `N/A` for candidate-vector fields and
one `N/A` Candidate Repositories row.

## Review Ledger

No review has been recorded. The Reviewer appends one section per iteration and never rewrites
earlier records.

Every finding has exactly one type:

- `SUBJECT_DEFECT`: the researched or delivered subject is wrong or incomplete.
- `ASSURANCE_DEFECT`: a harness, test, validator, simulator, or evidence generator is wrong.
- `CONTRACT_GAP`: the plan or design cannot express a correct implementable path.
- `EXTERNAL_BLOCKER`: a required asset, device, permission, service, or real observation is absent.

An `ASSURANCE_DEFECT` must include concrete reachability evidence, such as a reproducible false
pass or unsafe side effect. Its required action is limited to removing or shrinking assurance,
Reviewer recomputation from immutable evidence, or a minimum local repair within existing
interfaces. Adding a schema, provider, phase, interface, simulator, or validator layer requires a
Controller pause and explicit user authorization.

Use exactly one action class: `SUBJECT_FIX`, `SHRINK_ASSURANCE`, `DIRECT_RECOMPUTE`,
`MINIMAL_LOCAL_FIX`, `REPLAN`, `UNBLOCK_EXTERNAL`, `CLOSE`, or `ESCALATE`. An open
`ASSURANCE_DEFECT` may use only `SHRINK_ASSURANCE`, `DIRECT_RECOMPUTE`, `MINIMAL_LOCAL_FIX`, or
`ESCALATE`.

<!--
## ITER-001 Review

| Field | Value |
|---|---|
| Reviewer | reviewer identity |
| Date | YYYY-MM-DD |
| Environment | repo, cwd, branch/commit, dependencies |
| Candidate commit | full candidate commit SHA or N/A for non-Git |
| Candidate branch | candidate branch or N/A for non-Git |
| Candidate vector SHA-256 | full CONTROL-plus-participant vector digest or N/A |
| Snapshot SHA-256 | sha256 from scripts/ralph_loop.py snapshot |
| Verdict | ACCEPTED / CHANGES_REQUIRED / NEEDS_REPLAN / BLOCKED |
| Residual risk | none, or a concrete risk |
| Direct subject evidence delta | new immutable or live subject evidence, or NONE |
| External blocker delta | newly resolved/introduced dependency IDs, or NONE |
| Assurance surface delta | removed/added harness paths and physical lines, or NONE |
| Recommended next lifecycle | ARCHIVE / IMPLEMENT / REPLAN / PAUSE_EXTERNAL |

Normalize machine-local roots in Environment and command evidence as `<CONTROL_WORKTREE>` and
`<REPO-NNN_WORKTREE>`. Preserve argv structure, exit codes, and relevant output, but do not persist
absolute participant worktree paths in `verify.md`.

### Candidate Repositories

`CONTROL` is the Candidate commit above. List every registered participant even when it was
unchanged in this iteration. For the CONTROL-only compatibility profile, write one row containing
`N/A` in all six columns.

| Repository | Logical identity | Branch | Base commit | Candidate commit | Changed this iteration |
|---|---|---|---|---|---|
| REPO-001 / N/A | origin URL or stable label / N/A | ralph/task-id / N/A | full base SHA / N/A | full candidate SHA / N/A | Yes / No / N/A |

### AC Decision Matrix

| AC | Result | Evidence |
|---|---|---|
| AC-001 | PASS / FAIL / BLOCKED | independently observed evidence |

### Findings

| Finding | ACs | Type | Severity | Status | Evidence | Action class | Required action |
|---|---|---|---|---|---|---|---|
| F-001 | AC-001 | SUBJECT_DEFECT / ASSURANCE_DEFECT / CONTRACT_GAP / EXTERNAL_BLOCKER | P0 / P1 / P2 / P3 | Open / Closed | path, command, output, and reachability when assurance-related | SUBJECT_FIX / SHRINK_ASSURANCE / DIRECT_RECOMPUTE / MINIMAL_LOCAL_FIX / REPLAN / UNBLOCK_EXTERNAL / CLOSE / ESCALATE | bounded actionable change |

### Commands

Use the normalized worktree tokens above in recorded commands.

| Command / review step | Expected exit | Actual exit | Result | Relevant output |
|---|---|---|---|---|
| exact command or manual review step | 0 / N/A | 0 / N/A | PASS / FAIL | concise output |

### Conclusion

One evidence-backed conclusion and next action.
-->
