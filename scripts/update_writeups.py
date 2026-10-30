#!/usr/bin/env python3
"""Update the "Latest Writeups" table in the profile README.

Reads every Markdown file inside a folder of the writeups repo (e.g. htb/<box>/README.md
or "HTB Principal/Principal.md"), keeps those whose YAML front matter has a date, sorts by
date and writes the newest entries between the WRITEUPS markers in this README.
Folders or files starting with "_" (templates) are skipped, and so is any writeup with
"status: active" in its front matter.

    python scripts/update_writeups.py                     # GitHub mode (used by the workflow)
    python scripts/update_writeups.py --local ../writeups # test against a local clone
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import quote
from pathlib import Path

import yaml

OWNER = "tscherwinski"
REPO = "writeups"
BRANCH = "main"
LIMIT = 5
README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!-- WRITEUPS:START -->", "<!-- WRITEUPS:END -->"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-readme-updater"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def frontmatter(text):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}
    return {}


def wanted(path):
    parts = path.split("/")
    return (
        len(parts) > 1
        and path.lower().endswith(".md")
        and not any(part.startswith("_") for part in parts)
    )


def collect_remote():
    tree = json.loads(get(f"https://api.github.com/repos/{OWNER}/{REPO}/git/trees/{BRANCH}?recursive=1"))
    for item in tree.get("tree", []):
        p = item["path"]
        if item.get("type") == "blob" and wanted(p):
            raw = get(f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{quote(p)}")
            yield p, frontmatter(raw)


def collect_local(root: Path):
    for f in root.rglob("*.md"):
        rel = f.relative_to(root).as_posix()
        if wanted(rel):
            yield rel, frontmatter(f.read_text(encoding="utf-8"))


def table(entries):
    rows = ["| Machine | Platform | OS | Difficulty |", "|---|---|---|---|"]
    for path, m in entries:
        link = f"https://github.com/{OWNER}/{REPO}/blob/{BRANCH}/{quote(path)}"
        name = m.get("title") or path.rsplit("/", 1)[0].rsplit("/", 1)[-1]
        rows.append(f"| [{name}]({link}) | {m.get('platform', '')} "
                    f"| {m.get('os', '')} | {m.get('difficulty', '')} |")
    rows.append("")
    rows.append(f"[All writeups](https://github.com/{OWNER}/{REPO})")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="path to a local clone of the writeups repo")
    a = ap.parse_args()

    try:
        found = list(collect_local(Path(a.local)) if a.local else collect_remote())
    except urllib.error.HTTPError as e:
        print(f"Writeups repo not reachable yet ({e.code}), nothing to update")
        return
    found = [
        e for e in found
        if e[1].get("date") and str(e[1].get("status", "")).strip().lower() != "active"
    ]
    found.sort(key=lambda e: str(e[1]["date"]), reverse=True)

    readme = README.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        raise SystemExit("WRITEUPS markers not found in README.md")
    new_block = f"{START}\n{table(found[:LIMIT])}\n{END}"
    updated = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: new_block, readme, flags=re.S)

    if updated != readme:
        README.write_text(updated, encoding="utf-8")
        print(f"README updated with {min(len(found), LIMIT)} writeups")
    else:
        print("README already up to date")


if __name__ == "__main__":
    main()
