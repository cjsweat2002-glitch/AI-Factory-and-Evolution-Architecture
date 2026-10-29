import subprocess
from pathlib import Path

import pytest

from src.authority_worktrees import apply_authority_patch, create_authority_worktree


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Autonomy Test")
    _git(path, "config", "user.email", "autonomy-test@example.invalid")
    (path / "README.md").write_text("test repository\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "Initial commit")


def test_authority_worktree_gets_its_own_branch_and_workspace(tmp_path):
    repo = tmp_path / "repo"
    _repository(repo)

    authority = create_authority_worktree(
        repository=repo,
        worktree_root=tmp_path / "authorities",
        cycle_id="a" * 32,
        authority_id="b" * 32,
        base_branch="main",
    )

    try:
        assert authority["branch_ref"] == f"agents/{'a' * 32}/{'b' * 32}"
        assert Path(authority["worktree_path"]).is_dir()
        assert _git(
            Path(authority["worktree_path"]), "branch", "--show-current"
        ) == authority["branch_ref"]
        assert _git(repo, "branch", "--list", authority["branch_ref"])
        patch = (
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1 +1 @@\n"
            "-test repository\n"
            "+updated repository\n"
        )
        diff_stat = apply_authority_patch(
            authority["worktree_path"],
            patch,
            expected_branch=authority["branch_ref"],
        )
        assert "README.md" in diff_stat
        assert (Path(authority["worktree_path"]) / "README.md").read_text(
            encoding="utf-8"
        ) == "updated repository\n"
        with pytest.raises(ValueError, match="outside the allowed areas"):
            apply_authority_patch(
                authority["worktree_path"],
                patch.replace("README.md", ".github/workflows/test.yml"),
                expected_branch=authority["branch_ref"],
            )
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", authority["worktree_path"]],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )


def test_authority_worktree_rejects_invalid_identifiers_and_base_refs(tmp_path):
    repo = tmp_path / "repo"
    _repository(repo)

    with pytest.raises(ValueError, match="IDs"):
        create_authority_worktree(
            repository=repo,
            worktree_root=tmp_path / "authorities",
            cycle_id="../main",
            authority_id="b" * 32,
            base_branch="main",
        )

    with pytest.raises(ValueError, match="invalid Git branch ref"):
        create_authority_worktree(
            repository=repo,
            worktree_root=tmp_path / "authorities",
            cycle_id="a" * 32,
            authority_id="b" * 32,
            base_branch="../main",
        )
