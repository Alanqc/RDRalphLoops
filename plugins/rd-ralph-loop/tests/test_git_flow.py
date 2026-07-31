from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RALPH = (
    PLUGIN_ROOT
    / "skills"
    / "run-rd-ralph-loop"
    / "scripts"
    / "ralph_loop.py"
)
ARCHIVE_CONFIRMATION = "post-acceptance-user-confirmation"
ARCHIVE_CONFIRMATION_SHA256 = hashlib.sha256(
    ARCHIVE_CONFIRMATION.encode("utf-8")
).hexdigest()


def run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"expected {expected}, got {result.returncode}\n"
            f"command: {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def git(cwd: Path, *arguments: str) -> str:
    return run(["git", "-C", str(cwd), *arguments]).stdout.strip()


def git_exclude_path(cwd: Path) -> Path:
    path = Path(git(cwd, "rev-parse", "--git-path", "info/exclude"))
    return path if path.is_absolute() else cwd / path


def cli(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(RALPH), *arguments], expected=expected)


def task_cli(
    command: str,
    worktree: Path,
    task_dir: Path,
    task_id: str,
    *arguments: str,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    return cli(
        command,
        "--workspace-root",
        str(worktree),
        "--task-dir",
        str(task_dir),
        "--task-id",
        task_id,
        *arguments,
        expected=expected,
    )


def proposal(task_id: str, run_id: str) -> str:
    return f"""# Example Proposal

| Field | Value |
|---|---|
| Task ID | `{task_id}` |
| Run ID | `{run_id}` |
| Contract owner | Planner |
| Contract status | Active |
| Created | 2026-07-28 |

## What & Why

Create a retained output.

## Scope

In scope:

- Create output.txt.

Out of scope:

- Network publication.

## Global Spec References

- N/A: isolated fixture.

## References

- README.md

## Acceptance Criteria

- `AC-001`: THE workspace SHALL contain output.txt with the exact text `done`.

## Contract Change Log

| Iteration | Change | Affected ACs | User authorization |
|---|---|---|---|
| INIT | Initial contract | All | Initial request |
"""


def design(task_id: str) -> str:
    return f"""# Example Design

## Context

Isolated test worktree.

## Spec Alignment

- N/A.

## Goals

- Create one file.

## Non-goals

- No integration.

## Output Design

| Deliverable | Path | Format / interface | Owner | ACs | Retention |
|---|---|---|---|---|---|
| `DEL-001` | `output.txt` | UTF-8 text | {task_id} | `AC-001` | Retain |

## Concurrent Resource Ownership

| Resource | Location / identity | Access | Owner | Collision avoidance |
|---|---|---|---|---|
| Output | `output.txt` | Exclusive write | {task_id} | Dedicated worktree |

## Constraints

- No external resources.

## Approach

1. Write the exact text.

## Key Decisions

- Use a plain file.

## Risks

- None.

## Design Amendment Log

| Iteration | Author | Reason | Changed invariant / interface | Affected ACs |
|---|---|---|---|---|
| INIT | Planner | Initial design | Initial design | All |
"""


def plan(
    run_id: str,
    worktree: Path,
    branch: str,
    base: str,
    *,
    implemented: bool,
) -> str:
    status = "Done" if implemented else "Pending"
    check = "x" if implemented else " "
    state = "In Review" if implemented else "Planned"
    iteration = 1 if implemented else 0
    rows = (
        "| 0 | Planner | Four-pack | Planning only | N/A | Implementer |\n"
        + (
            "| 1 | Implementer | `output.txt`, `plan.md` | "
            "`test \"$(cat output.txt)\" = done` exit 0 | N/A | Independent review |\n"
            if implemented
            else ""
        )
    )
    return f"""# Example Plan

## Loop Control

| Field | Value |
|---|---|
| Run ID | `{run_id}` |
| Worktree root | `{worktree}` |
| Branch | `{branch}` |
| Base commit | `{base}` |
| Merge mode | Manual; no automatic merge or push |
| Merge owner | User |
| State | {state} |
| Current iteration | {iteration} |
| Next actor | {"Reviewer" if implemented else "Implementer"} |
| Planner required next | No |
| Planner re-entry reason | N/A |
| Last Reviewer verdict | PENDING |
| Soft / hard threshold | 3 / 8 |
| Last updated | 2026-07-28 |

## Next Step

- {"Independent review." if implemented else "Create output.txt."}

## Deliverables

| ID | ACs | Path | Required | Status | Evidence target |
|---|---|---|---|---|---|
| `DEL-001` | `AC-001` | `output.txt` | Yes | {status} | Exact content check |

## Delivery Items

| Done | ID | Deliverable / ACs | Depends | Owner | Target | Action |
|---|---|---|---|---|---|---|
| [{check}] | `ITEM-001` | `DEL-001`; `AC-001` | None | Implementer | `output.txt` | Write exact content |

## AC Verification Plan

| AC | Method | Command / review step | Expected evidence |
|---|---|---|---|
| `AC-001` | Command | `test "$(cat output.txt)" = done` | Exit 0 |

## Iteration Log

| Iteration | Role | Changed paths | Commands and results | Finding disposition | Next action |
|---|---|---|---|---|---|
{rows}"""


def external_evidence_plan(
    run_id: str,
    worktree: Path,
    branch: str,
    base: str,
    *,
    implemented: bool,
) -> str:
    section = """## External Evidence Exclusions

| ID | Repository | Excluded path | Manifest path | Reason |
|---|---|---|---|---|
| `XEV-001` | `CONTROL` | `bundle/external/raw.pt` | `evidence/manifest.json` | Raw tensor evidence is retained externally and hash-bound by the manifest |

"""
    return (
        plan(
            run_id,
            worktree,
            branch,
            base,
            implemented=implemented,
        )
        .replace("output.txt", "bundle")
        .replace("## Delivery Items\n", section + "## Delivery Items\n", 1)
    )


def empty_verify(run_id: str) -> str:
    return f"""# Example Verify

| Field | Value |
|---|---|
| Run ID | `{run_id}` |
| Evidence owner | Reviewer |
| Final decision | PENDING |
| Accepted snapshot SHA-256 | PENDING |
| Accepted candidate commit | PENDING |

## Review Ledger

No review has been recorded.
"""


def accepted_verify(
    run_id: str,
    candidate: str,
    branch: str,
    snapshot: str,
) -> str:
    return f"""# Example Verify

| Field | Value |
|---|---|
| Run ID | `{run_id}` |
| Evidence owner | Reviewer |
| Final decision | ACCEPTED |
| Accepted snapshot SHA-256 | `{snapshot}` |
| Accepted candidate commit | `{candidate}` |

## Review Ledger

## ITER-001 Review

| Field | Value |
|---|---|
| Reviewer | Independent fixture reviewer |
| Date | 2026-07-28 |
| Environment | temporary repo, isolated worktree, no dependencies |
| Candidate commit | `{candidate}` |
| Candidate branch | `{branch}` |
| Snapshot SHA-256 | `{snapshot}` |
| Verdict | ACCEPTED |
| Residual risk | None |

### AC Decision Matrix

| AC | Result | Evidence |
|---|---|---|
| AC-001 | PASS | `output.txt` contains exact text and command exited 0 |

### Findings

| Finding | ACs | Severity | Status | Evidence | Required action |
|---|---|---|---|---|---|

### Commands

| Command / review step | Expected exit | Actual exit | Result | Relevant output |
|---|---|---|---|---|
| `test "$(cat output.txt)" = done` | 0 | 0 | PASS | exact content matched |

### Conclusion

Every AC passed against the immutable candidate.
"""


def proposal_v2(task_id: str, run_id: str) -> str:
    guard_sections = """## External Dependency Registry

| Dependency | Blocking ACs | Required immutable evidence | Owner | Initial status | Unblock proof |
|---|---|---|---|---|---|
| N/A | N/A | N/A | N/A | READY | N/A |

## Guard Budgets

| Budget | Profile | Guarded deliverable paths | Warning | Iteration pause | Cumulative pause | Per-path pause | Exclusions | User authorization |
|---|---|---|---:|---:|---:|---:|---|---|
| `BUD-001` | CODE | `output.txt` | 3000 | 5000 | 12000 | 6000 | N/A | Initial task request |

"""
    return (
        proposal(task_id, run_id)
        .replace(
            "| Task ID |",
            "| Protocol version | 2 |\n| Task ID |",
            1,
        )
        .replace(
            "## Acceptance Criteria\n",
            guard_sections + "## Acceptance Criteria\n",
            1,
        )
    )


def design_v2(task_id: str) -> str:
    return (
        design(task_id)
        .replace(
            "| Deliverable | Path | Format / interface | Owner | ACs | Retention |",
            "| Deliverable | Class | Path | Format / interface | Owner | ACs | "
            "Guard budget | Retention |",
            1,
        )
        .replace(
            "|---|---|---|---|---|---|",
            "|---|---|---|---|---|---|---|---|",
            1,
        )
        .replace(
            f"| `DEL-001` | `output.txt` | UTF-8 text | {task_id} | `AC-001` | Retain |",
            f"| `DEL-001` | SUBJECT | `output.txt` | UTF-8 text | {task_id} | "
            "`AC-001` | `BUD-001` | Retain |",
            1,
        )
    )


def plan_v2(
    run_id: str,
    worktree: Path,
    branch: str,
    base: str,
    *,
    implemented: bool,
) -> str:
    return (
        plan(
            run_id,
            worktree,
            branch,
            base,
            implemented=implemented,
        )
        .replace(
            "| Run ID |",
            "| Protocol version | 2 |\n| Run ID |",
            1,
        )
        .replace(
            "| ID | ACs | Path | Required | Status | Evidence target |",
            "| ID | Class | ACs | Path | Required | Guard budget | Status | "
            "Evidence target |",
            1,
        )
        .replace(
            "|---|---|---|---|---|---|",
            "|---|---|---|---|---|---|---|---|",
            1,
        )
        .replace(
            "| `DEL-001` | `AC-001` | `output.txt` | Yes |",
            "| `DEL-001` | SUBJECT | `AC-001` | `output.txt` | Yes | "
            "`BUD-001` |",
            1,
        )
    )


def proposal_v3(task_id: str, run_id: str) -> str:
    return (
        proposal_v2(task_id, run_id)
        .replace("| Protocol version | 2 |", "| Protocol version | 3 |", 1)
        .replace(
            "| Budget | Profile |",
            "| Budget | Repository | Profile |",
            1,
        )
        .replace(
            "|---|---|---|---:|---:|---:|---:|---|---|",
            "|---|---|---|---|---:|---:|---:|---:|---|---|",
            1,
        )
        .replace(
            "| `BUD-001` | CODE | `output.txt` | 3000 | 5000 | 12000 | "
            "6000 | N/A | Initial task request |",
            "| `BUD-001` | `REPO-001` | CODE | `artifact/output.txt` | 3000 | "
            "5000 | 12000 | 6000 | N/A | Initial task request |\n"
            "| `BUD-002` | `REPO-002` | CODE | `artifact/output.txt` | 3000 | "
            "5000 | 12000 | 6000 | N/A | Initial task request |",
            1,
        )
        .replace(
            "THE workspace SHALL contain output.txt with the exact text `done`",
            "THE task SHALL retain both repository-qualified outputs",
            1,
        )
    )


def design_v3(
    task_id: str,
    repo_1_base: str,
    repo_2_base: str,
) -> str:
    branch = f"ralph/{task_id}"
    registry = f"""## Repository Participants

| Repository | Logical identity | Branch | Base commit | Write scopes | ACs | Merge order | User authorization |
|---|---|---|---|---|---|---:|---|
| `REPO-001` | participant-one | `{branch}` | `{repo_1_base}` | `artifact` | `AC-001` | 10 | Initial task request |
| `REPO-002` | participant-two | `{branch}` | `{repo_2_base}` | `artifact` | `AC-001` | 20 | Initial task request |

"""
    return (
        design_v2(task_id)
        .replace("## Output Design\n", registry + "## Output Design\n", 1)
        .replace(
            "| Deliverable | Class | Path |",
            "| Deliverable | Class | Repository | Path |",
            1,
        )
        .replace(
            "|---|---|---|---|---|---|---|---|",
            "|---|---|---|---|---|---|---|---|---|",
            1,
        )
        .replace(
            f"| `DEL-001` | SUBJECT | `output.txt` | UTF-8 text | {task_id} | "
            "`AC-001` | `BUD-001` | Retain |",
            f"| `DEL-001` | SUBJECT | `REPO-001` | `artifact/output.txt` | "
            f"UTF-8 text | {task_id} | `AC-001` | `BUD-001` | Retain |\n"
            f"| `DEL-002` | SUBJECT | `REPO-002` | `artifact/output.txt` | "
            f"UTF-8 text | {task_id} | `AC-001` | `BUD-002` | Retain |",
            1,
        )
        .replace(
            "| Output | `output.txt` |",
            "| Output | `REPO-001`: `artifact/output.txt`; "
            "`REPO-002`: `artifact/output.txt` |",
            1,
        )
    )


def plan_v3(
    run_id: str,
    control_worktree: Path,
    branch: str,
    control_base: str,
) -> str:
    return (
        plan_v2(
            run_id,
            control_worktree,
            branch,
            control_base,
            implemented=False,
        )
        .replace("| Protocol version | 2 |", "| Protocol version | 3 |", 1)
        .replace(
            "| ID | Class | ACs | Path |",
            "| ID | Class | ACs | Repository | Path |",
            1,
        )
        .replace(
            "|---|---|---|---|---|---|---|---|",
            "|---|---|---|---|---|---|---|---|---|",
            1,
        )
        .replace(
            "| `DEL-001` | SUBJECT | `AC-001` | `output.txt` | Yes | "
            "`BUD-001` | Pending | Exact content check |",
            "| `DEL-001` | SUBJECT | `AC-001` | `REPO-001` | "
            "`artifact/output.txt` | Yes | `BUD-001` | Pending | Content hash |\n"
            "| `DEL-002` | SUBJECT | `AC-001` | `REPO-002` | "
            "`artifact/output.txt` | Yes | `BUD-002` | Pending | Content hash |",
            1,
        )
        .replace(
            "| [ ] | `ITEM-001` | `DEL-001`; `AC-001` | None | Implementer | "
            "`output.txt` | Write exact content |",
            "| [ ] | `ITEM-001` | `DEL-001`; `AC-001` | None | Implementer | "
            "`REPO-001`: `artifact/output.txt` | Preserve first output |\n"
            "| [ ] | `ITEM-002` | `DEL-002`; `AC-001` | None | Implementer | "
            "`REPO-002`: `artifact/output.txt` | Preserve second output |",
            1,
        )
        .replace(
            '| `AC-001` | Command | `test "$(cat output.txt)" = done` | Exit 0 |',
            "| `AC-001` | Snapshot | Compare repository-qualified entries | "
            "Two distinct retained entries |",
            1,
        )
    )


def implemented_plan_v3(plan_text: str, iteration: int = 1) -> str:
    updated = (
        plan_text.replace("| State | Planned |", "| State | In Review |", 1)
        .replace("| Current iteration | 0 |", f"| Current iteration | {iteration} |", 1)
        .replace("| Next actor | Implementer |", "| Next actor | Reviewer |", 1)
        .replace("| Pending |", "| Done |")
        .replace("| [ ] |", "| [x] |")
        .replace(
            "| 0 | Planner | Four-pack | Planning only | N/A | Implementer |",
            "| 0 | Planner | Four-pack | Planning only | N/A | Implementer |\n"
            f"| {iteration} | Implementer | Participant outputs and plan.md | "
            "fixture checks passed | N/A | Independent review |",
            1,
        )
    )
    if updated == plan_text:
        raise AssertionError("protocol-v3 fixture plan did not enter review")
    return updated


def empty_verify_v3(run_id: str) -> str:
    return empty_verify(run_id).replace(
        "| Accepted candidate commit | PENDING |",
        "| Accepted candidate commit | PENDING |\n"
        "| Accepted candidate vector SHA-256 | PENDING |",
        1,
    )


def accepted_verify_v3(
    run_id: str,
    candidate: str,
    branch: str,
    snapshot: str,
    vector: str,
    repositories: dict[str, tuple[str, str]],
) -> str:
    repository_rows = "\n".join(
        f"| {repository} | participant-{word} | `{branch}` | `{base}` | "
        f"`{commit}` | Yes |"
        for repository, word, (base, commit) in (
            ("REPO-001", "one", repositories["REPO-001"]),
            ("REPO-002", "two", repositories["REPO-002"]),
        )
    )
    return f"""# Multi-repository Verify

| Field | Value |
|---|---|
| Run ID | `{run_id}` |
| Evidence owner | Reviewer |
| Final decision | ACCEPTED |
| Accepted snapshot SHA-256 | `{snapshot}` |
| Accepted candidate commit | `{candidate}` |
| Accepted candidate vector SHA-256 | `{vector}` |

## Review Ledger

## ITER-001 Review

| Field | Value |
|---|---|
| Reviewer | Independent fixture reviewer |
| Date | 2026-07-30 |
| Environment | isolated CONTROL and participant worktrees |
| Candidate commit | `{candidate}` |
| Candidate branch | `{branch}` |
| Candidate vector SHA-256 | `{vector}` |
| Snapshot SHA-256 | `{snapshot}` |
| Verdict | ACCEPTED |
| Residual risk | Manual integration remains user-controlled |

### Candidate Repositories

| Repository | Logical identity | Branch | Base commit | Candidate commit | Changed this iteration |
|---|---|---|---|---|---|
{repository_rows}

### AC Decision Matrix

| AC | Result | Evidence |
|---|---|---|
| AC-001 | PASS | Independently matched both repository-qualified candidate bytes |

### Findings

| Finding | ACs | Type | Severity | Status | Evidence | Action class | Required action |
|---|---|---|---|---|---|---|---|

### Commands

| Command / review step | Expected exit | Actual exit | Result | Relevant output |
|---|---|---|---|---|
| repository-qualified snapshot comparison | 0 | 0 | PASS | Both immutable participant candidates matched |

### Conclusion

Every AC passed against the sealed multi-repository candidate vector.
"""


def typed_verify(
    run_id: str,
    candidate: str,
    branch: str,
    snapshot: str,
    *,
    verdict: str,
    finding_type: str,
    action_class: str,
    ac_result: str,
    finding_status: str = "Open",
    evidence: str = "fixture evidence",
) -> str:
    return f"""# Example Verify

| Field | Value |
|---|---|
| Run ID | `{run_id}` |
| Evidence owner | Reviewer |
| Final decision | {verdict} |
| Accepted snapshot SHA-256 | PENDING |
| Accepted candidate commit | PENDING |

## Review Ledger

## ITER-001 Review

| Field | Value |
|---|---|
| Reviewer | Independent fixture reviewer |
| Date | 2026-07-30 |
| Environment | temporary linked worktree, isolated fixture |
| Candidate commit | `{candidate}` |
| Candidate branch | `{branch}` |
| Snapshot SHA-256 | `{snapshot}` |
| Verdict | {verdict} |
| Residual risk | Required work remains |

### AC Decision Matrix

| AC | Result | Evidence |
|---|---|---|
| AC-001 | {ac_result} | independently observed fixture evidence |

### Findings

| Finding | ACs | Type | Severity | Status | Evidence | Action class | Required action |
|---|---|---|---|---|---|---|---|
| F-001 | AC-001 | {finding_type} | P1 | {finding_status} | {evidence} | {action_class} | Perform the bounded required action |

### Commands

| Command / review step | Expected exit | Actual exit | Result | Relevant output |
|---|---|---|---|---|
| fixture review | 0 | 1 | FAIL | required condition unavailable |

### Conclusion

The typed finding determines the next lifecycle action.
"""


def git_repo_with_task_worktree(
    root: Path,
    name: str,
    task_id: str,
    files: dict[str, str],
) -> tuple[Path, Path, str]:
    integration = root / f"{name}-integration"
    integration.mkdir()
    run(["git", "init", "-b", "main"], cwd=integration)
    git(integration, "config", "user.name", "Ralph Test")
    git(integration, "config", "user.email", "ralph@example.invalid")
    for relative, content in files.items():
        path = integration / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(integration, "add", *sorted(files))
    git(integration, "commit", "-m", f"{name} base")
    base = git(integration, "rev-parse", "HEAD")
    worktree = root / f"{name}-worktree"
    cli(
        "worktree-create",
        "--repo-root",
        str(integration),
        "--worktree-path",
        str(worktree),
        "--task-id",
        task_id,
        "--base",
        base,
    )
    return integration, worktree, base


@contextmanager
def git_v3_repository_fixture(
    task_id: str,
    run_id: str,
) -> Iterator[
    tuple[Path, Path, Path, Path, Path, str, str, str]
]:
    with tempfile.TemporaryDirectory(prefix="ralph-v3-repositories-") as raw:
        root = Path(raw)
        _, control, control_base = git_repo_with_task_worktree(
            root,
            "control",
            task_id,
            {"README.md": "control base\n"},
        )
        _, repo_1, repo_1_base = git_repo_with_task_worktree(
            root,
            "participant-one",
            task_id,
            {
                "README.md": "participant one base\n",
                "artifact/output.txt": "participant one output\n",
                "outside/output.txt": "outside declared scope\n",
            },
        )
        _, repo_2, repo_2_base = git_repo_with_task_worktree(
            root,
            "participant-two",
            task_id,
            {
                "README.md": "participant two base\n",
                "artifact/output.txt": "participant two output\n",
            },
        )
        _, extra_repo, _ = git_repo_with_task_worktree(
            root,
            "undeclared-extra",
            task_id,
            {"README.md": "undeclared extra base\n"},
        )

        initialized = json.loads(
            cli(
                "init",
                "--workspace-root",
                str(control),
                "--tasks-root",
                "tasks",
                "--task-id",
                task_id,
                "--title",
                "Protocol v3 repository mapping",
                "--run-id",
                run_id,
            ).stdout
        )
        task_dir = Path(initialized["task_dir"])
        (task_dir / "proposal.md").write_text(
            proposal_v3(task_id, run_id),
            encoding="utf-8",
        )
        (task_dir / "design.md").write_text(
            design_v3(task_id, repo_1_base, repo_2_base),
            encoding="utf-8",
        )
        (task_dir / "plan.md").write_text(
            plan_v3(
                run_id,
                control,
                f"ralph/{task_id}",
                control_base,
            ),
            encoding="utf-8",
        )
        (task_dir / "verify.md").write_text(
            empty_verify_v3(run_id),
            encoding="utf-8",
        )
        yield (
            control,
            repo_1,
            repo_2,
            extra_repo,
            task_dir,
            control_base,
            repo_1_base,
            repo_2_base,
        )


@contextmanager
def git_task_fixture(
    task_id: str,
    run_id: str,
    *,
    tracked_output: bool = False,
) -> Iterator[tuple[Path, Path, str]]:
    with tempfile.TemporaryDirectory(prefix="ralph-checkpoint-regression-") as raw:
        root = Path(raw)
        integration = root / "integration"
        integration.mkdir()
        run(["git", "init", "-b", "main"], cwd=integration)
        git(integration, "config", "user.name", "Ralph Test")
        git(integration, "config", "user.email", "ralph@example.invalid")
        (integration / "README.md").write_text("base\n", encoding="utf-8")
        tracked_paths = ["README.md"]
        if tracked_output:
            (integration / "output.txt").write_text("not done\n", encoding="utf-8")
            tracked_paths.append("output.txt")
        git(integration, "add", *tracked_paths)
        git(integration, "commit", "-m", "base")
        base = git(integration, "rev-parse", "HEAD")

        worktree = root / task_id
        cli(
            "worktree-create",
            "--repo-root",
            str(integration),
            "--worktree-path",
            str(worktree),
            "--task-id",
            task_id,
            "--base",
            base,
        )
        init = json.loads(
            cli(
                "init",
                "--workspace-root",
                str(worktree),
                "--tasks-root",
                "tasks",
                "--task-id",
                task_id,
                "--title",
                "Checkpoint regression",
                "--run-id",
                run_id,
            ).stdout
        )
        task_dir = Path(init["task_dir"])
        (task_dir / "proposal.md").write_text(
            proposal(task_id, run_id), encoding="utf-8"
        )
        (task_dir / "design.md").write_text(design(task_id), encoding="utf-8")
        (task_dir / "plan.md").write_text(
            plan(
                run_id,
                worktree,
                f"ralph/{task_id}",
                base,
                implemented=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "verify.md").write_text(
            empty_verify(run_id), encoding="utf-8"
        )
        yield worktree, task_dir, base


@contextmanager
def git_v2_task_fixture(
    task_id: str,
    run_id: str,
) -> Iterator[tuple[Path, Path, str]]:
    with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
        (task_dir / "proposal.md").write_text(
            proposal_v2(task_id, run_id),
            encoding="utf-8",
        )
        (task_dir / "design.md").write_text(
            design_v2(task_id),
            encoding="utf-8",
        )
        (task_dir / "plan.md").write_text(
            plan_v2(
                run_id,
                worktree,
                f"ralph/{task_id}",
                base,
                implemented=False,
            ),
            encoding="utf-8",
        )
        yield worktree, task_dir, base


def planner_checkpoint(
    worktree: Path,
    task_dir: Path,
    task_id: str,
) -> subprocess.CompletedProcess[str]:
    return cli(
        "checkpoint",
        "--workspace-root",
        str(worktree),
        "--task-dir",
        str(task_dir),
        "--task-id",
        task_id,
        "--role",
        "planner-init",
        "--iteration",
        "0",
        "--index",
        "tasks/index.md",
    )


class GitFlowTest(unittest.TestCase):
    def test_planner_rejects_ignored_task_index(self) -> None:
        task_id = "TASK-IGNORED-INDEX"
        run_id = "RUN-IGNORED-INDEX"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            exclude = git_exclude_path(worktree)
            original = exclude.read_text(encoding="utf-8")
            exclude.write_text(
                original + "\ntasks/index.md\n",
                encoding="utf-8",
            )
            result = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--task-id",
                task_id,
                "--role",
                "planner-init",
                "--iteration",
                "0",
                "--index",
                "tasks/index.md",
                expected=2,
            )

            self.assertIn(
                "Planner four-pack/index paths are ignored or otherwise unavailable",
                result.stderr,
            )
            self.assertIn("tasks/index.md", result.stderr)
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), base)
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_implementer_rejects_manual_commit_after_planner(self) -> None:
        task_id = "TASK-MANUAL"
        run_id = "RUN-MANUAL"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            planner_checkpoint(worktree, task_dir, task_id)
            planner_head = git(worktree, "rev-parse", "HEAD")

            (worktree / "manual.txt").write_text(
                "unrelated user commit\n", encoding="utf-8"
            )
            git(worktree, "add", "manual.txt")
            git(worktree, "commit", "-m", "manual unrelated change")
            manual_head = git(worktree, "rev-parse", "HEAD")
            self.assertNotEqual(manual_head, planner_head)

            (worktree / "output.txt").write_text("done\n", encoding="utf-8")
            (task_dir / "plan.md").write_text(
                plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )
            result = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--task-id",
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
                expected=2,
            )

            self.assertIn(f"is not a checkpoint for {task_id}", result.stderr)
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), manual_head)
            self.assertEqual(
                git(worktree, "show", "-s", "--format=%s", "HEAD"),
                "manual unrelated change",
            )
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_implementer_rejects_rewritten_base_commit(self) -> None:
        task_id = "TASK-BASE"
        run_id = "RUN-BASE"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, _):
            planner_checkpoint(worktree, task_dir, task_id)
            planner_head = git(worktree, "rev-parse", "HEAD")

            (worktree / "output.txt").write_text("done\n", encoding="utf-8")
            (task_dir / "plan.md").write_text(
                plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    planner_head,
                    implemented=True,
                ),
                encoding="utf-8",
            )
            result = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--task-id",
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
                expected=2,
            )

            self.assertIn(
                "plan Base commit changed from authoritative",
                result.stderr,
            )
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), planner_head)
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_task_pack_artifacts_cannot_expand_implementer_authority(self) -> None:
        cases = (
            ("PROPOSAL", "proposal.md", False),
            ("VERIFY", "verify.md", False),
            ("ANCESTOR", None, False),
            ("EXPLICIT", None, True),
        )
        for suffix, pack_name, explicit in cases:
            with self.subTest(case=suffix):
                task_id = f"TASK-PACK-{suffix}"
                run_id = f"RUN-PACK-{suffix}"
                with git_task_fixture(task_id, run_id) as (
                    worktree,
                    task_dir,
                    base,
                ):
                    planner_checkpoint(worktree, task_dir, task_id)
                    planner_head = git(worktree, "rev-parse", "HEAD")
                    task_relative = (
                        task_dir.resolve()
                        .relative_to(worktree.resolve())
                        .as_posix()
                    )
                    target = task_dir / (pack_name or "verify.md")
                    target.write_text(
                        target.read_text(encoding="utf-8")
                        + "\nunauthorized implementer edit\n",
                        encoding="utf-8",
                    )

                    implemented_plan = plan(
                        run_id,
                        worktree,
                        f"ralph/{task_id}",
                        base,
                        implemented=True,
                    )
                    if explicit:
                        artifact_arguments = ["--artifact", task_relative]
                        (worktree / "output.txt").write_text(
                            "done\n", encoding="utf-8"
                        )
                    else:
                        declared_path = (
                            f"{task_relative}/{pack_name}"
                            if pack_name is not None
                            else task_relative
                        )
                        implemented_plan = implemented_plan.replace(
                            "output.txt",
                            declared_path,
                        )
                        artifact_arguments = []
                    (task_dir / "plan.md").write_text(
                        implemented_plan,
                        encoding="utf-8",
                    )

                    result = cli(
                        "checkpoint",
                        "--workspace-root",
                        str(worktree),
                        "--task-dir",
                        str(task_dir),
                        "--task-id",
                        task_id,
                        "--role",
                        "implementer",
                        "--iteration",
                        "1",
                        *artifact_arguments,
                        expected=2,
                    )

                    self.assertIn(
                        "must not overlap the four-pack task directory",
                        result.stderr,
                    )
                    self.assertEqual(
                        git(worktree, "rev-parse", "HEAD"),
                        planner_head,
                    )
                    self.assertEqual(
                        git(worktree, "diff", "--cached", "--name-only"),
                        "",
                    )

    def test_declared_and_explicit_artifacts_do_not_expand_planner_authority(
        self,
    ) -> None:
        cases = (
            ("DECLARED", "output.txt", []),
            ("EXPLICIT", "planner-extra.txt", ["--artifact", "planner-extra.txt"]),
        )
        for suffix, changed_path, artifact_arguments in cases:
            with self.subTest(case=suffix):
                task_id = f"TASK-PLANNER-{suffix}"
                run_id = f"RUN-PLANNER-{suffix}"
                with git_task_fixture(task_id, run_id) as (
                    worktree,
                    task_dir,
                    base,
                ):
                    (worktree / changed_path).write_text(
                        "planner must not implement this\n",
                        encoding="utf-8",
                    )
                    result = cli(
                        "checkpoint",
                        "--workspace-root",
                        str(worktree),
                        "--task-dir",
                        str(task_dir),
                        "--task-id",
                        task_id,
                        "--role",
                        "planner-init",
                        "--iteration",
                        "0",
                        "--index",
                        "tasks/index.md",
                        *artifact_arguments,
                        expected=2,
                    )

                    self.assertIn(
                        "planner-init changed paths outside its authority",
                        result.stderr,
                    )
                    self.assertIn(changed_path, result.stderr)
                    self.assertEqual(git(worktree, "rev-parse", "HEAD"), base)
                    self.assertEqual(
                        git(worktree, "diff", "--cached", "--name-only"),
                        "",
                    )

    def test_implementer_rejects_nondefault_snapshot_index_flags(self) -> None:
        cases = (
            ("ASSUME", "--assume-unchanged"),
            ("SKIP", "--skip-worktree"),
        )
        for suffix, flag in cases:
            with self.subTest(flag=flag):
                task_id = f"TASK-FLAG-{suffix}"
                run_id = f"RUN-FLAG-{suffix}"
                with git_task_fixture(
                    task_id,
                    run_id,
                    tracked_output=True,
                ) as (worktree, task_dir, base):
                    planner_checkpoint(worktree, task_dir, task_id)
                    planner_head = git(worktree, "rev-parse", "HEAD")
                    git(worktree, "update-index", flag, "output.txt")
                    (worktree / "output.txt").write_text(
                        "done\n", encoding="utf-8"
                    )
                    (task_dir / "plan.md").write_text(
                        plan(
                            run_id,
                            worktree,
                            f"ralph/{task_id}",
                            base,
                            implemented=True,
                        ),
                        encoding="utf-8",
                    )

                    result = cli(
                        "checkpoint",
                        "--workspace-root",
                        str(worktree),
                        "--task-dir",
                        str(task_dir),
                        "--task-id",
                        task_id,
                        "--role",
                        "implementer",
                        "--iteration",
                        "1",
                        expected=2,
                    )

                    self.assertIn(
                        "snapshot members use non-default Git index flags",
                        result.stderr,
                    )
                    self.assertIn("output.txt", result.stderr)
                    self.assertEqual(
                        git(worktree, "rev-parse", "HEAD"),
                        planner_head,
                    )
                    self.assertEqual(
                        git(worktree, "diff", "--cached", "--name-only"),
                        "",
                    )

    def test_implementer_rejects_unsupported_nested_artifact_member(self) -> None:
        task_id = "TASK-FIFO"
        run_id = "RUN-FIFO"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            for name in ("proposal.md", "design.md", "plan.md"):
                path = task_dir / name
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "output.txt",
                        "bundle",
                    ),
                    encoding="utf-8",
                )
            planner_checkpoint(worktree, task_dir, task_id)
            planner_head = git(worktree, "rev-parse", "HEAD")

            bundle = worktree / "bundle"
            bundle.mkdir()
            (bundle / "data.txt").write_text("done\n", encoding="utf-8")
            os.mkfifo(bundle / "pipe")
            (task_dir / "plan.md").write_text(
                plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            result = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--task-id",
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
                expected=2,
            )

            self.assertIn(
                "cannot preserve unsupported snapshot members",
                result.stderr,
            )
            self.assertIn("bundle/pipe", result.stderr)
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), planner_head)
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_two_worktrees_checkpoint_archive_and_manual_handoff(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ralph-git-flow-") as raw:
            root = Path(raw)
            integration = root / "integration"
            integration.mkdir()
            run(["git", "init", "-b", "main"], cwd=integration)
            git(integration, "config", "user.name", "Ralph Test")
            git(integration, "config", "user.email", "ralph@example.invalid")
            (integration / "README.md").write_text("base\n", encoding="utf-8")
            git(integration, "add", "README.md")
            git(integration, "commit", "-m", "base")
            base = git(integration, "rev-parse", "HEAD")

            worktree_a = root / "TASK-A"
            worktree_b = root / "TASK-B"
            cli(
                "worktree-create",
                "--repo-root",
                str(integration),
                "--worktree-path",
                str(worktree_a),
                "--task-id",
                "TASK-A",
                "--base",
                base,
            )
            cli(
                "worktree-create",
                "--repo-root",
                str(integration),
                "--worktree-path",
                str(worktree_b),
                "--task-id",
                "TASK-B",
                "--base",
                base,
            )
            self.assertEqual(git(worktree_a, "branch", "--show-current"), "ralph/TASK-A")
            self.assertEqual(git(worktree_b, "branch", "--show-current"), "ralph/TASK-B")
            nested = integration / "nested-TASK-N"
            nested_result = cli(
                "worktree-create",
                "--repo-root",
                str(worktree_a),
                "--worktree-path",
                str(nested),
                "--task-id",
                "TASK-N",
                "--base",
                base,
                expected=2,
            )
            self.assertIn("outside every registered worktree", nested_result.stderr)
            self.assertFalse(nested.exists())
            self.assertEqual(git(integration, "status", "--porcelain"), "")

            init = json.loads(
                cli(
                    "init",
                    "--workspace-root",
                    str(worktree_a),
                    "--tasks-root",
                    "tasks",
                    "--task-id",
                    "TASK-A",
                    "--title",
                    "Example",
                    "--run-id",
                    "RUN-A",
                ).stdout
            )
            task_dir = Path(init["task_dir"])
            (task_dir / "proposal.md").write_text(
                proposal("TASK-A", "RUN-A"), encoding="utf-8"
            )
            (task_dir / "design.md").write_text(
                design("TASK-A"), encoding="utf-8"
            )
            (task_dir / "plan.md").write_text(
                plan(
                    "RUN-A",
                    worktree_a,
                    "ralph/TASK-A",
                    base,
                    implemented=False,
                ),
                encoding="utf-8",
            )
            (task_dir / "verify.md").write_text(
                empty_verify("RUN-A"), encoding="utf-8"
            )
            cli(
                "checkpoint",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--task-id",
                "TASK-A",
                "--role",
                "planner-init",
                "--iteration",
                "0",
                "--index",
                "tasks/index.md",
            )

            (worktree_a / "output.txt").write_text("done\n", encoding="utf-8")
            (task_dir / "plan.md").write_text(
                plan(
                    "RUN-A",
                    worktree_a,
                    "ralph/TASK-A",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )
            candidate_result = json.loads(
                cli(
                    "checkpoint",
                    "--workspace-root",
                    str(worktree_a),
                    "--task-dir",
                    str(task_dir),
                    "--task-id",
                    "TASK-A",
                    "--role",
                    "implementer",
                    "--iteration",
                    "1",
                ).stdout
            )
            candidate = candidate_result["commit"]
            snapshot = candidate_result["snapshot_sha256"]
            snapshot_result = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree_a),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )
            self.assertEqual(snapshot_result["snapshot_sha256"], snapshot)
            self.assertEqual(snapshot_result["git"]["candidate_commit"], candidate)

            (task_dir / "verify.md").write_text(
                accepted_verify(
                    "RUN-A",
                    candidate,
                    "ralph/TASK-A",
                    snapshot,
                ),
                encoding="utf-8",
            )
            skipped_reviewer = cli(
                "archive",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-root",
                "tasks/archive",
                "--index",
                "tasks/index.md",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
                expected=2,
            )
            self.assertIn("Reviewer checkpoint", skipped_reviewer.stderr)
            self.assertTrue(task_dir.exists())
            (worktree_a / "README.md").write_text(
                "reviewer must not change this\n",
                encoding="utf-8",
            )
            rejected_review = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--task-id",
                "TASK-A",
                "--role",
                "reviewer",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn("outside its authority", rejected_review.stderr)
            self.assertEqual(git(worktree_a, "rev-parse", "HEAD"), candidate)
            self.assertEqual(git(worktree_a, "diff", "--cached", "--name-only"), "")
            (worktree_a / "README.md").write_text("base\n", encoding="utf-8")
            cli(
                "checkpoint",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--task-id",
                "TASK-A",
                "--role",
                "reviewer",
                "--iteration",
                "1",
            )
            reviewer_head = git(worktree_a, "rev-parse", "HEAD")
            index_before_confirmation = (
                worktree_a / "tasks/index.md"
            ).read_bytes()
            missing_archive_confirmation = cli(
                "archive",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-root",
                "tasks/archive",
                "--index",
                "tasks/index.md",
                expected=2,
            )
            self.assertIn(
                "--authorization-token",
                missing_archive_confirmation.stderr,
            )
            self.assertEqual(git(worktree_a, "rev-parse", "HEAD"), reviewer_head)
            self.assertEqual(git(worktree_a, "status", "--porcelain"), "")
            self.assertEqual(
                (worktree_a / "tasks/index.md").read_bytes(),
                index_before_confirmation,
            )
            self.assertTrue(task_dir.exists())
            self.assertFalse((worktree_a / "tasks/archive/TASK-A").exists())
            verify_at_review = run(
                [
                    "git",
                    "-C",
                    str(worktree_a),
                    "show",
                    (
                        "HEAD:"
                        f"{task_dir.resolve().relative_to(worktree_a.resolve()).as_posix()}"
                        "/verify.md"
                    ),
                ]
            ).stdout
            (task_dir / "verify.md").write_text(
                verify_at_review + "\npost-review mutation\n",
                encoding="utf-8",
            )
            mutated_review = cli(
                "archive",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-root",
                "tasks/archive",
                "--index",
                "tasks/index.md",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
                expected=2,
            )
            self.assertIn("clean worktree", mutated_review.stderr)
            (task_dir / "verify.md").write_text(verify_at_review, encoding="utf-8")
            git(
                worktree_a,
                "update-index",
                "--assume-unchanged",
                "tasks/index.md",
            )
            flagged_archive = cli(
                "archive",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-root",
                "tasks/archive",
                "--index",
                "tasks/index.md",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
                expected=2,
            )
            self.assertIn(
                "archive paths use non-default Git index flags",
                flagged_archive.stderr,
            )
            self.assertTrue(task_dir.exists())
            git(
                worktree_a,
                "update-index",
                "--no-assume-unchanged",
                "tasks/index.md",
            )
            exclude = git_exclude_path(worktree_a)
            original_exclude = exclude.read_text(encoding="utf-8")
            exclude.write_text(
                original_exclude + "\ntasks/archive/\n",
                encoding="utf-8",
            )
            ignored_archive = cli(
                "archive",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-root",
                "tasks/archive",
                "--index",
                "tasks/index.md",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
                expected=2,
            )
            self.assertIn(
                "archive destination paths are ignored",
                ignored_archive.stderr,
            )
            self.assertTrue(task_dir.exists())
            exclude.write_text(original_exclude, encoding="utf-8")
            archive = json.loads(
                cli(
                    "archive",
                    "--workspace-root",
                    str(worktree_a),
                    "--task-dir",
                    str(task_dir),
                    "--archive-root",
                    "tasks/archive",
                    "--index",
                    "tasks/index.md",
                    "--authorization-token",
                    ARCHIVE_CONFIRMATION,
                ).stdout
            )
            self.assertEqual(
                archive["archive_authorization_sha256"],
                ARCHIVE_CONFIRMATION_SHA256,
            )
            archived_task = Path(archive["archived_task_dir"])
            archive_wip = git(worktree_a, "status", "--porcelain")
            missing_closure_confirmation = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-task-dir",
                str(archived_task),
                "--index",
                "tasks/index.md",
                "--task-id",
                "TASK-A",
                "--role",
                "closure",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn(
                "closure checkpoint requires --authorization-token",
                missing_closure_confirmation.stderr,
            )
            self.assertEqual(git(worktree_a, "rev-parse", "HEAD"), reviewer_head)
            self.assertEqual(git(worktree_a, "status", "--porcelain"), archive_wip)
            self.assertTrue(archived_task.exists())
            exclude.write_text(
                original_exclude + "\ntasks/archive/\n",
                encoding="utf-8",
            )
            ignored_closure = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(task_dir),
                "--archive-task-dir",
                str(archived_task),
                "--index",
                "tasks/index.md",
                "--task-id",
                "TASK-A",
                "--role",
                "closure",
                "--iteration",
                "1",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
                expected=2,
            )
            self.assertIn(
                "Closure checkpoint must capture every active deletion",
                ignored_closure.stderr,
            )
            self.assertTrue(archived_task.exists())
            self.assertEqual(git(worktree_a, "diff", "--cached", "--name-only"), "")
            exclude.write_text(original_exclude, encoding="utf-8")
            closure = json.loads(
                cli(
                    "checkpoint",
                    "--workspace-root",
                    str(worktree_a),
                    "--task-dir",
                    str(task_dir),
                    "--archive-task-dir",
                    str(archived_task),
                    "--index",
                    "tasks/index.md",
                    "--task-id",
                    "TASK-A",
                    "--role",
                    "closure",
                    "--iteration",
                    "1",
                    "--authorization-token",
                    ARCHIVE_CONFIRMATION,
                ).stdout
            )
            self.assertEqual(
                closure["archive_authorization_sha256"],
                ARCHIVE_CONFIRMATION_SHA256,
            )
            closure_message = git(
                worktree_a,
                "show",
                "-s",
                "--format=%B",
                closure["commit"],
            )
            self.assertIn(
                f"Ralph-Authorization-SHA256: {ARCHIVE_CONFIRMATION_SHA256}",
                closure_message,
            )
            git(
                worktree_a,
                "update-index",
                "--skip-worktree",
                "tasks/index.md",
            )
            flagged_handoff = cli(
                "handoff",
                "--workspace-root",
                str(worktree_a),
                "--task-dir",
                str(archived_task),
                "--index",
                "tasks/index.md",
                expected=2,
            )
            self.assertIn(
                "handoff paths use non-default Git index flags",
                flagged_handoff.stderr,
            )
            git(
                worktree_a,
                "update-index",
                "--no-skip-worktree",
                "tasks/index.md",
            )
            handoff = json.loads(
                cli(
                    "handoff",
                    "--workspace-root",
                    str(worktree_a),
                    "--task-dir",
                    str(archived_task),
                    "--index",
                    "tasks/index.md",
                ).stdout
            )
            self.assertTrue(handoff["merge_ready"])
            self.assertEqual(handoff["merge_mode"], "manual")
            self.assertEqual(handoff["base_commit"], base)
            self.assertEqual(handoff["accepted_candidate_commit"], candidate)
            self.assertEqual(handoff["closure_commit"], closure["commit"])
            self.assertEqual(
                handoff["archive_authorization_sha256"],
                ARCHIVE_CONFIRMATION_SHA256,
            )

            self.assertEqual(git(integration, "rev-parse", "HEAD"), base)
            self.assertEqual(git(worktree_b, "rev-parse", "HEAD"), base)
            self.assertEqual(git(integration, "status", "--porcelain"), "")
            self.assertEqual(git(worktree_b, "status", "--porcelain"), "")
            self.assertFalse((integration / "tasks").exists())
            self.assertFalse((worktree_b / "tasks").exists())

    def test_implementer_checkpoint_rejects_ignored_deliverable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ralph-ignored-") as raw:
            root = Path(raw)
            integration = root / "integration"
            integration.mkdir()
            run(["git", "init", "-b", "main"], cwd=integration)
            git(integration, "config", "user.name", "Ralph Test")
            git(integration, "config", "user.email", "ralph@example.invalid")
            (integration / "README.md").write_text("base\n", encoding="utf-8")
            (integration / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            git(integration, "add", "README.md", ".gitignore")
            git(integration, "commit", "-m", "base")
            base = git(integration, "rev-parse", "HEAD")
            worktree = root / "TASK-I"
            cli(
                "worktree-create",
                "--repo-root",
                str(integration),
                "--worktree-path",
                str(worktree),
                "--task-id",
                "TASK-I",
                "--base",
                base,
            )
            init = json.loads(
                cli(
                    "init",
                    "--workspace-root",
                    str(worktree),
                    "--tasks-root",
                    "tasks",
                    "--task-id",
                    "TASK-I",
                    "--title",
                    "Ignored",
                    "--run-id",
                    "RUN-I",
                ).stdout
            )
            task_dir = Path(init["task_dir"])
            (task_dir / "proposal.md").write_text(
                proposal("TASK-I", "RUN-I").replace("output.txt", "ignored.txt"),
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                design("TASK-I").replace("output.txt", "ignored.txt"),
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                plan(
                    "RUN-I",
                    worktree,
                    "ralph/TASK-I",
                    base,
                    implemented=False,
                ).replace("output.txt", "ignored.txt"),
                encoding="utf-8",
            )
            (task_dir / "verify.md").write_text(
                empty_verify("RUN-I"), encoding="utf-8"
            )
            cli(
                "checkpoint",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--task-id",
                "TASK-I",
                "--role",
                "planner-init",
                "--iteration",
                "0",
                "--index",
                "tasks/index.md",
            )
            planner_head = git(worktree, "rev-parse", "HEAD")
            (worktree / "ignored.txt").write_text("done\n", encoding="utf-8")
            (task_dir / "plan.md").write_text(
                plan(
                    "RUN-I",
                    worktree,
                    "ralph/TASK-I",
                    base,
                    implemented=True,
                ).replace("output.txt", "ignored.txt"),
                encoding="utf-8",
            )
            result = cli(
                "checkpoint",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--task-id",
                "TASK-I",
                "--role",
                "implementer",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn("unavailable to the candidate commit", result.stderr)
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), planner_head)
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_directory_deliverable_accepts_manifested_external_evidence(
        self,
    ) -> None:
        task_id = "TASK-EXTERNAL-EVIDENCE"
        run_id = "RUN-EXTERNAL-EVIDENCE"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            (task_dir / "proposal.md").write_text(
                proposal(task_id, run_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                design(task_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=False,
                ),
                encoding="utf-8",
            )
            planner_checkpoint(worktree, task_dir, task_id)

            exclude = git_exclude_path(worktree)
            exclude.write_text(
                exclude.read_text(encoding="utf-8")
                + "\nbundle/external/*.pt\n",
                encoding="utf-8",
            )
            (worktree / "bundle").mkdir()
            (worktree / "bundle" / "result.txt").write_text(
                "done\n",
                encoding="utf-8",
            )
            (worktree / "bundle" / "external").mkdir()
            raw_evidence = worktree / "bundle" / "external" / "raw.pt"
            raw_evidence.write_bytes(b"raw tensor v1")
            (worktree / "evidence").mkdir()
            manifest = worktree / "evidence" / "manifest.json"
            manifest.write_text(
                '{"files":{"bundle/external/raw.pt":"fixture-sha256"}}\n',
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )

            snapshot_with_raw = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )
            hidden_artifact = cli(
                "snapshot",
                "--workspace-root",
                str(worktree),
                "--task-dir",
                str(task_dir),
                "--artifact",
                "bundle/external/raw.pt",
                expected=2,
            )
            self.assertIn(
                "external-evidence exclusions must not hide snapshot artifacts",
                hidden_artifact.stderr,
            )
            raw_evidence.write_bytes(b"raw tensor v2")
            snapshot_with_changed_raw = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )
            raw_evidence.unlink()
            raw_evidence.parent.rmdir()
            snapshot_without_raw = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )
            self.assertEqual(
                snapshot_with_raw["snapshot_sha256"],
                snapshot_with_changed_raw["snapshot_sha256"],
            )
            self.assertEqual(
                snapshot_with_raw["snapshot_sha256"],
                snapshot_without_raw["snapshot_sha256"],
            )
            self.assertEqual(
                snapshot_with_raw["schema"],
                "rd-ralph-snapshot-v3",
            )

            original_manifest = manifest.read_text(encoding="utf-8")
            manifest.write_text(
                '{"files":{"bundle/external/raw.pt":"changed-sha256"}}\n',
                encoding="utf-8",
            )
            changed_manifest_snapshot = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )
            self.assertNotEqual(
                snapshot_with_raw["snapshot_sha256"],
                changed_manifest_snapshot["snapshot_sha256"],
            )
            manifest.write_text(original_manifest, encoding="utf-8")
            exclude.write_text(
                exclude.read_text(encoding="utf-8").replace(
                    "\nbundle/external/*.pt\n",
                    "\n",
                ),
                encoding="utf-8",
            )

            checkpoint = json.loads(
                task_cli(
                    "checkpoint",
                    worktree,
                    task_dir,
                    task_id,
                    "--role",
                    "implementer",
                    "--iteration",
                    "1",
                ).stdout
            )
            candidate_paths = set(
                git(
                    worktree,
                    "ls-tree",
                    "-r",
                    "--name-only",
                    checkpoint["commit"],
                ).splitlines()
            )
            self.assertIn("bundle/result.txt", candidate_paths)
            self.assertIn("evidence/manifest.json", candidate_paths)
            self.assertNotIn("bundle/external/raw.pt", candidate_paths)
            self.assertFalse(raw_evidence.exists())
            self.assertEqual(git(worktree, "status", "--porcelain"), "")
            (task_dir / "verify.md").write_text(
                accepted_verify(
                    run_id,
                    checkpoint["commit"],
                    f"ralph/{task_id}",
                    checkpoint["snapshot_sha256"],
                ),
                encoding="utf-8",
            )
            reviewed = json.loads(
                cli(
                    "validate",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                    "--phase",
                    "reviewed",
                ).stdout
            )
            self.assertTrue(reviewed["valid"], reviewed["errors"])
            manifest.write_text(
                '{"files":{"bundle/external/raw.pt":"tampered"}}\n',
                encoding="utf-8",
            )
            tampered_snapshot = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )["snapshot_sha256"]
            (task_dir / "verify.md").write_text(
                accepted_verify(
                    run_id,
                    checkpoint["commit"],
                    f"ralph/{task_id}",
                    tampered_snapshot,
                ),
                encoding="utf-8",
            )
            tampered = json.loads(
                cli(
                    "validate",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                    "--phase",
                    "reviewed",
                    expected=1,
                ).stdout
            )
            self.assertFalse(tampered["valid"])
            self.assertTrue(
                any(
                    "candidate trailer" in error.casefold()
                    or "recorded commit" in error.casefold()
                    for error in tampered["errors"]
                ),
                tampered["errors"],
            )

    def test_legacy_directory_snapshot_keeps_global_member_order(self) -> None:
        task_id = "TASK-LEGACY-DIRECTORY-ORDER"
        run_id = "RUN-LEGACY-DIRECTORY-ORDER"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            (task_dir / "proposal.md").write_text(
                proposal(task_id, run_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                design(task_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=False,
                ).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (worktree / "bundle" / "a").mkdir(parents=True)
            nested = worktree / "bundle" / "a" / "x.txt"
            sibling = worktree / "bundle" / "a-"
            nested.write_text("nested\n", encoding="utf-8")
            sibling.write_text("sibling\n", encoding="utf-8")

            snapshot = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )
            entry = next(
                item for item in snapshot["entries"] if item["path"] == "bundle"
            )
            members = [
                {"path": "a", "type": "directory"},
                {
                    "path": "a-",
                    "type": "file",
                    "sha256": hashlib.sha256(sibling.read_bytes()).hexdigest(),
                    "size": sibling.stat().st_size,
                },
                {
                    "path": "a/x.txt",
                    "type": "file",
                    "sha256": hashlib.sha256(nested.read_bytes()).hexdigest(),
                    "size": nested.stat().st_size,
                },
            ]
            expected_hash = hashlib.sha256(
                json.dumps(
                    members,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(snapshot["schema"], "rd-ralph-snapshot-v1")
            self.assertEqual(entry["sha256"], expected_hash)

    def test_external_evidence_can_remove_a_previously_tracked_raw_file(
        self,
    ) -> None:
        task_id = "TASK-EXTERNAL-MIGRATION"
        run_id = "RUN-EXTERNAL-MIGRATION"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, _):
            tracked_raw = worktree / "bundle" / "external" / "raw.pt"
            tracked_raw.parent.mkdir(parents=True)
            tracked_raw.write_bytes(b"legacy tracked raw")
            git(worktree, "add", "bundle/external/raw.pt")
            git(worktree, "commit", "-m", "fixture tracked evidence base")
            base = git(worktree, "rev-parse", "HEAD")
            (task_dir / "proposal.md").write_text(
                proposal(task_id, run_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                design(task_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=False,
                ),
                encoding="utf-8",
            )
            planner_checkpoint(worktree, task_dir, task_id)

            tracked_raw.unlink()
            (worktree / "bundle" / "result.txt").write_text(
                "done\n",
                encoding="utf-8",
            )
            (worktree / "evidence").mkdir()
            (worktree / "evidence" / "manifest.json").write_text(
                '{"files":{"bundle/external/raw.pt":"legacy-sha256"}}\n',
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )
            checkpoint = json.loads(
                task_cli(
                    "checkpoint",
                    worktree,
                    task_dir,
                    task_id,
                    "--role",
                    "implementer",
                    "--iteration",
                    "1",
                ).stdout
            )
            candidate_paths = set(
                git(
                    worktree,
                    "ls-tree",
                    "-r",
                    "--name-only",
                    checkpoint["commit"],
                ).splitlines()
            )
            self.assertNotIn("bundle/external/raw.pt", candidate_paths)
            self.assertIn("bundle/result.txt", candidate_paths)
            self.assertIn("evidence/manifest.json", candidate_paths)
            self.assertEqual(git(worktree, "status", "--porcelain"), "")

    def test_external_evidence_exclusion_does_not_hide_unlisted_ignored_file(
        self,
    ) -> None:
        task_id = "TASK-EXTERNAL-BOUNDARY"
        run_id = "RUN-EXTERNAL-BOUNDARY"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            (task_dir / "proposal.md").write_text(
                proposal(task_id, run_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                design(task_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=False,
                ),
                encoding="utf-8",
            )
            planner_checkpoint(worktree, task_dir, task_id)
            planner_head = git(worktree, "rev-parse", "HEAD")

            exclude = git_exclude_path(worktree)
            exclude.write_text(
                exclude.read_text(encoding="utf-8")
                + "\nbundle/external/*.pt\n",
                encoding="utf-8",
            )
            (worktree / "bundle").mkdir()
            (worktree / "bundle" / "result.txt").write_text(
                "done\n",
                encoding="utf-8",
            )
            (worktree / "bundle" / "external").mkdir()
            (worktree / "bundle" / "external" / "raw.pt").write_bytes(b"listed")
            (worktree / "bundle" / "external" / "unlisted.pt").write_bytes(
                b"unlisted"
            )
            (worktree / "evidence").mkdir()
            (worktree / "evidence" / "manifest.json").write_text(
                '{"files":{"bundle/external/raw.pt":"fixture-sha256"}}\n',
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )

            result = task_cli(
                "checkpoint",
                worktree,
                task_dir,
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn("bundle/external/unlisted.pt", result.stderr)
            self.assertIn("unavailable to the candidate commit", result.stderr)
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), planner_head)
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_implementer_cannot_add_external_evidence_exclusion_without_authority(
        self,
    ) -> None:
        task_id = "TASK-EXTERNAL-AUTHORITY"
        run_id = "RUN-EXTERNAL-AUTHORITY"
        with git_task_fixture(task_id, run_id) as (worktree, task_dir, base):
            (task_dir / "proposal.md").write_text(
                proposal(task_id, run_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                design(task_id).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=False,
                ).replace("output.txt", "bundle"),
                encoding="utf-8",
            )
            planner_checkpoint(worktree, task_dir, task_id)
            planner_head = git(worktree, "rev-parse", "HEAD")

            exclude = git_exclude_path(worktree)
            exclude.write_text(
                exclude.read_text(encoding="utf-8")
                + "\nbundle/external/*.pt\n",
                encoding="utf-8",
            )
            (worktree / "bundle").mkdir()
            (worktree / "bundle" / "result.txt").write_text(
                "done\n",
                encoding="utf-8",
            )
            (worktree / "bundle" / "external").mkdir()
            (worktree / "bundle" / "external" / "raw.pt").write_bytes(
                b"external"
            )
            (worktree / "evidence").mkdir()
            (worktree / "evidence" / "manifest.json").write_text(
                '{"files":{"bundle/external/raw.pt":"fixture-sha256"}}\n',
                encoding="utf-8",
            )
            (task_dir / "plan.md").write_text(
                external_evidence_plan(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )
            result = task_cli(
                "checkpoint",
                worktree,
                task_dir,
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn(
                "expanded External Evidence Exclusions; route through "
                "an authorized Planner checkpoint",
                result.stderr,
            )
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), planner_head)
            self.assertEqual(git(worktree, "diff", "--cached", "--name-only"), "")

    def test_git_context_rejects_primary_worktree_for_loop(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ralph-primary-") as raw:
            repo = Path(raw)
            run(["git", "init", "-b", "ralph/TASK-X"], cwd=repo)
            git(repo, "config", "user.name", "Ralph Test")
            git(repo, "config", "user.email", "ralph@example.invalid")
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "base")
            result = cli(
                "git-context",
                "--workspace-root",
                str(repo),
                "--task-id",
                "TASK-X",
                "--require-git",
                expected=2,
            )
            self.assertIn("linked worktree", result.stderr)


class ProtocolV3RepositoryMappingTest(unittest.TestCase):
    @staticmethod
    def _repository_arguments(repo_1: Path, repo_2: Path) -> list[str]:
        return [
            "--repo",
            f"REPO-001={repo_1}",
            "--repo",
            f"REPO-002={repo_2}",
        ]

    @classmethod
    def _command(
        cls,
        command: str,
        control: Path,
        task_dir: Path,
        repo_1: Path,
        repo_2: Path,
        *arguments: str,
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return cli(
            command,
            "--workspace-root",
            str(control),
            "--task-dir",
            str(task_dir),
            *arguments,
            *cls._repository_arguments(repo_1, repo_2),
            expected=expected,
        )

    @classmethod
    def _json(
        cls,
        command: str,
        control: Path,
        task_dir: Path,
        repo_1: Path,
        repo_2: Path,
        *arguments: str,
    ) -> dict[str, object]:
        return json.loads(
            cls._command(
                command,
                control,
                task_dir,
                repo_1,
                repo_2,
                *arguments,
            ).stdout
        )

    @classmethod
    def _planner_checkpoint(
        cls,
        control: Path,
        task_dir: Path,
        task_id: str,
        repo_1: Path,
        repo_2: Path,
    ) -> dict[str, object]:
        return cls._json(
            "checkpoint",
            control,
            task_dir,
            repo_1,
            repo_2,
            "--task-id",
            task_id,
            "--role",
            "planner-init",
            "--iteration",
            "0",
            "--index",
            "tasks/index.md",
        )

    def test_participant_external_evidence_is_manifested_and_repository_scoped(
        self,
    ) -> None:
        task_id = "TASK-V3-EXTERNAL"
        run_id = "RUN-V3-EXTERNAL"
        with git_v3_repository_fixture(task_id, run_id) as (
            control,
            repo_1,
            repo_2,
            _,
            task_dir,
            _,
            repo_1_base,
            repo_2_base,
        ):
            proposal_path = task_dir / "proposal.md"
            proposal_path.write_text(
                proposal_path.read_text(encoding="utf-8").replace(
                    "| `BUD-001` | `REPO-001` | CODE | `artifact/output.txt` |",
                    "| `BUD-001` | `REPO-001` | CODE | `artifact` |",
                    1,
                ),
                encoding="utf-8",
            )
            design_path = task_dir / "design.md"
            design_path.write_text(
                design_path.read_text(encoding="utf-8").replace(
                    "| `DEL-001` | SUBJECT | `REPO-001` | `artifact/output.txt` |",
                    "| `DEL-001` | SUBJECT | `REPO-001` | `artifact` |",
                    1,
                ),
                encoding="utf-8",
            )
            plan_path = task_dir / "plan.md"
            external_section = """## External Evidence Exclusions

| ID | Repository | Excluded path | Manifest path | Reason |
|---|---|---|---|---|
| `XEV-001` | `REPO-001` | `artifact/raw.pt` | `artifact/manifest.json` | Raw tensor bytes are retained externally and hash-bound by the manifest |

"""
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                .replace(
                    "| `DEL-001` | SUBJECT | `AC-001` | `REPO-001` | "
                    "`artifact/output.txt` |",
                    "| `DEL-001` | SUBJECT | `AC-001` | `REPO-001` | "
                    "`artifact` |",
                    1,
                )
                .replace(
                    "## Delivery Items\n",
                    external_section + "## Delivery Items\n",
                    1,
                ),
                encoding="utf-8",
            )
            proposal_text = proposal_path.read_text(encoding="utf-8")
            proposal_path.write_text(
                proposal_text.replace(
                    "| `BUD-001` | `REPO-001` | CODE | `artifact` | 3000 | "
                    "5000 | 12000 | 6000 | N/A | Initial task request |",
                    "| `BUD-001` | `REPO-001` | CODE | `artifact` | 3000 | "
                    "5000 | 12000 | 6000 | `artifact/manifest.json :: exempt` | "
                    "Initial task request |",
                    1,
                ),
                encoding="utf-8",
            )
            excluded_manifest = json.loads(
                self._command(
                    "validate",
                    control,
                    task_dir,
                    repo_1,
                    repo_2,
                    "--phase",
                    "planned",
                    expected=1,
                ).stdout
            )
            self.assertTrue(
                any(
                    "external-evidence manifest" in error
                    and "budget exclusion" in error
                    for error in excluded_manifest["errors"]
                ),
                excluded_manifest["errors"],
            )
            proposal_path.write_text(proposal_text, encoding="utf-8")
            self._planner_checkpoint(
                control,
                task_dir,
                task_id,
                repo_1,
                repo_2,
            )

            exclude = git_exclude_path(repo_1)
            exclude.write_text(
                exclude.read_text(encoding="utf-8") + "\nartifact/*.pt\n",
                encoding="utf-8",
            )
            raw_evidence = repo_1 / "artifact/raw.pt"
            raw_evidence.write_bytes(b"participant raw evidence")
            manifest = repo_1 / "artifact/manifest.json"
            manifest.write_text(
                '{"files":{"artifact/raw.pt":"fixture-sha256"}}\n',
                encoding="utf-8",
            )
            plan_path.write_text(
                implemented_plan_v3(plan_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            prepared = self._json(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-001",
                "--iteration",
                "1",
            )
            self.assertEqual(prepared["status"], "prepared")
            candidate_paths = set(
                git(
                    repo_1,
                    "ls-tree",
                    "-r",
                    "--name-only",
                    str(prepared["commit"]),
                ).splitlines()
            )
            self.assertIn("artifact/manifest.json", candidate_paths)
            self.assertIn("artifact/output.txt", candidate_paths)
            self.assertNotIn("artifact/raw.pt", candidate_paths)

            carried = self._json(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-002",
                "--iteration",
                "1",
            )
            self.assertEqual(carried["commit"], repo_2_base)
            seal = self._json(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
            )
            snapshot = self._json(
                "snapshot",
                control,
                task_dir,
                repo_1,
                repo_2,
            )
            self.assertEqual(snapshot["schema"], "rd-ralph-snapshot-v3")
            self.assertEqual(
                snapshot["external_evidence"],
                [
                    {
                        "repository": "REPO-001",
                        "excluded_path": "artifact/raw.pt",
                        "manifest_path": "artifact/manifest.json",
                    }
                ],
            )
            self.assertEqual(
                snapshot["participant_commits"]["REPO-001"],
                prepared["commit"],
            )
            self.assertEqual(
                snapshot["participant_commits"]["REPO-002"],
                repo_2_base,
            )
            self.assertEqual(seal["snapshot_sha256"], snapshot["snapshot_sha256"])
            verify_text = accepted_verify_v3(
                    run_id,
                    str(seal["commit"]),
                    f"ralph/{task_id}",
                    str(snapshot["snapshot_sha256"]),
                    str(seal["candidate_vector_sha256"]),
                    {
                        "REPO-001": (
                            repo_1_base,
                            str(prepared["commit"]),
                        ),
                        "REPO-002": (repo_2_base, repo_2_base),
                    },
                )
            verify_text = verify_text.replace(
                f"| REPO-002 | participant-two | `ralph/{task_id}` | "
                f"`{repo_2_base}` | `{repo_2_base}` | Yes |",
                f"| REPO-002 | participant-two | `ralph/{task_id}` | "
                f"`{repo_2_base}` | `{repo_2_base}` | No |",
                1,
            )
            (task_dir / "verify.md").write_text(
                verify_text,
                encoding="utf-8",
            )
            reviewed = self._json(
                "validate",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--phase",
                "reviewed",
            )
            self.assertTrue(reviewed["valid"], reviewed["errors"])
            reviewer = self._json(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--role",
                "reviewer",
                "--iteration",
                "1",
            )
            self.assertEqual(reviewer["role"], "Reviewer")
            raw_evidence.write_bytes(b"changed ignored participant evidence")
            changed_raw_snapshot = self._json(
                "snapshot",
                control,
                task_dir,
                repo_1,
                repo_2,
            )
            self.assertEqual(
                snapshot["snapshot_sha256"],
                changed_raw_snapshot["snapshot_sha256"],
            )
            for root in (control, repo_1, repo_2):
                self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_unchanged_participant_carries_base_into_control_seal(self) -> None:
        task_id = "TASK-V3-CARRY"
        run_id = "RUN-V3-CARRY"
        with git_v3_repository_fixture(task_id, run_id) as (
            control,
            repo_1,
            repo_2,
            _,
            task_dir,
            _,
            repo_1_base,
            repo_2_base,
        ):
            planned = self._json(
                "validate",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--phase",
                "planned",
            )
            self.assertTrue(planned["valid"], planned["errors"])
            snapshot = self._json(
                "snapshot",
                control,
                task_dir,
                repo_1,
                repo_2,
            )
            entries = {entry["path"]: entry for entry in snapshot["entries"]}
            first_path = "repo/REPO-001/artifact/output.txt"
            second_path = "repo/REPO-002/artifact/output.txt"
            self.assertEqual(snapshot["schema"], "rd-ralph-snapshot-v2")
            self.assertNotEqual(
                entries[first_path]["sha256"],
                entries[second_path]["sha256"],
            )
            canonical_snapshot = json.dumps(
                {
                    "schema": snapshot["schema"],
                    "entries": snapshot["entries"],
                    "participant_commits": {
                        "REPO-001": repo_1_base,
                        "REPO-002": repo_2_base,
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.assertEqual(
                hashlib.sha256(canonical_snapshot.encode()).hexdigest(),
                snapshot["snapshot_sha256"],
            )
            self.assertNotIn(str(repo_1), canonical_snapshot)
            self.assertNotIn(str(repo_2), canonical_snapshot)
            planner = self._planner_checkpoint(
                control,
                task_dir,
                task_id,
                repo_1,
                repo_2,
            )
            (repo_1 / "artifact/output.txt").write_text(
                "participant one candidate\n",
                encoding="utf-8",
            )
            plan_path = task_dir / "plan.md"
            plan_path.write_text(
                implemented_plan_v3(plan_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            prepared = self._json(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-001",
                "--iteration",
                "1",
            )
            carried = self._json(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-002",
                "--iteration",
                "1",
            )
            self.assertEqual(prepared["status"], "prepared")
            self.assertEqual(carried["status"], "unchanged")
            self.assertEqual(carried["commit"], repo_2_base)
            self.assertFalse(carried["committed"])

            seal = self._json(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
            )
            participant_commits = {
                "REPO-001": prepared["commit"],
                "REPO-002": repo_2_base,
            }
            self.assertEqual(seal["participant_commits"], participant_commits)
            self.assertEqual(seal["advanced_participants"], ["REPO-001"])
            full_vector = {
                "CONTROL": seal["commit"],
                **participant_commits,
            }
            expected_vector = hashlib.sha256(
                json.dumps(
                    full_vector,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(
                seal["candidate_vector_sha256"],
                expected_vector,
            )
            self.assertEqual(
                seal["manual_merge_order"][-1],
                {
                    "repository": "CONTROL",
                    "logical_identity": "CONTROL",
                    "merge_order": "LAST",
                    "commit": seal["commit"],
                },
            )
            self.assertEqual(git(control, "rev-parse", "HEAD"), seal["commit"])
            self.assertEqual(git(repo_1, "rev-parse", "HEAD"), prepared["commit"])
            self.assertEqual(git(repo_2, "rev-parse", "HEAD"), repo_2_base)
            self.assertEqual(
                git(repo_2, "rev-list", "--count", f"{repo_2_base}..HEAD"),
                "0",
            )
            repository_trailer = (
                "Ralph-Repositories: "
                + json.dumps(
                    participant_commits,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            seal_message = git(control, "show", "-s", "--format=%B", seal["commit"])
            self.assertIn(repository_trailer, seal_message)
            self.assertNotIn("Ralph-Vector:", seal_message)
            self.assertEqual(prepared["control_parent"], planner["commit"])
            for root in (control, repo_1, repo_2):
                self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_partial_failure_recovers_to_accepted_manual_handoff(self) -> None:
        task_id = "TASK-V3-RECOVERY"
        run_id = "RUN-V3-RECOVERY"
        with git_v3_repository_fixture(task_id, run_id) as (
            control,
            repo_1,
            repo_2,
            _,
            task_dir,
            control_base,
            repo_1_base,
            repo_2_base,
        ):
            planner = self._planner_checkpoint(
                control,
                task_dir,
                task_id,
                repo_1,
                repo_2,
            )
            first_output = repo_1 / "artifact/output.txt"
            second_output = repo_2 / "artifact/output.txt"
            first_output.write_text(
                "participant one recovered candidate\n",
                encoding="utf-8",
            )
            second_wip = "participant two preserved after hook failure\n"
            second_output.write_text(second_wip, encoding="utf-8")
            plan_path = task_dir / "plan.md"
            plan_path.write_text(
                implemented_plan_v3(plan_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            plan_wip = plan_path.read_bytes()

            hook = Path(
                git(repo_2, "rev-parse", "--git-path", "hooks/pre-commit")
            )
            if not hook.is_absolute():
                hook = repo_2 / hook
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text(
                "#!/bin/sh\nprintf 'injected participant failure\\n' >&2\nexit 1\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)

            first_prepared = self._json(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-001",
                "--iteration",
                "1",
            )
            failed_second = self._command(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-002",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn("injected participant failure", failed_second.stderr)
            self.assertEqual(
                git(repo_1, "rev-parse", "HEAD"),
                first_prepared["commit"],
            )
            self.assertEqual(git(repo_1, "status", "--porcelain"), "")
            self.assertEqual(git(repo_2, "rev-parse", "HEAD"), repo_2_base)
            self.assertEqual(
                git(repo_2, "diff", "--cached", "--name-only"),
                "",
            )
            self.assertEqual(second_output.read_text(encoding="utf-8"), second_wip)
            self.assertEqual(plan_path.read_bytes(), plan_wip)
            self.assertEqual(
                git(control, "rev-parse", "HEAD"),
                planner["commit"],
            )

            hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            hook.chmod(0o755)
            second_prepared = self._json(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-002",
                "--iteration",
                "1",
            )
            seal = self._json(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--role",
                "implementer",
                "--iteration",
                "1",
            )
            self.assertEqual(
                seal["participant_commits"],
                {
                    "REPO-001": first_prepared["commit"],
                    "REPO-002": second_prepared["commit"],
                },
            )
            self.assertEqual(
                seal["advanced_participants"],
                ["REPO-001", "REPO-002"],
            )
            self.assertEqual(
                seal["manual_merge_order"][-1]["repository"],
                "CONTROL",
            )
            participant_commits = {
                "REPO-001": first_prepared["commit"],
                "REPO-002": second_prepared["commit"],
            }
            candidate_vector = seal["candidate_vector_sha256"]
            (task_dir / "verify.md").write_text(
                accepted_verify_v3(
                    run_id,
                    seal["commit"],
                    f"ralph/{task_id}",
                    seal["snapshot_sha256"],
                    candidate_vector,
                    {
                        "REPO-001": (
                            repo_1_base,
                            participant_commits["REPO-001"],
                        ),
                        "REPO-002": (
                            repo_2_base,
                            participant_commits["REPO-002"],
                        ),
                    },
                ),
                encoding="utf-8",
            )
            reviewed_validation = self._json(
                "validate",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--phase",
                "reviewed",
            )
            self.assertTrue(
                reviewed_validation["valid"],
                reviewed_validation["errors"],
            )
            wrong_verify = control / "wrong-review" / "verify.md"
            wrong_verify.parent.mkdir()
            wrong_verify.write_text("not the task review\n", encoding="utf-8")
            rejected_reviewer = self._command(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--role",
                "reviewer",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn("outside its authority", rejected_reviewer.stderr)
            self.assertEqual(git(control, "rev-parse", "HEAD"), seal["commit"])
            self.assertEqual(git(control, "diff", "--cached", "--name-only"), "")
            wrong_verify.unlink()
            wrong_verify.parent.rmdir()
            reviewer = self._json(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--role",
                "reviewer",
                "--iteration",
                "1",
            )
            self.assertEqual(reviewer["participant_commits"], participant_commits)
            self.assertEqual(
                reviewer["candidate_vector_sha256"],
                candidate_vector,
            )
            canonical_map = json.dumps(
                participant_commits,
                sort_keys=True,
                separators=(",", ":"),
            )
            reviewer_message = git(
                control,
                "show",
                "-s",
                "--format=%B",
                reviewer["commit"],
            )
            self.assertIn(f"Ralph-Repositories: {canonical_map}", reviewer_message)
            self.assertIn(f"Ralph-Vector: {candidate_vector}", reviewer_message)

            archive = self._json(
                "archive",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--archive-root",
                "tasks/archive",
                "--index",
                "tasks/index.md",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
            )
            archived_task = Path(archive["archived_task_dir"])
            self.assertFalse(task_dir.exists())
            self.assertEqual(archive["participant_commits"], participant_commits)
            self.assertEqual(
                archive["candidate_vector_sha256"],
                candidate_vector,
            )
            self.assertEqual(
                archive["archive_authorization_sha256"],
                ARCHIVE_CONFIRMATION_SHA256,
            )
            index_text = (control / "tasks/index.md").read_text(encoding="utf-8")
            self.assertIn("REPO-001:artifact/output.txt", index_text)
            self.assertIn("REPO-002:artifact/output.txt", index_text)
            self.assertNotIn(str(repo_1), index_text)
            self.assertNotIn(str(repo_2), index_text)
            extra_closure_path = control / "closure-extra.txt"
            extra_closure_path.write_text("not part of archive\n", encoding="utf-8")
            rejected_closure = self._command(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--archive-task-dir",
                str(archived_task),
                "--index",
                "tasks/index.md",
                "--task-id",
                task_id,
                "--role",
                "closure",
                "--iteration",
                "1",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
                expected=2,
            )
            self.assertIn("outside its authority", rejected_closure.stderr)
            self.assertEqual(git(control, "rev-parse", "HEAD"), reviewer["commit"])
            self.assertEqual(git(control, "diff", "--cached", "--name-only"), "")
            extra_closure_path.unlink()
            closure = self._json(
                "checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--archive-task-dir",
                str(archived_task),
                "--index",
                "tasks/index.md",
                "--task-id",
                task_id,
                "--role",
                "closure",
                "--iteration",
                "1",
                "--authorization-token",
                ARCHIVE_CONFIRMATION,
            )
            closure_message = git(
                control,
                "show",
                "-s",
                "--format=%B",
                closure["commit"],
            )
            self.assertIn(f"Ralph-Repositories: {canonical_map}", closure_message)
            self.assertIn(f"Ralph-Vector: {candidate_vector}", closure_message)
            self.assertIn(
                f"Ralph-Authorization-SHA256: {ARCHIVE_CONFIRMATION_SHA256}",
                closure_message,
            )
            handoff = self._json(
                "handoff",
                control,
                archived_task,
                repo_1,
                repo_2,
                "--index",
                "tasks/index.md",
            )
            self.assertTrue(handoff["merge_ready"])
            self.assertEqual(handoff["merge_mode"], "manual")
            self.assertFalse(handoff["integration_mutated"])
            self.assertEqual(handoff["participant_commits"], participant_commits)
            self.assertEqual(handoff["candidate_vector_sha256"], candidate_vector)
            self.assertEqual(
                handoff["archive_authorization_sha256"],
                ARCHIVE_CONFIRMATION_SHA256,
            )
            self.assertEqual(
                [item["repository"] for item in handoff["repositories"]],
                ["REPO-001", "REPO-002", "CONTROL"],
            )
            self.assertEqual(
                [item["merge_order"] for item in handoff["repositories"]],
                [10, 20, "LAST"],
            )
            self.assertEqual(
                handoff["repositories"][-1]["candidate_commit"],
                closure["commit"],
            )
            self.assertEqual(
                handoff["repositories"][-1]["accepted_candidate_commit"],
                seal["commit"],
            )
            handoff_text = json.dumps(handoff, sort_keys=True)
            self.assertNotIn(str(repo_1), handoff_text)
            self.assertNotIn(str(repo_2), handoff_text)

            expected_heads = {
                control: closure["commit"],
                repo_1: first_prepared["commit"],
                repo_2: second_prepared["commit"],
            }
            for root, expected_head in expected_heads.items():
                self.assertEqual(git(root, "rev-parse", "HEAD"), expected_head)
                self.assertEqual(git(root, "status", "--porcelain"), "")
            integration_heads = {
                control.parent / "control-integration": control_base,
                repo_1.parent / "participant-one-integration": repo_1_base,
                repo_2.parent / "participant-two-integration": repo_2_base,
            }
            for root, expected_head in integration_heads.items():
                self.assertEqual(git(root, "rev-parse", "HEAD"), expected_head)
                self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_implementer_cannot_expand_repository_registry_or_scope(self) -> None:
        task_id = "TASK-V3-AUTHORITY"
        run_id = "RUN-V3-AUTHORITY"
        with git_v3_repository_fixture(task_id, run_id) as (
            control,
            repo_1,
            repo_2,
            extra_repo,
            task_dir,
            _,
            repo_1_base,
            repo_2_base,
        ):
            planner = self._planner_checkpoint(
                control,
                task_dir,
                task_id,
                repo_1,
                repo_2,
            )
            design_path = task_dir / "design.md"
            original_design = design_path.read_text(encoding="utf-8")
            extra_row = (
                f"| `REPO-003` | participant-three | `ralph/{task_id}` | "
                f"`{git(extra_repo, 'rev-parse', 'HEAD')}` | `artifact` | "
                "`AC-001` | 30 | Initial task request |"
            )
            expanded_registry = original_design.replace(
                "\n\n## Output Design",
                f"\n{extra_row}\n\n## Output Design",
                1,
            )
            design_path.write_text(expanded_registry, encoding="utf-8")
            registry_result = self._command(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-001",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn(
                "Implementer changed Repository Participants contract",
                registry_result.stderr,
            )
            self.assertEqual(
                design_path.read_text(encoding="utf-8"),
                expanded_registry,
            )

            design_path.write_text(
                original_design.replace(
                    "| `artifact` | `AC-001` | 10 |",
                    "| `artifact`; `outside` | `AC-001` | 10 |",
                    1,
                ),
                encoding="utf-8",
            )
            outside_path = repo_1 / "outside/output.txt"
            outside_path.write_text(
                "preserved unauthorized scope WIP\n",
                encoding="utf-8",
            )
            scope_result = self._command(
                "participant-checkpoint",
                control,
                task_dir,
                repo_1,
                repo_2,
                "--task-id",
                task_id,
                "--repo-id",
                "REPO-001",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn(
                "Implementer changed Repository Participants contract",
                scope_result.stderr,
            )
            self.assertEqual(
                outside_path.read_text(encoding="utf-8"),
                "preserved unauthorized scope WIP\n",
            )
            self.assertEqual(git(control, "rev-parse", "HEAD"), planner["commit"])
            self.assertEqual(git(repo_1, "rev-parse", "HEAD"), repo_1_base)
            self.assertEqual(git(repo_2, "rev-parse", "HEAD"), repo_2_base)
            for root in (control, repo_1, repo_2, extra_repo):
                self.assertEqual(
                    git(root, "diff", "--cached", "--name-only"),
                    "",
                )


class ProtocolV2GuardRegressionTest(unittest.TestCase):
    @staticmethod
    def _load_ralph_module():
        import importlib.util

        module_name = "ralph_loop_protocol_v2_regression"
        spec = importlib.util.spec_from_file_location(module_name, RALPH)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot import Ralph helper from {RALPH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _state_entry(
        role: str,
        iteration: int,
        *,
        commit: str,
        snapshot: str = "",
        candidate: str = "",
        verdict: str = "",
        control_action: str = "",
        pause_reasons: tuple[str, ...] = (),
        resume_role: str = "",
        authorization: str = "",
        references: tuple[str, ...] = (),
        pq_id: str = "",
        plan_decision: str = "",
    ) -> dict[str, object]:
        return {
            "commit": commit,
            "role": role,
            "iteration": iteration,
            "snapshot": snapshot,
            "candidate": candidate,
            "verdict": verdict,
            "reviewer": "",
            "control_action": control_action,
            "pause_reasons": list(pause_reasons),
            "resume_role": resume_role,
            "authorization": authorization,
            "pq_id": pq_id,
            "plan_decision": plan_decision,
            "child_task": "",
            "transferred_paths": [],
            "references": list(references),
        }

    def test_blocked_requires_explicit_external_pause_before_planner(self) -> None:
        task_id = "TASK-V2-BLOCKED"
        run_id = "RUN-V2-BLOCKED"
        with git_v2_task_fixture(task_id, run_id) as (
            worktree,
            task_dir,
            base,
        ):
            planner_checkpoint(worktree, task_dir, task_id)
            (worktree / "output.txt").write_text("done\n", encoding="utf-8")
            (task_dir / "plan.md").write_text(
                plan_v2(
                    run_id,
                    worktree,
                    f"ralph/{task_id}",
                    base,
                    implemented=True,
                ),
                encoding="utf-8",
            )
            candidate_data = json.loads(
                task_cli(
                    "checkpoint",
                    worktree,
                    task_dir,
                    task_id,
                    "--role",
                    "implementer",
                    "--iteration",
                    "1",
                ).stdout
            )
            candidate = candidate_data["commit"]
            snapshot = candidate_data["snapshot_sha256"]
            (task_dir / "verify.md").write_text(
                typed_verify(
                    run_id,
                    candidate,
                    f"ralph/{task_id}",
                    snapshot,
                    verdict="BLOCKED",
                    finding_type="EXTERNAL_BLOCKER",
                    action_class="UNBLOCK_EXTERNAL",
                    ac_result="BLOCKED",
                ),
                encoding="utf-8",
            )
            reviewer_data = json.loads(
                task_cli(
                    "checkpoint",
                    worktree,
                    task_dir,
                    task_id,
                    "--role",
                    "reviewer",
                    "--iteration",
                    "1",
                ).stdout
            )
            reviewer_head = reviewer_data["commit"]

            guard = json.loads(
                task_cli(
                    "guard",
                    worktree,
                    task_dir,
                    task_id,
                    "--role",
                    "planner-replan",
                    expected=1,
                ).stdout
            )
            self.assertEqual(guard["decision"], "PAUSED")
            self.assertEqual(guard["state"], "AWAITING_PAUSE")
            self.assertEqual(guard["reasons"], ["EXTERNAL"])
            self.assertEqual(guard["next_roles"], [])

            (task_dir / "plan.md").write_text(
                (task_dir / "plan.md").read_text(encoding="utf-8")
                + """

## Finding Disposition Ledger

| Iteration | Finding | Disposition |
|---|---|---|
| 2 | F-001 | DEFER |
""",
                encoding="utf-8",
            )
            direct_planner = task_cli(
                "checkpoint",
                worktree,
                task_dir,
                task_id,
                "--role",
                "planner-replan",
                "--iteration",
                "2",
                expected=2,
            )
            self.assertIn("state is AWAITING_PAUSE", direct_planner.stderr)
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), reviewer_head)

            paused = json.loads(
                task_cli(
                    "control",
                    worktree,
                    task_dir,
                    task_id,
                    "--action",
                    "pause",
                    "--reason",
                    "EXTERNAL",
                    "--reference",
                    "DEP-001 remains unavailable",
                    "--summary",
                    f"[{task_id}] pause for external evidence",
                ).stdout
            )
            self.assertEqual(paused["state"], "PAUSED")
            self.assertEqual(paused["pause_reasons"], ["EXTERNAL"])
            self.assertEqual(
                git(worktree, "rev-parse", f"{paused['commit']}^"),
                reviewer_head,
            )
            self.assertEqual(
                git(
                    worktree,
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    paused["commit"],
                ),
                "",
            )

    def test_control_empty_commit_preserves_dirty_tracked_and_untracked_wip(
        self,
    ) -> None:
        task_id = "TASK-V2-WIP"
        run_id = "RUN-V2-WIP"
        with git_v2_task_fixture(task_id, run_id) as (
            worktree,
            task_dir,
            _,
        ):
            planner_checkpoint(worktree, task_dir, task_id)
            previous_head = git(worktree, "rev-parse", "HEAD")
            previous_tree = git(worktree, "rev-parse", "HEAD^{tree}")
            plan_path = task_dir / "plan.md"
            scratch_path = worktree / "implementer-notes.txt"
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                + "\nImplementer observed an ambiguous plan step.\n",
                encoding="utf-8",
            )
            scratch_path.write_bytes(b"untracked implementation WIP\n")
            before_status = git(worktree, "status", "--porcelain=v1", "-uall")
            before_diff = git(worktree, "diff", "--binary")
            before_plan = plan_path.read_bytes()
            before_scratch = scratch_path.read_bytes()

            query = json.loads(
                task_cli(
                    "control",
                    worktree,
                    task_dir,
                    task_id,
                    "--action",
                    "plan-query",
                    "--pq-id",
                    "PQ-001",
                    "--reference",
                    "ITEM-001",
                    "--summary",
                    "Clarify the ambiguous implementation step",
                ).stdout
            )

            self.assertTrue(query["wip_preserved"])
            self.assertEqual(query["state"], "CONSULTING")
            self.assertNotEqual(query["commit"], previous_head)
            self.assertEqual(git(worktree, "rev-parse", "HEAD^"), previous_head)
            self.assertEqual(git(worktree, "rev-parse", "HEAD^{tree}"), previous_tree)
            self.assertEqual(
                git(
                    worktree,
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "HEAD",
                ),
                "",
            )
            self.assertEqual(
                git(worktree, "status", "--porcelain=v1", "-uall"),
                before_status,
            )
            self.assertEqual(git(worktree, "diff", "--binary"), before_diff)
            self.assertEqual(plan_path.read_bytes(), before_plan)
            self.assertEqual(scratch_path.read_bytes(), before_scratch)

    def test_guard_exact_untracked_boundary_is_read_only_and_budget_is_not_bypassable(
        self,
    ) -> None:
        task_id = "TASK-V2-BUDGET"
        run_id = "RUN-V2-BUDGET"
        with git_v2_task_fixture(task_id, run_id) as (
            worktree,
            task_dir,
            _,
        ):
            planner_checkpoint(worktree, task_dir, task_id)
            output = worktree / "output.txt"
            output.write_text("line\n" * 5000, encoding="utf-8")
            before_head = git(worktree, "rev-parse", "HEAD")
            before_tree = git(worktree, "rev-parse", "HEAD^{tree}")
            before_status = git(worktree, "status", "--porcelain=v1", "-uall")
            before_bytes = output.read_bytes()

            def budget_guard() -> dict[str, object]:
                return json.loads(
                    task_cli(
                        "guard",
                        worktree,
                        task_dir,
                        task_id,
                        "--role",
                        "implementer",
                        expected=1,
                    ).stdout
                )

            first = budget_guard()
            second = budget_guard()
            self.assertEqual(first, second)
            self.assertEqual(first["decision"], "PAUSED")
            self.assertIn("BUDGET", first["reasons"])
            self.assertEqual(first["budgets"][0]["iteration_added"], 5000)
            self.assertEqual(
                first["mechanism"],
                "git-diff-numstat-no-renames-plus-untracked-line-count",
            )
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), before_head)
            self.assertEqual(git(worktree, "rev-parse", "HEAD^{tree}"), before_tree)
            self.assertEqual(
                git(worktree, "status", "--porcelain=v1", "-uall"),
                before_status,
            )
            self.assertEqual(output.read_bytes(), before_bytes)

            task_cli(
                "control",
                worktree,
                task_dir,
                task_id,
                "--action",
                "pause",
                "--reason",
                "BUDGET",
                "--summary",
                "Pause at the approved line limit",
            )
            task_cli(
                "control",
                worktree,
                task_dir,
                task_id,
                "--action",
                "resume",
                "--reason",
                "BUDGET",
                "--resume-role",
                "implementer",
                "--authorization-token",
                "fixture-user-approval",
                "--reference",
                "scope must be contracted under the unchanged budget",
                "--summary",
                "Resume only to contract the candidate",
            )
            resumed_guard = budget_guard()
            self.assertEqual(resumed_guard["decision"], "PAUSED")
            self.assertIn("BUDGET", resumed_guard["reasons"])
            self.assertEqual(output.read_bytes(), before_bytes)

    def test_clarified_plan_query_returns_to_same_implementer_iteration(
        self,
    ) -> None:
        task_id = "TASK-V2-QUERY"
        run_id = "RUN-V2-QUERY"
        with git_v2_task_fixture(task_id, run_id) as (
            worktree,
            task_dir,
            _,
        ):
            planner_checkpoint(worktree, task_dir, task_id)
            task_cli(
                "control",
                worktree,
                task_dir,
                task_id,
                "--action",
                "plan-query",
                "--pq-id",
                "PQ-001",
                "--reference",
                "ITEM-001",
                "--summary",
                "Ask whether exact output includes a newline",
            )
            response = json.loads(
                task_cli(
                    "control",
                    worktree,
                    task_dir,
                    task_id,
                    "--action",
                    "plan-response",
                    "--pq-id",
                    "PQ-001",
                    "--decision",
                    "CLARIFIED",
                    "--summary",
                    "Use one trailing newline",
                ).stdout
            )
            self.assertEqual(response["iteration"], 1)
            self.assertEqual(response["state"], "ACTIVE")

            guard = json.loads(
                task_cli(
                    "guard",
                    worktree,
                    task_dir,
                    task_id,
                    "--role",
                    "implementer",
                ).stdout
            )
            self.assertEqual(
                guard["next_roles"],
                [{"iteration": 1, "role": "Implementer"}],
            )

            response_head = git(worktree, "rev-parse", "HEAD")
            snapshot = json.loads(
                cli(
                    "snapshot",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                ).stdout
            )["snapshot_sha256"]
            (task_dir / "verify.md").write_text(
                typed_verify(
                    run_id,
                    response_head,
                    f"ralph/{task_id}",
                    snapshot,
                    verdict="CHANGES_REQUIRED",
                    finding_type="SUBJECT_DEFECT",
                    action_class="SUBJECT_FIX",
                    ac_result="FAIL",
                ),
                encoding="utf-8",
            )
            premature_review = task_cli(
                "checkpoint",
                worktree,
                task_dir,
                task_id,
                "--role",
                "reviewer",
                "--iteration",
                "1",
                expected=2,
            )
            self.assertIn(
                "candidate trailer ralph-role is Control, expected Implementer",
                premature_review.stderr,
            )
            self.assertEqual(git(worktree, "rev-parse", "HEAD"), response_head)

    def test_open_plan_query_cannot_be_resumed_without_planner_response(
        self,
    ) -> None:
        module = self._load_ralph_module()
        state = module.initial_checkpoint_state()
        module.apply_checkpoint_entry(
            state,
            self._state_entry("Planner", 0, commit="planner-0"),
        )
        query = self._state_entry(
            "Control",
            1,
            commit="query-1",
            control_action="PLAN_QUERY",
            references=("ITEM-001",),
            pq_id="PQ-001",
        )
        module.apply_checkpoint_entry(state, query)
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                1,
                commit="response-1",
                control_action="PLAN_RESPONSE",
                pq_id="PQ-001",
                plan_decision="CLARIFIED",
            ),
        )
        query["commit"] = "query-2"
        query["pq_id"] = "PQ-002"
        module.apply_checkpoint_entry(state, query)
        self.assertEqual(state["status"], "PAUSED")
        self.assertEqual(state["pending_query"], "PQ-002")

        with self.assertRaisesRegex(module.RalphError, "cannot bypass an open plan query"):
            module.apply_checkpoint_entry(
                state,
                self._state_entry(
                    "Control",
                    1,
                    commit="resume-1",
                    control_action="RESUME",
                    pause_reasons=("PLAN_CONFLICT",),
                    resume_role="Implementer",
                    authorization="a" * 64,
                    references=("planner response still required",),
                ),
            )

        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                1,
                commit="response-2",
                control_action="PLAN_RESPONSE",
                pq_id="PQ-002",
                plan_decision="CLARIFIED",
            ),
        )
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                1,
                commit="resume-2",
                control_action="RESUME",
                pause_reasons=("PLAN_CONFLICT",),
                resume_role="Implementer",
                authorization="a" * 64,
                references=("PQ-002 clarified",),
            ),
        )
        self.assertEqual(state["expected"], {("Implementer", 1)})

    def test_replan_requires_a_disposition_for_each_open_finding(self) -> None:
        module = self._load_ralph_module()
        verify = typed_verify(
            "RUN-DISPOSITION",
            "0" * 40,
            "ralph/TASK-DISPOSITION",
            "0" * 64,
            verdict="NEEDS_REPLAN",
            finding_type="CONTRACT_GAP",
            action_class="REPLAN",
            ac_result="FAIL",
        )
        missing = module.replan_disposition_errors(
            "## Finding Disposition Ledger\n\n"
            "| Iteration | Finding | Disposition |\n"
            "|---|---|---|\n",
            verify,
            2,
        )
        self.assertIn(
            "planner replan has no disposition for open findings: F-001",
            missing,
        )
        complete = module.replan_disposition_errors(
            "## Finding Disposition Ledger\n\n"
            "| Iteration | Finding | Disposition |\n"
            "|---|---|---|\n"
            "| 2 | F-001 | FIX |\n",
            verify,
            2,
        )
        self.assertEqual(complete, [])

    def test_typed_finding_verdict_truth_table(self) -> None:
        task_id = "TASK-V2-FINDINGS"
        run_id = "RUN-V2-FINDINGS"
        with git_v2_task_fixture(task_id, run_id) as (
            worktree,
            task_dir,
            _,
        ):
            planner_checkpoint(worktree, task_dir, task_id)

            def validate_case(
                *,
                verdict: str,
                finding_type: str,
                action_class: str,
                expected: int,
            ) -> subprocess.CompletedProcess[str]:
                (task_dir / "verify.md").write_text(
                    typed_verify(
                        run_id,
                        "0" * 40,
                        f"ralph/{task_id}",
                        "0" * 64,
                        verdict=verdict,
                        finding_type=finding_type,
                        action_class=action_class,
                        ac_result="BLOCKED" if verdict == "BLOCKED" else "FAIL",
                    ),
                    encoding="utf-8",
                )
                return cli(
                    "validate",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                    "--phase",
                    "planned",
                    expected=expected,
                )

            invalid_external = json.loads(
                validate_case(
                    verdict="CHANGES_REQUIRED",
                    finding_type="EXTERNAL_BLOCKER",
                    action_class="UNBLOCK_EXTERNAL",
                    expected=1,
                ).stdout
            )
            self.assertIn(
                "ITER-001 has open EXTERNAL_BLOCKER findings, so Verdict must be BLOCKED",
                invalid_external["errors"],
            )
            valid_external = json.loads(
                validate_case(
                    verdict="BLOCKED",
                    finding_type="EXTERNAL_BLOCKER",
                    action_class="UNBLOCK_EXTERNAL",
                    expected=0,
                ).stdout
            )
            self.assertTrue(valid_external["valid"])

            invalid_replan = json.loads(
                validate_case(
                    verdict="NEEDS_REPLAN",
                    finding_type="SUBJECT_DEFECT",
                    action_class="SUBJECT_FIX",
                    expected=1,
                ).stdout
            )
            self.assertIn(
                "ITER-001 NEEDS_REPLAN requires an open CONTRACT_GAP with REPLAN",
                invalid_replan["errors"],
            )
            valid_replan = json.loads(
                validate_case(
                    verdict="NEEDS_REPLAN",
                    finding_type="CONTRACT_GAP",
                    action_class="REPLAN",
                    expected=0,
                ).stdout
            )
            self.assertTrue(valid_replan["valid"])

            invalid_open_close = (task_dir / "verify.md").read_text(
                encoding="utf-8"
            ).replace(
                "| F-001 | AC-001 | CONTRACT_GAP | P1 | Open | "
                "fixture evidence | REPLAN |",
                "| F-001 | AC-001 | CONTRACT_GAP | P1 | Open | "
                "fixture evidence | CLOSE |",
            )
            (task_dir / "verify.md").write_text(
                invalid_open_close,
                encoding="utf-8",
            )
            status_result = json.loads(
                cli(
                    "validate",
                    "--workspace-root",
                    str(worktree),
                    "--task-dir",
                    str(task_dir),
                    "--phase",
                    "planned",
                    expected=1,
                ).stdout
            )
            self.assertIn(
                "ITER-001 F-001 OPEN finding must not use CLOSE",
                status_result["errors"],
            )

    def test_resume_override_survives_until_the_next_reviewer(self) -> None:
        module = self._load_ralph_module()
        state = module.initial_checkpoint_state()
        snapshot_1 = "1" * 64
        snapshot_2 = "2" * 64
        planner_0 = self._state_entry(
            "Planner",
            0,
            commit="planner-0",
        )
        implementer_1 = self._state_entry(
            "Implementer",
            1,
            commit="implementer-1",
            snapshot=snapshot_1,
        )
        reviewer_1 = self._state_entry(
            "Reviewer",
            1,
            commit="reviewer-1",
            snapshot=snapshot_1,
            candidate="implementer-1",
            verdict="CHANGES_REQUIRED",
        )
        for entry in (planner_0, implementer_1, reviewer_1):
            module.apply_checkpoint_entry(state, entry)

        reasons = ("ASSURANCE", "REPLAN_STORM", "USER_CHECKPOINT")
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                1,
                commit="pause-1",
                control_action="PAUSE",
                pause_reasons=reasons,
            ),
        )
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                2,
                commit="resume-2",
                control_action="RESUME",
                pause_reasons=reasons,
                resume_role="Planner",
                authorization="a" * 64,
                references=("user approval",),
            ),
        )
        self.assertTrue(state["resume_grant"])
        self.assertEqual(state["resume_override"], set(reasons))

        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Planner",
                2,
                commit="planner-2",
            ),
        )
        self.assertTrue(state["resume_grant"])
        self.assertEqual(state["resume_override"], set(reasons))
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Implementer",
                2,
                commit="implementer-2",
                snapshot=snapshot_2,
            ),
        )
        self.assertTrue(state["resume_grant"])
        self.assertEqual(state["resume_override"], set(reasons))
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Reviewer",
                2,
                commit="reviewer-2",
                snapshot=snapshot_2,
                candidate="implementer-2",
                verdict="CHANGES_REQUIRED",
            ),
        )
        self.assertFalse(state["resume_grant"])
        self.assertEqual(state["resume_override"], set())

    def test_planner_only_pause_recovery_and_episode_reason_intersection(
        self,
    ) -> None:
        import copy

        module = self._load_ralph_module()

        def state_waiting_for_implementer() -> dict[str, object]:
            state = module.initial_checkpoint_state()
            module.apply_checkpoint_entry(
                state,
                self._state_entry(
                    "Planner",
                    0,
                    commit="planner-0",
                ),
            )
            return state

        for reason in ("CONFIGURATION_GAP", "SCHEMA_MIGRATION"):
            with self.subTest(reason=reason):
                state = state_waiting_for_implementer()
                module.apply_checkpoint_entry(
                    state,
                    self._state_entry(
                        "Control",
                        0,
                        commit=f"pause-{reason}",
                        control_action="PAUSE",
                        pause_reasons=(reason,),
                    ),
                )
                self.assertEqual(
                    state["suspended_expected"],
                    {("Implementer", 1), ("Planner", 1)},
                )
                module.apply_checkpoint_entry(
                    state,
                    self._state_entry(
                        "Control",
                        1,
                        commit=f"resume-{reason}",
                        control_action="RESUME",
                        pause_reasons=(reason,),
                        resume_role="Planner",
                        authorization="a" * 64,
                        references=("repair evidence",),
                    ),
                )
                self.assertEqual(state["status"], "ACTIVE")
                self.assertEqual(state["expected"], {("Planner", 1)})

        state = state_waiting_for_implementer()
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                0,
                commit="pause-configuration",
                control_action="PAUSE",
                pause_reasons=("CONFIGURATION_GAP",),
            ),
        )
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                0,
                commit="pause-budget",
                control_action="PAUSE",
                pause_reasons=("BUDGET",),
            ),
        )
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                1,
                commit="partial-resume",
                control_action="RESUME",
                pause_reasons=("CONFIGURATION_GAP",),
                resume_role="Planner",
                authorization="a" * 64,
                references=("configuration repaired",),
            ),
        )
        self.assertEqual(state["status"], "PAUSED")
        self.assertEqual(state["pause_reasons"], {"BUDGET"})
        self.assertEqual(
            state["pause_episode_reasons"],
            {"CONFIGURATION_GAP", "BUDGET"},
        )

        invalid_role_state = copy.deepcopy(state)
        with self.assertRaisesRegex(
            module.RalphError,
            "RESUME role Implementer is not legal for BUDGET, CONFIGURATION_GAP",
        ):
            module.apply_checkpoint_entry(
                invalid_role_state,
                self._state_entry(
                    "Control",
                    1,
                    commit="invalid-final-resume",
                    control_action="RESUME",
                    pause_reasons=("BUDGET",),
                    resume_role="Implementer",
                    authorization="a" * 64,
                    references=("budget disposition",),
                ),
            )
        module.apply_checkpoint_entry(
            state,
            self._state_entry(
                "Control",
                1,
                commit="valid-final-resume",
                control_action="RESUME",
                pause_reasons=("BUDGET",),
                resume_role="Planner",
                authorization="a" * 64,
                references=("budget disposition",),
            ),
        )
        self.assertEqual(state["status"], "ACTIVE")
        self.assertEqual(state["expected"], {("Planner", 1)})
        self.assertEqual(
            state["resume_override"],
            {"CONFIGURATION_GAP", "BUDGET"},
        )


