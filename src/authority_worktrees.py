import re
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import Dict


_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


def create_authority_worktree(
    *,
    repository: str | Path,
    worktree_root: str | Path,
    cycle_id: str,
    authority_id: str,
    base_branch: str,
) -> Dict[str, str]:
    if not _ID_PATTERN.fullmatch(cycle_id) or not _ID_PATTERN.fullmatch(authority_id):
        raise ValueError("cycle and authority IDs must be generated hexadecimal IDs")
    if not base_branch or base_branch.startswith("-"):
        raise ValueError("base branch is invalid")

    repository_path = Path(repository).resolve()
    root_path = Path(worktree_root).resolve()
    if root_path == repository_path or repository_path in root_path.parents:
        raise ValueError("authority worktrees must be stored outside the repository")

    branch = f"agents/{cycle_id}/{authority_id}"
    for ref in (branch, base_branch):
        try:
            subprocess.run(
                ["git", "check-ref-format", "--branch", ref],
                cwd=repository_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"invalid Git branch ref: {ref}") from exc

    root_path.mkdir(parents=True, exist_ok=True)
    worktree_path = (root_path / cycle_id / authority_id).resolve()
    if root_path not in worktree_path.parents:
        raise ValueError("resolved worktree path escaped its configured root")
    if worktree_path.exists():
        raise FileExistsError(f"authority worktree already exists: {worktree_path}")
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "git",
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            base_branch,
        ],
        cwd=repository_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return {"branch_ref": branch, "worktree_path": str(worktree_path)}


def apply_authority_patch(
    worktree: str | Path, patch: str, *, expected_branch: str | None = None
) -> str:
    if not isinstance(patch, str) or not patch.strip() or len(patch) > 200000:
        raise ValueError("agent patch must contain 1 to 200000 characters")
    if "GIT binary patch" in patch:
        raise ValueError("binary patches are not allowed")

    worktree_path = Path(worktree).resolve()
    repository_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    if repository_root != worktree_path:
        raise ValueError("patch target must be an authority worktree root")
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if expected_branch is not None and branch != expected_branch:
        raise ValueError("authority worktree is not on its recorded branch")

    headers = [
        match
        for line in patch.splitlines()
        if (match := _DIFF_HEADER.fullmatch(line)) is not None
    ]
    if not headers:
        raise ValueError("agent response must contain a unified Git diff")
    for line in patch.splitlines():
        if line.startswith(("new file mode ", "deleted file mode ", "old mode ", "new mode ")):
            if line.rsplit(" ", 1)[-1] != "100644":
                raise ValueError("agent patches may only create or modify regular text files")

    for header in headers:
        for raw_path in header.groups():
            path = PurePosixPath(raw_path)
            if (
                not _SAFE_PATH.fullmatch(raw_path)
                or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or not (
                    raw_path == "README.md"
                    or raw_path.startswith(("src/", "tests/", "docs/"))
                )
            ):
                raise ValueError(f"agent patch path is outside the allowed areas: {raw_path}")
            target = worktree_path.joinpath(*path.parts)
            if target.is_symlink():
                raise ValueError(f"agent patch cannot modify a symlink: {raw_path}")
            resolved_target = target.resolve()
            if worktree_path not in resolved_target.parents:
                raise ValueError(f"agent patch path escapes its worktree: {raw_path}")

    for arguments in (
        ["git", "apply", "--check", "--whitespace=error-all"],
        ["git", "apply", "--whitespace=error-all"],
    ):
        subprocess.run(
            arguments,
            cwd=worktree_path,
            input=patch,
            check=True,
            capture_output=True,
            text=True,
        )
    return subprocess.run(
        ["git", "diff", "--stat"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
