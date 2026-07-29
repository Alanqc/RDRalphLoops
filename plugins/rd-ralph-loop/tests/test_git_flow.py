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
