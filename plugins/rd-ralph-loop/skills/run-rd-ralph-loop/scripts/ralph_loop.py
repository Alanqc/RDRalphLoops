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
FINDING_TYPES = {
    "SUBJECT_DEFECT",
    "ASSURANCE_DEFECT",
    "CONTRACT_GAP",
    "EXTERNAL_BLOCKER",
}
FINDING_ACTIONS = {
    "SUBJECT_FIX",
    "SHRINK_ASSURANCE",
    "DIRECT_RECOMPUTE",
    "MINIMAL_LOCAL_FIX",
    "REPLAN",
    "UNBLOCK_EXTERNAL",
    "ESCALATE",
    "CLOSE",
}
ASSURANCE_ACTIONS = {
    "SHRINK_ASSURANCE",
    "DIRECT_RECOMPUTE",
    "MINIMAL_LOCAL_FIX",
    "ESCALATE",
}
PAUSE_REASONS = {
    "EXTERNAL",
    "BUDGET",
    "ASSURANCE",
    "REPLAN_STORM",
    "USER_CHECKPOINT",
    "PLAN_CONFLICT",
    "CONFIGURATION_GAP",
    "SCHEMA_MIGRATION",
}
PAUSE_RESUME_ROLES = {
    "EXTERNAL": {"Planner", "Implementer"},
    "BUDGET": {"Planner", "Implementer"},
    "ASSURANCE": {"Planner", "Implementer"},
    "REPLAN_STORM": {"Planner"},
    "USER_CHECKPOINT": {"Planner", "Implementer"},
    "PLAN_CONFLICT": {"Planner", "Implementer"},
    "CONFIGURATION_GAP": {"Planner"},
    "SCHEMA_MIGRATION": {"Planner"},
}
CONTROL_ACTIONS = {
    "PAUSE",
    "RESUME",
    "PLAN_QUERY",
    "PLAN_RESPONSE",
    "ABANDON",
    "SPLIT",
}
PLAN_RESPONSE_DECISIONS = {
    "CLARIFIED",
    "REPLAN_REQUIRED",
    "CONTRACT_CHANGE_REQUIRED",
    "EXTERNAL_BLOCKER",
}
GUARD_DEFAULTS = {
    "CODE": {
        "warning": 3000,
        "iteration_pause": 5000,
        "cumulative_pause": 12000,
        "per_path_pause": 6000,
    },
    "DOCUMENT": {
        "warning": 10000,
        "iteration_pause": 20000,
        "cumulative_pause": 50000,
        "per_path_pause": 30000,
    },
}
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
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
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
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
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