class ArchiveTransactionRegressionTest(unittest.TestCase):
    @staticmethod
    def _load_ralph_module():
        import importlib.util

        module_name = "ralph_loop_archive_regression"
        spec = importlib.util.spec_from_file_location(module_name, RALPH)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot import Ralph helper from {RALPH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _archive_fixture(
        self,
        root: Path,
        module,
        *,
        task_id: str,
        explicit_artifacts: list[str] | None = None,
    ):
        import argparse

        root = root.resolve(strict=True)
        explicit_artifacts = explicit_artifacts or []
        tasks_root = root / "tasks"
        task_dir = tasks_root / task_id
        task_dir.mkdir(parents=True)
        output = root / "output.txt"
        output.write_text("done\n", encoding="utf-8")
        for relative in explicit_artifacts:
            artifact = root / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("retained\n", encoding="utf-8")

        (task_dir / "proposal.md").write_text(
            proposal(task_id, f"RUN-{task_id}"), encoding="utf-8"
        )
        (task_dir / "design.md").write_text(design(task_id), encoding="utf-8")
        (task_dir / "plan.md").write_text(
            plan(
                f"RUN-{task_id}",
                root,
                "non-git",
                "N/A",
                implemented=True,
            ),
            encoding="utf-8",
        )
        (task_dir / "verify.md").write_text(
            empty_verify(f"RUN-{task_id}"), encoding="utf-8"
        )
        snapshot = module.snapshot_data(task_dir, root, explicit_artifacts)
        (task_dir / "verify.md").write_text(
            accepted_verify(
                f"RUN-{task_id}",
                "N/A",
                "N/A",
                str(snapshot["snapshot_sha256"]),
            ),
            encoding="utf-8",
        )

        index = tasks_root / "index.md"
        index_text = (
            "# R&D Ralph Tasks\n\n"
            "## Active\n\n"
            "| Task | State | Goal |\n"
            "|---|---|---|\n"
            f"{module.ACTIVE_START}\n"
            f"| [`{task_id}`]({task_id}/proposal.md) | In Review | fixture |\n"
            f"{module.ACTIVE_END}\n\n"
            "## Archived\n\n"
            "| Task | Deliverables | Verdict | Iterations | Accepted snapshot | "
            "Accepted candidate |\n"
            "|---|---|---|---|---|---|\n"
            f"{module.ARCHIVE_START}\n"
            f"{module.ARCHIVE_END}\n"
        )
        index.write_text(index_text, encoding="utf-8")
        destination = tasks_root / "archive" / task_id
        args = argparse.Namespace(
            workspace_root=str(root),
            task_dir=str(task_dir),
            archive_root="tasks/archive",
            index="tasks/index.md",
            artifact=explicit_artifacts,
            authorization_token=ARCHIVE_CONFIRMATION,
        )
        return args, task_dir, destination, index, index_text

    def test_archive_rolls_back_keyboard_interrupt_immediately_after_move(self) -> None:
        from unittest import mock

        module = self._load_ralph_module()
        with tempfile.TemporaryDirectory(prefix="ralph-archive-move-rollback-") as raw:
            root = Path(raw)
            args, task_dir, destination, index, original_index = self._archive_fixture(
                root,
                module,
                task_id="TASK-ROLLBACK-MOVE",
            )
            real_replace = module.os.replace
            calls = 0

            def interrupt_after_first_replace(source, target):
                nonlocal calls
                calls += 1
                real_replace(source, target)
                if calls == 1:
                    raise KeyboardInterrupt

            with mock.patch.object(
                module.os,
                "replace",
                side_effect=interrupt_after_first_replace,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    module.archive_command(args)

            self.assertEqual(calls, 2)
            self.assertTrue(task_dir.is_dir())
            self.assertFalse(destination.exists())
            self.assertEqual(index.read_text(encoding="utf-8"), original_index)
            self.assertTrue((root / "output.txt").is_file())
            self.assertEqual(
                sorted(path.name for path in task_dir.iterdir()),
                sorted(module.FOUR_PACK),
            )

    def test_archive_rolls_back_fault_after_index_write(self) -> None:
        from unittest import mock

        module = self._load_ralph_module()
        with tempfile.TemporaryDirectory(prefix="ralph-archive-index-rollback-") as raw:
            root = Path(raw)
            args, task_dir, destination, index, original_index = self._archive_fixture(
                root,
                module,
                task_id="TASK-ROLLBACK-INDEX",
            )
            real_validate = module.validate_task
            observed_post_write_state = False

            def fail_post_archive_validation(
                checked_task_dir,
                workspace_root,
                phase,
                checked_index,
                explicit_artifacts,
            ):
                nonlocal observed_post_write_state
                if phase == "archived":
                    observed_post_write_state = True
                    self.assertTrue(destination.is_dir())
                    self.assertFalse(task_dir.exists())
                    self.assertNotEqual(
                        index.read_text(encoding="utf-8"),
                        original_index,
                    )
                    raise RuntimeError("injected post-index-write fault")
                return real_validate(
                    checked_task_dir,
                    workspace_root,
                    phase,
                    checked_index,
                    explicit_artifacts,
                )

            with mock.patch.object(
                module,
                "validate_task",
                side_effect=fail_post_archive_validation,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected post-index-write fault",
                ):
                    module.archive_command(args)

            self.assertTrue(observed_post_write_state)
            self.assertTrue(task_dir.is_dir())
            self.assertFalse(destination.exists())
            self.assertEqual(index.read_text(encoding="utf-8"), original_index)
            self.assertTrue((root / "output.txt").is_file())
            self.assertEqual(
                sorted(path.name for path in task_dir.iterdir()),
                sorted(module.FOUR_PACK),
            )

    def test_archive_index_escapes_artifact_link_spaces_parentheses_and_pipe(
        self,
    ) -> None:
        import contextlib
        import io

        module = self._load_ralph_module()
        with tempfile.TemporaryDirectory(prefix="ralph-archive-markdown-link-") as raw:
            root = Path(raw)
            special_artifact = "retained folder/report (draft)|final.txt"
            args, task_dir, destination, index, _ = self._archive_fixture(
                root,
                module,
                task_id="TASK-MARKDOWN-LINK",
                explicit_artifacts=[special_artifact],
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.archive_command(args), 0)

            self.assertFalse(task_dir.exists())
            self.assertTrue(destination.is_dir())
            archive_index = index.read_text(encoding="utf-8")
            expected_link = (
                "[retained folder/report (draft)\\|final.txt]"
                "(../retained%20folder/report%20%28draft%29%7Cfinal.txt)"
            )
            self.assertIn(expected_link, archive_index)
            self.assertEqual(archive_index.count(expected_link), 1)


if __name__ == "__main__":
    unittest.main()
