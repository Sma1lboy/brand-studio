from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "skills" / "brand-studio" / "scripts" / "harness.py"


def load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("brand_studio_skill_launcher", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata(root: Path) -> dict[str, object]:
    return {
        "project": {
            "id": "current-product",
            "root": str(root),
            "marketingRoot": "packages/branding/marketing",
        },
        "organization": {
            "id": "codefox-org",
            "name": "CodeFox Org",
        },
        "theme": {
            "path": "packages/branding/marketing/theme.md",
            "campaigns": "packages/branding/marketing/campaigns",
            "references": "packages/branding/marketing/references",
        },
        "campaign": {
            "name": "launch",
            "path": "packages/branding/marketing/campaigns/launch.campaign.yaml",
        },
        "artifacts": {
            "scratch": "packages/branding/.harness/out",
            "approved": "packages/branding/public/marketing",
        },
        "state": {
            "plans": "packages/branding/marketing/plans",
            "assetIndex": "packages/branding/marketing/asset-state.yaml",
            "accepted": "packages/branding/marketing/accepted.yaml",
            "directoryStateFile": "asset-state.yaml",
        },
        "sources": {
            "assetRoots": [
                "packages/branding/marketing",
                "packages/branding/public/marketing",
            ],
            "relatedRepos": [],
        },
        "skills": {
            "image": "gpt-image",
        },
    }


def test_metadata_supplies_validate_and_render_paths(tmp_path: Path) -> None:
    launcher = load_launcher()
    meta = metadata(tmp_path)

    validate_args = launcher.apply_metadata_args(["validate"], meta)
    render_args = launcher.apply_metadata_args(["render", "--dry-run"], meta)

    campaign = str(tmp_path / "packages/branding/marketing/campaigns/launch.campaign.yaml")
    theme = str(tmp_path / "packages/branding/marketing/theme.md")
    outputs = str(tmp_path / "packages/branding/.harness/out")
    assert validate_args == ["validate", campaign, "--theme", theme]
    assert render_args == [
        "render",
        campaign,
        "--dry-run",
        "--theme",
        theme,
        "--outputs-dir",
        outputs,
    ]


def test_metadata_project_paths_are_root_relative(tmp_path: Path) -> None:
    launcher = load_launcher()

    paths = launcher.project_paths(metadata(tmp_path), tmp_path)

    assert paths["marketing_root"] == tmp_path / "packages/branding/marketing"
    assert paths["campaigns_dir"] == tmp_path / "packages/branding/marketing/campaigns"
    assert paths["references_dir"] == tmp_path / "packages/branding/marketing/references"
    assert paths["plans_dir"] == tmp_path / "packages/branding/marketing/plans"
    assert paths["asset_index"] == tmp_path / "packages/branding/marketing/asset-state.yaml"
    assert paths["accepted_state"] == tmp_path / "packages/branding/marketing/accepted.yaml"
    assert paths["directory_state_file"] == "asset-state.yaml"


def test_launcher_resolves_to_bundled_cli() -> None:
    launcher = load_launcher()

    assert launcher.bundled_cli_command() == [
        sys.executable,
        str(ROOT / "skills/brand-studio/scripts/cli.py"),
    ]


def test_bootstrap_is_dry_run_until_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    launcher = load_launcher()
    meta = metadata(tmp_path)
    marketing_root = tmp_path / "packages/branding/marketing"
    plans = tmp_path / "packages/branding/marketing/plans"
    accepted_parent = tmp_path / "packages/branding/marketing"
    scratch = tmp_path / "packages/branding/.harness/out"

    assert launcher.bootstrap_project([str(tmp_path)], meta, "marketing.harness.yaml") == 0
    assert not marketing_root.exists()
    assert not scratch.exists()
    assert "mode=dry-run" in capsys.readouterr().out

    assert (
        launcher.bootstrap_project(["--write", str(tmp_path)], meta, "marketing.harness.yaml")
        == 0
    )
    assert marketing_root.is_dir()
    assert plans.is_dir()
    assert accepted_parent.is_dir()
    assert scratch.is_dir()
    assert "mode=write" in capsys.readouterr().out


def test_publish_is_not_a_user_facing_command() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "skills/brand-studio/scripts/cli.py"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "publish" not in completed.stdout


def test_state_preflight_reads_repo_directory_and_related_state(tmp_path: Path) -> None:
    launcher = load_launcher()
    project = tmp_path / "repo-a"
    related = tmp_path / "repo-b"
    accepted = project / "packages/branding/marketing/accepted.yaml"
    directory_state = project / "packages/branding/public/marketing/banner/asset-state.yaml"
    related_state = related / "packages/branding/marketing/accepted.yaml"
    metadata_path = project / "marketing.harness.yaml"

    accepted.parent.mkdir(parents=True)
    directory_state.parent.mkdir(parents=True)
    related_state.parent.mkdir(parents=True)
    accepted.write_text(
        """
schema_version: "1.0"
owner:
  kind: "repo"
  id: "repo-a"
revision: 1
accepted:
  - id: "launch-banner"
    asset_id: "web-banner"
""".lstrip(),
        encoding="utf-8",
    )
    directory_state.write_text(
        """
schema_version: "1.0"
owner:
  kind: "directory"
  id: "banner"
revision: 2
assets:
  - id: "landscape-banner"
patterns:
  - id: "dark-grid"
""".lstrip(),
        encoding="utf-8",
    )
    related_state.write_text(
        """
schema_version: "1.0"
owner:
  kind: "repo"
  id: "repo-b"
revision: 4
accepted:
  - id: "launch-card"
""".lstrip(),
        encoding="utf-8",
    )

    metadata_path.write_text(
        """
project:
  id: current-product
  root: .
  marketingRoot: packages/branding/marketing
organization:
  id: codefox-org
  name: CodeFox Org
theme:
  path: packages/branding/marketing/theme.md
  campaigns: packages/branding/marketing/campaigns
  references: packages/branding/marketing/references
artifacts:
  scratch: packages/branding/.harness/out
  approved: packages/branding/public/marketing
state:
  plans: packages/branding/marketing/plans
  assetIndex: packages/branding/marketing/asset-state.yaml
  accepted: packages/branding/marketing/accepted.yaml
  directoryStateFile: asset-state.yaml
sources:
  assetRoots:
    - packages/branding/marketing
    - packages/branding/public/marketing
  relatedRepos:
    - id: repo-b
      kind: sibling-product
      root: ../repo-b
      state: packages/branding/marketing/accepted.yaml
""".lstrip(),
        encoding="utf-8",
    )

    loaded = launcher.load_metadata(str(metadata_path))
    snapshot = launcher.collect_state_snapshot(loaded, project, str(metadata_path))

    assert snapshot["errors"] == []
    state_summaries = {
        Path(entry["path"]).name: entry["summary"]
        for entry in snapshot["state_files"]
        if entry["exists"]
    }
    assert state_summaries["accepted.yaml"]["accepted_count"] == 1
    assert state_summaries["asset-state.yaml"]["asset_count"] == 1
    assert state_summaries["asset-state.yaml"]["pattern_count"] == 1
    assert snapshot["organization"]["id"] == "codefox-org"
    assert snapshot["theme"]["path"] == "packages/branding/marketing/theme.md"
    assert snapshot["related_repos"][0]["state_summary"]["accepted_count"] == 1
    assert any("accepted.yaml" in path for path in snapshot["read_before_production"])


def test_render_dry_run_uses_bundled_scripts(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "packages/branding/marketing/theme.md"
    campaign = project / "packages/branding/marketing/campaigns/launch.campaign.yaml"
    metadata_path = project / "marketing.harness.json"
    theme.parent.mkdir(parents=True)
    campaign.parent.mkdir(parents=True)
    theme.write_text(
        """
---
repo:
  id: test-repo
  name: Test Repo
version: 1.0.0
producer:
  params:
    seed_strategy: fixed
    seed: 7
    output_format: png
global:
  style-fragment:
    base:
      $value: clean editorial product lighting
      $type: text
  color:
    primary:
      $value: "#112233"
      $type: color
alias:
  style:
    launch-hero:
      $value:
        prompt: "{global.style-fragment.base}"
        palette:
          - "{global.color.primary}"
        negative: ""
        references: []
      $type: composite
---

# Test Repo Theme
""".lstrip(),
        encoding="utf-8",
    )
    campaign.write_text(
        """
name: launch
brief: Launch image
style: launch-hero
content:
  headline: Hello
  subject: Product on a table
deliverables:
  - id: web-banner
    size: [320, 120]
""".lstrip(),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata(project)), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "render",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output_dir = project / "packages/branding/.harness/out/launch"
    assert (output_dir / "web-banner.svg").is_file()
    assert (output_dir / "manifest.json").is_file()


def test_release_render_reads_monorepo_package_changelog_and_renders(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "packages/branding/marketing/theme.md"
    changelog = project / "packages/kobe/CHANGELOG.md"
    metadata_path = project / "marketing.harness.json"
    theme.parent.mkdir(parents=True)
    changelog.parent.mkdir(parents=True)
    theme.write_text(
        """
---
repo:
  id: test-repo
  name: Test Repo
version: 1.0.0
producer:
  params:
    seed_strategy: fixed
    seed: 7
    output_format: png
global:
  style-fragment:
    base:
      $value: clean release editorial product board
      $type: text
  color:
    primary:
      $value: "#112233"
      $type: color
alias:
  style:
    launch-hero:
      $value:
        prompt: "{global.style-fragment.base}"
        palette:
          - "{global.color.primary}"
        negative: ""
        references: []
      $type: composite
---

# Test Repo Theme
""".lstrip(),
        encoding="utf-8",
    )
    (project / "package.json").write_text(
        json.dumps({"name": "test-repo", "private": True, "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    (changelog.parent / "package.json").write_text(
        json.dumps({"name": "kobe", "version": "0.7.33"}),
        encoding="utf-8",
    )
    changelog.write_text(
        """
# Changelog

## 0.7.33

### Patch Changes

- dda80e9: Creating a task with `n` now drops you straight into the new task's engine pane.
- 9653cd7: TUI task sessions now expose tmux-native layout controls.

## 0.7.32

- Older release note that should not be used.
""".lstrip(),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata(project)), encoding="utf-8")

    generated_campaign = (
        project / "packages/branding/marketing/campaigns/release-v0-7-33.campaign.yaml"
    )
    copy_path = project / "packages/branding/.harness/out/release-v0-7-33/copy.yaml"
    copy = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-copy",
            "--write",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert copy.returncode == 0, copy.stderr
    assert "release_source=changelog" in copy.stdout
    assert "changelog_count=1" in copy.stdout
    assert "copy_status=created" in copy.stdout
    copy_text = copy_path.read_text(encoding="utf-8")
    assert 'kind: "release_copy"' in copy_text
    assert 'product: "kobe"' in copy_text
    assert 'version: "0.7.33"' in copy_text
    assert 'release_theme: "Faster task starts, deeper workspace control"' in copy_text
    assert 'title: "Jump straight into the engine"' in copy_text
    assert 'title: "Control layouts without losing work"' in copy_text
    copy_path.write_text(
        copy_text.replace(
            'headline: "Faster task starts, deeper workspace control"',
            'headline: "Manual release headline"',
        ).replace(
            'subheadline: "kobe 0.7.33 sharpens faster task starts, deeper workspace control."',
            'subheadline: "Manual revised subheadline."',
        ),
        encoding="utf-8",
    )

    release = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-render",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert release.returncode == 0, release.stderr
    assert "release_source=copy" in release.stdout
    assert "changelog_count=1" in release.stdout
    assert "copy_status=existing" in release.stdout
    assert "campaign_status=created" in release.stdout
    assert "producer_skill=gpt-image" in release.stdout
    assert "producer_context=" in release.stdout
    campaign_text = generated_campaign.read_text(encoding="utf-8")
    assert 'name: "release-v0-7-33"' in campaign_text
    assert 'headline: "Manual release headline"' in campaign_text
    assert "Manual revised subheadline." in campaign_text
    assert "Creating a task with n now drops you straight" in campaign_text
    assert "TUI task sessions now expose tmux-native layout controls." in campaign_text

    output_dir = project / "packages/branding/.harness/out/release-v0-7-33"
    assert (output_dir / "release-card.svg").is_file()
    assert (output_dir / "manifest.json").is_file()
    producer_context = json.loads(
        (output_dir / "producer-context.json").read_text(encoding="utf-8")
    )
    assert producer_context["kind"] == "producer_context"
    assert producer_context["capability"] == "image"
    assert producer_context["producer_skill"] == "gpt-image"
    assert producer_context["copy"] == str(copy_path)
    assert producer_context["campaign"] == str(generated_campaign)
    assert producer_context["assets"][0]["id"] == "release-card"
    assert producer_context["assets"][0]["size"] == [1200, 630]
    release_prompt = producer_context["assets"][0]["prompt"]
    assert "Manual release headline" in release_prompt
    assert "tmux-native layout controls" in release_prompt
    assert "release notes page" in release_prompt
    assert "chronological release list" in release_prompt
    assert "The release notes are the main subject" in release_prompt
    assert "Do not make the changelog a small side panel" in release_prompt
