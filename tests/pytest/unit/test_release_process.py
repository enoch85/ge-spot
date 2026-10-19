"""Exercise release scripts and the workflow without contacting GitHub."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/release/release.sh"
NOTES = """## What's Changed
* Correct provider prices by @owner in https://github.com/enoch85/ge-spot/pull/1

### Key Changes

- **Provider prices**: Show the correct cached price while requests are pending.

**Full Changelog**: https://github.com/enoch85/ge-spot/compare/v1.9.0...v1.9.1
"""
pytestmark = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("bash", "git", "jq")),
    reason="Release checks require bash, git and jq",
)


def _git(repo: Path, env: dict[str, str], *args: str) -> str:
    """Run Git against a local remote without inheriting signing settings."""
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def release_repo(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """Use real Git and a logging gh stub that rejects unexpected commands."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    remote, repo, commands = (tmp_path / name for name in ("origin.git", "repo", "bin"))
    repo.mkdir()
    commands.mkdir()
    _git(repo, env, "init", "--bare", str(remote))
    _git(repo, env, "init", "--initial-branch=main")
    _git(repo, env, "config", "user.name", "Release Test")
    _git(repo, env, "config", "user.email", "release@example.test")
    _git(repo, env, "remote", "add", "origin", str(remote))
    (repo / "custom_components/ge_spot").mkdir(parents=True)
    notes = repo / "scripts/release/notes/v1.9.1.md"
    notes.parent.mkdir(parents=True)
    notes.write_text(NOTES)
    for name in ("publish.sh", "validate_notes.py"):
        shutil.copy2(ROOT / "scripts/release" / name, repo / "scripts/release" / name)
    (repo / "LICENSE").write_text("Test license\n")
    gh = commands / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "path = Path(os.environ['RELEASE_TEST_GH_LOG'])\n"
        "previous = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []\n"
        "entry = {'args': args}\n"
        "if args[:2] == ['release', 'create'] and '--notes-file' in args:\n"
        "    entry['notes'] = Path(args[args.index('--notes-file') + 1]).read_text()\n"
        "with path.open('a') as log: log.write(json.dumps(entry) + '\\n')\n"
        "if args == ['auth', 'status']: sys.exit(0)\n"
        "if args[:2] == ['release', 'create']:\n"
        "    sys.exit(int(os.environ.get('RELEASE_TEST_CREATE_FAILURE', '0')))\n"
        "if args[:2] == ['release', 'edit']:\n"
        "    attempts = 1 + sum(row['args'][:2] == ['release', 'edit'] for row in previous)\n"
        "    sys.exit(attempts <= int(os.environ.get('RELEASE_TEST_EDIT_FAILURES', '0')))\n"
        "sys.exit('Unexpected gh command')\n"
    )
    gh.chmod(0o755)
    (commands / "python3").symlink_to(sys.executable)
    env["PATH"] = str(commands) + os.pathsep + env["PATH"]
    env["RELEASE_TEST_GH_LOG"] = str(tmp_path / "gh.ndjson")
    return repo, remote, env


def _initial_commit(repo: Path, env: dict[str, str], version: str = "v1.9.0") -> None:
    """Publish the starting version and its prepared notes."""
    (repo / "custom_components/ge_spot/manifest.json").write_text(
        json.dumps({"domain": "ge_spot", "version": version}, indent=4) + "\n"
    )
    (repo / "README.md").write_text(
        f"![Version](https://img.shields.io/badge/version-{version[1:]}-blue.svg)\n"
    )
    _git(repo, env, "add", ".")
    _git(repo, env, "commit", "-m", "Initial version")
    _git(repo, env, "push", "--set-upstream", "origin", "main")


