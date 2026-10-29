import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.issue_to_pr import (
    generate_candidate,
    prepare_validation,
    publish_candidate,
    record_validation,
    reject_duplicate_issue_pr,
    validate_eligible_issue,
)


def _issue(*, labels=None):
    return {
        "number": 17,
        "state": "open",
        "title": "Measure worker retry behavior",
        "body": "Add a bounded retry metric and a deterministic acceptance test.",
        "html_url": "https://github.com/example/project/issues/17",
        "labels": [
            {"name": name}
            for name in (labels or ["agent-candidate"])
        ],
    }


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(path: Path) -> str:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Issue Pipeline Test")
    _git(path, "config", "user.email", "issue-pipeline@example.invalid")
    (path / "README.md").write_text("before\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "Initial commit")
    return _git(path, "rev-parse", "HEAD")


def test_issue_scope_requires_candidate_label_and_maintainer_triage():
    issue = _issue(labels=["agent-candidate", "needs-triage"])

    with pytest.raises(ValueError, match="triaged"):
        validate_eligible_issue(issue)

    issue["labels"] = [{"name": "needs-triage"}]
    with pytest.raises(ValueError, match="agent-candidate"):
        validate_eligible_issue(issue)


def test_duplicate_open_pr_blocks_a_second_issue_cycle():
    with pytest.raises(ValueError, match="already references"):
        reject_duplicate_issue_pr(
            _issue()["html_url"],
            [
                {
                    "html_url": "https://github.com/example/project/pull/42",
                    "body": "Closes #17",
                }
            ],
        )


def test_failed_validation_cannot_be_published(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    patch_path = tmp_path / "candidate.patch"
    patch_path.write_text("patch", encoding="utf-8")
    manifest = {
        "generation_status": "generated",
        "issue_number": 17,
        "cycle_id": "a" * 32,
        "agent_id": "b" * 32,
        "base_commit": "c" * 40,
        "patch_sha256": hashlib.sha256(b"patch").hexdigest(),
        "validation": {"status": "pending", "result": ""},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    record_validation(manifest_path, status="failed", result="1 failed")
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    calls = []

    def unexpected_publish(arguments, **kwargs):
        calls.append(arguments)
        raise AssertionError("failed validation must not publish")

    with pytest.raises(ValueError, match="did not pass"):
        publish_candidate(
            repository=tmp_path / "unused",
            patch_path=patch_path,
            manifest_path=manifest_path,
            worktree_root=tmp_path / "publisher-worktrees",
            expected_repository="example/project",
            expected_issue_number=17,
            expected_base_commit="c" * 40,
            runner=unexpected_publish,
        )
    assert calls == []
    assert updated["validation"]["status"] == "failed"


def test_out_of_scope_patch_is_rejected_and_recorded(tmp_path):
    repository = tmp_path / "repo"
    base_commit = _repository(repository)
    issue = _issue()
    request_manifest = {
        "issue_number": issue["number"],
        "issue_url": issue["html_url"],
        "issue_title": issue["title"],
        "repository": "example/project",
        "base_commit": base_commit,
        "agent_id": "b" * 32,
        "cycle_id": "a" * 32,
        "run_url": "https://github.com/example/project/actions/runs/1",
        "dispatch_actor": "maintainer",
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request_status": "accepted", "manifest": request_manifest}),
        encoding="utf-8",
    )
    patch = (
        "diff --git a/.github/workflows/test.yml b/.github/workflows/test.yml\n"
        "--- a/.github/workflows/test.yml\n"
        "+++ b/.github/workflows/test.yml\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    patch_path = tmp_path / "candidate.patch"
    patch_path.write_text(patch, encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                **request_manifest,
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside the allowed areas"):
        prepare_validation(
            repository=repository,
            request_path=request_path,
            patch_path=patch_path,
            manifest_path=manifest_path,
            worktree_root=tmp_path / "validation-worktrees",
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["validation"]["status"] == "failed"


def test_generated_patch_and_manifest_are_reusable_for_validation(
    monkeypatch, tmp_path
):
    repository = tmp_path / "repo"
    base_commit = _repository(repository)
    request_path = tmp_path / "request.json"
    manifest = {
        "issue_number": 17,
        "issue_url": "https://github.com/example/project/issues/17",
        "issue_title": "A bounded change",
        "repository": "example/project",
        "base_commit": base_commit,
        "agent_id": "b" * 32,
        "cycle_id": "a" * 32,
        "run_url": "https://github.com/example/project/actions/runs/1",
        "generation_status": "pending",
        "validation": {"status": "pending", "result": ""},
        "review_status": "pending_human_review",
        "publication_status": "not_published",
    }
    request_path.write_text(
        json.dumps(
            {
                "request_status": "accepted",
                "issue": _issue(),
                "manifest": manifest,
            }
        ),
        encoding="utf-8",
    )
    patch = (
        "diff --git a/README.md b/README.md\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
    )
    monkeypatch.setattr("src.issue_to_pr.run_native_agent", lambda *args, **kwargs: patch)
    patch_path = tmp_path / "candidate.patch"
    manifest_path = tmp_path / "generated-manifest.json"

    generated = generate_candidate(
        repository=repository,
        request_path=request_path,
        worktree_root=tmp_path / "agent-worktrees",
        patch_path=patch_path,
        manifest_path=manifest_path,
    )

    assert generated["generation_status"] == "generated"
    generated_patch = patch_path.read_text(encoding="utf-8")
    assert generated["patch_sha256"] == hashlib.sha256(
        generated_patch.encode("utf-8")
    ).hexdigest()
    assert "-before" in generated_patch
    assert "+after" in generated_patch

    validation_repository = tmp_path / "validation-repo"
    subprocess.run(
        ["git", "clone", "--quiet", str(repository), str(validation_repository)],
        check=True,
        capture_output=True,
        text=True,
    )
    validation_worktree = prepare_validation(
        repository=validation_repository,
        request_path=request_path,
        patch_path=patch_path,
        manifest_path=manifest_path,
        worktree_root=tmp_path / "validation-worktrees",
    )
    assert (validation_worktree / "README.md").read_text(
        encoding="utf-8"
    ) == "after\n"
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(validation_worktree)],
        cwd=validation_repository,
        check=True,
        capture_output=True,
        text=True,
    )


def test_publication_failure_is_recorded_in_audit_manifest(tmp_path):
    repository = tmp_path / "repo"
    base_commit = _repository(repository)
    patch = (
        "diff --git a/README.md b/README.md\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
    )
    patch_path = tmp_path / "candidate.patch"
    patch_path.write_text(patch, encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_number": 17,
                "issue_url": "https://github.com/example/project/issues/17",
                "issue_title": "A bounded change",
                "repository": "example/project",
                "base_commit": base_commit,
                "agent_id": "b" * 32,
                "cycle_id": "a" * 32,
                "run_url": "https://github.com/example/project/actions/runs/1",
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
                "generation_status": "generated",
                "validation": {"status": "passed", "result": "3 passed"},
                "review_status": "pending_human_review",
                "publication_status": "not_published",
            }
        ),
        encoding="utf-8",
    )

    def fail_push(arguments, **kwargs):
        if arguments[:2] == ["gh", "auth"]:
            return SimpleNamespace(stdout="", stderr="")
        if arguments[:2] == ["git", "push"]:
            raise subprocess.CalledProcessError(
                1, arguments, stderr="simulated push rejection"
            )
        return subprocess.run(arguments, **kwargs)

    with pytest.raises(subprocess.CalledProcessError):
        publish_candidate(
            repository=repository,
            patch_path=patch_path,
            manifest_path=manifest_path,
            worktree_root=tmp_path / "publisher-worktrees",
            expected_repository="example/project",
            expected_issue_number=17,
            expected_base_commit=base_commit,
            runner=fail_push,
        )

    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated["publication_status"] == "failed"
    assert "CalledProcessError" in updated["publication_error"]