def trailer_list(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RalphError(f"invalid JSON list trailer: {raw}") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RalphError(f"invalid JSON list trailer: {raw}")
    return value


def initial_checkpoint_state() -> dict[str, object]:
    return {
        "status": "ACTIVE",
        "expected": {("Planner", 0)},
        "suspended_expected": set(),
        "pause_reasons": set(),
        "pause_episode_reasons": set(),
        "required_pause_reasons": set(),
        "resume_override": set(),
        "resume_grant": False,
        "resolved_external": False,
        "pending_query": "",
        "query_counts": {},
        "last_substantive": None,
    }


def apply_checkpoint_entry(
    state: dict[str, object],
    entry: dict[str, object],
) -> None:
    role = str(entry["role"])
    iteration = int(entry["iteration"])
    expected = state["expected"]
    assert isinstance(expected, set)
    if role != "Control":
        if state["status"] != "ACTIVE" or (role, iteration) not in expected:
            wanted = ", ".join(
                f"{item_role} iteration {item_iteration}"
                for item_role, item_iteration in sorted(expected)
            ) or "no role checkpoint"
            raise RalphError(
                f"invalid Ralph checkpoint sequence: found {role} iteration "
                f"{iteration}; expected {wanted} while state is {state['status']}"
            )
        previous = state["last_substantive"]
        if role == "Reviewer":
            if not isinstance(previous, dict) or previous["role"] != "Implementer":
                raise RalphError("Reviewer must immediately follow an Implementer candidate")
            if entry["candidate"] != previous["commit"]:
                raise RalphError(
                    f"Reviewer checkpoint {entry['commit']} is not bound to its "
                    "immediately preceding Implementer"
                )
            if entry["snapshot"] != previous["snapshot"]:
                raise RalphError(
                    f"Reviewer checkpoint {entry['commit']} snapshot differs from "
                    "its Implementer candidate"
                )
        if role == "Closure":
            if not isinstance(previous, dict) or previous["role"] != "Reviewer":
                raise RalphError("Closure must immediately follow an accepted Reviewer")
            if entry["reviewer"] != previous["commit"]:
                raise RalphError(
                    f"Closure checkpoint {entry['commit']} is not bound to its "
                    "immediately preceding Reviewer"
                )
            if (
                entry["candidate"] != previous["candidate"]
                or entry["snapshot"] != previous["snapshot"]
                or entry["verdict"] != previous["verdict"]
            ):
                raise RalphError(
                    f"Closure checkpoint {entry['commit']} does not preserve the "
                    "Reviewer acceptance binding"
                )
        if role in {"Reviewer", "Closure"}:
            state["resume_grant"] = False
            state["resume_override"] = set()
            state["pause_episode_reasons"] = set()
        state["last_substantive"] = entry
        state["suspended_expected"] = set()
        if role == "Planner":
            state["expected"] = {
                ("Implementer", 1 if iteration == 0 else iteration)
            }
        elif role == "Implementer":
            state["expected"] = {("Reviewer", iteration)}
        elif role == "Reviewer":
            verdict = str(entry["verdict"])
            if verdict == "ACCEPTED":
                state["expected"] = {("Closure", iteration)}
            elif verdict == "BLOCKED":
                state["resolved_external"] = False
                state["status"] = "AWAITING_PAUSE"
                state["pause_reasons"] = set()
                state["required_pause_reasons"] = {"EXTERNAL"}
                state["expected"] = set()
                state["suspended_expected"] = {
                    ("Planner", iteration + 1),
                    ("Implementer", iteration + 1),
                }
            elif verdict == "NEEDS_REPLAN":
                state["expected"] = {("Planner", iteration + 1)}
            else:
                state["expected"] = {
                    ("Planner", iteration + 1),
                    ("Implementer", iteration + 1),
                }
        else:
            state["status"] = "CLOSED"
            state["expected"] = set()
        return

    if state["status"] in {"CLOSED", "ABANDONED"}:
        raise RalphError(f"{state['status']} is terminal; no Control event is allowed")
    action = str(entry["control_action"])
    reasons = set(entry["pause_reasons"])
    if action not in CONTROL_ACTIONS:
        raise RalphError(
            f"Control checkpoint {entry['commit']} has invalid action "
            f"{action or 'missing'}"
        )
    if reasons - PAUSE_REASONS:
        raise RalphError(
            "Control checkpoint has invalid pause reasons: "
            + ", ".join(sorted(reasons - PAUSE_REASONS))
        )
    if action == "PAUSE":
        if not reasons:
            raise RalphError("PAUSE requires at least one reason")
        if state["status"] == "ACTIVE" and any(
            target_role == "Closure" for target_role, _ in expected
        ):
            raise RalphError(
                "an ACCEPTED review may only close or be explicitly abandoned"
            )
        if "EXTERNAL" in reasons and not entry["references"]:
            raise RalphError("PAUSE(EXTERNAL) requires an evidence --reference")
        required_reasons = set(state["required_pause_reasons"])
        if not required_reasons.issubset(reasons):
            raise RalphError(
                "PAUSE must include required reasons: "
                + ", ".join(sorted(required_reasons))
            )
        already_paused = state["status"] == "PAUSED"
        if not already_paused:
            if not state["suspended_expected"]:
                state["suspended_expected"] = set(expected)
            state["pause_episode_reasons"] = set()
        state["pause_episode_reasons"] = (
            set(state["pause_episode_reasons"]) | reasons
        )
        suspended = state["suspended_expected"]
        assert isinstance(suspended, set)
        if reasons & {
            "EXTERNAL",
            "BUDGET",
            "ASSURANCE",
            "USER_CHECKPOINT",
            "CONFIGURATION_GAP",
            "SCHEMA_MIGRATION",
        }:
            recovery_sources = [
                (target_role, target_iteration)
                for target_role, target_iteration in list(suspended or expected)
                if target_role in {"Planner", "Implementer"}
            ]
            suspended.update(
                ("Planner", target_iteration)
                for _, target_iteration in recovery_sources
            )
        state["status"] = "PAUSED"
        state["resume_grant"] = False
        state["resume_override"] = set()
        if "EXTERNAL" in reasons:
            state["resolved_external"] = False
        state["pause_reasons"] = set(state["pause_reasons"]) | reasons
        state["required_pause_reasons"] = set()
        state["expected"] = set()
    elif action == "RESUME":
        if state["status"] != "PAUSED":
            raise RalphError("RESUME requires a PAUSED task")
        if state["pending_query"]:
            raise RalphError(
                "RESUME cannot bypass an open plan query; record PLAN_RESPONSE "
                "or explicitly split/abandon"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry["authorization"])):
            raise RalphError("RESUME requires an audited user authorization")
        if not entry["references"]:
            raise RalphError("RESUME requires a resolution-evidence --reference")
        active_reasons = set(state["pause_reasons"])
        if not reasons or not reasons.issubset(active_reasons):
            raise RalphError(
                "RESUME reasons must be a non-empty subset of active pause reasons"
            )
        remaining = active_reasons - reasons
        if "EXTERNAL" in reasons:
            state["resolved_external"] = True
        state["pause_reasons"] = remaining
        if not remaining:
            resume_role = str(entry["resume_role"])
            target = (resume_role, iteration)
            episode_reasons = set(state["pause_episode_reasons"])
            allowed_roles = {"Planner", "Implementer"}
            for reason in episode_reasons:
                allowed_roles &= PAUSE_RESUME_ROLES[reason]
            if resume_role not in allowed_roles:
                raise RalphError(
                    f"RESUME role {resume_role or 'missing'} is not legal for "
                    + ", ".join(sorted(episode_reasons))
                )
            suspended = state["suspended_expected"]
            assert isinstance(suspended, set)
            if target not in suspended:
                wanted = ", ".join(
                    f"{item_role} iteration {item_iteration}"
                    for item_role, item_iteration in sorted(suspended)
                ) or "no legal resume target"
                raise RalphError(
                    f"RESUME target {resume_role} iteration {iteration} is invalid; "
                    f"expected {wanted}"
                )
            state["status"] = "ACTIVE"
            state["expected"] = {target}
            state["resume_override"] = episode_reasons
            state["resume_grant"] = True
            state["pause_episode_reasons"] = set()
    elif action == "PLAN_QUERY":
        if state["status"] != "ACTIVE" or state["pending_query"]:
            raise RalphError("PLAN_QUERY requires active Implementer work and no open query")
        implementer_targets = [
            target for target in expected if target[0] == "Implementer"
        ]
        if len(implementer_targets) != 1 or implementer_targets[0][1] != iteration:
            raise RalphError("PLAN_QUERY is only legal before an Implementer candidate")
        query_id = str(entry["pq_id"])
        if not re.fullmatch(r"PQ-\d{3,}", query_id):
            raise RalphError("PLAN_QUERY requires a PQ-NNN identifier")
        if not any(
            re.fullmatch(r"(?:ITEM|DEL|AC)-\d{3,}", value.upper())
            for value in entry["references"]
        ):
            raise RalphError("PLAN_QUERY requires at least one ITEM/DEL/AC --reference")
        counts = state["query_counts"]
        assert isinstance(counts, dict)
        counts[iteration] = int(counts.get(iteration, 0)) + 1
        state["pending_query"] = query_id
        state["expected"] = set()
        state["suspended_expected"] = {("Implementer", iteration)}
        if counts[iteration] >= 2:
            state["status"] = "PAUSED"
            state["resume_grant"] = False
            state["resume_override"] = set()
            state["pause_reasons"] = set(state["pause_reasons"]) | {"PLAN_CONFLICT"}
            state["pause_episode_reasons"] = (
                set(state["pause_episode_reasons"]) | {"PLAN_CONFLICT"}
            )
        else:
            state["status"] = "CONSULTING"
    elif action == "PLAN_RESPONSE":
        if str(entry["pq_id"]) != state["pending_query"]:
            raise RalphError("PLAN_RESPONSE must resolve the currently open PQ-NNN")
        decision = str(entry["plan_decision"])
        if decision not in PLAN_RESPONSE_DECISIONS:
            raise RalphError(
                f"PLAN_RESPONSE has invalid decision {decision or 'missing'}"
            )
        if decision == "EXTERNAL_BLOCKER" and not entry["references"]:
            raise RalphError(
                "PLAN_RESPONSE(EXTERNAL_BLOCKER) requires a dependency/evidence --reference"
            )
        state["pending_query"] = ""
        if decision == "CLARIFIED" and state["status"] != "PAUSED":
            state["status"] = "ACTIVE"
            state["expected"] = {("Implementer", iteration)}
            state["suspended_expected"] = set()
        else:
            reason = {
                "REPLAN_REQUIRED": "PLAN_CONFLICT",
                "CONTRACT_CHANGE_REQUIRED": "USER_CHECKPOINT",
                "EXTERNAL_BLOCKER": "EXTERNAL",
                "CLARIFIED": "PLAN_CONFLICT",
            }[decision]
            state["status"] = "PAUSED"
            state["resume_grant"] = False
            state["resume_override"] = set()
            if reason == "EXTERNAL":
                state["resolved_external"] = False
            state["pause_reasons"] = set(state["pause_reasons"]) | {reason}
            state["pause_episode_reasons"] = (
                set(state["pause_episode_reasons"]) | {reason}
            )
            state["expected"] = set()
            state["suspended_expected"] = (
                {("Planner", iteration)}
                if decision in {"REPLAN_REQUIRED", "CONTRACT_CHANGE_REQUIRED"}
                else {("Planner", iteration), ("Implementer", iteration)}
            )
    elif action == "ABANDON":
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry["authorization"])):
            raise RalphError("ABANDON requires an audited user authorization")
        state["status"] = "ABANDONED"
        state["resume_grant"] = False
        state["resume_override"] = set()
        state["expected"] = set()
        state["pause_reasons"] = set()
        state["pause_episode_reasons"] = set()
    else:
        if (
            not re.fullmatch(r"[0-9a-f]{64}", str(entry["authorization"]))
            or not entry["child_task"]
        ):
            raise RalphError("SPLIT requires user authorization and a child task ID")
        if not entry["transferred_paths"]:
            raise RalphError("SPLIT requires at least one transferred path")
        if state["status"] != "PAUSED":
            state["suspended_expected"] = set(expected)
        state["status"] = "PAUSED"
        state["resume_grant"] = False
        state["resume_override"] = set()
        state["pause_reasons"] = set(state["pause_reasons"]) | {"USER_CHECKPOINT"}
        state["pause_episode_reasons"] = (
            set(state["pause_episode_reasons"]) | {"USER_CHECKPOINT"}
        )
        state["expected"] = set()


def replay_checkpoint_chain(chain: list[dict[str, object]]) -> dict[str, object]:
    state = initial_checkpoint_state()
    for entry in chain:
        apply_checkpoint_entry(state, entry)
    return state


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
    allowed_roles = {"Planner", "Implementer", "Reviewer", "Closure", "Control"}
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
        control_action = trailers.get("ralph-control-action", "").upper()
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
                "control_action": control_action,
                "pause_reasons": trailer_list(
                    trailers.get("ralph-pause-reasons", "")
                ),
                "resume_role": trailers.get("ralph-resume-role", "").title(),
                "authorization": trailers.get(
                    "ralph-authorization-sha256", ""
                ).lower(),
                "pq_id": trailers.get("ralph-plan-query", "").upper(),
                "plan_decision": trailers.get(
                    "ralph-plan-decision", ""
                ).upper(),
                "child_task": trailers.get("ralph-child-task", ""),
                "transferred_paths": trailer_list(
                    trailers.get("ralph-transferred-paths", "")
                ),
                "references": trailer_list(
                    trailers.get("ralph-references", "")
                ),
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

    replay_checkpoint_chain(chain)
    return chain


