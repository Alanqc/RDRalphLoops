from __future__ import annotations

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
                ).stdout
            )
            archived_task = Path(archive["archived_task_dir"])
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
                ).stdout
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