def _release(
    repo: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess:
    """Invoke the production script with publication confirmation."""
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=repo,
        env=env,
        input="y\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("version", ["v1.9.0", "v1.9.1"])
def test_direct_release_pushes_the_versioned_tag(release_repo, version):
    """Support both a version bump and already-versioned tagging."""
    repo, remote, env = release_repo
    _initial_commit(repo, env, version)
    result = _release(repo, env, "v1.9.1")
    assert result.returncode == 0, result.stdout + result.stderr
    tagged = json.loads(
        _git(
            repo,
            env,
            "--git-dir",
            str(remote),
            "show",
            "v1.9.1:custom_components/ge_spot/manifest.json",
        )
    )
    assert tagged["version"] == "v1.9.1"
    assert "version-1.9.1-blue.svg" in _git(repo, env, "show", "v1.9.1:README.md")
    assert (
        _git(repo, env, "show", "v1.9.1:scripts/release/notes/v1.9.1.md")
        == NOTES.strip()
    )
    assert _git(repo, env, "rev-list", "--count", "main") == (
        "1" if version == "v1.9.1" else "2"
    )
    assert "sed:" not in result.stderr


def test_removed_pr_option_cannot_mutate_the_remote(release_repo):
    """Reject the removed path before any GitHub call or branch push."""
    repo, remote, env = release_repo
    _initial_commit(repo, env)
    result = _release(repo, env, "v1.9.1", "--pr-only")
    assert result.returncode != 0
    assert not Path(env["RELEASE_TEST_GH_LOG"]).exists()
    assert (
        _git(repo, env, "--git-dir", str(remote), "branch", "--list").strip() == "main"
    )
    assert not _git(repo, env, "--git-dir", str(remote), "tag", "--list")


@pytest.mark.parametrize("version", ["v01.9.1", "v1.9.1-beta.1", "1.9.1", "v1.8.9"])
def test_invalid_production_version_cannot_be_published(release_repo, version):
    """Reject malformed, suffixed and backwards versions before tagging."""
    repo, remote, env = release_repo
    _initial_commit(repo, env)
    result = _release(repo, env, version)
    assert result.returncode != 0
    assert not _git(repo, env, "--git-dir", str(remote), "tag", "--list")
    assert (
        json.loads((repo / "custom_components/ge_spot/manifest.json").read_text())[
            "version"
        ]
        == "v1.9.0"
    )


@pytest.mark.parametrize(
    "notes",
    [
        None,
        NOTES.replace("Provider prices", "{{CHANGE_NAME}}"),
        NOTES.replace("...v1.9.1", "...v9.9.9"),
    ],
)
def test_invalid_notes_stop_publication(release_repo, notes):
    """Missing notes, template placeholders or a wrong changelog stop the tag."""
    repo, remote, env = release_repo
    _initial_commit(repo, env)
    path = repo / "scripts/release/notes/v1.9.1.md"
    if notes is None:
        path.unlink()
    else:
        path.write_text(notes)
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-m", "Prepare invalid notes")
    result = _release(repo, env, "v1.9.1")
    assert result.returncode != 0
    assert not _git(repo, env, "--git-dir", str(remote), "tag", "--list")


def _publish(
    repo: Path, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess, list]:
    """Run the workflow's actual publish command with GitHub stubbed."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    step = workflow["jobs"]["release"]["steps"][-1]
    (repo / "ge_spot.zip").write_bytes(b"packaged integration")
    result = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=repo,
        env={
            **env,
            "RELEASE_TAG": "v1.9.1",
            "tag": "v1.9.1",
            "GITHUB_REPOSITORY": "enoch85/ge-spot",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    log = Path(env["RELEASE_TEST_GH_LOG"])
    calls = (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else []
    )
    return result, calls


@pytest.mark.parametrize("edit_failures", [0, 1])
def test_workflow_publishes_then_immediately_marks_prerelease(
    release_repo, edit_failures
):
    """Production creation is followed directly by conversion of the same tag."""
    repo, _, env = release_repo
    _initial_commit(repo, env)
    env["RELEASE_TEST_EDIT_FAILURES"] = str(edit_failures)
    result, calls = _publish(repo, env)
    assert result.returncode == 0, result.stdout + result.stderr
    created = calls[0]
    assert created["args"][:3] == ["release", "create", "v1.9.1"]
    assert "--latest" in created["args"]
    assert "--prerelease" not in created["args"]
    assert "--verify-tag" in created["args"]
    assert created["notes"] == NOTES
    assert len(calls) == 2 + edit_failures
    for call in calls[1:]:
        assert call["args"][:3] == ["release", "edit", "v1.9.1"]
        assert "--prerelease" in call["args"]
        assert "--latest=false" in call["args"]


@pytest.mark.parametrize("failure", ["create", "edit"])
def test_workflow_reports_publication_or_conversion_failure(release_repo, failure):
    """Fail the workflow when publication or conversion cannot complete."""
    repo, _, env = release_repo
    _initial_commit(repo, env)
    env["RELEASE_TEST_CREATE_FAILURE"] = str(int(failure == "create"))
    env["RELEASE_TEST_EDIT_FAILURES"] = "3" if failure == "edit" else "0"
    result, calls = _publish(repo, env)
    assert result.returncode != 0
    assert len(calls) == (1 if failure == "create" else 4)