def assert_next_checkpoint(
    chain: list[dict[str, object]],
    role: str,
    iteration: int,
) -> None:
    role_label = checkpoint_role_label(role)
    state = replay_checkpoint_chain(chain)
    expected = state["expected"]
    assert isinstance(expected, set)
    if state["status"] != "ACTIVE" or (role_label, iteration) not in expected:
        wanted = ", ".join(
            f"{item_role} iteration {item_iteration}"
            for item_role, item_iteration in sorted(expected)
        ) or "no role checkpoint"
        raise RalphError(
            f"next Ralph checkpoint cannot be {role_label} iteration {iteration}; "
            f"state is {state['status']} and expected {wanted}"
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
    value = value.replace(r"\|", "|").strip().strip("`").strip()
    link = re.fullmatch(r"\[[^\]]+\]\(([^)]+)\)", value)
    return link.group(1).strip() if link else value


def split_markdown_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line.strip()[1:-1]:
        if escaped:
            current.extend(("\\", character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current))
    return cells


def markdown_rows(section_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [clean_cell(cell) for cell in split_markdown_row(stripped)]
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
        "class": {"class", "profile", "deliverable class"},
        "guarded": {"guarded", "budget guarded"},
        "budget": {"guard budget", "budget"},
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
                "class": row[columns["class"]] if "class" in columns else "",
                "guarded": row[columns["guarded"]] if "guarded" in columns else "",
                "budget": row[columns["budget"]] if "budget" in columns else "",
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


def parse_findings(review_block: str) -> dict[str, object]:
    rows = markdown_rows(markdown_subsection(review_block, "Findings"))
    if not rows:
        return {"schema": "missing", "findings": [], "errors": []}
    aliases = {
        "id": {"finding", "id"},
        "acs": {"acs", "ac"},
        "type": {"type", "finding type"},
        "severity": {"severity"},
        "status": {"status"},
        "evidence": {"evidence"},
        "action_class": {"action class", "action"},
        "required_action": {"required action", "remediation"},
    }
    header = [cell.casefold() for cell in rows[0]]
    columns: dict[str, int] = {}
    for key, names in aliases.items():
        for index, value in enumerate(header):
            if value in names:
                columns[key] = index
                break
    typed = {"id", "acs", "type", "severity", "status"}.issubset(columns)
    legacy = (
        {"id", "acs", "severity", "status"}.issubset(columns)
        and "type" not in columns
    )
    if not typed and not legacy:
        return {
            "schema": "invalid",
            "findings": [],
            "errors": ["Findings table has invalid or unrecognized columns"],
        }
    parsed: list[dict[str, str]] = []
    errors: list[str] = []
    for row in rows[1:]:
        if "id" not in columns or len(row) <= columns["id"]:
            continue
        finding_id = row[columns["id"]]
        if not re.fullmatch(r"F-\d{3,}", finding_id):
            continue

        def value(key: str) -> str:
            index = columns.get(key)
            return row[index].strip() if index is not None and index < len(row) else ""

        finding = {
            "id": finding_id,
            "acs": value("acs"),
            "type": value("type").upper(),
            "severity": value("severity").upper(),
            "status": value("status").upper(),
            "evidence": value("evidence"),
            "action_class": value("action_class").upper(),
            "required_action": value("required_action"),
        }
        if typed and (
            not finding["type"]
            or not finding["action_class"]
            or not finding["required_action"]
        ):
            errors.append(f"{finding_id} lacks Type, Action class, or Required action")
        parsed.append(finding)
    return {
        "schema": "typed" if typed else "legacy",
        "findings": parsed,
        "errors": errors,
    }


def latest_review(
    verify: str,
    *,
    legacy_findings: bool = False,
) -> dict[str, object] | None:
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

    finding_data = parse_findings(block)
    parsed_findings = finding_data["findings"]
    assert isinstance(parsed_findings, list)
    open_blocking = [
        str(finding["id"])
        for finding in parsed_findings
        if finding["severity"] in {"P0", "P1"} and finding["status"] == "OPEN"
    ]

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
        "findings": parsed_findings,
        "finding_schema": finding_data["schema"],
        "finding_errors": finding_data["errors"],
        "legacy_findings_allowed": legacy_findings,
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


def protocol_version(texts: Iterable[str]) -> int:
    versions = {
        value
        for text in texts
        if (value := summary_field(text, "Protocol version"))
    }
    if not versions:
        return 1
    if len(versions) != 1:
        raise RalphError(
            "four-pack Protocol version fields disagree: " + ", ".join(sorted(versions))
        )
    value = next(iter(versions))
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise RalphError(f"invalid Protocol version: {value}")
    return int(value)


def cell_items(value: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"(?i)<br\s*/?>|;", value)
        if item.strip() and item.strip().casefold() not in {"n/a", "na", "none", "-"}
    ]


def line_limit(value: str, default: int) -> int:
    cleaned = value.strip().replace(",", "").casefold()
    if not cleaned or cleaned == "default":
        return default
    match = re.fullmatch(r"([1-9][0-9]*)\s*(?:lines?)?", cleaned)
    if not match:
        raise RalphError(f"invalid line budget: {value}")
    return int(match.group(1))


def guard_scope(raw: str, workspace_root: Path) -> str:
    value = raw.strip().strip("`")
    value = re.sub(r"/\*\*?$", "", value).rstrip("/")
    path = workspace_path(value, workspace_root, "guarded path")
    return git_relative(path, workspace_root, "guarded path")


def parse_guard_budgets(
    proposal: str,
    workspace_root: Path,
) -> tuple[list[dict[str, object]], list[str]]:
    rows = markdown_rows(markdown_section(proposal, "Guard Budgets"))
    if not rows:
        return [], ["proposal.md has no Guard Budgets table"]
    header = [cell.casefold() for cell in rows[0]]
    wanted = {
        "id": "budget",
        "profile": "profile",
        "paths": "guarded deliverable paths",
        "warning": "warning",
        "iteration_pause": "iteration pause",
        "cumulative_pause": "cumulative pause",
        "per_path_pause": "per-path pause",
        "exclusions": "exclusions",
    }
    columns = {
        key: header.index(label)
        for key, label in wanted.items()
        if label in header
    }
    if not {"id", "profile", "paths"}.issubset(columns):
        return [], ["Guard Budgets table has invalid columns"]
    budgets: list[dict[str, object]] = []
    errors: list[str] = []
    for row in rows[1:]:
        if len(row) <= max(columns.values()):
            continue

        def value(key: str) -> str:
            index = columns.get(key)
            return row[index] if index is not None and index < len(row) else ""

        budget_id = value("id")
        if not budget_id or budget_id.casefold() in {"budget", "n/a"}:
            continue
        profile = value("profile").upper()
        if profile not in GUARD_DEFAULTS:
            errors.append(f"{budget_id} has invalid guard Profile {profile or 'missing'}")
            continue
        defaults = GUARD_DEFAULTS[profile]
        try:
            paths = [
                guard_scope(item, workspace_root)
                for item in cell_items(value("paths"))
            ]
            exclusions: list[str] = []
            for item in cell_items(value("exclusions")):
                if "::" not in item:
                    errors.append(
                        f"{budget_id} exclusion must be 'path :: reason': {item}"
                    )
                    continue
                raw_path, reason = (part.strip() for part in item.split("::", 1))
                if not raw_path or not reason:
                    errors.append(f"{budget_id} has an unreasoned exclusion: {item}")
                    continue
                exclusions.append(guard_scope(raw_path, workspace_root))
            budgets.append(
                {
                    "id": budget_id,
                    "profile": profile,
                    "paths": paths,
                    "exclusions": exclusions,
                    "warning": line_limit(
                        value("warning"), int(defaults["warning"])
                    ),
                    "iteration_pause": line_limit(
                        value("iteration_pause"),
                        int(defaults["iteration_pause"]),
                    ),
                    "cumulative_pause": line_limit(
                        value("cumulative_pause"),
                        int(defaults["cumulative_pause"]),
                    ),
                    "per_path_pause": line_limit(
                        value("per_path_pause"),
                        int(defaults["per_path_pause"]),
                    ),
                }
            )
        except RalphError as exc:
            errors.append(f"{budget_id}: {exc}")
    return budgets, errors


def parse_external_dependencies(proposal: str) -> tuple[list[dict[str, str]], list[str]]:
    rows = markdown_rows(
        markdown_section(proposal, "External Dependency Registry")
    )
    if not rows:
        return [], ["proposal.md has no External Dependency Registry table"]
    header = [cell.casefold() for cell in rows[0]]
    required = {
        "dependency": "dependency",
        "acs": "blocking acs",
        "required_evidence": "required immutable evidence",
        "owner": "owner",
        "status": "initial status",
        "proof": "unblock proof",
    }
    columns = {
        key: header.index(label)
        for key, label in required.items()
        if label in header
    }
    if set(columns) != set(required):
        return [], ["External Dependency Registry has invalid columns"]
    dependencies: list[dict[str, str]] = []
    errors: list[str] = []
    seen: set[str] = set()
    valid_acs = set(extract_ac_ids(proposal))
    for row in rows[1:]:
        if len(row) <= max(columns.values()):
            continue
        dependency = row[columns["dependency"]]
        if dependency.casefold() in {"n/a", "na", "none", "-"}:
            continue
        if not re.fullmatch(r"DEP-\d{3,}", dependency):
            errors.append(f"invalid external dependency ID: {dependency}")
        elif dependency in seen:
            errors.append(f"duplicate external dependency ID: {dependency}")
        seen.add(dependency)
        acs = set(re.findall(r"AC-\d{3,}", row[columns["acs"]]))
        if not acs:
            errors.append(f"{dependency} has no Blocking AC")
        unknown = sorted(acs - valid_acs)
        if unknown:
            errors.append(
                f"{dependency} references unknown Blocking ACs: "
                + ", ".join(unknown)
            )
        if not row[columns["required_evidence"]].strip():
            errors.append(f"{dependency} has no Required immutable evidence")
        if not row[columns["owner"]].strip():
            errors.append(f"{dependency} has no Owner")
        if not row[columns["proof"]].strip():
            errors.append(f"{dependency} has no Unblock proof")
        status = row[columns["status"]].upper()
        if status not in {"READY", "BLOCKED"}:
            errors.append(
                f"{dependency} has invalid external dependency status "
                f"{status or 'missing'}"
            )
        dependencies.append(
            {
                "dependency": dependency,
                "acs": row[columns["acs"]],
                "required_evidence": row[columns["required_evidence"]],
                "owner": row[columns["owner"]],
                "status": status,
                "proof": row[columns["proof"]],
            }
        )
    return dependencies, errors


def deliverable_budget_coverage(
    plan: str,
    budgets: list[dict[str, object]],
    workspace_root: Path,
) -> list[str]:
    guarded = [
        scope
        for budget in budgets
        for scope in budget["paths"]
        if isinstance(scope, str)
    ]
    excluded = [
        scope
        for budget in budgets
        for scope in budget["exclusions"]
        if isinstance(scope, str)
    ]
    errors: list[str] = []
    for item in parse_deliverables(plan):
        try:
            path = git_relative(
                normalize_artifact_path(item["path"], workspace_root),
                workspace_root,
                "deliverable",
            )
        except RalphError as exc:
            errors.append(str(exc))
            continue
        if not path_in_scopes(path, guarded) and not path_in_scopes(path, excluded):
            errors.append(
                f"{item['id']} path {path} is neither budget-guarded nor "
                "explicitly excluded with a reason"
            )
    return errors


def diff_added_lines(
    workspace_root: Path,
    baseline: str,
    scopes: Iterable[str],
    *,
    end: str | None = None,
    include_untracked: bool = False,
) -> tuple[dict[str, int], list[str]]:
    scope_list = sorted(set(scopes))
    if not scope_list:
        return {}, []
    arguments = ["diff", "--numstat", "-z", "--no-renames", baseline]
    if end is not None:
        arguments.append(end)
    arguments.extend(["--", *literal_pathspecs(scope_list)])
    output = run_git_bytes(workspace_root, arguments).stdout
    additions: dict[str, int] = {}
    binary: list[str] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        parts = record.split(b"\t", 2)
        if len(parts) != 3:
            continue
        added, _, raw_path = parts
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if added == b"-":
            binary.append(path)
        elif added.isdigit():
            additions[path] = additions.get(path, 0) + int(added)
    if include_untracked:
        untracked = nul_paths(
            run_git(
                workspace_root,
                ["ls-files", "--others", "--exclude-standard", "-z"],
            ).stdout
        )
        for path in sorted(untracked):
            if not path_in_scopes(path, scope_list):
                continue
            source = workspace_root / path
            if source.is_symlink():
                binary.append(path)
                continue
            line_count = 0
            saw_data = False
            final_byte = b""
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    if b"\0" in chunk:
                        binary.append(path)
                        line_count = -1
                        break
                    saw_data = True
                    final_byte = chunk[-1:]
                    line_count += chunk.count(b"\n")
            if line_count >= 0:
                additions[path] = line_count + int(saw_data and final_byte != b"\n")
    return additions, sorted(set(binary))


def review_guard_metrics(verify: str) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for number, block in sorted(review_blocks(verify).items()):
        data = parse_findings(block)
        findings = data["findings"]
        assert isinstance(findings, list)
        blocking = [
            item
            for item in findings
            if item["status"] == "OPEN" and item["severity"] in {"P0", "P1"}
        ]
        assurance = [
            item for item in blocking if item["type"] == "ASSURANCE_DEFECT"
        ]
        rows.append(
            {
                "iteration": number,
                "verdict": summary_field(block, "Verdict").upper(),
                "blocking": len(blocking),
                "assurance": len(assurance),
                "assurance_ratio": (
                    len(assurance) / len(blocking) if blocking else 0.0
                ),
                "escalated_assurance": any(
                    item["type"] == "ASSURANCE_DEFECT"
                    and item["status"] == "OPEN"
                    and item["action_class"] == "ESCALATE"
                    for item in findings
                ),
                "schema": data["schema"],
            }
        )
    nonaccepted = sum(
        row["verdict"] in VERDICTS - {"ACCEPTED"} for row in rows
    )
    consecutive_replan = 0
    for row in reversed(rows):
        if row["verdict"] != "NEEDS_REPLAN":
            break
        consecutive_replan += 1
    assurance_dominated = 0
    for row in reversed(rows):
        if row["blocking"] and float(row["assurance_ratio"]) >= 0.5:
            assurance_dominated += 1
        else:
            break
    return {
        "reviews": rows,
        "nonaccepted": nonaccepted,
        "consecutive_needs_replan": consecutive_replan,
        "consecutive_assurance_dominated": assurance_dominated,
    }


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


def validate_finding_history(
    verify: str,
    *,
    version: int,
    phase: str,
    legacy_findings: bool,
    valid_acs: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    signatures: dict[str, tuple[str, tuple[str, ...]]] = {}
    for number, block in sorted(review_blocks(verify).items()):
        data = parse_findings(block)
        schema = str(data["schema"])
        findings = data["findings"]
        finding_errors = data["errors"]
        assert isinstance(findings, list)
        assert isinstance(finding_errors, list)
        errors.extend(f"ITER-{number:03d}: {value}" for value in finding_errors)
        if version >= 2 and schema != "typed":
            errors.append(
                f"ITER-{number:03d} Findings must use the protocol-v2 typed schema"
            )
        elif version == 1 and schema == "legacy":
            if phase == "reviewed" and findings and not legacy_findings:
                errors.append(
                    f"ITER-{number:03d} uses legacy Findings; active continuation "
                    "requires --legacy-findings or protocol-v2 migration"
                )
            else:
                warnings.append(
                    f"ITER-{number:03d} uses legacy unclassified Findings"
                )

        seen: set[str] = set()
        for finding in findings:
            finding_id = str(finding["id"])
            finding_type = str(finding["type"])
            action_class = str(finding["action_class"])
            if finding_id in seen:
                errors.append(f"ITER-{number:03d} repeats finding {finding_id}")
            seen.add(finding_id)
            if schema != "typed":
                continue
            if finding_type not in FINDING_TYPES:
                errors.append(
                    f"ITER-{number:03d} {finding_id} has invalid Type "
                    f"{finding_type or 'missing'}"
                )
            if action_class not in FINDING_ACTIONS:
                errors.append(
                    f"ITER-{number:03d} {finding_id} has invalid Action class "
                    f"{action_class or 'missing'}"
                )
            status = str(finding["status"])
            severity = str(finding["severity"])
            if status not in {"OPEN", "CLOSED"}:
                errors.append(
                    f"ITER-{number:03d} {finding_id} has invalid Status "
                    f"{status or 'missing'}"
                )
            if severity not in {"P0", "P1", "P2", "P3"}:
                errors.append(
                    f"ITER-{number:03d} {finding_id} has invalid Severity "
                    f"{severity or 'missing'}"
                )
            if status == "CLOSED" and action_class != "CLOSE":
                errors.append(
                    f"ITER-{number:03d} {finding_id} CLOSED finding must use CLOSE"
                )
            if status == "OPEN" and action_class == "CLOSE":
                errors.append(
                    f"ITER-{number:03d} {finding_id} OPEN finding must not use CLOSE"
                )
            allowed_actions = {
                "SUBJECT_DEFECT": {"SUBJECT_FIX", "CLOSE"},
                "ASSURANCE_DEFECT": ASSURANCE_ACTIONS | {"CLOSE"},
                "CONTRACT_GAP": {"REPLAN", "CLOSE"},
                "EXTERNAL_BLOCKER": {"UNBLOCK_EXTERNAL", "CLOSE"},
            }.get(finding_type, set())
            if action_class not in allowed_actions:
                errors.append(
                    f"ITER-{number:03d} {finding_id} Action class {action_class} "
                    f"is invalid for {finding_type}"
                )
            if (
                finding_type == "ASSURANCE_DEFECT"
                and str(finding["status"]) == "OPEN"
                and action_class not in ASSURANCE_ACTIONS
            ):
                errors.append(
                    f"ITER-{number:03d} {finding_id} open ASSURANCE_DEFECT must use "
                    "SHRINK_ASSURANCE, DIRECT_RECOMPUTE, MINIMAL_LOCAL_FIX, or ESCALATE"
                )
            ac_set = set(re.findall(r"AC-\d{3,}", str(finding["acs"])))
            if not ac_set:
                errors.append(f"ITER-{number:03d} {finding_id} has no AC mapping")
            if valid_acs is not None:
                unknown_acs = sorted(ac_set - valid_acs)
                if unknown_acs:
                    errors.append(
                        f"ITER-{number:03d} {finding_id} maps unknown ACs: "
                        + ", ".join(unknown_acs)
                    )
            if not str(finding["evidence"]).strip():
                errors.append(
                    f"ITER-{number:03d} {finding_id} has no concrete Evidence"
                )
            acs = tuple(sorted(ac_set))
            signature = (finding_type, acs)
            previous = signatures.get(finding_id)
            if previous is not None and previous != signature:
                errors.append(
                    f"{finding_id} changed immutable Type/AC identity across reviews"
                )
            signatures.setdefault(finding_id, signature)

        verdict = summary_field(block, "Verdict").upper()
        open_findings = [
            finding
            for finding in findings
            if str(finding["status"]) == "OPEN"
        ]
        open_external = [
            finding
            for finding in open_findings
            if str(finding["type"]) == "EXTERNAL_BLOCKER"
        ]
        open_contract = [
            finding
            for finding in open_findings
            if str(finding["type"]) == "CONTRACT_GAP"
            and str(finding["action_class"]) == "REPLAN"
        ]
        if schema == "typed":
            if open_external and verdict != "BLOCKED":
                errors.append(
                    f"ITER-{number:03d} has open EXTERNAL_BLOCKER findings, "
                    "so Verdict must be BLOCKED"
                )
            if verdict == "BLOCKED" and not any(
                str(finding["action_class"]) == "UNBLOCK_EXTERNAL"
                for finding in open_external
            ):
                errors.append(
                    f"ITER-{number:03d} BLOCKED requires an open EXTERNAL_BLOCKER "
                    "with UNBLOCK_EXTERNAL"
                )
            if verdict == "NEEDS_REPLAN" and not open_contract:
                errors.append(
                    f"ITER-{number:03d} NEEDS_REPLAN requires an open CONTRACT_GAP "
                    "with REPLAN"
                )
            if open_contract and not open_external and verdict != "NEEDS_REPLAN":
                errors.append(
                    f"ITER-{number:03d} has an open CONTRACT_GAP and no external "
                    "blocker, so Verdict must be NEEDS_REPLAN"
                )
            if verdict == "CHANGES_REQUIRED" and (open_contract or open_external):
                errors.append(
                    f"ITER-{number:03d} CHANGES_REQUIRED permits only open "
                    "SUBJECT_DEFECT or ASSURANCE_DEFECT findings"
                )
    return errors, warnings


def replan_disposition_errors(
    plan: str,
    verify: str,
    iteration: int,
) -> list[str]:
    review = latest_review(verify)
    if review is None:
        return []
    findings = review["findings"]
    assert isinstance(findings, list)
    triggering = {
        str(item["id"]) for item in findings if str(item["status"]) == "OPEN"
    }
    if not triggering:
        return []
    rows = markdown_rows(markdown_section(plan, "Finding Disposition Ledger"))
    if not rows:
        return ["Finding Disposition Ledger is missing"]
    header = [cell.casefold() for cell in rows[0]]
    required = {
        "iteration": "iteration",
        "finding": "finding",
        "disposition": "disposition",
    }
    columns = {
        key: header.index(label)
        for key, label in required.items()
        if label in header
    }
    if set(columns) != set(required):
        return ["Finding Disposition Ledger has invalid columns"]
    dispositions: dict[str, str] = {}
    errors: list[str] = []
    for row in rows[1:]:
        if len(row) <= max(columns.values()):
            continue
        raw_iteration = row[columns["iteration"]].upper()
        if raw_iteration not in {str(iteration), f"ITER-{iteration:03d}"}:
            continue
        finding_id = row[columns["finding"]].upper()
        if not re.fullmatch(r"F-\d{3,}", finding_id):
            continue
        if finding_id in dispositions:
            errors.append(
                f"planner replan repeats disposition for {finding_id}"
            )
        dispositions[finding_id] = row[columns["disposition"]].upper()
    missing = sorted(triggering - set(dispositions))
    unknown = sorted(set(dispositions) - triggering)
    invalid = sorted(
        finding_id
        for finding_id, value in dispositions.items()
        if value not in {"FIX", "DESCOPE", "DEFER", "ESCALATE"}
    )
    if missing:
        errors.append(
            "planner replan has no disposition for open findings: "
            + ", ".join(missing)
        )
    if unknown:
        errors.append(
            "planner replan disposition references non-triggering findings: "
            + ", ".join(unknown)
        )
    if invalid:
        errors.append(
            "planner replan has invalid finding dispositions: "
            + ", ".join(invalid)
        )
    return errors


def validate_task(
    task_dir: Path,
    workspace_root: Path,
    phase: str,
    index: Path | None,
    explicit_artifacts: Iterable[str],
    *,
    legacy_findings: bool = False,
) -> tuple[list[str], list[str], dict[str, object]]:
    texts = require_four_pack(task_dir)
    errors: list[str] = []
    warnings: list[str] = []
    identity = task_identity(task_dir, texts["proposal.md"])
    try:
        version = protocol_version(texts.values())
    except RalphError as exc:
        errors.append(str(exc))
        version = 2
    if version >= 2:
        _, dependency_errors = parse_external_dependencies(
            texts["proposal.md"]
        )
        errors.extend(dependency_errors)
        budgets, budget_errors = parse_guard_budgets(
            texts["proposal.md"], workspace_root
        )
        errors.extend(budget_errors)
        errors.extend(
            deliverable_budget_coverage(
                texts["plan.md"], budgets, workspace_root
            )
        )
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

    finding_errors, finding_warnings = validate_finding_history(
        texts["verify.md"],
        version=version,
        phase=phase,
        legacy_findings=legacy_findings,
        valid_acs=set(ac_ids),
    )
    errors.extend(finding_errors)
    warnings.extend(finding_warnings)
    review = latest_review(
        texts["verify.md"],
        legacy_findings=legacy_findings,
    )
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


def authorization_sha256(token: str | None) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""


def infer_control_iteration(
    state: dict[str, object],
    action: str,
    resume_role: str,
) -> int:
    if action == "RESUME":
        suspended = state["suspended_expected"]
        assert isinstance(suspended, set)
        matches = sorted(
            iteration for role, iteration in suspended if role == resume_role
        )
        if len(matches) != 1:
            raise RalphError(
                f"cannot infer one legal {resume_role} resume iteration"
            )
        return matches[0]
    if action in {"PLAN_QUERY", "PLAN_RESPONSE"}:
        candidates = state["expected"] or state["suspended_expected"]
        assert isinstance(candidates, set)
        iterations = sorted({iteration for _, iteration in candidates})
        if len(iterations) != 1:
            raise RalphError("cannot infer one plan consultation iteration")
        return iterations[0]
    previous = state["last_substantive"]
    return int(previous["iteration"]) if isinstance(previous, dict) else 0


def wip_fingerprint(workspace_root: Path) -> dict[str, object]:
    tracked = run_git_bytes(
        workspace_root,
        ["diff", "--binary", "--no-ext-diff", "HEAD"],
    ).stdout
    untracked = sorted(
        nul_paths(
            run_git(
                workspace_root,
                ["ls-files", "--others", "--exclude-standard", "-z"],
            ).stdout
        )
    )
    entries: list[tuple[str, str]] = []
    for relative in untracked:
        path = workspace_root / relative
        if path.is_file() or path.is_symlink():
            entries.append((relative, str(hash_path(path))))
        else:
            entries.append((relative, "unsupported"))
    return {
        "tracked_sha256": hashlib.sha256(tracked).hexdigest(),
        "untracked": entries,
    }


def legacy_guard_budgets(
    plan: str,
    workspace_root: Path,
) -> list[dict[str, object]]:
    budgets: list[dict[str, object]] = []
    for item in parse_deliverables(plan):
        profile = item["class"].upper()
        if profile not in GUARD_DEFAULTS:
            profile = "CODE"
        defaults = GUARD_DEFAULTS[profile]
        path = git_relative(
            normalize_artifact_path(item["path"], workspace_root),
            workspace_root,
            "deliverable",
        )
        budgets.append(
            {
                "id": f"LEGACY-{item['id']}",
                "profile": profile,
                "paths": [path],
                "exclusions": [],
                **defaults,
            }
        )
    return budgets


def guard_data(
    workspace_root: Path,
    task_dir: Path,
    task_id: str,
    role: str,
    explicit_artifacts: Iterable[str],
    *,
    legacy_findings: bool,
    allow_primary_worktree: bool = False,
) -> dict[str, object]:
    texts = require_four_pack(task_dir)
    if task_identity(task_dir, texts["proposal.md"]) != task_id:
        raise RalphError("--task-id does not match the four-pack")
    context = require_loop_git_context(
        workspace_root,
        task_id,
        require_linked=not allow_primary_worktree,
    )
    base_commit = summary_field(texts["plan.md"], "Base commit").lower()
    chain = task_commit_chain(
        workspace_root,
        task_id,
        base_commit,
        str(context["head"]),
        current_plan=texts["plan.md"],
        require_initialized=True,
    )
    state = replay_checkpoint_chain(chain)
    try:
        version = protocol_version(texts.values())
    except RalphError:
        version = 2
    reasons: set[str] = set()
    details: list[str] = []
    warnings: list[str] = []
    budget_results: list[dict[str, object]] = []
    if state["status"] == "PAUSED":
        reasons.update(state["pause_reasons"])
    elif state["status"] == "AWAITING_PAUSE":
        reasons.update(state["required_pause_reasons"])
    elif state["status"] in {"CLOSED", "ABANDONED", "CONSULTING"}:
        reasons.add("USER_CHECKPOINT")
        details.append(f"lifecycle state {state['status']} has no role continuation")

    if version == 1 and review_blocks(texts["verify.md"]) and not legacy_findings:
        reasons.add("SCHEMA_MIGRATION")
        details.append(
            "protocol-v1 active continuation requires --legacy-findings or migration"
        )
    if version >= 2:
        dependencies, dependency_errors = parse_external_dependencies(
            texts["proposal.md"]
        )
        if dependency_errors:
            reasons.add("CONFIGURATION_GAP")
            details.extend(dependency_errors)
        blocked_dependencies = [
            item["dependency"]
            for item in dependencies
            if item["status"] == "BLOCKED"
        ]
        if blocked_dependencies:
            reasons.add("EXTERNAL")
            details.append(
                "blocked external dependencies: "
                + ", ".join(blocked_dependencies)
            )

    if role == "planner-replan":
        declared_budgets, _ = parse_guard_budgets(
            texts["proposal.md"], workspace_root
        )
        planner_profile = (
            "DOCUMENT"
            if declared_budgets
            and all(item["profile"] == "DOCUMENT" for item in declared_budgets)
            else "CODE"
        )
        planner_limits = (
            {
                "warning": 1000,
                "iteration_pause": 2000,
                "cumulative_pause": 6000,
                "per_path_pause": 4000,
            }
            if planner_profile == "DOCUMENT"
            else {
                "warning": 500,
                "iteration_pause": 1000,
                "cumulative_pause": 3000,
                "per_path_pause": 2000,
            }
        )
        planner_paths = [
            git_relative(task_dir / name, workspace_root, name)
            for name in ("design.md", "plan.md")
        ]
        budgets = [
            {
                "id": "PLANNER-REPLAN-DEFAULT",
                "profile": planner_profile,
                "paths": planner_paths,
                "exclusions": [],
                **planner_limits,
            }
        ]
        cumulative_base = str(chain[0]["commit"])
    elif role == "implementer":
        budgets, configuration = parse_guard_budgets(
            texts["proposal.md"], workspace_root
        )
        if version == 1:
            budgets = legacy_guard_budgets(texts["plan.md"], workspace_root)
            configuration = []
        else:
            configuration.extend(
                deliverable_budget_coverage(
                    texts["plan.md"], budgets, workspace_root
                )
            )
            guarded_scopes = [
                scope for budget in budgets for scope in budget["paths"]
            ]
            excluded_scopes = [
                scope for budget in budgets for scope in budget["exclusions"]
            ]
            for raw in explicit_artifacts:
                path = git_relative(
                    normalize_artifact_path(raw, workspace_root),
                    workspace_root,
                    "explicit artifact",
                )
                if not path_in_scopes(path, guarded_scopes) and not path_in_scopes(
                    path, excluded_scopes
                ):
                    configuration.append(
                        f"explicit artifact {path} has no guard budget or exclusion"
                    )
        if configuration:
            reasons.add("CONFIGURATION_GAP")
            details.extend(configuration)
        cumulative_base = base_commit
    else:
        budgets = []
        cumulative_base = base_commit

    for budget in budgets:
        scopes = list(budget["paths"])
        exclusions = list(budget["exclusions"])
        iteration_lines, iteration_binary = diff_added_lines(
            workspace_root,
            str(context["head"]),
            scopes,
            include_untracked=True,
        )
        cumulative_lines, cumulative_binary = diff_added_lines(
            workspace_root,
            cumulative_base,
            scopes,
            include_untracked=True,
        )
        iteration_lines = {
            path: count
            for path, count in iteration_lines.items()
            if not path_in_scopes(path, exclusions)
        }
        cumulative_lines = {
            path: count
            for path, count in cumulative_lines.items()
            if not path_in_scopes(path, exclusions)
        }
        binary = sorted(
            {
                path
                for path in iteration_binary + cumulative_binary
                if not path_in_scopes(path, exclusions)
            }
        )
        iteration_total = sum(iteration_lines.values())
        cumulative_total = sum(cumulative_lines.values())
        warning_limit = int(budget["warning"])
        iteration_limit = int(budget["iteration_pause"])
        cumulative_limit = int(budget["cumulative_pause"])
        per_path_limit = int(budget["per_path_pause"])
        over_paths = {
            path: count
            for path, count in cumulative_lines.items()
            if count >= per_path_limit
        }
        if iteration_total >= warning_limit:
            warnings.append(
                f"{budget['id']} iteration additions {iteration_total} "
                f"reached warning {warning_limit}"
            )
        if (
            iteration_total >= iteration_limit
            or cumulative_total >= cumulative_limit
            or over_paths
        ):
            reasons.add("BUDGET")
        if binary:
            reasons.add("CONFIGURATION_GAP")
            details.append(
                f"{budget['id']} has guarded binary/non-text paths requiring exclusion: "
                + ", ".join(binary)
            )
        budget_results.append(
            {
                "id": budget["id"],
                "profile": budget["profile"],
                "iteration_added": iteration_total,
                "cumulative_added": cumulative_total,
                "per_path_added": dict(sorted(cumulative_lines.items())),
                "limits": {
                    "warning": warning_limit,
                    "iteration_pause": iteration_limit,
                    "cumulative_pause": cumulative_limit,
                    "per_path_pause": per_path_limit,
                },
                "binary_or_non_text": binary,
            }
        )

    review_metrics = review_guard_metrics(texts["verify.md"])
    if int(review_metrics["consecutive_needs_replan"]) >= 2:
        reasons.add("REPLAN_STORM")
    if int(review_metrics["nonaccepted"]) >= 3:
        reasons.add("USER_CHECKPOINT")
    if int(review_metrics["consecutive_assurance_dominated"]) >= 2:
        reasons.add("ASSURANCE")
    reviews = review_metrics["reviews"]
    assert isinstance(reviews, list)
    if reviews and reviews[-1]["escalated_assurance"]:
        reasons.update({"ASSURANCE", "USER_CHECKPOINT"})

    if state["resolved_external"]:
        reasons.discard("EXTERNAL")
    if state["resume_grant"]:
        override = set(state["resume_override"])
        suppressible = {
            "EXTERNAL",
            "ASSURANCE",
            "REPLAN_STORM",
            "USER_CHECKPOINT",
        }
        if role == "planner-replan":
            suppressible |= {"CONFIGURATION_GAP", "SCHEMA_MIGRATION"}
        reasons -= override & suppressible
    expected = state["expected"]
    assert isinstance(expected, set)
    return {
        "decision": "PAUSED" if reasons else "CONTINUE",
        "reasons": sorted(reasons),
        "details": sorted(set(details)),
        "warnings": sorted(set(warnings)),
        "role": role,
        "protocol_version": version,
        "state": state["status"],
        "next_roles": [
            {"role": item_role, "iteration": iteration}
            for item_role, iteration in sorted(expected)
        ],
        "budgets": budget_results,
        "review_history": review_metrics,
        "mechanism": "git-diff-numstat-no-renames-plus-untracked-line-count",
    }


def guard_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    task_dir = resolve_existing(
        workspace_path(args.task_dir, workspace_root, "task directory"),
        "task directory",
    )
    data = guard_data(
        workspace_root,
        task_dir,
        args.task_id,
        args.role,
        args.artifact,
        legacy_findings=getattr(args, "legacy_findings", False),
        allow_primary_worktree=args.allow_primary_worktree,
    )
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0 if data["decision"] == "CONTINUE" else 1


def control_command(args: argparse.Namespace) -> int:
    workspace_root = resolve_existing(Path(args.workspace_root), "workspace root")
    context = require_loop_git_context(
        workspace_root,
        args.task_id,
        require_linked=not args.allow_primary_worktree,
    )
    if context["operations_in_progress"]:
        raise RalphError("control refuses an in-progress Git operation")
    if git_staged_paths(workspace_root):
        raise RalphError("control requires an empty staging area")
    task_dir = resolve_existing(
        workspace_path(args.task_dir, workspace_root, "task directory"),
        "task directory",
    )
    texts = require_four_pack(task_dir)
    if task_identity(task_dir, texts["proposal.md"]) != args.task_id:
        raise RalphError("--task-id does not match the four-pack")
    base_commit = summary_field(texts["plan.md"], "Base commit").lower()
    chain = task_commit_chain(
        workspace_root,
        args.task_id,
        base_commit,
        str(context["head"]),
        current_plan=texts["plan.md"],
        require_initialized=True,
    )
    state = replay_checkpoint_chain(chain)
    action = args.action.upper().replace("-", "_")
    resume_role = args.resume_role.title() if args.resume_role else ""
    if action == "RESUME" and resume_role == "Planner" and git_changed_paths(
        workspace_root
    ):
        raise RalphError(
            "RESUME to Planner requires a clean worktree; keep PAUSED and resume "
            "Implementer only for authorized contraction, or preserve the WIP "
            "outside this role flow"
        )
    iteration = infer_control_iteration(state, action, resume_role)
    reasons = sorted({value.upper() for value in args.reason})
    transferred_paths: list[str] = []
    for value in args.transferred_path:
        path = workspace_path(value, workspace_root, "transferred path")
        transferred_paths.append(git_relative(path, workspace_root, "transferred path"))
    authorization = authorization_sha256(args.authorization_token)
    pending_entry: dict[str, object] = {
        "commit": "<pending-control>",
        "role": "Control",
        "iteration": iteration,
        "snapshot": "",
        "candidate": "",
        "verdict": "",
        "reviewer": "",
        "control_action": action,
        "pause_reasons": reasons,
        "resume_role": resume_role,
        "authorization": authorization,
        "pq_id": args.pq_id.upper() if args.pq_id else "",
        "plan_decision": args.decision or "",
        "child_task": args.child_task or "",
        "transferred_paths": transferred_paths,
        "references": list(args.reference),
    }
    if action in {"PLAN_QUERY", "PLAN_RESPONSE"} and not args.summary:
        raise RalphError(f"{action} requires --summary")
    if action == "SPLIT":
        validate_task_id(args.child_task or "")
        if args.child_task == args.task_id:
            raise RalphError("SPLIT child task must differ from the parent task")
    apply_checkpoint_entry(state, pending_entry)
    if action in {"PLAN_RESPONSE", "SPLIT"} and state["status"] == "PAUSED":
        reasons = sorted(set(reasons) | set(state["pause_reasons"]))
        pending_entry["pause_reasons"] = reasons

    before = wip_fingerprint(workspace_root)
    trailers = [
        f"Ralph-Task: {args.task_id}",
        "Ralph-Role: Control",
        f"Ralph-Iteration: {iteration}",
        f"Ralph-Control-Action: {action}",
    ]
    if reasons:
        trailers.append(f"Ralph-Pause-Reasons: {json.dumps(reasons)}")
    if resume_role:
        trailers.append(f"Ralph-Resume-Role: {resume_role}")
    if authorization:
        trailers.append(f"Ralph-Authorization-SHA256: {authorization}")
    if args.pq_id:
        trailers.append(f"Ralph-Plan-Query: {args.pq_id.upper()}")
    if args.decision:
        trailers.append(f"Ralph-Plan-Decision: {args.decision}")
    if args.reference:
        trailers.append(
            f"Ralph-References: {json.dumps(args.reference, ensure_ascii=True)}"
        )
    if args.child_task:
        trailers.append(f"Ralph-Child-Task: {args.child_task}")
    if transferred_paths:
        trailers.append(
            "Ralph-Transferred-Paths: "
            + json.dumps(transferred_paths, ensure_ascii=True)
        )
    subject = args.summary or f"[{args.task_id}] control: {action.lower()}"
    run_git(
        workspace_root,
        ["commit", "--allow-empty", "-m", subject, "-m", "\n".join(trailers)],
    )
    commit = run_git(workspace_root, ["rev-parse", "HEAD"]).stdout.strip().lower()
    if commit_changed_paths(workspace_root, commit):
        raise RalphError("Control checkpoint unexpectedly changed files")
    if wip_fingerprint(workspace_root) != before:
        raise RalphError("Control checkpoint did not preserve WIP bytes exactly")
    committed_chain = task_commit_chain(
        workspace_root,
        args.task_id,
        base_commit,
        commit,
        current_plan=texts["plan.md"],
        require_initialized=True,
    )
    committed_state = replay_checkpoint_chain(committed_chain)
    print(
        json.dumps(
            {
                "task_id": args.task_id,
                "action": action,
                "iteration": iteration,
                "commit": commit,
                "state": committed_state["status"],
                "pause_reasons": sorted(committed_state["pause_reasons"]),
                "wip_preserved": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
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
            if not args.authorization_token:
                raise RalphError(
                    "--allow-contract-change requires --authorization-token "
                    "from explicit user approval"
                )
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
        explicit_paths = {
            str(normalize_artifact_path(value, workspace_root))
            for value in artifact_arguments
        }
        planned_paths = {
            str(path)
            for path in (
                declared_artifact_paths(previous_plan, workspace_root, [])
                + declared_artifact_paths(texts["plan.md"], workspace_root, [])
            )
        }
        if (
            protocol_version(texts.values()) >= 2
            and explicit_paths - planned_paths
            and not args.authorization_token
        ):
            raise RalphError(
                "protocol-v2 explicit artifacts outside the plan require explicit "
                "user authorization: "
                + ", ".join(sorted(explicit_paths - planned_paths))
            )
        added_specs = {
            (item["id"], item["path"]) for item in parse_deliverables(texts["plan.md"])
        } - {
            (item["id"], item["path"]) for item in parse_deliverables(previous_plan)
        }
        if added_specs and not args.authorization_token:
            raise RalphError(
                "Implementer expanded Deliverables without explicit user authorization: "
                + ", ".join(f"{item_id} -> {path}" for item_id, path in sorted(added_specs))
            )
        previous_budget_assignments = {
            (item["id"], item["path"]): item["budget"]
            for item in parse_deliverables(previous_plan)
        }
        changed_budget_assignments = sorted(
            (item["id"], item["path"])
            for item in parse_deliverables(texts["plan.md"])
            if (item["id"], item["path"]) in previous_budget_assignments
            and item["budget"]
            != previous_budget_assignments[(item["id"], item["path"])]
        )
        if changed_budget_assignments and not args.authorization_token:
            raise RalphError(
                "Implementer changed deliverable guard-budget assignments without "
                "explicit user authorization: "
                + ", ".join(
                    f"{item_id} -> {path}"
                    for item_id, path in changed_budget_assignments
                )
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
        if explicitly_allowed_new and not args.authorization_token:
            raise RalphError(
                "--allow-new-deliverable requires --authorization-token "
                "from explicit user approval"
            )
        unexpected_new = sorted(
            str(path)
            for path in current_artifacts
            if str(path) not in {str(item) for item in previous_artifacts}
            and str(path) not in explicitly_allowed_new
        )
        if unexpected_new:
            raise RalphError(
                "Implementer introduced new deliverable paths without explicit user "
                "authorization; use --allow-new-deliverable and --authorization-token "
                "for each approved design amendment: "
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
        if review["findings"] and review["finding_schema"] != "typed":
            raise RalphError(
                "a new Reviewer checkpoint with findings must use typed protocol-v2 "
                "Finding and Action class columns"
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
    if args.role == "planner-replan":
        disposition_errors = replan_disposition_errors(
            checkpoint_plan,
            read_text(checkpoint_pack / "verify.md"),
            args.iteration,
        )
        if disposition_errors:
            raise RalphError(
                "planner-replan finding disposition validation failed:\n- "
                + "\n- ".join(disposition_errors)
            )
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
    if args.role == "planner-replan":
        previous_plan = git_file_text(
            workspace_root,
            head_commit,
            git_relative(task_dir / "plan.md", workspace_root, "plan"),
        )
        initial_deliverables = {
            (item["id"], item["path"]) for item in parse_deliverables(previous_plan)
        }
        current_deliverables = {
            (item["id"], item["path"]) for item in parse_deliverables(checkpoint_plan)
        }
        expanded = sorted(current_deliverables - initial_deliverables)
        if expanded and not args.authorization_token:
            raise RalphError(
                "Planner replan added or redirected deliverables without explicit "
                "user authorization: "
                + ", ".join(f"{item_id} -> {path}" for item_id, path in expanded)
            )
        previous_budget_assignments = {
            (item["id"], item["path"]): item["budget"]
            for item in parse_deliverables(previous_plan)
        }
        changed_budget_assignments = sorted(
            (item["id"], item["path"])
            for item in parse_deliverables(checkpoint_plan)
            if (item["id"], item["path"]) in previous_budget_assignments
            and item["budget"]
            != previous_budget_assignments[(item["id"], item["path"])]
        )
        if changed_budget_assignments and not args.authorization_token:
            raise RalphError(
                "Planner replan changed deliverable guard-budget assignments "
                "without explicit user authorization: "
                + ", ".join(
                    f"{item_id} -> {path}"
                    for item_id, path in changed_budget_assignments
                )
            )
    assert_next_checkpoint(chain, args.role, args.iteration)
    if args.role in {"planner-replan", "implementer"}:
        guard = guard_data(
            workspace_root,
            task_dir,
            args.task_id,
            args.role,
            artifact_arguments,
            legacy_findings=getattr(args, "legacy_findings", False),
            allow_primary_worktree=args.allow_primary_worktree,
        )
        if guard["decision"] != "CONTINUE":
            raise RalphError(
                f"{args.role} continuation guard is PAUSED: "
                + ", ".join(str(value) for value in guard["reasons"])
            )
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
        **(
            {"legacy_findings": True}
            if getattr(args, "legacy_findings", False)
            else {}
        ),
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
    authorization = authorization_sha256(args.authorization_token)
    if authorization:
        trailers.append(f"Ralph-Authorization-SHA256: {authorization}")
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
        **(
            {"legacy_findings": True}
            if getattr(args, "legacy_findings", False)
            else {}
        ),
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
    control_events = [
        {
            "commit": item["commit"],
            "iteration": item["iteration"],
            "action": item["control_action"],
            "reasons": item["pause_reasons"],
            "resume_role": item["resume_role"] or None,
            "authorization_sha256": item["authorization"] or None,
            "references": item["references"],
            "plan_query": item["pq_id"] or None,
            "plan_decision": item["plan_decision"] or None,
            "child_task": item["child_task"] or None,
            "transferred_paths": item["transferred_paths"],
        }
        for item in chain
        if item["role"] == "Control"
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
                "control_events": control_events,
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
        **(
            {"legacy_findings": True}
            if getattr(args, "legacy_findings", False)
            else {}
        ),
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
        **(
            {"legacy_findings": True}
            if getattr(args, "legacy_findings", False)
            else {}
        ),
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
            **(
                {"legacy_findings": True}
                if getattr(args, "legacy_findings", False)
                else {}
            ),
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

    guard_parser = subparsers.add_parser(
        "guard",
        help="read-only continuation guard using Git numstat and declared metadata",
    )
    guard_parser.add_argument("--workspace-root", required=True)
    guard_parser.add_argument("--task-dir", required=True)
    guard_parser.add_argument("--task-id", required=True)
    guard_parser.add_argument(
        "--role",
        required=True,
        choices=("planner-replan", "implementer", "post-review"),
    )
    guard_parser.add_argument("--artifact", action="append", default=[])
    guard_parser.add_argument("--legacy-findings", action="store_true")
    guard_parser.add_argument("--allow-primary-worktree", action="store_true")
    guard_parser.set_defaults(handler=guard_command)

    control_parser = subparsers.add_parser(
        "control",
        help="append an audited pause, resume, consultation, split, or abandon event",
    )
    control_parser.add_argument("--workspace-root", required=True)
    control_parser.add_argument("--task-dir", required=True)
    control_parser.add_argument("--task-id", required=True)
    control_parser.add_argument(
        "--action",
        required=True,
        choices=(
            "pause",
            "resume",
            "plan-query",
            "plan-response",
            "split",
            "abandon",
        ),
    )
    control_parser.add_argument("--reason", action="append", default=[])
    control_parser.add_argument(
        "--resume-role",
        choices=("planner", "implementer"),
    )
    control_parser.add_argument("--authorization-token")
    control_parser.add_argument("--pq-id")
    control_parser.add_argument(
        "--decision",
        choices=tuple(sorted(PLAN_RESPONSE_DECISIONS)),
    )
    control_parser.add_argument("--summary")
    control_parser.add_argument("--reference", action="append", default=[])
    control_parser.add_argument("--child-task")
    control_parser.add_argument("--transferred-path", action="append", default=[])
    control_parser.add_argument("--allow-primary-worktree", action="store_true")
    control_parser.set_defaults(handler=control_command)

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
    validate_parser.add_argument("--legacy-findings", action="store_true")
    validate_parser.set_defaults(handler=validate_command)

    archive_parser = subparsers.add_parser(
        "archive", help="archive an accepted exact four-pack with a marker-managed index"
    )
    archive_parser.add_argument("--workspace-root", required=True)
    archive_parser.add_argument("--task-dir", required=True)
    archive_parser.add_argument("--archive-root", required=True)
    archive_parser.add_argument("--index", required=True)
    archive_parser.add_argument("--artifact", action="append", default=[])
    archive_parser.add_argument("--legacy-findings", action="store_true")
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
    checkpoint_parser.add_argument("--authorization-token")
    checkpoint_parser.add_argument("--legacy-findings", action="store_true")
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
    handoff_parser.add_argument("--legacy-findings", action="store_true")
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
