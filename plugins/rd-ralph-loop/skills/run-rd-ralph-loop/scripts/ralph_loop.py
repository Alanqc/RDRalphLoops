#!/usr/bin/env python3
"""Lifecycle helper for the run-rd-ralph-loop skill."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import quote


FOUR_PACK = ("proposal.md", "design.md", "plan.md", "verify.md")
SNAPSHOT_DOCS = ("proposal.md", "design.md", "plan.md")
VERDICTS = {"ACCEPTED", "CHANGES_REQUIRED", "NEEDS_REPLAN", "BLOCKED"}
REVIEW_PLACEHOLDERS = {
    "reviewer identity",
    "repo, cwd, branch/commit, dependencies",
    "full candidate commit sha or n/a for non-git",
    "candidate branch or n/a for non-git",
    "independently observed evidence",
    "exact command or manual review step",
    "concise output",
    "one evidence-backed conclusion and next action.",
}
ACTIVE_START = "<!-- ralph-loop:active:start -->"
ACTIVE_END = "<!-- ralph-loop:active:end -->"
ARCHIVE_START = "<!-- ralph-loop:archive:start -->"
ARCHIVE_END = "<!-- ralph-loop:archive:end -->"
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_ROOT = SKILL_ROOT / "assets" / "templates"


class RalphError(RuntimeError):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RalphError(f"cannot read UTF-8 file {path}: {exc}") from exc


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if text and not text.endswith("\n"):
        text += "\n"
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (Exception, KeyboardInterrupt):
        temporary.unlink(missing_ok=True)
        raise


def resolve_existing(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RalphError(f"{label} does not exist: {path}") from exc
    return resolved


def ensure_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RalphError(f"{label} escapes workspace root: {resolved}") from exc
    return resolved


def workspace_path(raw: str, workspace_root: Path, label: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return ensure_within(candidate, workspace_root, label)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def run_git(
    workspace_root: Path,
    arguments: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RalphError(f"cannot run git: {exc}") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RalphError(f"git {' '.join(arguments)} failed: {detail}")
    return result


def run_git_bytes(
    workspace_root: Path,
    arguments: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise RalphError(f"cannot run git: {exc}") from exc
    if check and result.returncode != 0:
        detail = (
            result.stderr.decode("utf-8", errors="replace").strip()
            or result.stdout.decode("utf-8", errors="replace").strip()
            or "unknown git error"
        )
        raise RalphError(f"git {' '.join(arguments)} failed: {detail}")
    return result


def resolve_git_path(raw: str, workspace_root: Path) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return candidate.resolve(strict=False)


def git_operations_in_progress(workspace_root: Path) -> list[str]:
    markers = (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    )
    active: list[str] = []
    for marker in markers:
        raw = run_git(
            workspace_root,
            ["rev-parse", "--git-path", marker],
        ).stdout.strip()
        if resolve_git_path(raw, workspace_root).exists():
            active.append(marker)
    return active


def git_context_data(
    workspace_root: Path,
    *,
    require_git: bool = False,
) -> dict[str, object] | None:
    probe = run_git(
        workspace_root,
        ["rev-parse", "--show-toplevel"],
        check=False,
    )
    if probe.returncode != 0:
        if require_git:
            raise RalphError(f"workspace is not a Git worktree: {workspace_root}")
        return None

    top_level = Path(probe.stdout.strip()).resolve(strict=True)
    if top_level != workspace_root.resolve(strict=True):
        raise RalphError(
            f"workspace root must be the Git worktree top level: {top_level}"
        )

    git_dir = resolve_git_path(
        run_git(workspace_root, ["rev-parse", "--git-dir"]).stdout.strip(),
        workspace_root,
    )
    common_dir = resolve_git_path(
        run_git(workspace_root, ["rev-parse", "--git-common-dir"]).stdout.strip(),
        workspace_root,
    )
    branch_result = run_git(
        workspace_root,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    head = run_git(workspace_root, ["rev-parse", "HEAD"]).stdout.strip().lower()
    status = run_git(
        workspace_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    ).stdout
    operations = git_operations_in_progress(workspace_root)
    return {
        "vcs": "git",
        "workspace_root": str(workspace_root),
        "git_dir": str(git_dir),
        "common_dir": str(common_dir),
        "branch": branch,
        "head": head,
        "linked_worktree": git_dir != common_dir,
        "clean": not bool(status) and not operations,
        "operations_in_progress": operations,
    }


def validate_task_id(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*", value):
        raise RalphError(
            "task ID must be hyphen-delimited letters/digits and start with a letter"
        )


def expected_branch(task_id: str) -> str:
    validate_task_id(task_id)
    return f"ralph/{task_id}"


def require_loop_git_context(
    workspace_root: Path,
    task_id: str,
    *,
    require_linked: bool,
) -> dict[str, object]:
    context = git_context_data(workspace_root, require_git=True)
    assert context is not None
    branch = str(context["branch"])
    if not branch:
        raise RalphError("loop worktree must not use a detached HEAD")
    wanted = expected_branch(task_id)
    if branch != wanted:
        raise RalphError(f"loop branch must be {wanted}, found {branch}")
    if require_linked and not bool(context["linked_worktree"]):
        raise RalphError(
            "loop must use a linked worktree; pass --allow-primary-worktree only "
            "for an explicitly serialized single-loop checkout"
        )
    return context


def registered_worktree_paths(repo_root: Path) -> list[Path]:
    result = run_git(
        repo_root,
        ["worktree", "list", "--porcelain", "-z"],
        check=False,
    )
    if result.returncode == 0:
        values = result.stdout.split("\0")
    else:
        values = run_git(
            repo_root,
            ["worktree", "list", "--porcelain"],
        ).stdout.splitlines()
    paths: list[Path] = []
    for value in values:
        if value.startswith("worktree "):
            paths.append(Path(value[len("worktree ") :]).resolve(strict=False))
    if not paths:
        raise RalphError("Git reported no registered worktrees")
    return paths


def git_relative(path: Path, workspace_root: Path, label: str) -> str:
    resolved = ensure_within(path, workspace_root, label)
    relative = resolved.relative_to(workspace_root).as_posix()
    return relative or "."


def nul_paths(output: str) -> set[str]:
    return {value for value in output.split("\0") if value}


def git_changed_paths(workspace_root: Path) -> set[str]:
    unstaged = nul_paths(
        run_git(
            workspace_root,
            ["diff", "--no-renames", "--name-only", "-z"],
        ).stdout
    )
    staged = nul_paths(
        run_git(
            workspace_root,
            ["diff", "--cached", "--no-renames", "--name-only", "-z"],
        ).stdout
    )
    untracked = nul_paths(
        run_git(
            workspace_root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
        ).stdout
    )
    return unstaged | staged | untracked


def git_staged_paths(workspace_root: Path) -> set[str]:
    return nul_paths(
        run_git(
            workspace_root,
            ["diff", "--cached", "--no-renames", "--name-only", "-z"],
        ).stdout
    )


def path_in_scopes(path: str, scopes: Iterable[str]) -> bool:
    normalized = Path(path).as_posix().strip("/")
    for scope in scopes:
        candidate = Path(scope).as_posix().strip("/")
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def literal_pathspecs(paths: Iterable[str]) -> list[str]:
    return [f":(literal){path}" for path in paths]


def commit_exists(workspace_root: Path, commit: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        return False
    return (
        run_git(
            workspace_root,
            ["cat-file", "-e", f"{commit}^{{commit}}"],
            check=False,
        ).returncode
        == 0
    )


def is_ancestor(workspace_root: Path, ancestor: str, descendant: str) -> bool:
    return (
        run_git(
            workspace_root,
            ["merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
        ).returncode
        == 0
    )


def commit_trailers(workspace_root: Path, commit: str) -> dict[str, str]:
    message = run_git(
        workspace_root,
        ["show", "-s", "--format=%B", commit],
    ).stdout
    trailers: dict[str, str] = {}
    for line in message.splitlines():
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9-]*):\s*(.+)", line.strip())
        if match:
            trailers[match.group(1).casefold()] = match.group(2).strip()
    return trailers


def commit_parents(workspace_root: Path, commit: str) -> list[str]:
    line = run_git(
        workspace_root,
        ["rev-list", "--parents", "-n", "1", commit],
    ).stdout.strip()
    values = line.split()
    if not values or values[0].lower() != commit.lower():
        raise RalphError(f"cannot resolve commit parents for {commit}")
    return [value.lower() for value in values[1:]]


def commit_changed_paths(workspace_root: Path, commit: str) -> set[str]:
    return nul_paths(
        run_git(
            workspace_root,
            [
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "--no-renames",
                "-r",
                "-z",
                commit,
            ],
        ).stdout
    )


def assert_commit_contains_files(
    workspace_root: Path,
    commit: str,
    paths: Iterable[str],
    *,
    label: str,
) -> None:
    required = set(paths)
    tracked = nul_paths(
        run_git(
            workspace_root,
            [
                "ls-tree",
                "-r",
                "--name-only",
                "-z",
                commit,
                "--",
                *literal_pathspecs(required),
            ],
        ).stdout
    )
    missing = sorted(required - tracked)
    if missing:
        raise RalphError(
            f"{label} are missing from commit {commit}: "
            + ", ".join(missing)
        )


def assert_paths_not_ignored(
    workspace_root: Path,
    paths: Iterable[str],
    *,
    label: str,
) -> None:
    ignored: list[str] = []
    for path in sorted(set(paths)):
        result = run_git(
            workspace_root,
            [
                "check-ignore",
                "--quiet",
                "--no-index",
                "--",
                path,
            ],
            check=False,
        )
        if result.returncode == 0:
            ignored.append(path)
        elif result.returncode != 1:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RalphError(
                f"cannot evaluate Git ignore rules for {path}: "
                f"{detail or 'unknown git error'}"
            )
    if ignored:
        raise RalphError(
            f"{label} are ignored and cannot be preserved in the Closure commit: "
            + ", ".join(ignored)
        )


def assert_files_trackable_for_checkpoint(
    workspace_root: Path,
    paths: Iterable[str],
    changed_paths: set[str],
    *,
    label: str,
) -> None:
    required = set(paths)
    tracked = nul_paths(
        run_git(
            workspace_root,
            [
                "ls-files",
                "--cached",
                "-z",
                "--",
                *literal_pathspecs(required),
            ],
        ).stdout
    )
    unavailable = sorted(required - tracked - changed_paths)
    if unavailable:
        raise RalphError(
            f"{label} are ignored or otherwise unavailable to the checkpoint: "
            + ", ".join(unavailable)
        )


def task_commit_chain(
    workspace_root: Path,
    task_id: str,
    base_commit: str,
    head_commit: str,
    *,
    current_plan: str | None = None,
    require_initialized: bool = False,
) -> list[dict[str, object]]:
    claimed_base = base_commit.lower()
    head = head_commit.lower()
    if not commit_exists(workspace_root, claimed_base):
        raise RalphError("plan Base commit is missing or invalid")
    if not commit_exists(workspace_root, head):
        raise RalphError("Ralph checkpoint HEAD is missing or invalid")

    head_trailers = commit_trailers(workspace_root, head)
    if (
        head == claimed_base
        and head_trailers.get("ralph-task", "") != task_id
    ):
        if require_initialized:
            raise RalphError(
                "Ralph checkpoint history has no Planner iteration 0 commit"
            )
        if current_plan is not None:
            current_base = summary_field(current_plan, "Base commit").lower()
            if current_base != claimed_base:
                raise RalphError(
                    f"plan Base commit changed from {claimed_base} to "
                    f"{current_base or 'missing'}"
                )
        return []

    newest_first: list[str] = []
    cursor = head
    authoritative_base = ""
    while True:
        trailers = commit_trailers(workspace_root, cursor)
        commit_task = trailers.get("ralph-task", "")
        role = trailers.get("ralph-role", "")
        raw_iteration = trailers.get("ralph-iteration", "")
        if commit_task != task_id:
            raise RalphError(
                f"commit {cursor} is not a checkpoint for {task_id}; "
                f"Ralph-Task is {commit_task or 'missing'}"
            )
        parents = commit_parents(workspace_root, cursor)
        if len(parents) != 1:
            raise RalphError(
                "Ralph checkpoint history must be linear with exactly one parent "
                f"per task commit; {cursor} has {len(parents)} parents"
            )
        newest_first.append(cursor)
        if role == "Planner" and raw_iteration == "0":
            authoritative_base = parents[0]
            break
        cursor = parents[0]
        if len(newest_first) > 10000:
            raise RalphError("Ralph checkpoint history exceeds the safety limit")
    commits = list(reversed(newest_first))
    if claimed_base != authoritative_base:
        raise RalphError(
            f"plan Base commit changed from authoritative {authoritative_base} to "
            f"{claimed_base or 'missing'}"
        )

    if current_plan is not None:
        current_base = summary_field(current_plan, "Base commit").lower()
        if current_base != authoritative_base:
            raise RalphError(
                f"plan Base commit changed from authoritative {authoritative_base} to "
                f"{current_base or 'missing'}"
            )

    chain: list[dict[str, object]] = []
    allowed_roles = {"Planner", "Implementer", "Reviewer", "Closure"}
    for commit in commits:
        trailers = commit_trailers(workspace_root, commit)
        commit_task = trailers.get("ralph-task", "")
        role = trailers.get("ralph-role", "")
        raw_iteration = trailers.get("ralph-iteration", "")
        if commit_task != task_id:
            raise RalphError(
                f"commit {commit} is not a checkpoint for {task_id}; "
                f"Ralph-Task is {commit_task or 'missing'}"
            )
        if role not in allowed_roles:
            raise RalphError(
                f"commit {commit} has invalid or missing Ralph-Role: "
                f"{role or 'missing'}"
            )
        if not re.fullmatch(r"0|[1-9][0-9]*", raw_iteration):
            raise RalphError(
                f"commit {commit} has invalid or missing Ralph-Iteration"
            )
        iteration = int(raw_iteration)
        snapshot = trailers.get("ralph-snapshot", "").lower()
        candidate = trailers.get("ralph-candidate", "").lower()
        verdict = trailers.get("ralph-verdict", "").upper()
        reviewer = trailers.get("ralph-reviewer", "").lower()
        if role in {"Implementer", "Reviewer", "Closure"} and not re.fullmatch(
            r"[0-9a-f]{64}", snapshot
        ):
            raise RalphError(
                f"{role} checkpoint {commit} has no full Ralph-Snapshot"
            )
        if role in {"Reviewer", "Closure"}:
            if not commit_exists(workspace_root, candidate):
                raise RalphError(
                    f"{role} checkpoint {commit} has no valid Ralph-Candidate"
                )
            if verdict not in VERDICTS:
                raise RalphError(
                    f"{role} checkpoint {commit} has invalid Ralph-Verdict: "
                    f"{verdict or 'missing'}"
                )
        if role == "Closure" and not commit_exists(workspace_root, reviewer):
            raise RalphError(
                f"Closure checkpoint {commit} has no valid Ralph-Reviewer"
            )
        chain.append(
            {
                "commit": commit,
                "role": role,
                "iteration": iteration,
                "snapshot": snapshot,
                "candidate": candidate,
                "verdict": verdict,
                "reviewer": reviewer,
            }
        )

    first = chain[0]
    if first["role"] != "Planner" or first["iteration"] != 0:
        raise RalphError(
            "the first commit after Base commit must be Planner iteration 0"
        )
    planner_paths = commit_changed_paths(workspace_root, str(first["commit"]))
    initial_plans = [
        path for path in planner_paths if Path(path).name == "plan.md"
    ]
    if len(initial_plans) != 1:
        raise RalphError(
            "Planner iteration 0 must commit exactly one plan.md path"
        )
    initial_plan = git_file_text(
        workspace_root,
        str(first["commit"]),
        initial_plans[0],
    )
    initial_base = summary_field(initial_plan, "Base commit").lower()
    if initial_base != authoritative_base:
        raise RalphError(
            f"initial Planner plan Base commit is {initial_base or 'missing'}, "
            f"expected {authoritative_base}"
        )

    for previous, current in zip(chain, chain[1:]):
        previous_role = str(previous["role"])
        current_role = str(current["role"])
        previous_iteration = int(previous["iteration"])
        current_iteration = int(current["iteration"])
        allowed: set[tuple[str, int]]
        if previous_role == "Planner":
            allowed = {
                (
                    "Implementer",
                    1 if previous_iteration == 0 else previous_iteration,
                )
            }
        elif previous_role == "Implementer":
            allowed = {("Reviewer", previous_iteration)}
        elif previous_role == "Reviewer":
            if previous["verdict"] == "ACCEPTED":
                allowed = {("Closure", previous_iteration)}
            elif previous["verdict"] in {"NEEDS_REPLAN", "BLOCKED"}:
                allowed = {("Planner", previous_iteration + 1)}
            else:
                allowed = {
                    ("Planner", previous_iteration + 1),
                    ("Implementer", previous_iteration + 1),
                }
        else:
            allowed = set()
        if (current_role, current_iteration) not in allowed:
            expected = ", ".join(
                f"{role} iteration {iteration}"
                for role, iteration in sorted(allowed)
            ) or "no further checkpoint"
            raise RalphError(
                f"invalid Ralph checkpoint sequence after {previous_role} "
                f"iteration {previous_iteration}: found {current_role} iteration "
                f"{current_iteration}; expected {expected}"
            )
        if current_role == "Reviewer":
            if current["candidate"] != previous["commit"]:
                raise RalphError(
                    f"Reviewer checkpoint {current['commit']} is not bound to its "
                    "immediately preceding Implementer"
                )
            if current["snapshot"] != previous["snapshot"]:
                raise RalphError(
                    f"Reviewer checkpoint {current['commit']} snapshot differs from "
                    "its Implementer candidate"
                )
        if current_role == "Closure":
            if current["reviewer"] != previous["commit"]:
                raise RalphError(
                    f"Closure checkpoint {current['commit']} is not bound to its "
                    "immediately preceding Reviewer"
                )
            if (
                current["candidate"] != previous["candidate"]
                or current["snapshot"] != previous["snapshot"]
                or current["verdict"] != previous["verdict"]
            ):
                raise RalphError(
                    f"Closure checkpoint {current['commit']} does not preserve the "
                    "Reviewer acceptance binding"
                )
    return chain


def assert_next_checkpoint(
    chain: list[dict[str, object]],
    role: str,
    iteration: int,
) -> None:
    role_label = checkpoint_role_label(role)
    if not chain:
        expected = ("Planner", 0)
    else:
        previous = chain[-1]
        previous_role = str(previous["role"])
        previous_iteration = int(previous["iteration"])
        if previous_role == "Planner":
            expected = (
                "Implementer",
                1 if previous_iteration == 0 else previous_iteration,
            )
        elif previous_role == "Implementer":
            expected = ("Reviewer", previous_iteration)
        elif previous_role == "Reviewer":
            if previous["verdict"] == "ACCEPTED":
                expected = ("Closure", previous_iteration)
            elif previous["verdict"] in {"NEEDS_REPLAN", "BLOCKED"}:
                expected = ("Planner", previous_iteration + 1)
            elif role_label in {"Planner", "Implementer"}:
                expected = (role_label, previous_iteration + 1)
            else:
                expected = ("Implementer", previous_iteration + 1)
        else:
            raise RalphError("Closure is terminal; no further checkpoint is allowed")
    if (role_label, iteration) != expected:
        raise RalphError(
            f"next Ralph checkpoint must be {expected[0]} iteration {expected[1]}, "
            f"not {role_label} iteration {iteration}"
        )


def assert_reviewer_checkpoint(
    workspace_root: Path,
    task_id: str,
    review: dict[str, object],
    snapshot_sha256: str,
    *,
    review_commit: str | None = None,
    current_verify: Path | None = None,
) -> str:
    commit = (
        review_commit.lower()
        if review_commit is not None
        else run_git(workspace_root, ["rev-parse", "HEAD"]).stdout.strip().lower()
    )
    if not commit_exists(workspace_root, commit):
        raise RalphError("Reviewer checkpoint commit is missing")
    candidate = str(review["candidate_commit"]).lower()
    parents = commit_parents(workspace_root, commit)
    if parents != [candidate]:
        raise RalphError(
            "Reviewer checkpoint must have the accepted candidate as its only parent"
        )
    trailers = commit_trailers(workspace_root, commit)
    required = {
        "ralph-task": task_id,
        "ralph-role": "Reviewer",
        "ralph-iteration": str(review["number"]),
        "ralph-snapshot": snapshot_sha256,
        "ralph-candidate": candidate,
        "ralph-verdict": str(review["verdict"]),
    }
    for key, expected in required.items():
        actual = trailers.get(key, "")
        if actual.casefold() != expected.casefold():
            raise RalphError(
                f"Reviewer checkpoint trailer {key} is "
                f"{actual or 'missing'}, expected {expected}"
            )
    changed = commit_changed_paths(workspace_root, commit)
    if len(changed) != 1:
        raise RalphError("Reviewer checkpoint must change exactly one verify.md path")
    verify_path = next(iter(changed))
    if Path(verify_path).name != "verify.md":
        raise RalphError("Reviewer checkpoint changed a path other than verify.md")
    if current_verify is not None:
        committed_verify = git_file_text(workspace_root, commit, verify_path)
        if committed_verify != read_text(current_verify):
            raise RalphError(
                "current verify.md differs from the immutable Reviewer checkpoint"
            )
    return commit


def git_file_text(workspace_root: Path, commit: str, path: str) -> str:
    result = run_git(
        workspace_root,
        ["show", f"{commit}:{path}"],
        check=False,
    )
    if result.returncode != 0:
        raise RalphError(f"candidate commit does not contain {path}")
    return result.stdout


def snapshot_git_paths(
    task_dir: Path,
    workspace_root: Path,
    explicit_artifacts: Iterable[str],
) -> list[str]:
    paths = [
        git_relative(task_dir / name, workspace_root, f"snapshot {name}")
        for name in SNAPSHOT_DOCS
    ]
    plan = read_text(task_dir / "plan.md")
    paths.extend(
        git_relative(path, workspace_root, "snapshot artifact")
        for path in artifact_paths(plan, workspace_root, explicit_artifacts)
    )
    return sorted(set(paths))


def current_snapshot_files(
    task_dir: Path,
    workspace_root: Path,
    explicit_artifacts: Iterable[str],
) -> set[str]:
    files: set[str] = set()
    for relative in snapshot_git_paths(
        task_dir,
        workspace_root,
        explicit_artifacts,
    ):
        path = workspace_root / relative
        if path.is_symlink() or path.is_file():
            files.add(relative)
            continue
        if not path.exists():
            continue
        if not path.is_dir():
            raise RalphError(f"snapshot path has unsupported file type: {relative}")
        all_members = list(path.rglob("*"))
        unsupported = [
            member
            for member in all_members
            if not (
                member.is_symlink()
                or member.is_file()
                or member.is_dir()
            )
        ]
        if unsupported:
            raise RalphError(
                "Git candidate cannot preserve unsupported snapshot members: "
                + ", ".join(
                    display_path(member, workspace_root)
                    for member in unsupported
                )
            )
        members = [
            member
            for member in all_members
            if member.is_symlink() or member.is_file()
        ]
        empty_directories = [
            directory
            for directory in [
                path,
                *(
                    item
                    for item in all_members
                    if item.is_dir() and not item.is_symlink()
                ),
            ]
            if not any(
                child.is_symlink() or child.is_file()
                for child in directory.rglob("*")
            )
        ]
        if empty_directories:
            raise RalphError(
                "Git candidate cannot preserve empty snapshot directories: "
                + ", ".join(
                    display_path(directory, workspace_root)
                    for directory in empty_directories
                )
            )
        files.update(
            git_relative(member, workspace_root, "snapshot member")
            for member in members
        )
    return files


def assert_default_git_index_flags(
    workspace_root: Path,
    scopes: Iterable[str],
    *,
    label: str,
) -> None:
    records = run_git(
        workspace_root,
        [
            "ls-files",
            "-v",
            "-z",
            "--",
            *literal_pathspecs(scopes),
        ],
    ).stdout.split("\0")
    flagged: list[str] = []
    for record in records:
        if not record:
            continue
        if len(record) < 3 or record[1] != " ":
            raise RalphError("cannot parse Git index flags for snapshot members")
        tag = record[0]
        path = record[2:]
        if tag != "H":
            flagged.append(f"{path} ({tag})")
    if flagged:
        raise RalphError(
            f"{label} use non-default Git index flags "
            "(assume-unchanged/skip-worktree or unsupported state): "
            + ", ".join(sorted(flagged))
        )


def assert_snapshot_trackable_before_commit(
    task_dir: Path,
    workspace_root: Path,
    explicit_artifacts: Iterable[str],
    changed_paths: set[str],
) -> None:
    scopes = snapshot_git_paths(task_dir, workspace_root, explicit_artifacts)
    expected_files = current_snapshot_files(
        task_dir,
        workspace_root,
        explicit_artifacts,
    )
    tracked_files = nul_paths(
        run_git(
            workspace_root,
            [
                "ls-files",
                "--cached",
                "-z",
                "--",
                *literal_pathspecs(scopes),
            ],
        ).stdout
    )
    assert_default_git_index_flags(
        workspace_root,
        scopes,
        label="snapshot members",
    )
    unavailable = sorted(expected_files - tracked_files - changed_paths)
    if unavailable:
        raise RalphError(
            "snapshot files are ignored or otherwise unavailable to the candidate commit: "
            + ", ".join(unavailable)
        )


def assert_snapshot_matches_commit(
    task_dir: Path,
    workspace_root: Path,
    explicit_artifacts: Iterable[str],
    commit: str,
) -> None:
    paths = snapshot_git_paths(task_dir, workspace_root, explicit_artifacts)
    expected_files = current_snapshot_files(
        task_dir,
        workspace_root,
        explicit_artifacts,
    )
    tracked_files = nul_paths(
        run_git(
            workspace_root,
            [
                "ls-tree",
                "-r",
                "--name-only",
                "-z",
                commit,
                "--",
                *literal_pathspecs(paths),
            ],
        ).stdout
    )
    if tracked_files != expected_files:
        raise RalphError(
            "candidate commit does not track the exact existing snapshot files: "
            + ", ".join(sorted(tracked_files ^ expected_files))
        )
    assert_default_git_index_flags(
        workspace_root,
        paths,
        label="snapshot members",
    )
    tree_records = run_git_bytes(
        workspace_root,
        [
            "ls-tree",
            "-r",
            "-z",
            commit,
            "--",
            *literal_pathspecs(paths),
        ],
    ).stdout.split(b"\0")
    tree_entries: dict[str, tuple[str, str, str]] = {}
    for record in tree_records:
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
            relative = raw_path.decode("utf-8", errors="surrogateescape")
        except (ValueError, UnicodeError) as exc:
            raise RalphError("cannot parse candidate tree snapshot members") from exc
        tree_entries[relative] = (mode, object_type, object_id)
    for relative in sorted(expected_files):
        mode, object_type, object_id = tree_entries[relative]
        path = workspace_root / relative
        if path.is_symlink():
            if mode != "120000":
                raise RalphError(
                    f"candidate tree type differs for snapshot member: {relative}"
                )
            current_bytes = os.fsencode(os.readlink(path))
        else:
            if object_type != "blob" or mode == "120000":
                raise RalphError(
                    f"candidate tree type differs for snapshot member: {relative}"
                )
            try:
                current_bytes = path.read_bytes()
            except OSError as exc:
                raise RalphError(
                    f"cannot read snapshot member {relative}: {exc}"
                ) from exc
        committed_bytes = run_git_bytes(
            workspace_root,
            ["cat-file", "blob", object_id],
        ).stdout
        if current_bytes != committed_bytes:
            raise RalphError(
                "snapshot member bytes differ from the recorded candidate commit: "
                + relative
            )
    untracked = nul_paths(
        run_git(
            workspace_root,
            [
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *literal_pathspecs(paths),
            ],
        ).stdout
    )
    if untracked:
        raise RalphError(
            "snapshot includes paths not tracked by the candidate commit: "
            + ", ".join(sorted(untracked))
        )


def clean_cell(value: str) -> str:
    value = value.strip().strip("`").strip()
    link = re.fullmatch(r"\[[^\]]+\]\(([^)]+)\)", value)
    return link.group(1).strip() if link else value


def markdown_rows(section_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [clean_cell(cell) for cell in stripped[1:-1].split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def markdown_section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1) if match else ""


def markdown_subsection(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^###\s+{re.escape(heading)}\s*$\n(.*?)(?=^###\s+|^##\s+|\Z)",
        text,
    )
    return match.group(1) if match else ""


def extract_ac_ids(proposal: str) -> list[str]:
    criteria = markdown_section(proposal, "Acceptance Criteria")
    return sorted(
        set(re.findall(r"(?<![A-Z0-9-])AC-\d{3,}(?![A-Z0-9-])", criteria)),
        key=lambda value: int(value.split("-")[1]),
    )


def parse_deliverables(plan: str) -> list[dict[str, str]]:
    rows = markdown_rows(markdown_section(plan, "Deliverables"))
    if not rows:
        return []
    header = [cell.casefold() for cell in rows[0]]
    aliases = {
        "id": {"id", "deliverable"},
        "acs": {"acs", "ac", "acceptance criteria"},
        "path": {"path", "target"},
        "required": {"required"},
        "status": {"status"},
    }
    columns: dict[str, int] = {}
    for key, names in aliases.items():
        for index, value in enumerate(header):
            if value in names:
                columns[key] = index
                break
    if not {"id", "acs", "path"}.issubset(columns):
        return []
    parsed: list[dict[str, str]] = []
    for row in rows[1:]:
        if len(row) <= max(columns.values()):
            continue
        deliverable_id = row[columns["id"]]
        if not re.fullmatch(r"DEL-\d{3,}", deliverable_id):
            continue
        parsed.append(
            {
                "id": deliverable_id,
                "acs": row[columns["acs"]],
                "path": row[columns["path"]],
                "required": row[columns["required"]] if "required" in columns else "Yes",
                "status": row[columns["status"]] if "status" in columns else "",
            }
        )
    return parsed


def required_deliverables(plan: str) -> list[dict[str, str]]:
    false_values = {"no", "false", "optional", "n", "否"}
    return [
        item
        for item in parse_deliverables(plan)
        if item["required"].strip().casefold() not in false_values
    ]


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def latest_review(verify: str) -> dict[str, object] | None:
    visible = strip_comments(verify)
    headings = list(re.finditer(r"(?m)^##\s+(ITER-(\d{3,}))\s+Review\s*$", visible))
    if not headings:
        return None
    match = headings[-1]
    block = visible[match.end() :]
    next_heading = re.search(r"(?m)^##\s+", block)
    if next_heading:
        block = block[: next_heading.start()]

    def field(name: str) -> str:
        field_match = re.search(
            rf"(?mi)^\|\s*{re.escape(name)}\s*\|\s*([^|]+?)\s*\|$",
            block,
        )
        return field_match.group(1).strip().strip("`") if field_match else ""

    decisions: dict[str, dict[str, str]] = {}
    duplicate_decisions: list[str] = []
    matrix = markdown_subsection(block, "AC Decision Matrix")
    for row in markdown_rows(matrix):
        if len(row) >= 3 and re.fullmatch(r"AC-\d{3,}", row[0]):
            if row[0] in decisions:
                duplicate_decisions.append(row[0])
            decisions[row[0]] = {"result": row[1].upper(), "evidence": row[2].strip()}

    open_blocking: list[str] = []
    findings = markdown_subsection(block, "Findings")
    for row in markdown_rows(findings):
        if len(row) < 4 or not re.fullmatch(r"F-\d{3,}", row[0]):
            continue
        severity = row[2].upper()
        status = row[3].upper()
        if severity in {"P0", "P1"} and status == "OPEN":
            open_blocking.append(row[0])

    command_records: list[dict[str, str]] = []
    commands = markdown_subsection(block, "Commands")
    for row in markdown_rows(commands):
        if len(row) >= 3 and row[0].casefold() not in {"command / review step", "command"}:
            if len(row) >= 5:
                expected_exit = row[1]
                actual_exit = row[2]
                result = row[3].upper()
                output = row[4]
            elif len(row) >= 4:
                expected_exit = (
                    "N/A"
                    if row[1].strip().upper() in {"N/A", "NA", "NOT APPLICABLE"}
                    else "0"
                )
                actual_exit = row[1]
                result = row[2].upper()
                output = row[3]
            else:
                expected_exit = (
                    "N/A"
                    if row[1].strip().upper() in {"N/A", "NA", "NOT APPLICABLE"}
                    else "0"
                )
                actual_exit = row[1]
                result = (
                    "PASS"
                    if row[1].strip().upper() in {"0", "N/A", "NA", "NOT APPLICABLE"}
                    else "FAIL"
                )
                output = row[2]
            command_records.append(
                {
                    "step": row[0],
                    "expected_exit": expected_exit,
                    "exit_code": actual_exit,
                    "result": result,
                    "output": output,
                }
            )

    return {
        "id": match.group(1),
        "number": int(match.group(2)),
        "verdict": field("Verdict").upper(),
        "snapshot": field("Snapshot SHA-256").lower(),
        "candidate_commit": field("Candidate commit").lower(),
        "candidate_branch": field("Candidate branch"),
        "reviewer": field("Reviewer"),
        "date": field("Date"),
        "environment": field("Environment"),
        "residual_risk": field("Residual risk"),
        "decisions": decisions,
        "duplicate_decisions": duplicate_decisions,
        "open_blocking": open_blocking,
        "commands": command_records,
        "block": block,
    }


def review_blocks(verify: str) -> dict[int, str]:
    visible = strip_comments(verify)
    headings = list(
        re.finditer(r"(?m)^##\s+ITER-(\d{3,})\s+Review\s*$", visible)
    )
    blocks: dict[int, str] = {}
    for index, match in enumerate(headings):
        number = int(match.group(1))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(visible)
        blocks[number] = visible[match.start() : end].strip()
    return blocks


def assert_review_history_append_only(
    previous_verify: str,
    current_verify: str,
    iteration: int,
) -> None:
    previous = review_blocks(previous_verify)
    current = review_blocks(current_verify)
    previous_numbers = sorted(previous)
    current_numbers = sorted(current)
    expected_numbers = [*previous_numbers, iteration]
    if current_numbers != expected_numbers or iteration in previous:
        raise RalphError(
            "Reviewer must append exactly one new sequential review block; "
            f"found {current_numbers}, expected {expected_numbers}"
        )
    changed = [
        number
        for number in previous_numbers
        if current.get(number) != previous[number]
    ]
    if changed:
        raise RalphError(
            "Reviewer must not rewrite prior review evidence: "
            + ", ".join(f"ITER-{number:03d}" for number in changed)
        )


def summary_field(verify: str, name: str) -> str:
    match = re.search(
        rf"(?mi)^\|\s*{re.escape(name)}\s*\|\s*([^|]+?)\s*\|$",
        strip_comments(verify),
    )
    return match.group(1).strip().strip("`") if match else ""


def review_numbers(verify: str) -> list[int]:
    visible = strip_comments(verify)
    return [
        int(value)
        for value in re.findall(r"(?m)^##\s+ITER-(\d{3,})\s+Review\s*$", visible)
    ]


def iteration_roles(plan: str) -> dict[int, set[str]]:
    rows = markdown_rows(markdown_section(plan, "Iteration Log"))
    roles: dict[int, set[str]] = {}
    for row in rows:
        if len(row) < 2 or not row[0].isdigit():
            continue
        roles.setdefault(int(row[0]), set()).add(row[1].strip().casefold())
    return roles


def placeholder_locations(texts: dict[str, str]) -> list[str]:
    patterns = (
        re.compile(r"\[\[(?:PLANNER|IMPLEMENTER|REVIEWER):", re.IGNORECASE),
        re.compile(r"\{\{[A-Z0-9_]+\}\}"),
        re.compile(r"\[TODO:", re.IGNORECASE),
        re.compile(
            r"<(?:说明|本任务|当前|下一步|证据|上游|关键|影响|风险|交付|验证|"
            r"短标题|人或 agent|repo|cwd|fixture|path or output|command|criteria)[^>]*>",
            re.IGNORECASE,
        ),
    )
    found: list[str] = []
    for name, text in texts.items():
        visible = strip_comments(text)
        for number, line in enumerate(visible.splitlines(), 1):
            if any(pattern.search(line) for pattern in patterns):
                found.append(f"{name}:{number}")
    return found


def normalize_artifact_path(raw: str, workspace_root: Path) -> Path:
    value = clean_cell(raw)
    if not value or value.casefold().startswith("n/a"):
        raise RalphError(f"invalid required deliverable path: {raw!r}")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return ensure_within(candidate, workspace_root, "artifact")


def artifact_paths(
    plan: str,
    workspace_root: Path,
    explicit: Iterable[str],
) -> list[Path]:
    values = [item["path"] for item in required_deliverables(plan)]
    values.extend(explicit)
    paths: dict[str, Path] = {}
    for value in values:
        path = normalize_artifact_path(value, workspace_root)
        paths[str(path)] = path
    return [paths[key] for key in sorted(paths)]


def declared_artifact_paths(
    plan: str,
    workspace_root: Path,
    explicit: Iterable[str],
) -> list[Path]:
    values = [item["path"] for item in parse_deliverables(plan)]
    values.extend(explicit)
    paths: dict[str, Path] = {}
    for value in values:
        path = normalize_artifact_path(value, workspace_root)
        paths[str(path)] = path
    return [paths[key] for key in sorted(paths)]


def assert_artifacts_do_not_overlap_task_pack(
    artifacts: Iterable[Path],
    task_dir: Path,
) -> None:
    overlapping = sorted(
        str(path)
        for path in artifacts
        if is_within(path, task_dir) or is_within(task_dir, path)
    )
    if overlapping:
        raise RalphError(
            "declared and explicit deliverables must not overlap the four-pack "
            "task directory: "
            + ", ".join(overlapping)
        )


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> dict[str, object]:
    if path.is_symlink():
        return {
            "type": "symlink",
            "sha256": hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest(),
            "target": os.readlink(path),
        }
    if path.is_file():
        return {"type": "file", "sha256": hash_file(path), "size": path.stat().st_size}
    if path.is_dir():
        members: list[dict[str, object]] = []
        for member in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
            relative = member.relative_to(path).as_posix()
            if member.is_symlink():
                item = hash_path(member)
            elif member.is_file():
                item = hash_path(member)
            elif member.is_dir():
                item = {"type": "directory"}
            else:
                item = {"type": "other"}
            members.append({"path": relative, **item})
        encoded = json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "type": "directory",
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "members": len(members),
        }
    return {"type": "missing", "sha256": None}


def display_path(path: Path, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return str(path)


def markdown_table_link(label: str, destination: str) -> str:
    safe_label = (
        label.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", " ")
    )
    safe_destination = quote(destination, safe="/.")
    return f"[{safe_label}]({safe_destination})"


def artifact_index_link(
    artifact: Path,
    index: Path,
    workspace_root: Path,
) -> str:
    return markdown_table_link(
        display_path(artifact, workspace_root),
        os.path.relpath(artifact, index.parent),
    )


def legacy_artifact_index_link(
    artifact: Path,
    index: Path,
    workspace_root: Path,
) -> str:
    return (
        f"[`{display_path(artifact, workspace_root)}`]"
        f"({os.path.relpath(artifact, index.parent)})"
    )


def snapshot_data(
    task_dir: Path,
    workspace_root: Path,
    explicit_artifacts: Iterable[str],
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for name in SNAPSHOT_DOCS:
        path = task_dir / name
        entries.append({"path": f"four-pack/{name}", **hash_path(path)})
    plan = read_text(task_dir / "plan.md")
    artifacts = artifact_paths(plan, workspace_root, explicit_artifacts)
    assert_artifacts_do_not_overlap_task_pack(artifacts, task_dir)
    for path in artifacts:
        entries.append({"path": display_path(path, workspace_root), **hash_path(path)})
    entries.sort(key=lambda item: str(item["path"]))
    canonical = json.dumps(
        {"schema": "rd-ralph-snapshot-v1", "entries": entries},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema": "rd-ralph-snapshot-v1",
        "task_dir": display_path(task_dir, workspace_root),
        "entries": entries,
        "snapshot_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def require_four_pack(task_dir: Path) -> dict[str, str]:
    if task_dir.is_symlink() or not task_dir.is_dir():
        raise RalphError(f"task directory must be a real directory: {task_dir}")
    missing = [name for name in FOUR_PACK if not (task_dir / name).is_file()]
    if missing:
        raise RalphError(f"missing four-pack files: {', '.join(missing)}")
    symlinks = [name for name in FOUR_PACK if (task_dir / name).is_symlink()]
    if symlinks:
        raise RalphError(f"four-pack files must not be symlinks: {', '.join(symlinks)}")
    return {name: read_text(task_dir / name) for name in FOUR_PACK}


def task_identity(task_dir: Path, proposal: str) -> str:
    match = re.search(r"(?mi)^\|\s*Task ID\s*\|\s*`?([^|`]+)`?\s*\|$", proposal)
    if match:
        return match.group(1).strip()
    return task_dir.name


def four_pack_dirs_with_identity(workspace_root: Path, identity: str) -> list[Path]:
    ignored = {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
    matches: list[Path] = []
    for directory, child_dirs, filenames in os.walk(workspace_root, followlinks=False):
        child_dirs[:] = [name for name in child_dirs if name not in ignored]
        if not set(FOUR_PACK).issubset(filenames):
            continue
        candidate = Path(directory)
        if candidate.is_symlink():
            continue
        try:
            candidate_identity = task_identity(
                candidate, read_text(candidate / "proposal.md")
            )
        except RalphError:
            continue
        if candidate_identity == identity:
            matches.append(candidate)
    return matches


def validate_task(
    task_dir: Path,
    workspace_root: Path,
    phase: str,
    index: Path | None,
    explicit_artifacts: Iterable[str],
) -> tuple[list[str], list[str], dict[str, object]]:
    texts = require_four_pack(task_dir)
    errors: list[str] = []
    warnings: list[str] = []
    identity = task_identity(task_dir, texts["proposal.md"])
    try:
        git_context = git_context_data(workspace_root)
    except RalphError as exc:
        errors.append(str(exc))
        git_context = None

    if git_context is not None:
        branch = str(git_context["branch"])
        planned_branch = summary_field(texts["plan.md"], "Branch")
        planned_worktree = summary_field(texts["plan.md"], "Worktree root")
        base_commit = summary_field(texts["plan.md"], "Base commit").lower()
        merge_mode = summary_field(texts["plan.md"], "Merge mode").casefold()
        if branch != expected_branch(identity):
            errors.append(
                f"Git Ralph task must run on {expected_branch(identity)}, found "
                f"{branch or 'detached HEAD'}"
            )
        if planned_branch != branch:
            errors.append(
                f"plan Branch is {planned_branch or 'missing'}, expected "
                f"{branch or 'detached HEAD'}"
            )
        try:
            planned_worktree_path = Path(planned_worktree).resolve(strict=True)
        except OSError:
            planned_worktree_path = None
        if planned_worktree_path != workspace_root.resolve(strict=True):
            errors.append("plan Worktree root does not match --workspace-root")
        if not commit_exists(workspace_root, base_commit):
            errors.append("plan Base commit is missing or invalid")
        elif not is_ancestor(
            workspace_root,
            base_commit,
            str(git_context["head"]),
        ):
            errors.append("plan Base commit is not an ancestor of current HEAD")
        else:
            try:
                task_commit_chain(
                    workspace_root,
                    identity,
                    base_commit,
                    str(git_context["head"]),
                    current_plan=texts["plan.md"],
                    require_initialized=phase
                    in {"reviewed", "accepted", "archived"},
                )
            except RalphError as exc:
                errors.append(str(exc))
        if "manual" not in merge_mode:
            errors.append("plan Merge mode must be manual")

    ac_ids = extract_ac_ids(texts["proposal.md"])
    if not ac_ids:
        errors.append("proposal.md has no AC-NNN criteria under Acceptance Criteria")
    verification_plan = markdown_section(texts["plan.md"], "AC Verification Plan")
    for ac_id in ac_ids:
        if ac_id not in texts["plan.md"]:
            errors.append(f"plan.md does not trace {ac_id}")
        if ac_id not in verification_plan:
            errors.append(f"AC Verification Plan does not cover {ac_id}")

    placeholders = placeholder_locations(
        {
            "proposal.md": texts["proposal.md"],
            "design.md": texts["design.md"],
            "plan.md": texts["plan.md"],
        }
    )
    if placeholders:
        errors.append("unresolved template placeholders: " + ", ".join(placeholders))

    deliverables = parse_deliverables(texts["plan.md"])
    if not deliverables:
        errors.append(
            "standard Deliverables table is missing or invalid; use project-native gates "
            "for a custom four-pack"
        )
    elif not required_deliverables(texts["plan.md"]):
        errors.append("Deliverables table has no required retained output")
    try:
        assert_artifacts_do_not_overlap_task_pack(
            declared_artifact_paths(
                texts["plan.md"],
                workspace_root,
                explicit_artifacts,
            ),
            task_dir,
        )
    except RalphError as exc:
        errors.append(str(exc))
    valid_acs = set(ac_ids)
    for item in deliverables:
        mapped = set(re.findall(r"AC-\d{3,}", item["acs"]))
        if not mapped:
            errors.append(f"{item['id']} has no AC mapping")
        unknown = sorted(mapped - valid_acs)
        if unknown:
            errors.append(f"{item['id']} maps unknown ACs: {', '.join(unknown)}")

    item_section = markdown_section(texts["plan.md"], "Delivery Items")
    item_lines = [
        line for line in item_section.splitlines() if re.search(r"ITEM-\d{3,}", line)
    ]
    if not item_lines:
        errors.append("Delivery Items has no ITEM-NNN records")
    item_ids: list[str] = []
    known_deliverables = {item["id"] for item in deliverables}
    mapped_deliverables: set[str] = set()
    for line in item_lines:
        match = re.search(r"ITEM-\d{3,}", line)
        assert match is not None
        item_id = match.group(0)
        item_ids.append(item_id)
        referenced_deliverables = set(re.findall(r"DEL-\d{3,}", line))
        referenced_acs = set(re.findall(r"AC-\d{3,}", line))
        mapped_deliverables.update(referenced_deliverables)
        if not referenced_deliverables:
            errors.append(f"{item_id} has no DEL mapping")
        elif referenced_deliverables - known_deliverables:
            errors.append(
                f"{item_id} maps unknown deliverables: "
                + ", ".join(sorted(referenced_deliverables - known_deliverables))
            )
        if not referenced_acs:
            errors.append(f"{item_id} has no AC mapping")
        elif referenced_acs - valid_acs:
            errors.append(
                f"{item_id} maps unknown ACs: "
                + ", ".join(sorted(referenced_acs - valid_acs))
            )
    repeated_items = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
    if repeated_items:
        errors.append("duplicate Delivery Item IDs: " + ", ".join(repeated_items))
    unmapped_required = sorted(
        item["id"]
        for item in required_deliverables(texts["plan.md"])
        if item["id"] not in mapped_deliverables
    )
    if unmapped_required:
        errors.append(
            "required deliverables have no Delivery Item: " + ", ".join(unmapped_required)
        )

    review = latest_review(texts["verify.md"])
    snapshot = snapshot_data(task_dir, workspace_root, explicit_artifacts)
    roles = iteration_roles(texts["plan.md"])
    if not roles:
        errors.append("standard Iteration Log is missing or has no role records")
    elif "planner" not in roles.get(0, set()):
        errors.append("standard Iteration Log has no initialization Planner row at iteration 0")

    if phase in {"reviewed", "accepted", "archived"}:
        if review is None:
            errors.append("verify.md has no real ITER-NNN review record")
        else:
            verdict = str(review["verdict"])
            if verdict not in VERDICTS:
                errors.append(f"latest review has invalid verdict: {verdict or 'missing'}")
            decisions = review["decisions"]
            assert isinstance(decisions, dict)
            for ac_id in ac_ids:
                if ac_id not in decisions:
                    errors.append(f"latest review has no decision for {ac_id}")
            duplicates = review["duplicate_decisions"]
            assert isinstance(duplicates, list)
            if duplicates:
                errors.append(
                    "latest review repeats AC decisions: " + ", ".join(sorted(set(duplicates)))
                )
            for field_name in ("reviewer", "date", "environment", "residual_risk"):
                if not str(review[field_name]).strip():
                    errors.append(f"latest review is missing {field_name.replace('_', ' ')}")
            review_block = str(review["block"]).casefold()
            leaked_placeholders = sorted(
                value for value in REVIEW_PLACEHOLDERS if value in review_block
            )
            if leaked_placeholders:
                errors.append(
                    "latest review contains template placeholders: "
                    + ", ".join(leaked_placeholders)
                )
            commands = review["commands"]
            assert isinstance(commands, list)
            if not commands:
                errors.append("latest review records no independent command or review step")
            for command in commands:
                if str(command.get("result", "")).upper() not in {"PASS", "FAIL"}:
                    errors.append(
                        f"review step has invalid Result: {command.get('step', 'unknown')}"
                    )
                if not str(command.get("expected_exit", "")).strip() or not str(
                    command.get("exit_code", "")
                ).strip():
                    errors.append(
                        f"review step lacks expected/actual exit: "
                        f"{command.get('step', 'unknown')}"
                    )
            reviewed_snapshot = str(review["snapshot"])
            if not re.fullmatch(r"[0-9a-f]{64}", reviewed_snapshot):
                errors.append("latest review has no valid Snapshot SHA-256")
            elif reviewed_snapshot != snapshot["snapshot_sha256"]:
                errors.append(
                    "latest review snapshot does not match current proposal/design/plan/deliverables"
                )
            try:
                git_context = git_context_data(workspace_root)
            except RalphError as exc:
                errors.append(str(exc))
                git_context = None
            candidate_commit = str(review["candidate_commit"]).lower()
            candidate_branch = str(review["candidate_branch"])
            if git_context is None:
                allowed_non_git = {"", "n/a", "na", "none", "non-git"}
                if candidate_commit not in allowed_non_git:
                    errors.append("non-Git review must use Candidate commit N/A")
                if candidate_branch.strip().casefold() not in allowed_non_git:
                    errors.append("non-Git review must use Candidate branch N/A")
            else:
                branch = str(git_context["branch"])
                wanted_branch = expected_branch(identity)
                if branch != wanted_branch:
                    errors.append(
                        f"Git Ralph review must run on {wanted_branch}, found "
                        f"{branch or 'detached HEAD'}"
                    )
                if candidate_branch != branch:
                    errors.append(
                        f"latest review Candidate branch is {candidate_branch or 'missing'}, "
                        f"expected {branch or 'detached HEAD'}"
                    )
                if not commit_exists(workspace_root, candidate_commit):
                    errors.append("latest review has no reachable full Candidate commit")
                else:
                    head = str(git_context["head"])
                    if not is_ancestor(workspace_root, candidate_commit, head):
                        errors.append(
                            "latest review Candidate commit is not an ancestor of current HEAD"
                        )
                    trailers = commit_trailers(workspace_root, candidate_commit)
                    expected_trailers = {
                        "ralph-task": identity,
                        "ralph-role": "Implementer",
                        "ralph-iteration": str(review["number"]),
                        "ralph-snapshot": reviewed_snapshot,
                    }
                    for key, expected in expected_trailers.items():
                        actual = trailers.get(key.casefold(), "")
                        if actual.casefold() != expected.casefold():
                            errors.append(
                                f"Candidate commit trailer {key} is "
                                f"{actual or 'missing'}, expected {expected}"
                            )
                    if phase != "archived":
                        try:
                            assert_snapshot_matches_commit(
                                task_dir,
                                workspace_root,
                                explicit_artifacts,
                                candidate_commit,
                            )
                        except RalphError as exc:
                            errors.append(str(exc))
            numbers = review_numbers(texts["verify.md"])
            if numbers != list(range(1, numbers[-1] + 1)):
                errors.append("review iteration IDs must be unique and sequential from ITER-001")
            review_number = int(review["number"])
            for iteration in numbers:
                if "implementer" not in roles.get(iteration, set()):
                    errors.append(
                        f"standard Iteration Log has no Implementer pass for iteration {iteration}"
                    )
            current = summary_field(texts["plan.md"], "Current iteration")
            if current and current != str(review_number):
                errors.append(
                    f"plan Current iteration is {current}, latest review is {review_number}"
                )
            final_summary = summary_field(texts["verify.md"], "Final decision").upper()
            if final_summary != verdict:
                errors.append(
                    f"verify.md Final decision summary {final_summary or 'missing'} "
                    f"does not match latest verdict {verdict}"
                )

    acceptance_claimed = (
        phase in {"accepted", "archived"}
        or (
            phase == "reviewed"
            and review is not None
            and review["verdict"] == "ACCEPTED"
        )
    )
    if acceptance_claimed and review is not None:
        if review["verdict"] != "ACCEPTED":
            errors.append(f"latest Reviewer verdict is {review['verdict']}, not ACCEPTED")
        accepted_snapshot = summary_field(
            texts["verify.md"], "Accepted snapshot SHA-256"
        ).lower()
        if accepted_snapshot != snapshot["snapshot_sha256"]:
            errors.append("verify.md accepted snapshot summary does not match the current snapshot")
        git_context = git_context_data(workspace_root)
        if git_context is not None:
            accepted_candidate = summary_field(
                texts["verify.md"], "Accepted candidate commit"
            ).lower()
            latest_candidate = str(review["candidate_commit"]).lower()
            if accepted_candidate != latest_candidate:
                errors.append(
                    "verify.md accepted candidate summary does not match the latest review"
                )
        decisions = review["decisions"]
        assert isinstance(decisions, dict)
        for ac_id in ac_ids:
            decision = decisions.get(ac_id, {})
            if not isinstance(decision, dict) or decision.get("result") != "PASS":
                errors.append(f"{ac_id} is not PASS in the latest review")
            elif len(str(decision.get("evidence", "")).strip()) < 3:
                errors.append(f"{ac_id} has no substantive evidence in the latest review")
        open_blocking = review["open_blocking"]
        assert isinstance(open_blocking, list)
        if open_blocking:
            errors.append("open P0/P1 findings remain: " + ", ".join(open_blocking))
        commands = review["commands"]
        assert isinstance(commands, list)
        failed_steps = [
            str(command["step"])
            for command in commands
            if str(command.get("result", "")).upper() != "PASS"
            or str(command.get("expected_exit", "")).strip().upper()
            != str(command.get("exit_code", "")).strip().upper()
        ]
        if failed_steps:
            errors.append(
                "latest review has non-passing command/review steps: " + ", ".join(failed_steps)
            )
        for item in required_deliverables(texts["plan.md"]):
            path = normalize_artifact_path(item["path"], workspace_root)
            if not path.exists() and not path.is_symlink():
                errors.append(f"required deliverable is missing: {item['id']} -> {path}")
            if item["status"].strip().casefold() not in {"done", "complete", "completed", "pass", "完成"}:
                errors.append(f"required deliverable is not marked complete: {item['id']}")
        unchecked = re.findall(r"(?mi)^\|\s*\[\s\]\s*\|\s*`?(ITEM-\d{3,})", item_section)
        if unchecked:
            errors.append("unchecked delivery items remain: " + ", ".join(unchecked))
        missing_snapshot_paths = [
            str(entry["path"])
            for entry in snapshot["entries"]
            if entry.get("type") == "missing"
        ]
        if missing_snapshot_paths:
            errors.append("snapshot contains missing paths: " + ", ".join(missing_snapshot_paths))

    if phase == "archived":
        if index is None:
            errors.append("--index is required for archived validation")
        else:
            index_text = read_text(index)
            try:
                active_start, active_end = marker_block(index_text, ACTIVE_START, ACTIVE_END)
                archive_start, archive_end = marker_block(
                    index_text, ARCHIVE_START, ARCHIVE_END
                )
            except RalphError as exc:
                errors.append(str(exc))
            else:
                active_body = index_text[active_start:active_end]
                archive_body = index_text[archive_start:archive_end]
                active_names = {
                    name
                    for line in active_body.splitlines()
                    if (name := index_row_task_name(line)) is not None
                }
                if task_dir.name in active_names:
                    errors.append(f"managed index still has an active row for {identity}")
                archive_lines = [
                    line
                    for line in archive_body.splitlines()
                    if index_row_task_name(line) == task_dir.name
                ]
                if len(archive_lines) != 1:
                    errors.append(
                        f"managed index must have exactly one archived row for {identity}"
                    )
                else:
                    archive_line = archive_lines[0]
                    if "ACCEPTED" not in archive_line:
                        errors.append(f"managed index verdict for {identity} is not ACCEPTED")
                    full_snapshot = str(snapshot["snapshot_sha256"])
                    if full_snapshot not in archive_line:
                        errors.append(
                            f"managed index entry for {identity} lacks the full accepted snapshot"
                        )
                    if review is not None:
                        candidate_commit = str(review["candidate_commit"]).lower()
                        if candidate_commit and candidate_commit not in archive_line:
                            errors.append(
                                f"managed index entry for {identity} lacks the accepted "
                                "candidate commit"
                            )
                    review_number = int(review["number"]) if review is not None else 0
                    if f"| {review_number} |" not in archive_line:
                        errors.append(
                            f"managed index entry for {identity} has the wrong iteration count"
                        )
                    for artifact in artifact_paths(
                        texts["plan.md"], workspace_root, explicit_artifacts
                    ):
                        expected_links = {
                            artifact_index_link(
                                artifact,
                                index,
                                workspace_root,
                            ),
                            legacy_artifact_index_link(
                                artifact,
                                index,
                                workspace_root,
                            ),
                        }
                        if not any(link in archive_line for link in expected_links):
                            errors.append(
                                f"managed index entry omits deliverable "
                                f"{display_path(artifact, workspace_root)}"
                            )

            duplicate_dirs = four_pack_dirs_with_identity(workspace_root, identity)
            unique = {str(path.resolve()) for path in duplicate_dirs}
            if len(unique) != 1:
                errors.append(
                    f"expected exactly one active/archive four-pack for {identity}, found {len(unique)}"
                )
            relative_parts = [part.casefold() for part in task_dir.relative_to(workspace_root).parts]
            if "archive" not in relative_parts:
                errors.append("archived task directory is not under an archive path")

    return errors, warnings, snapshot


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "task"


def replace_tokens(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def marker_block(text: str, start: str, end: str) -> tuple[int, int]:
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index < 0 or end_index < 0 or end_index < start_index:
        raise RalphError("index is not managed by rd-ralph-loop markers")
    return start_index + len(start), end_index


def insert_marker_row(text: str, start: str, end: str, row: str) -> str:
    body_start, body_end = marker_block(text, start, end)
    body = text[body_start:body_end]
    if row in body:
        return text
    replacement = "\n" + body.strip("\n")
    if replacement != "\n":
        replacement += "\n"
    replacement += row + "\n"
    return text[:body_start] + replacement + text[body_end:]


def index_row_task_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    first_cell = stripped[1:-1].split("|", 1)[0].strip()
    link = re.fullmatch(r"\[`?([^`\]]+)`?\]\([^)]+\)", first_cell)
    if link:
        return link.group(1).strip()
    plain = first_cell.strip("`").strip()
    return plain if plain else None


def remove_marker_task_row(text: str, start: str, end: str, task_name: str) -> str:
    body_start, body_end = marker_block(text, start, end)
    kept = [
        line
        for line in text[body_start:body_end].splitlines()
        if index_row_task_name(line) != task_name
    ]
    replacement = "\n"
    if kept:
        replacement += "\n".join(kept) + "\n"
    return text[:body_start] + replacement + text[body_end:]


def worktree_create_command(args: argparse.Namespace) -> int:
    repo_root = resolve_existing(Path(args.repo_root), "repository root")
    repo_probe = run_git(
        repo_root,
        ["rev-parse", "--show-toplevel"],
        check=False,
    )
    if repo_probe.returncode != 0:
        raise RalphError(f"repository root is not a Git worktree: {repo_root}")
    top_level = Path(repo_probe.stdout.strip()).resolve(strict=True)
    if top_level != repo_root:
        raise RalphError(f"--repo-root must be the Git worktree top level: {top_level}")

    validate_task_id(args.task_id)
    branch = expected_branch(args.task_id)
    if (
        run_git(
            repo_root,
            ["check-ref-format", "--branch", branch],
            check=False,
        ).returncode
        != 0
    ):
        raise RalphError(f"invalid worktree branch name: {branch}")
    if (
        run_git(
            repo_root,
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            check=False,
        ).returncode
        == 0
    ):
        raise RalphError(f"worktree branch already exists: {branch}")

    target = Path(args.worktree_path).expanduser().resolve(strict=False)
    if target.exists():
        raise RalphError(f"worktree path already exists: {target}")
    containing_worktrees = [
        path
        for path in registered_worktree_paths(repo_root)
        if is_within(target, path)
    ]
    if containing_worktrees:
        raise RalphError(
            "worktree path must be outside every registered worktree: "
            + ", ".join(str(path) for path in containing_worktrees)
        )

    base = args.base or "HEAD"
    base_commit = run_git(
        repo_root,
        ["rev-parse", f"{base}^{{commit}}"],
    ).stdout.strip().lower()
    run_git(
        repo_root,
        ["worktree", "add", "-b", branch, str(target), base_commit],
    )
    context = require_loop_git_context(
        resolve_existing(target, "created worktree"),
        args.task_id,
        require_linked=True,
    )
    print(
        json.dumps(
            {
                "created": True,
                "task_id": args.task_id,
                "base_commit": base_commit,
                **context,
                "next": (
                    "Run init and every role with this exact workspace_root; "
                    "do not merge, push, rebase, or remove the worktree automatically."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def git_context_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    context = git_context_data(workspace_root, require_git=args.require_git)
    if context is None:
        print(
            json.dumps(
                {
                    "vcs": "none",
                    "workspace_root": str(workspace_root),
                    "valid": not args.require_git,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.task_id:
        context = require_loop_git_context(
            workspace_root,
            args.task_id,
            require_linked=not args.allow_primary_worktree,
        )
    if args.require_clean and not bool(context["clean"]):
        raise RalphError("Git worktree is not clean")
    print(json.dumps({"valid": True, **context}, indent=2, sort_keys=True))
    return 0


def checkpoint_role_label(role: str) -> str:
    return {
        "planner-init": "Planner",
        "planner-replan": "Planner",
        "implementer": "Implementer",
        "reviewer": "Reviewer",
        "closure": "Closure",
    }[role]


def checkpoint_subject(
    role: str,
    task_id: str,
    iteration: int,
    review: dict[str, object] | None,
) -> str:
    if role == "planner-init":
        return f"[{task_id}] planner: establish contract"
    if role == "planner-replan":
        return f"[{task_id}] planner(iter-{iteration:03d}): replan"
    if role == "implementer":
        return f"[{task_id}] implement(iter-{iteration:03d}): candidate"
    if role == "reviewer":
        verdict = str(review["verdict"]) if review is not None else "reviewed"
        return f"[{task_id}] review(iter-{iteration:03d}): {verdict}"
    return f"[{task_id}] close: archive and update index"


def checkpoint_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    context = require_loop_git_context(
        workspace_root,
        args.task_id,
        require_linked=not args.allow_primary_worktree,
    )
    if not context["branch"]:
        raise RalphError("checkpoint requires a branch, not detached HEAD")
    if context["operations_in_progress"]:
        raise RalphError(
            "checkpoint refuses an in-progress Git operation: "
            + ", ".join(str(value) for value in context["operations_in_progress"])
        )
    if args.iteration < 0:
        raise RalphError("--iteration must be zero or greater")
    if git_staged_paths(workspace_root):
        raise RalphError(
            "staging area must be empty before a role checkpoint; "
            "do not mix pre-staged user changes"
        )
    unmerged = nul_paths(
        run_git(
            workspace_root,
            ["diff", "--name-only", "--diff-filter=U", "-z"],
        ).stdout
    )
    if unmerged:
        raise RalphError("checkpoint refuses unresolved merges: " + ", ".join(sorted(unmerged)))

    task_dir = workspace_path(args.task_dir, workspace_root, "task directory")
    index = (
        workspace_path(args.index, workspace_root, "task index")
        if args.index
        else None
    )
    archive_task_dir = (
        workspace_path(args.archive_task_dir, workspace_root, "archived task directory")
        if args.archive_task_dir
        else None
    )
    scopes: list[str] = []
    snapshot: dict[str, object] | None = None
    review: dict[str, object] | None = None
    reviewer_checkpoint: str | None = None
    artifact_arguments = args.artifact

    if args.role == "planner-init":
        if args.iteration != 0:
            raise RalphError("planner-init checkpoint requires --iteration 0")
        require_four_pack(resolve_existing(task_dir, "task directory"))
        scopes.extend(
            git_relative(task_dir / name, workspace_root, name) for name in FOUR_PACK
        )
        if index is not None:
            scopes.append(git_relative(index, workspace_root, "task index"))
    elif args.role == "planner-replan":
        if args.iteration < 1:
            raise RalphError("planner-replan checkpoint requires --iteration 1 or greater")
        require_four_pack(resolve_existing(task_dir, "task directory"))
        scopes.extend(
            [
                git_relative(task_dir / "plan.md", workspace_root, "plan"),
                git_relative(task_dir / "design.md", workspace_root, "design"),
            ]
        )
        proposal_path = git_relative(
            task_dir / "proposal.md",
            workspace_root,
            "proposal",
        )
        if args.allow_contract_change:
            scopes.append(proposal_path)
        elif proposal_path in git_changed_paths(workspace_root):
            raise RalphError(
                "Planner proposal change requires --allow-contract-change after explicit "
                "user authorization"
            )
    elif args.role == "implementer":
        if args.iteration < 1:
            raise RalphError("implementer checkpoint requires --iteration 1 or greater")
        texts = require_four_pack(resolve_existing(task_dir, "task directory"))
        scopes.extend(
            [
                git_relative(task_dir / "plan.md", workspace_root, "plan"),
                git_relative(task_dir / "design.md", workspace_root, "design"),
            ]
        )
        plan_relative = git_relative(
            task_dir / "plan.md",
            workspace_root,
            "plan",
        )
        previous_plan = git_file_text(
            workspace_root,
            str(context["head"]),
            plan_relative,
        )
        previous_artifacts = declared_artifact_paths(
            previous_plan,
            workspace_root,
            artifact_arguments,
        )
        current_artifacts = declared_artifact_paths(
            texts["plan.md"],
            workspace_root,
            artifact_arguments,
        )
        assert_artifacts_do_not_overlap_task_pack(
            previous_artifacts,
            task_dir,
        )
        assert_artifacts_do_not_overlap_task_pack(
            current_artifacts,
            task_dir,
        )
        explicitly_allowed_new = {
            str(
                normalize_artifact_path(
                    value,
                    workspace_root,
                )
            )
            for value in args.allow_new_deliverable
        }
        unexpected_new = sorted(
            str(path)
            for path in current_artifacts
            if str(path) not in {str(item) for item in previous_artifacts}
            and str(path) not in explicitly_allowed_new
        )
        if unexpected_new:
            raise RalphError(
                "Implementer introduced new deliverable paths without Controller approval; "
                "use --allow-new-deliverable for each inspected design amendment: "
                + ", ".join(unexpected_new)
            )
        scopes.extend(
            git_relative(path, workspace_root, "declared deliverable")
            for path in sorted(
                {str(path): path for path in previous_artifacts + current_artifacts}.values(),
                key=lambda item: str(item),
            )
        )
        snapshot = snapshot_data(task_dir, workspace_root, artifact_arguments)
    elif args.role == "reviewer":
        if args.iteration < 1:
            raise RalphError("reviewer checkpoint requires --iteration 1 or greater")
        texts = require_four_pack(resolve_existing(task_dir, "task directory"))
        verify_relative = git_relative(
            task_dir / "verify.md",
            workspace_root,
            "verify",
        )
        scopes.append(verify_relative)
        review = latest_review(texts["verify.md"])
        if review is None or int(review["number"]) != args.iteration:
            raise RalphError(
                f"verify.md must contain latest ITER-{args.iteration:03d} before checkpoint"
            )
        candidate_commit = str(review["candidate_commit"]).lower()
        candidate_branch = str(review["candidate_branch"])
        head = str(context["head"]).lower()
        if candidate_commit != head:
            raise RalphError(
                f"Reviewer Candidate commit must equal pre-review HEAD {head}"
            )
        if candidate_branch != str(context["branch"]):
            raise RalphError(
                f"Reviewer Candidate branch must equal {context['branch']}"
            )
        previous_verify = git_file_text(
            workspace_root,
            head,
            verify_relative,
        )
        assert_review_history_append_only(
            previous_verify,
            texts["verify.md"],
            args.iteration,
        )
        snapshot = snapshot_data(task_dir, workspace_root, artifact_arguments)
        reviewed_snapshot = str(review["snapshot"]).lower()
        if reviewed_snapshot != snapshot["snapshot_sha256"]:
            raise RalphError("Reviewer snapshot does not match the current candidate bytes")
        assert_snapshot_matches_commit(
            task_dir,
            workspace_root,
            artifact_arguments,
            candidate_commit,
        )
        trailers = commit_trailers(workspace_root, candidate_commit)
        required = {
            "ralph-task": args.task_id,
            "ralph-role": "Implementer",
            "ralph-iteration": str(args.iteration),
            "ralph-snapshot": reviewed_snapshot,
        }
        for key, expected in required.items():
            actual = trailers.get(key, "")
            if actual.casefold() != expected.casefold():
                raise RalphError(
                    f"candidate trailer {key} is {actual or 'missing'}, expected {expected}"
                )
    else:
        if archive_task_dir is None or index is None:
            raise RalphError(
                "closure checkpoint requires --archive-task-dir and --index"
            )
        archived = resolve_existing(archive_task_dir, "archived task directory")
        texts = require_four_pack(archived)
        review = latest_review(texts["verify.md"])
        if review is None or review["verdict"] != "ACCEPTED":
            raise RalphError("closure checkpoint requires a latest ACCEPTED review")
        snapshot = snapshot_data(archived, workspace_root, artifact_arguments)
        accepted_snapshot = summary_field(
            texts["verify.md"], "Accepted snapshot SHA-256"
        ).lower()
        if accepted_snapshot != snapshot["snapshot_sha256"]:
            raise RalphError("closure snapshot differs from accepted snapshot")
        reviewer_checkpoint = assert_reviewer_checkpoint(
            workspace_root,
            args.task_id,
            review,
            str(snapshot["snapshot_sha256"]),
            current_verify=archived / "verify.md",
        )
        scopes.extend(
            git_relative(task_dir / name, workspace_root, f"active {name}")
            for name in FOUR_PACK
        )
        scopes.extend(
            git_relative(archived / name, workspace_root, f"archived {name}")
            for name in FOUR_PACK
        )
        scopes.append(git_relative(index, workspace_root, "task index"))

    checkpoint_pack = (
        resolve_existing(archive_task_dir, "archived task directory")
        if args.role == "closure"
        else resolve_existing(task_dir, "task directory")
    )
    checkpoint_plan = read_text(checkpoint_pack / "plan.md")
    base_commit = summary_field(checkpoint_plan, "Base commit").lower()
    head_commit = str(context["head"]).lower()
    if args.role == "planner-init" and base_commit != head_commit:
        raise RalphError(
            "planner-init Base commit must equal the worktree HEAD before its checkpoint"
        )
    chain = task_commit_chain(
        workspace_root,
        args.task_id,
        base_commit,
        head_commit,
        current_plan=checkpoint_plan,
        require_initialized=args.role != "planner-init",
    )
    assert_next_checkpoint(chain, args.role, args.iteration)
    assert_default_git_index_flags(
        workspace_root,
        scopes,
        label=(
            "snapshot members"
            if args.role == "implementer"
            else f"{args.role} authority paths"
        ),
    )

    validation_phase = {
        "planner-init": "planned",
        "planner-replan": "planned",
        "implementer": "planned",
        "reviewer": "reviewed",
        "closure": "archived",
    }[args.role]
    validation_dir = archive_task_dir if args.role == "closure" else task_dir
    assert validation_dir is not None
    lifecycle_errors, _, _ = validate_task(
        validation_dir,
        workspace_root,
        validation_phase,
        index if validation_phase == "archived" else None,
        artifact_arguments,
    )
    if lifecycle_errors:
        raise RalphError(
            f"{args.role} lifecycle validation failed:\n- "
            + "\n- ".join(lifecycle_errors)
        )

    changed = git_changed_paths(workspace_root)
    if args.role == "planner-init":
        assert_files_trackable_for_checkpoint(
            workspace_root,
            scopes,
            changed,
            label="Planner four-pack/index paths",
        )
    if args.role == "closure":
        missing_closure_paths = sorted(set(scopes) - changed)
        if missing_closure_paths:
            raise RalphError(
                "Closure checkpoint must capture every active deletion, archived "
                "four-pack addition, and index update: "
                + ", ".join(missing_closure_paths)
            )
    if not changed:
        raise RalphError("role checkpoint has no changes to commit")
    outside = sorted(path for path in changed if not path_in_scopes(path, scopes))
    if outside:
        raise RalphError(
            f"{args.role} changed paths outside its authority: " + ", ".join(outside)
        )
    if args.role == "implementer":
        assert_snapshot_trackable_before_commit(
            task_dir,
            workspace_root,
            artifact_arguments,
            changed,
        )

    explicit_paths = sorted(changed)
    run_git(
        workspace_root,
        ["add", "-A", "--", *literal_pathspecs(explicit_paths)],
    )
    staged = git_staged_paths(workspace_root)
    if staged != changed:
        raise RalphError(
            "staged paths differ from the validated role change set: "
            + ", ".join(sorted(staged ^ changed))
        )

    role_label = checkpoint_role_label(args.role)
    trailers = [
        f"Ralph-Task: {args.task_id}",
        f"Ralph-Role: {role_label}",
        f"Ralph-Iteration: {args.iteration}",
    ]
    if snapshot is not None:
        trailers.append(f"Ralph-Snapshot: {snapshot['snapshot_sha256']}")
    if review is not None:
        candidate = str(review["candidate_commit"]).lower()
        if candidate:
            trailers.append(f"Ralph-Candidate: {candidate}")
        verdict = str(review["verdict"])
        if verdict:
            trailers.append(f"Ralph-Verdict: {verdict}")
    if reviewer_checkpoint is not None:
        trailers.append(f"Ralph-Reviewer: {reviewer_checkpoint}")
    subject = args.message or checkpoint_subject(
        args.role,
        args.task_id,
        args.iteration,
        review,
    )
    run_git(
        workspace_root,
        ["commit", "-m", subject, "-m", "\n".join(trailers)],
    )
    commit = run_git(workspace_root, ["rev-parse", "HEAD"]).stdout.strip().lower()
    committed_paths = commit_changed_paths(workspace_root, commit)
    if committed_paths != changed:
        raise RalphError(
            "commit paths differ from the validated role change set: "
            + ", ".join(sorted(committed_paths ^ changed))
        )
    committed_chain = task_commit_chain(
        workspace_root,
        args.task_id,
        base_commit,
        commit,
        current_plan=checkpoint_plan,
        require_initialized=True,
    )
    if not committed_chain or committed_chain[-1]["commit"] != commit:
        raise RalphError("new role commit is not the terminal Ralph checkpoint")
    if args.role == "implementer":
        assert_snapshot_matches_commit(
            task_dir,
            workspace_root,
            artifact_arguments,
            commit,
        )
    remaining = git_changed_paths(workspace_root)
    if remaining:
        raise RalphError(
            "checkpoint commit completed but hooks left the worktree dirty: "
            + ", ".join(sorted(remaining))
        )
    print(
        json.dumps(
            {
                "task_id": args.task_id,
                "role": role_label,
                "iteration": args.iteration,
                "branch": context["branch"],
                "commit": commit,
                "snapshot_sha256": (
                    snapshot["snapshot_sha256"] if snapshot is not None else None
                ),
                "changed_paths": sorted(changed),
                "clean": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def handoff_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    task_dir = resolve_existing(
        workspace_path(args.task_dir, workspace_root, "archived task directory"),
        "archived task directory",
    )
    index = resolve_existing(
        workspace_path(args.index, workspace_root, "task index"),
        "task index",
    )
    texts = require_four_pack(task_dir)
    identity = task_identity(task_dir, texts["proposal.md"])
    context = require_loop_git_context(
        workspace_root,
        identity,
        require_linked=not args.allow_primary_worktree,
    )
    if not bool(context["clean"]):
        raise RalphError("manual-merge handoff requires a clean worktree")
    handoff_required_files = [
        git_relative(task_dir / name, workspace_root, f"archived {name}")
        for name in FOUR_PACK
    ]
    handoff_required_files.append(
        git_relative(index, workspace_root, "task index")
    )
    assert_commit_contains_files(
        workspace_root,
        str(context["head"]),
        handoff_required_files,
        label="archived four-pack/index paths",
    )
    handoff_scopes = snapshot_git_paths(
        task_dir,
        workspace_root,
        args.artifact,
    )
    handoff_scopes.extend(
        [
            git_relative(task_dir / "verify.md", workspace_root, "verify"),
            git_relative(index, workspace_root, "task index"),
        ]
    )
    assert_default_git_index_flags(
        workspace_root,
        handoff_scopes,
        label="handoff paths",
    )
    errors, warnings, snapshot = validate_task(
        task_dir,
        workspace_root,
        "archived",
        index,
        args.artifact,
    )
    if errors:
        raise RalphError("archived handoff validation failed:\n- " + "\n- ".join(errors))
    review = latest_review(texts["verify.md"])
    assert review is not None
    head = str(context["head"])
    trailers = commit_trailers(workspace_root, head)
    closure_parents = commit_parents(workspace_root, head)
    if len(closure_parents) != 1:
        raise RalphError("Closure checkpoint must have exactly one Reviewer parent")
    reviewer_commit = closure_parents[0]
    required_trailers = {
        "ralph-task": identity,
        "ralph-role": "Closure",
        "ralph-snapshot": str(snapshot["snapshot_sha256"]),
        "ralph-candidate": str(review["candidate_commit"]),
        "ralph-verdict": "ACCEPTED",
        "ralph-reviewer": reviewer_commit,
    }
    for key, expected in required_trailers.items():
        actual = trailers.get(key, "")
        if actual.casefold() != expected.casefold():
            raise RalphError(
                f"closure commit trailer {key} is {actual or 'missing'}, expected {expected}"
            )
    assert_reviewer_checkpoint(
        workspace_root,
        identity,
        review,
        str(snapshot["snapshot_sha256"]),
        review_commit=reviewer_commit,
        current_verify=task_dir / "verify.md",
    )
    base_commit = summary_field(texts["plan.md"], "Base commit").lower()
    chain = task_commit_chain(
        workspace_root,
        identity,
        base_commit,
        head,
        current_plan=texts["plan.md"],
        require_initialized=True,
    )
    if (
        not chain
        or chain[-1]["commit"] != head
        or chain[-1]["role"] != "Closure"
        or chain[-1]["verdict"] != "ACCEPTED"
    ):
        raise RalphError(
            "manual-merge handoff requires a terminal ACCEPTED Closure checkpoint"
        )
    commits = [
        (
            f"{item['commit']}\t"
            + run_git(
                workspace_root,
                ["show", "-s", "--format=%s", str(item["commit"])],
            ).stdout.strip()
        )
        for item in chain
    ]
    changed_paths = sorted(
        nul_paths(
            run_git(
                workspace_root,
                [
                    "diff",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    base_commit,
                    head,
                ],
            ).stdout
        )
    )
    artifacts = [
        display_path(path, workspace_root)
        for path in artifact_paths(texts["plan.md"], workspace_root, args.artifact)
    ]
    print(
        json.dumps(
            {
                "merge_ready": True,
                "merge_mode": "manual",
                "task_id": identity,
                "worktree": str(workspace_root),
                "branch": context["branch"],
                "base_commit": base_commit,
                "closure_commit": head,
                "accepted_candidate_commit": review["candidate_commit"],
                "accepted_snapshot_sha256": snapshot["snapshot_sha256"],
                "deliverables": artifacts,
                "changed_paths": changed_paths,
                "commits": commits,
                "warnings": warnings,
                "next": (
                    "User manually merges this branch. The plugin will not "
                    "merge, push, rebase, delete the worktree, or maintain an integration queue. "
                    "If conflict resolution changes any accepted snapshot member, run a new "
                    "Implementer and independent Reviewer pass on the merged bytes."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def init_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    tasks_root = workspace_path(args.tasks_root, workspace_root, "tasks root")
    archive_root = (
        workspace_path(args.archive_root, workspace_root, "archive root")
        if args.archive_root
        else tasks_root / "archive"
    )
    validate_task_id(args.task_id)
    slug = args.slug or slugify(args.title)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise RalphError("slug must use lower-case letters, digits, and single hyphens only")
    directory_name = f"{args.task_id}-{slug}"
    for root in (tasks_root, archive_root):
        if not root.exists():
            continue
        for candidate in root.iterdir():
            if candidate.is_dir() and (
                candidate.name == args.task_id or candidate.name.startswith(args.task_id + "-")
            ):
                raise RalphError(f"task ID already exists: {candidate}")

    template_dir = (
        resolve_existing(
            workspace_path(args.template_dir, workspace_root, "template directory"),
            "template directory",
        )
        if args.template_dir
        else DEFAULT_TEMPLATE_ROOT / "task"
    )
    for name in FOUR_PACK:
        if not (template_dir / name).is_file():
            raise RalphError(f"template directory is missing {name}: {template_dir}")

    task_dir = ensure_within(tasks_root / directory_name, workspace_root, "task directory")
    task_dir.mkdir(parents=True, exist_ok=False)
    now = utc_now()
    run_id = args.run_id or f"{args.task_id}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    git_context = git_context_data(workspace_root)
    tokens = {
        "TASK_TITLE": args.title,
        "TASK_ID": args.task_id,
        "RUN_ID": run_id,
        "DATE": now.date().isoformat(),
        "WORKSPACE_ROOT": str(workspace_root),
        "WORKTREE_ROOT": str(workspace_root),
        "GIT_BRANCH": (
            str(git_context["branch"]) if git_context is not None else "N/A"
        ),
        "BASE_COMMIT": (
            str(git_context["head"]) if git_context is not None else "N/A"
        ),
        "MERGE_MODE": "Manual; no automatic merge or push",
    }
    try:
        for name in FOUR_PACK:
            atomic_write(task_dir / name, replace_tokens(read_text(template_dir / name), tokens))
    except Exception:
        shutil.rmtree(task_dir)
        raise

    index_path = (
        workspace_path(args.index, workspace_root, "index")
        if args.index
        else tasks_root / "index.md"
    )
    index_updated = False
    if not index_path.exists():
        atomic_write(index_path, read_text(DEFAULT_TEMPLATE_ROOT / "index.md"))
    index_text = read_text(index_path)
    if ACTIVE_START in index_text and ACTIVE_END in index_text:
        safe_title = args.title.replace("|", "\\|").replace("\n", " ")
        row = f"| [`{directory_name}`](./{directory_name}/proposal.md) | Proposed | {safe_title} |"
        atomic_write(
            index_path,
            insert_marker_row(index_text, ACTIVE_START, ACTIVE_END, row),
        )
        index_updated = True

    print(
        json.dumps(
            {
                "task_dir": str(task_dir),
                "run_id": run_id,
                "index": str(index_path),
                "index_updated": index_updated,
                "next": (
                    "Planner must populate the four-pack."
                    if index_updated
                    else "Planner must populate the four-pack and update the project-specific index."
                ),
            },
            indent=2,
        )
    )
    return 0


def snapshot_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    task_dir = resolve_existing(
        workspace_path(args.task_dir, workspace_root, "task directory"),
        "task directory",
    )
    require_four_pack(task_dir)
    data = snapshot_data(task_dir, workspace_root, args.artifact)
    git_context = git_context_data(workspace_root)
    if git_context is not None:
        data["git"] = {
            "branch": git_context["branch"],
            "candidate_commit": git_context["head"],
            "linked_worktree": git_context["linked_worktree"],
            "clean": git_context["clean"],
        }
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def validate_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    task_dir = resolve_existing(
        workspace_path(args.task_dir, workspace_root, "task directory"),
        "task directory",
    )
    index = None
    if args.index:
        index = resolve_existing(
            workspace_path(args.index, workspace_root, "task index"),
            "task index",
        )
    errors, warnings, snapshot = validate_task(
        task_dir,
        workspace_root,
        args.phase,
        index,
        args.artifact,
    )
    result = {
        "phase": args.phase,
        "task_dir": str(task_dir),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "snapshot_sha256": snapshot["snapshot_sha256"],
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


def archive_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    task_dir = resolve_existing(
        workspace_path(args.task_dir, workspace_root, "task directory"),
        "task directory",
    )
    archive_root = workspace_path(args.archive_root, workspace_root, "archive root")
    index = resolve_existing(
        workspace_path(args.index, workspace_root, "task index"),
        "task index",
    )
    if is_within(index, task_dir):
        raise RalphError("task index must be outside the task directory")

    errors, warnings, snapshot = validate_task(
        task_dir,
        workspace_root,
        "accepted",
        None,
        args.artifact,
    )
    if errors:
        raise RalphError("task is not accepted:\n- " + "\n- ".join(errors))
    git_context = git_context_data(workspace_root)
    if git_context is not None:
        if not bool(git_context["clean"]):
            raise RalphError(
                "archive requires a clean worktree after the Reviewer checkpoint"
            )
        verify = read_text(task_dir / "verify.md")
        review = latest_review(verify)
        assert review is not None
        assert_reviewer_checkpoint(
            workspace_root,
            task_identity(task_dir, read_text(task_dir / "proposal.md")),
            review,
            str(snapshot["snapshot_sha256"]),
            current_verify=task_dir / "verify.md",
        )
        task_id = task_identity(task_dir, read_text(task_dir / "proposal.md"))
        plan_text = read_text(task_dir / "plan.md")
        base_commit = summary_field(plan_text, "Base commit").lower()
        chain = task_commit_chain(
            workspace_root,
            task_id,
            base_commit,
            str(git_context["head"]),
            current_plan=plan_text,
            require_initialized=True,
        )
        assert_next_checkpoint(
            chain,
            "closure",
            int(review["number"]),
        )
    entries = sorted(path.name for path in task_dir.iterdir())
    if entries != sorted(FOUR_PACK):
        extra = sorted(set(entries) - set(FOUR_PACK))
        raise RalphError(
            "archive moves only an exact four-pack; move retained outputs outside the task "
            f"directory first. Extra entries: {', '.join(extra) or 'none'}"
        )

    plan = read_text(task_dir / "plan.md")
    artifacts = artifact_paths(plan, workspace_root, args.artifact)
    if git_context is not None:
        archive_scopes = snapshot_git_paths(
            task_dir,
            workspace_root,
            args.artifact,
        )
        archive_scopes.extend(
            [
                git_relative(task_dir / "verify.md", workspace_root, "verify"),
                git_relative(index, workspace_root, "task index"),
            ]
        )
        assert_default_git_index_flags(
            workspace_root,
            archive_scopes,
            label="archive paths",
        )
    destination = ensure_within(
        archive_root / task_dir.name, workspace_root, "archive destination"
    )
    if git_context is not None:
        active_files = [
            git_relative(task_dir / name, workspace_root, f"active {name}")
            for name in FOUR_PACK
        ]
        index_relative = git_relative(index, workspace_root, "task index")
        assert_commit_contains_files(
            workspace_root,
            str(git_context["head"]),
            [*active_files, index_relative],
            label="active four-pack/index paths",
        )
        future_archive_files = [
            git_relative(destination / name, workspace_root, f"archived {name}")
            for name in FOUR_PACK
        ]
        assert_paths_not_ignored(
            workspace_root,
            future_archive_files,
            label="archive destination paths",
        )
    if is_within(destination, task_dir):
        raise RalphError("archive destination must be outside the active task directory")
    for artifact in artifacts:
        if is_within(artifact, task_dir):
            raise RalphError(
                f"deliverable must remain outside the archived four-pack: {artifact}"
            )
        if artifact == index or (
            artifact.is_dir()
            and (is_within(destination, artifact) or is_within(index, artifact))
        ):
            raise RalphError(
                "archive destination or index update would mutate declared deliverable: "
                f"{artifact}"
            )

    index_text = read_text(index)
    for start, end in (
        (ACTIVE_START, ACTIVE_END),
        (ARCHIVE_START, ARCHIVE_END),
    ):
        marker_block(index_text, start, end)
    proposal = read_text(task_dir / "proposal.md")
    identity = task_identity(task_dir, proposal)
    active_start, active_end = marker_block(index_text, ACTIVE_START, ACTIVE_END)
    active_names = {
        name
        for line in index_text[active_start:active_end].splitlines()
        if (name := index_row_task_name(line)) is not None
    }
    if task_dir.name not in active_names:
        raise RalphError(f"managed index has no active row for {identity}")

    if destination.exists():
        raise RalphError(f"archive destination already exists: {destination}")
    archive_root.mkdir(parents=True, exist_ok=True)

    verify = read_text(task_dir / "verify.md")
    review = latest_review(verify)
    assert review is not None
    relative_proposal = os.path.relpath(destination / "proposal.md", index.parent)
    artifact_links = []
    for artifact in artifacts:
        artifact_links.append(
            artifact_index_link(
                artifact,
                index,
                workspace_root,
            )
        )
    deliverable_cell = "<br>".join(artifact_links) if artifact_links else "See plan.md"
    candidate_commit = str(review["candidate_commit"]).lower()
    candidate_cell = f"`{candidate_commit}`" if candidate_commit else "N/A"
    archive_row = (
        f"| [`{task_dir.name}`]({relative_proposal}) | {deliverable_cell} | ACCEPTED | "
        f"{review['number']} | `{snapshot['snapshot_sha256']}` | {candidate_cell} |"
    )
    updated_index = remove_marker_task_row(
        index_text,
        ACTIVE_START,
        ACTIVE_END,
        task_dir.name,
    )
    updated_index = insert_marker_row(
        updated_index,
        ARCHIVE_START,
        ARCHIVE_END,
        archive_row,
    )

    moved = False
    index_updated = False
    try:
        moved = True
        os.replace(task_dir, destination)
        index_updated = True
        atomic_write(index, updated_index)
        post_errors, _, post_snapshot = validate_task(
            destination,
            workspace_root,
            "archived",
            index,
            args.artifact,
        )
        if post_errors:
            raise RalphError(
                "post-archive validation failed:\n- " + "\n- ".join(post_errors)
            )
        if post_snapshot["snapshot_sha256"] != snapshot["snapshot_sha256"]:
            raise RalphError("archive changed the accepted candidate snapshot")
    except (Exception, KeyboardInterrupt):
        rollback_errors: list[str] = []
        if index_updated:
            try:
                atomic_write(index, index_text)
            except Exception as exc:
                rollback_errors.append(f"index rollback failed: {exc}")
        if moved and destination.exists() and not task_dir.exists():
            try:
                os.replace(destination, task_dir)
            except Exception as exc:
                rollback_errors.append(f"task rollback failed: {exc}")
        if rollback_errors:
            raise RalphError("; ".join(rollback_errors))
        raise

    print(
        json.dumps(
            {
                "archived_task_dir": str(destination),
                "index": str(index),
                "deliverables_preserved": [str(path) for path in artifacts],
                "warnings": warnings,
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "accepted_candidate_commit": review["candidate_commit"],
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create isolated worktrees, checkpoint roles, validate evidence, archive, "
            "and prepare a manual-merge handoff for an R&D Ralph task."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    worktree_parser = subparsers.add_parser(
        "worktree-create",
        help="create a dedicated linked worktree and ralph/TASK-ID branch",
    )
    worktree_parser.add_argument("--repo-root", required=True)
    worktree_parser.add_argument("--worktree-path", required=True)
    worktree_parser.add_argument("--task-id", required=True)
    worktree_parser.add_argument("--base")
    worktree_parser.set_defaults(handler=worktree_create_command)

    context_parser = subparsers.add_parser(
        "git-context",
        help="inspect or enforce the current loop worktree and branch",
    )
    context_parser.add_argument("--workspace-root", required=True)
    context_parser.add_argument("--task-id")
    context_parser.add_argument("--require-git", action="store_true")
    context_parser.add_argument("--require-clean", action="store_true")
    context_parser.add_argument("--allow-primary-worktree", action="store_true")
    context_parser.set_defaults(handler=git_context_command)

    init_parser = subparsers.add_parser("init", help="create a four-document task pack")
    init_parser.add_argument("--workspace-root", required=True)
    init_parser.add_argument("--tasks-root", required=True)
    init_parser.add_argument("--archive-root")
    init_parser.add_argument("--index")
    init_parser.add_argument("--template-dir")
    init_parser.add_argument("--task-id", required=True)
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--slug")
    init_parser.add_argument("--run-id")
    init_parser.set_defaults(handler=init_command)

    snapshot_parser = subparsers.add_parser(
        "snapshot", help="hash proposal/design/plan and required deliverables"
    )
    snapshot_parser.add_argument("--workspace-root", required=True)
    snapshot_parser.add_argument("--task-dir", required=True)
    snapshot_parser.add_argument("--artifact", action="append", default=[])
    snapshot_parser.set_defaults(handler=snapshot_command)

    validate_parser = subparsers.add_parser("validate", help="validate a lifecycle phase")
    validate_parser.add_argument("--workspace-root", required=True)
    validate_parser.add_argument("--task-dir", required=True)
    validate_parser.add_argument(
        "--phase",
        required=True,
        choices=("planned", "reviewed", "accepted", "archived"),
    )
    validate_parser.add_argument("--index")
    validate_parser.add_argument("--artifact", action="append", default=[])
    validate_parser.set_defaults(handler=validate_command)

    archive_parser = subparsers.add_parser(
        "archive", help="archive an accepted exact four-pack with a marker-managed index"
    )
    archive_parser.add_argument("--workspace-root", required=True)
    archive_parser.add_argument("--task-dir", required=True)
    archive_parser.add_argument("--archive-root", required=True)
    archive_parser.add_argument("--index", required=True)
    archive_parser.add_argument("--artifact", action="append", default=[])
    archive_parser.set_defaults(handler=archive_command)

    checkpoint_parser = subparsers.add_parser(
        "checkpoint",
        help="validate one role's path authority and create a scoped Git commit",
    )
    checkpoint_parser.add_argument("--workspace-root", required=True)
    checkpoint_parser.add_argument("--task-dir", required=True)
    checkpoint_parser.add_argument("--task-id", required=True)
    checkpoint_parser.add_argument(
        "--role",
        required=True,
        choices=(
            "planner-init",
            "planner-replan",
            "implementer",
            "reviewer",
            "closure",
        ),
    )
    checkpoint_parser.add_argument("--iteration", type=int, required=True)
    checkpoint_parser.add_argument("--index")
    checkpoint_parser.add_argument("--archive-task-dir")
    checkpoint_parser.add_argument("--artifact", action="append", default=[])
    checkpoint_parser.add_argument(
        "--allow-new-deliverable",
        action="append",
        default=[],
    )
    checkpoint_parser.add_argument("--allow-contract-change", action="store_true")
    checkpoint_parser.add_argument("--allow-primary-worktree", action="store_true")
    checkpoint_parser.add_argument("--message")
    checkpoint_parser.set_defaults(handler=checkpoint_command)

    handoff_parser = subparsers.add_parser(
        "handoff",
        help="validate and describe a branch for user-controlled manual integration",
    )
    handoff_parser.add_argument("--workspace-root", required=True)
    handoff_parser.add_argument("--task-dir", required=True)
    handoff_parser.add_argument("--index", required=True)
    handoff_parser.add_argument("--artifact", action="append", default=[])
    handoff_parser.add_argument("--allow-primary-worktree", action="store_true")
    handoff_parser.set_defaults(handler=handoff_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except RalphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
