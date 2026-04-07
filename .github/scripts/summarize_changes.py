#!/usr/bin/env python3
"""Generic change summarizer for automation pipelines.

Runs after the pipeline, captures git diff, and writes run-summary.json.
If rich-changes.json exists (from a custom reporter), merges its changes.
"""

import json
import subprocess
import os
from datetime import datetime, timezone


def get_changed_files():
    """Get list of changed/new/untracked files."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True
    )
    files = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        files.update(result.stdout.strip().split("\n"))
    return sorted(f for f in files if f)


def get_diff_stats():
    """Get insertion/deletion counts."""
    result = subprocess.run(
        ["git", "diff", "--shortstat", "HEAD"],
        capture_output=True, text=True
    )
    text = result.stdout.strip()
    insertions = deletions = 0
    for part in text.split(","):
        if "insertion" in part:
            insertions = int(part.strip().split()[0])
        elif "deletion" in part:
            deletions = int(part.strip().split()[0])
    return insertions, deletions


def categorize_files(files):
    """Categorize changed files into types."""
    categories = {"data": [], "dashboard": [], "config": [], "other": []}
    for f in files:
        if f.endswith((".json", ".csv", ".tsv")):
            categories["data"].append(f)
        elif f.endswith(".html"):
            categories["dashboard"].append(f)
        elif f.endswith((".yaml", ".yml", ".toml", ".cfg")):
            categories["config"].append(f)
        else:
            categories["other"].append(f)
    return categories


def build_generic_changes(files, categories):
    """Build human-readable change descriptions from file list."""
    changes = []
    for html_file in categories["dashboard"]:
        changes.append(f"{os.path.basename(html_file)} updated")
    data_files = categories["data"]
    if data_files:
        dirs = {}
        for f in data_files:
            d = os.path.dirname(f) or "."
            dirs.setdefault(d, []).append(f)
        for d, fs in dirs.items():
            if len(fs) == 1:
                changes.append(f"{fs[0]} updated")
            else:
                changes.append(f"{d}/ — {len(fs)} files updated")
    return changes


def main():
    files = get_changed_files()
    if not files:
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "changes": ["No changes detected"],
        }
    else:
        insertions, deletions = get_diff_stats()
        categories = categorize_files(files)
        changes = build_generic_changes(files, categories)
        rich_path = "rich-changes.json"
        if os.path.exists(rich_path):
            with open(rich_path) as f:
                rich = json.load(f)
            changes = rich.get("changes", []) + changes
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files_changed": len(files),
            "insertions": insertions,
            "deletions": deletions,
            "changes": changes,
        }

    with open("run-summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Run summary: {len(files)} files changed, {len(summary['changes'])} change entries")
    for c in summary["changes"]:
        print(f"  - {c}")


if __name__ == "__main__":
    main()
