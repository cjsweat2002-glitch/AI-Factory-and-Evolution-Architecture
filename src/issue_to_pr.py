"""Helpers for the manually approved GitHub issue-to-draft-PR workflow."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping

from src.authority_worktrees import apply_authority_patch, create_authority_worktree
from src.native_agents import run_native_agent


_ALLOWED_CONTEXT_FILES = (
    "README.md",
    "src/coordinator.py",
    "src/autonomy_store.py",
    "src/factory.py",
    "src/factory_worker.py",
)
_ALLOWED_TEST_STATUSES = {"passed", "failed"}
_ISSUE_REFERENCE = re.compile(r"/issues/(\d+)(?:\b|/)")
_ISSUE_CLOSER = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+#(\d+)\b", re.IGNORECASE
)
_SAFE_ID = re.compile(r"^[0-9a-f]{32}$")
_SAFE_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


def validate_eligible_issue(issue: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(issue, Mapping):
        raise ValueError("issue response must be an object")
    number = issue.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("issue number must be a positive integer")
    if issue.get("state") != "open" or issue.get("pull_request"):
        raise ValueError("only open issues can start an agent cycle")
    title = issue.get("title")
    body = issue.get("body")
    if (
        not isinstance(title, str)
        or not 1 <= len(title.strip()) <= 200
        or "\n" in title
        or "\r" in title
    ):
        raise ValueError("issue title must contain 1 to 200 characters")
    if not isinstance(body, str) or not 1 <= len(body) <= 20000:
        raise ValueError("issue body must contain 1 to 20000 characters")
    url = issue.get("html_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("issue must have a canonical HTTPS URL")
    labels = issue.get("labels")
    if not isinstance(labels, list):
        raise ValueError("issue labels must be a list")
    label_names = {
        label.get("name")
        for label in labels
        if isinstance(label, Mapping) and isinstance(label.get("name"), str)
    }
    if "agent-candidate" not in label_names:
        raise ValueError("issue must have the agent-candidate label")
    if "needs-triage" in label_names:
        raise ValueError("issue must be triaged before an agent cycle")
    return {
        "number": number,
        "title": title.strip(),
        "body": body,
        "html_url": url,
    }


def reject_duplicate_issue_pr(
    issue_url: str, pull_requests: Iterable[Mapping[str, Any]]
) -> None:
    issue_match = _ISSUE_REFERENCE.search(issue_url)
    if not issue_match:
        raise ValueError("issue URL does not contain a valid issue number")
    issue_number = issue_match.group(1)
    for pull_request in pull_requests:
        body = pull_request.get("body")
        if not isinstance(body, str):
            continue
        if issue_url in body or any(
            match.group(1) == issue_number
            for match in _ISSUE_CLOSER.finditer(body)
        ):
            url = pull_request.get("html_url", "an open pull request")
            raise ValueError(f"an open pull request already references this issue: {url}")


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(target)


def _read_json(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError("workflow artifact must contain a JSON object")
    return value


def _run(arguments: list[str], *, cwd: str | Path | None = None) -> str:
    result = subprocess.run(
        arguments, cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _new_manifest(
    issue: Mapping[str, Any],
    *,
    repository: str,
    base_commit: str,
    run_url: str,
    actor: str,
) -> Dict[str, Any]:
    return {
        "issue_number": issue["number"],
        "issue_url": issue["html_url"],
        "issue_title": issue["title"],
        "repository": repository,
        "base_commit": base_commit,
        "agent_id": uuid.uuid4().hex,
        "cycle_id": uuid.uuid4().hex,
        "run_url": run_url,
        "dispatch_actor": actor,
        "patch_sha256": None,
        "generation_status": "pending",
        "validation": {"status": "pending", "result": ""},
        "review_status": "pending_human_review",
        "publication_status": "not_published",
    }


def prepare_request(
    *,
    issue_number: int,
    repository: str,
    base_commit: str,
    run_url: str,
    actor: str,
    output_path: str | Path,
    runner: Callable[..., Any] = subprocess.run,
) -> Dict[str, Any]:
    audit: Dict[str, Any] = {
        "issue_number": issue_number,
        "repository": repository,
        "base_commit": base_commit,
        "run_url": run_url,
        "dispatch_actor": actor,
        "request_status": "rejected",
    }
    try:
        issue = json.loads(
            runner(
                ["gh", "api", f"repos/{repository}/issues/{issue_number}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        clean_issue = validate_eligible_issue(issue)
        pulls_result = runner(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{repository}/pulls?state=open&per_page=100",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        pages = json.loads(pulls_result.stdout or "[]")
        open_pulls = [pull for page in pages for pull in page] if pages else []
        reject_duplicate_issue_pr(clean_issue["html_url"], open_pulls)
        manifest = _new_manifest(
            clean_issue,
            repository=repository,
            base_commit=base_commit,
            run_url=run_url,
            actor=actor,
        )
        _write_json(
            output_path,
            {"issue": clean_issue, "manifest": manifest, "request_status": "accepted"},
        )
        return manifest
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        audit["rejection_reason"] = str(exc)[:1000]
        _write_json(output_path, audit)
        raise ValueError(audit["rejection_reason"]) from exc


def _repository_context(repository: Path) -> str:
    parts = []
    remaining = 40000
    for relative_path in _ALLOWED_CONTEXT_FILES:
        path = repository / relative_path
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        part = f"--- {relative_path} ---\n{content[:remaining]}"
        parts.append(part)
        remaining -= len(part)
        if remaining <= 0:
            break
    if not parts:
        raise RuntimeError("no readable repository context files were found")
    return "\n\n".join(parts)


def generate_candidate(
    *,
    repository: str | Path,
    request_path: str | Path,
    worktree_root: str | Path,
    patch_path: str | Path,
    manifest_path: str | Path,
) -> Dict[str, Any]:
    request = _read_json(request_path)
    if request.get("request_status") != "accepted":
        raise ValueError("request was not accepted for an agent cycle")
    issue = request["issue"]
    manifest = request["manifest"]
    repository_path = Path(repository).resolve()
    manifest_path = Path(manifest_path)
    _write_json(manifest_path, manifest)
    worktree_path: Path | None = None
    try:
        if not _SAFE_COMMIT.fullmatch(str(manifest.get("base_commit", ""))):
            raise ValueError("manifest base commit is invalid")
        if (
            _run(["git", "rev-parse", "HEAD"], cwd=repository_path)
            != manifest["base_commit"]
        ):
            raise ValueError("checked out source does not match the recorded base commit")
        worktree = create_authority_worktree(
            repository=repository_path,
            worktree_root=worktree_root,
            cycle_id=manifest["cycle_id"],
            authority_id=manifest["agent_id"],
            base_branch=manifest["base_commit"],
        )
        worktree_path = Path(worktree["worktree_path"])
        objective = (
            f"Implement the bounded change requested by GitHub issue "
            f"#{issue['number']}: {issue['title']}. Follow its acceptance "
            "criteria and scope boundaries."
        )
        patch = run_native_agent(
            "builder",
            objective,
            branch_ref=worktree["branch_ref"],
            evidence=issue["body"],
            context=_repository_context(worktree_path),
        )
        apply_authority_patch(
            worktree_path, patch, expected_branch=worktree["branch_ref"]
        )
        intent_paths = [
            path
            for path in ("README.md", "src", "tests", "docs")
            if (worktree_path / path).exists()
        ]
        _run(["git", "add", "-N", "--", *intent_paths], cwd=worktree_path)
        patch_text = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--no-color"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if not patch_text:
            raise ValueError("agent produced no changes")
        patch_file = Path(patch_path)
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch_text, encoding="utf-8")
        manifest["patch_sha256"] = hashlib.sha256(
            patch_text.encode("utf-8")
        ).hexdigest()
        manifest["generation_status"] = "generated"
        _write_json(manifest_path, manifest)
        return manifest
    except Exception as exc:
        manifest["generation_status"] = "failed"
        manifest["generation_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        _write_json(manifest_path, manifest)
        raise
    finally:
        if worktree_path is not None:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=repository_path,
                check=False,
                capture_output=True,
                text=True,
            )


def prepare_validation(
    *,
    repository: str | Path,
    request_path: str | Path,
    patch_path: str | Path,
    manifest_path: str | Path,
    worktree_root: str | Path,
) -> Path:
    manifest = _read_json(manifest_path)
    try:
        request = _read_json(request_path)
        if request.get("request_status") != "accepted":
            raise ValueError("request was not accepted for an agent cycle")
        requested_manifest = request.get("manifest")
        if not isinstance(requested_manifest, Mapping):
            raise ValueError("request artifact has no cycle manifest")
        for key in (
            "issue_number",
            "issue_url",
            "issue_title",
            "repository",
            "base_commit",
            "agent_id",
            "cycle_id",
            "run_url",
            "dispatch_actor",
        ):
            if manifest.get(key) != requested_manifest.get(key):
                raise ValueError(
                    f"generated manifest {key} does not match the approved request"
                )
        patch = Path(patch_path).read_text(encoding="utf-8")
        if hashlib.sha256(patch.encode("utf-8")).hexdigest() != manifest.get(
            "patch_sha256"
        ):
            raise ValueError("patch digest does not match the generation manifest")
        worktree = create_authority_worktree(
            repository=repository,
            worktree_root=worktree_root,
            cycle_id=manifest["cycle_id"],
            authority_id=manifest["agent_id"],
            base_branch=manifest["base_commit"],
        )
        worktree_path = Path(worktree["worktree_path"])
        apply_authority_patch(
            worktree_path, patch, expected_branch=worktree["branch_ref"]
        )
        return worktree_path
    except Exception as exc:
        manifest["validation"] = {
            "status": "failed",
            "result": f"Patch validation failed: {type(exc).__name__}: {exc}"[:8000],
        }
        _write_json(manifest_path, manifest)
        raise


def record_validation(
    manifest_path: str | Path, *, status: str, result: str
) -> Dict[str, Any]:
    if status not in _ALLOWED_TEST_STATUSES:
        raise ValueError("validation status must be passed or failed")
    manifest = _read_json(manifest_path)
    manifest["validation"] = {
        "status": status,
        "result": result[-8000:],
        "result_sha256": hashlib.sha256(result.encode("utf-8")).hexdigest(),
    }
    _write_json(manifest_path, manifest)
    return manifest


def _require_publishable(manifest: Mapping[str, Any], patch_text: str) -> None:
    if manifest.get("generation_status") != "generated":
        raise ValueError("only generated candidates can be published")
    if manifest.get("validation", {}).get("status") != "passed":
        raise ValueError("candidate validation did not pass")
    if hashlib.sha256(patch_text.encode("utf-8")).hexdigest() != manifest.get(
        "patch_sha256"
    ):
        raise ValueError("patch digest does not match the generation manifest")
    issue_number = manifest.get("issue_number")
    if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1:
        raise ValueError("manifest issue number is invalid")
    for key in ("cycle_id", "agent_id", "base_commit"):
        if key in {"cycle_id", "agent_id"} and not _SAFE_ID.fullmatch(
            str(manifest.get(key, ""))
        ):
            raise ValueError(f"manifest {key} is invalid")
        if key == "base_commit" and not _SAFE_COMMIT.fullmatch(
            str(manifest.get(key, ""))
        ):
            raise ValueError("manifest base commit is invalid")
        if not manifest.get(key):
            raise ValueError(f"manifest {key} is required")
    if not isinstance(manifest.get("repository"), str) or not manifest["repository"]:
        raise ValueError("manifest repository is required")
    if not isinstance(manifest.get("issue_url"), str) or not isinstance(
        manifest.get("run_url"), str
    ):
        raise ValueError("manifest source and validation URLs are required")


def publish_candidate(
    *,
    repository: str | Path,
    patch_path: str | Path,
    manifest_path: str | Path,
    worktree_root: str | Path,
    expected_repository: str,
    expected_issue_number: int,
    expected_base_commit: str,
    runner: Callable[..., Any] = subprocess.run,
) -> Dict[str, Any]:
    manifest = _read_json(manifest_path)
    worktree_path: Path | None = None
    try:
        patch = Path(patch_path).read_text(encoding="utf-8")
        _require_publishable(manifest, patch)
        if manifest.get("repository") != expected_repository:
            raise ValueError("manifest repository does not match the workflow repository")
        if manifest.get("issue_number") != expected_issue_number:
            raise ValueError("manifest issue does not match the selected issue")
        if manifest.get("issue_url") != (
            f"https://github.com/{expected_repository}/issues/{expected_issue_number}"
        ):
            raise ValueError("manifest issue URL is not canonical for this repository")
        if manifest.get("base_commit") != expected_base_commit:
            raise ValueError("manifest base commit does not match the dispatched commit")
        repository_path = Path(repository).resolve()
        if _run(["git", "rev-parse", "HEAD"], cwd=repository_path) != manifest["base_commit"]:
            raise ValueError("publisher checkout does not match the recorded base commit")
        worktree = create_authority_worktree(
            repository=repository_path,
            worktree_root=worktree_root,
            cycle_id=manifest["cycle_id"],
            authority_id=manifest["agent_id"],
            base_branch=manifest["base_commit"],
        )
        worktree_path = Path(worktree["worktree_path"])
        apply_authority_patch(
            worktree_path, patch, expected_branch=worktree["branch_ref"]
        )
        runner(
            ["git", "add", "--", "README.md", "src", "tests", "docs"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        runner(
            [
                "git",
                "-c",
                "user.name=github-actions[bot]",
                "-c",
                "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "commit",
                "-m",
                f"Implement issue #{manifest['issue_number']} proposal",
            ],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        runner(
            ["gh", "auth", "setup-git"],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        runner(
            ["git", "push", "origin", worktree["branch_ref"]],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        body = (
            f"Closes {manifest['issue_url']}\n\n"
            "## Agent validation evidence\n"
            f"- Source issue: {manifest['issue_url']}\n"
            f"- Base commit: `{manifest['base_commit']}`\n"
            f"- Agent ID: `{manifest['agent_id']}`\n"
            f"- Cycle ID: `{manifest['cycle_id']}`\n"
            f"- Patch SHA-256: `{manifest['patch_sha256']}`\n"
            f"- Validation: **{manifest['validation']['status']}**\n"
            f"- Validation run: {manifest['run_url']}\n"
            "- Review status: **pending human review**\n\n"
            "This is an agent-generated proposal. It was not auto-merged."
        )
        result = runner(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                manifest["repository"],
                "--draft",
                "--base",
                "main",
                "--head",
                worktree["branch_ref"],
                "--title",
                f"[Agent proposal] {manifest['issue_title']}"[:250],
                "--body",
                body,
            ],
            cwd=worktree_path,
            check=True,
            capture_output=True,
            text=True,
        )
        manifest["publication_status"] = "published"
        manifest["pull_request_url"] = result.stdout.strip()
        _write_json(manifest_path, manifest)
        return manifest
    except Exception as exc:
        manifest["publication_status"] = "failed"
        manifest["publication_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        _write_json(manifest_path, manifest)
        raise
    finally:
        if worktree_path is not None:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=Path(repository).resolve(),
                check=False,
                capture_output=True,
                text=True,
            )


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--issue-number", type=int, required=True)
    prepare.add_argument("--repository", required=True)
    prepare.add_argument("--base-commit", required=True)
    prepare.add_argument("--run-url", required=True)
    prepare.add_argument("--actor", required=True)
    prepare.add_argument("--output", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--repository", required=True)
    generate.add_argument("--request", required=True)
    generate.add_argument("--worktree-root", required=True)
    generate.add_argument("--patch", required=True)
    generate.add_argument("--manifest", required=True)

    validate = commands.add_parser("prepare-validation")
    validate.add_argument("--repository", required=True)
    validate.add_argument("--request", required=True)
    validate.add_argument("--patch", required=True)
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--worktree-root", required=True)

    record = commands.add_parser("record-validation")
    record.add_argument("--manifest", required=True)
    record.add_argument("--status", choices=sorted(_ALLOWED_TEST_STATUSES), required=True)
    record.add_argument("--result-file", required=True)

    publish = commands.add_parser("publish")
    publish.add_argument("--repository", required=True)
    publish.add_argument("--patch", required=True)
    publish.add_argument("--manifest", required=True)
    publish.add_argument("--worktree-root", required=True)
    publish.add_argument("--expected-repository", required=True)
    publish.add_argument("--expected-issue-number", type=int, required=True)
    publish.add_argument("--expected-base-commit", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare_request(
            issue_number=args.issue_number,
            repository=args.repository,
            base_commit=args.base_commit,
            run_url=args.run_url,
            actor=args.actor,
            output_path=args.output,
        )
    elif args.command == "generate":
        generate_candidate(
            repository=args.repository,
            request_path=args.request,
            worktree_root=args.worktree_root,
            patch_path=args.patch,
            manifest_path=args.manifest,
        )
    elif args.command == "prepare-validation":
        worktree = prepare_validation(
            repository=args.repository,
            request_path=args.request,
            patch_path=args.patch,
            manifest_path=args.manifest,
            worktree_root=args.worktree_root,
        )
        print(worktree)
    elif args.command == "record-validation":
        result = Path(args.result_file).read_text(encoding="utf-8")
        record_validation(args.manifest, status=args.status, result=result)
    elif args.command == "publish":
        publish_candidate(
            repository=args.repository,
            patch_path=args.patch,
            manifest_path=args.manifest,
            worktree_root=args.worktree_root,
            expected_repository=args.expected_repository,
            expected_issue_number=args.expected_issue_number,
            expected_base_commit=args.expected_base_commit,
        )


if __name__ == "__main__":
    try:
        _main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"issue-to-PR workflow failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
