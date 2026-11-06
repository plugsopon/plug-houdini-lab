#!/usr/bin/env python
"""The Lab's skill catalog — one versioned, repo-owned list of the skills Plug authored here, so
that anyone who opens or clones this repo (Codex, Dremzo Code with any engine, FX AI inside
Houdini) sees the SAME skills, by the same name, at the same content version.

    python tools/skills_catalog.py            write skills/CATALOG.json + the Codex mirrors
    python tools/skills_catalog.py --check    exit 1 when the catalog or a mirror is stale (tests, CI)
    python tools/skills_catalog.py --probe <project-root>
                                              what a client opening THAT folder would see (read-only)
    python tools/skills_catalog.py --fxai [packages/fx_ai.json]
                                              what the installed FX AI (Claude inside Houdini) would see:
                                              FXAI_HOME from the Houdini package, its checkout, its skills

Where things live, and which copy is the truth:
  .claude/skills/<name>/SKILL.md     CANONICAL. Claude Code (Dremzo Code's Claude engine, FX AI's chat)
                                     loads these itself when the project folder is the cwd.
  .agents/skills/<name>/SKILL.md     GENERATED mirror for Codex (reads .agents/skills in a project).
                                     Never edited by hand: `.mirror-source` names the canonical file and
                                     its sha256, and --check fails on any drift.
  skills/CATALOG.json                GENERATED index: name, description, path, every file's sha256 and a
                                     content_id (first 12 hex of the sha256 over the file list). The same
                                     content_id on three clients = the same skill version.

Only the Python standard library (works in hython too). No network, no model, nothing installed.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

CATALOG_VERSION = 1
CANON = os.path.join(".claude", "skills")
MIRROR = os.path.join(".agents", "skills")
CATALOG = os.path.join("skills", "CATALOG.json")
MARK = ".mirror-source"
REPO_SLUG = "plugsopon/plug-houdini-lab"
BANNER = ("<!-- GENERATED MIRROR for Codex of {canon} (content_id {cid}). Do not edit this copy: change the\n"
          "     canonical file, then run `python tools/skills_catalog.py`; `--check` fails while they differ. -->\n")


def repo_root(start: str | None = None) -> str:
    here = os.path.abspath(start or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return here


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def frontmatter(text: str) -> tuple[dict, str, str]:
    """(meta, raw frontmatter block incl. fences, body)."""
    m = re.match(r"^﻿?(---\r?\n(.*?)\r?\n---\r?\n?)", text, re.S)
    if not m:
        return {}, "", text
    meta: dict = {}
    for line in m.group(2).splitlines():
        kv = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if kv:
            meta[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return meta, m.group(1), text[m.end():]


def walk_files(base: str) -> list[str]:
    out: list[str] = []
    for d, dirs, files in os.walk(base):
        dirs.sort()
        for f in sorted(files):
            out.append(os.path.relpath(os.path.join(d, f), base).replace(os.sep, "/"))
    return sorted(out)


def _inside(base: str, p: str) -> bool:
    b, q = os.path.normcase(base), os.path.normcase(p)
    return q.startswith(b.rstrip("\\/") + os.sep)


def _is_link(p: str) -> bool:
    """A symlink OR a Windows junction (os.path.islink is False for junctions, and os.path.isjunction is 3.12+ while
    hython may be 3.11): the entry resolves somewhere other than its own name inside its real parent, or is dangling."""
    if os.path.islink(p) or (os.path.lexists(p) and not os.path.exists(p)):
        return True
    try:
        here = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
        return os.path.normcase(os.path.realpath(p)) != os.path.normcase(here)
    except OSError:
        return True


def escapes(root: str, canon_dir: str = CANON) -> list[str]:
    """Links under <root>/<canon_dir> (that folder, its parent, or anything inside) that lead OUT of the repo, or cannot
    be resolved. Claude Code's own loader follows links (measured on claude.exe 2.1.226), so FX AI started in a checkout
    with one would load a skill from elsewhere. Read-only and fail closed: only lstat/realpath run on a link; nothing it
    points to outside the repo is listed, stat'ed or read. Empty = every path stays inside."""
    rroot = os.path.realpath(root)
    out: list[str] = []
    rel_parts = canon_dir.split(os.sep)
    for i in range(1, len(rel_parts) + 1):   # .claude, then .claude/skills
        p = os.path.join(root, *rel_parts[:i])
        if _is_link(p):
            try:
                rp = os.path.realpath(p, strict=True)
            except OSError:
                return [f"{'/'.join(rel_parts[:i])}: a link whose target is missing"]
            if not _inside(rroot, rp):
                return [f"{'/'.join(rel_parts[:i])}: a link that leads outside the repo"]
    base = os.path.join(root, canon_dir)
    if not os.path.isdir(base):
        return out

    def walk(d: str, rel: str, depth: int) -> None:
        if depth > 12:
            out.append(f"{rel}: too deep to check")
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError as e:
            out.append(f"{rel}: cannot be listed ({e.__class__.__name__})")
            return
        for e in entries:
            r = f"{rel}/{e.name}"
            if _is_link(e.path):
                try:
                    rp = os.path.realpath(e.path, strict=True)
                except OSError:
                    out.append(f"{r}: a link whose target is missing")
                    continue
                if not _inside(rroot, rp):
                    out.append(f"{r}: a link that leads outside the repo")
                    continue
                if os.path.isdir(rp):
                    walk(rp, r, depth + 1)
            elif e.is_dir(follow_symlinks=False):
                walk(e.path, r, depth + 1)
    walk(base, canon_dir.replace(os.sep, "/"), 0)
    return out


def _contained_skill(root: str, d: str) -> bool:
    """The skill folder and its SKILL.md both resolve inside the repo — checked BEFORE anything is read."""
    try:
        rd = os.path.realpath(d, strict=True)
        rf = os.path.realpath(os.path.join(d, "SKILL.md"), strict=True)
    except OSError:
        return False
    rroot = os.path.realpath(root)
    return _inside(rroot, rd) and _inside(rd, rf)


def scan(root: str, canon_dir: str = CANON) -> list[dict]:
    """Every skill under <root>/<canon_dir>: name, description, files with sha256, content_id. A skill folder (or its
    SKILL.md) that leads out of the repo is skipped unread — `escapes()` reports it."""
    base = os.path.join(root, canon_dir)
    skills: list[dict] = []
    canon = canon_dir.replace(os.sep, "/")
    bad = [e.split(":", 1)[0] for e in escapes(root, canon_dir)]
    if not os.path.isdir(base) or any(not b.startswith(canon + "/") for b in bad):
        return skills   # .claude or .claude/skills itself leads out / cannot be resolved: nothing is read
    for entry in sorted(os.listdir(base)):
        d = os.path.join(base, entry)
        skill_md = os.path.join(d, "SKILL.md")
        here = f"{canon}/{entry}"
        if any(b == here or b.startswith(here + "/") for b in bad) or not _contained_skill(root, d):
            continue
        if not os.path.isdir(d) or not os.path.isfile(skill_md):
            continue
        with open(skill_md, "r", encoding="utf-8") as f:
            meta, _, _ = frontmatter(f.read())
        files = {rel: sha256_file(os.path.join(d, rel)) for rel in walk_files(d)}
        digest = hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()
        skills.append({
            "name": meta.get("name") or entry,
            "folder": entry,
            "description": meta.get("description", ""),
            "version": meta.get("version"),
            "path": f"{canon_dir.replace(os.sep, '/')}/{entry}",
            "skill_md_sha256": files["SKILL.md"],
            "content_id": digest[:12],
            "files": files,
        })
    return skills


def git_head(root: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def catalog_json(skills: list[dict]) -> str:
    doc = {
        "catalog_version": CATALOG_VERSION,
        "repo": REPO_SLUG,
        "canonical": CANON.replace(os.sep, "/"),
        "codex_mirror": MIRROR.replace(os.sep, "/"),
        "how": {
            "claude-code": "opens the project folder: .claude/skills is loaded as project skills (Dremzo Code Claude engine, FX AI chat in Houdini)",
            "codex": "opens the project folder: .agents/skills (generated mirror, same content as .claude/skills)",
            "dremzo-code get_skill": "the dremzo MCP tool get_skill lists this project's skills for the chat's project and reads one by name (Gemini, GPT, Antigravity, Claude)",
            "regenerate": "python tools/skills_catalog.py   (then commit skills/CATALOG.json and .agents/skills)",
        },
        "skills": [{k: v for k, v in s.items()} for s in skills],
    }
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def mirror_files(root: str, s: dict) -> dict[str, str]:
    """The files a Codex mirror folder must hold, as rel path -> text."""
    canon_md = os.path.join(root, CANON, s["folder"], "SKILL.md")
    with open(canon_md, "r", encoding="utf-8") as f:
        text = f.read()
    meta, fm, body = frontmatter(text)
    # references stay in ONE place: links into the skill's own folder are rewritten to the canonical copy
    up = f"../../../{CANON.replace(os.sep, '/')}/{s['folder']}/"
    # link TARGETS first (`](references/x.md)`), then bare `references/x.md` mentions that are not link text
    body = re.sub(r"\]\((?!https?://|/|\.\./|#)([^)\s]+)\)", lambda m: f"]({up}{m.group(1)})", body)
    body = re.sub(r"(?<![\w/.\[(`])(references/[\w./-]+)", lambda m: f"{up}{m.group(1)}", body)
    banner = BANNER.format(canon=s["path"] + "/SKILL.md", cid=s["content_id"])
    short = s["description"].split(". ")[0].strip()
    if len(short) > 110:
        short = short[:107].rstrip() + "..."
    title = s["name"].replace("-", " ")
    yaml = f'interface:\n  display_name: "{title}"\n  short_description: "{short.replace(chr(34), chr(39))}"\n'
    return {
        "SKILL.md": (fm or "") + banner + body,
        MARK: f"{s['path']}/SKILL.md\nsha256 {s['skill_md_sha256']}\ncontent_id {s['content_id']}\n",
        "agents/openai.yaml": yaml,
    }


def expected_state(root: str) -> tuple[list[dict], str, dict[str, dict[str, str]]]:
    skills = scan(root)
    return skills, catalog_json(skills), {s["folder"]: mirror_files(root, s) for s in skills}


def write_all(root: str) -> list[str]:
    skills, cat, mirrors = expected_state(root)
    written: list[str] = []
    cat_path = os.path.join(root, CATALOG)
    os.makedirs(os.path.dirname(cat_path), exist_ok=True)
    with open(cat_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(cat)
    written.append(CATALOG.replace(os.sep, "/"))
    mdir = os.path.join(root, MIRROR)
    os.makedirs(mdir, exist_ok=True)
    for folder, files in mirrors.items():
        for rel, text in files.items():
            p = os.path.join(mdir, folder, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            written.append(f"{MIRROR.replace(os.sep, '/')}/{folder}/{rel}")
    # a mirror whose canonical skill is gone is removed (only ours: it carries the mark)
    for entry in sorted(os.listdir(mdir)):
        if entry not in mirrors and os.path.isfile(os.path.join(mdir, entry, MARK)):
            for rel in walk_files(os.path.join(mdir, entry)):
                os.remove(os.path.join(mdir, entry, rel))
            for d, dirs, _ in os.walk(os.path.join(mdir, entry), topdown=False):
                os.rmdir(d)
            written.append(f"removed {MIRROR.replace(os.sep, '/')}/{entry}")
    return written


def check(root: str) -> list[str]:
    """Problems that make the committed catalog/mirrors differ from the canonical skills. Empty = clean."""
    problems: list[str] = [f"{e} (Claude Code would load it by itself)" for e in escapes(root)]
    skills, cat, mirrors = expected_state(root)
    if not skills:
        problems.append(f"no skills under {CANON}")
    cat_path = os.path.join(root, CATALOG)
    if not os.path.isfile(cat_path):
        problems.append(f"missing {CATALOG}")
    else:
        with open(cat_path, "r", encoding="utf-8") as f:
            if f.read() != cat:
                problems.append(f"stale {CATALOG} (run tools/skills_catalog.py)")
    mdir = os.path.join(root, MIRROR)
    for folder, files in mirrors.items():
        for rel, text in files.items():
            p = os.path.join(mdir, folder, rel)
            if not os.path.isfile(p):
                problems.append(f"missing mirror {MIRROR}/{folder}/{rel}")
                continue
            with open(p, "r", encoding="utf-8") as f:
                if f.read() != text:
                    problems.append(f"drifted mirror {MIRROR}/{folder}/{rel}")
        if os.path.isdir(os.path.join(mdir, folder)):
            extra = [r for r in walk_files(os.path.join(mdir, folder)) if r not in files]
            for r in extra:
                problems.append(f"unexpected file in mirror {MIRROR}/{folder}/{r}")
    if os.path.isdir(mdir):
        for entry in sorted(os.listdir(mdir)):
            if entry not in mirrors:
                problems.append(f"mirror without a canonical skill: {MIRROR}/{entry}")
    return [p.replace(os.sep, "/") for p in problems]


def claude_native_dirs(cwd: str) -> list[str]:
    """The .claude/skills folders Claude Code's own loader auto-loads for a session started in <cwd> (traced in
    claude.exe 2.1.226): <dir>/.claude/skills for cwd and each parent, stopping BEFORE the home folder and AT the git
    root (inclusive). FX AI starts claude with cwd = its checkout (brother_chat.REPO), so for a git checkout this is just
    <checkout>/.claude/skills. Existence only (lexists) — nothing is listed or read."""
    out: list[str] = []
    home = os.path.normcase(os.path.abspath(os.path.expanduser("~")))
    d = os.path.abspath(cwd)
    while True:
        if os.path.normcase(d) == home:
            break
        s = os.path.join(d, ".claude", "skills")
        if os.path.lexists(s):
            out.append(s.replace(os.sep, "/"))
        if os.path.lexists(os.path.join(d, ".git")):
            break
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return out


def probe(root: str) -> dict:
    """What a client that opens <root> sees. Read-only; never writes."""
    root = os.path.abspath(root)
    out: dict = {"root": root, "git_head": git_head(root), "catalog": None, "skills": [], "problems": []}
    if not os.path.isdir(root):
        out["problems"].append("folder does not exist")
        return out
    out["claude_native_dirs"] = claude_native_dirs(root)
    for e in escapes(root):
        out["problems"].append(f"{e} - Claude Code (FX AI) would load it by itself; not listed here, not read")
    skills = scan(root)
    out["skills"] = [{"name": s["name"], "content_id": s["content_id"], "version": s["version"], "path": s["path"]} for s in skills]
    cat_path = os.path.join(root, CATALOG)
    if os.path.isfile(cat_path):
        try:
            with open(cat_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            listed = {s["name"]: s["content_id"] for s in doc.get("skills", [])}
            out["catalog"] = {"path": CATALOG.replace(os.sep, "/"), "skills": len(listed), "repo": doc.get("repo")}
            for s in skills:
                if s["name"] not in listed:
                    out["problems"].append(f"{s['name']}: not in catalog")
                elif listed[s["name"]] != s["content_id"]:
                    out["problems"].append(f"{s['name']}: catalog content_id {listed[s['name']]} != files {s['content_id']}")
            for name in listed:
                if name not in {s["name"] for s in skills}:
                    out["problems"].append(f"{name}: in catalog but not on disk")
        except Exception as e:  # noqa: BLE001
            out["problems"].append(f"catalog unreadable: {e}")
    else:
        out["problems"].append(f"no {CATALOG.replace(os.sep, '/')} - skills (if any) are visible to Claude Code / Dremzo Code by folder, but unversioned")
    mdir = os.path.join(root, MIRROR)
    out["codex_mirror"] = sorted(os.listdir(mdir)) if os.path.isdir(mdir) else None
    if not skills:
        out["problems"].append(f"no skills under {CANON}")
    return out


def fxai_probe(package: str | None) -> dict:
    """The installed FX AI: FXAI_HOME from Houdini's package file, and what that checkout holds."""
    cands = [package] if package else []
    if not package:
        env = os.environ.get("FXAI_HOME")
        pref = os.environ.get("HOUDINI_USER_PREF_DIR")
        if pref:
            cands.append(os.path.join(pref, "packages", "fx_ai.json"))
        cands += sorted(glob.glob(os.path.join(os.path.expanduser("~"), "Documents", "houdini*", "packages", "fx_ai.json")))
    out: dict = {"package": None, "fxai_home": None, "probe": None, "problems": []}
    for c in cands:
        if c and os.path.isfile(c):
            out["package"] = c
            try:
                with open(c, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                for e in doc.get("env", []):
                    if isinstance(e, dict) and "FXAI_HOME" in e:
                        out["fxai_home"] = e["FXAI_HOME"]
            except Exception as e:  # noqa: BLE001
                out["problems"].append(f"package unreadable: {e}")
            break
    if not out["fxai_home"] and not package:
        out["fxai_home"] = os.environ.get("FXAI_HOME")
    if not out["package"] and not out["fxai_home"]:
        out["problems"].append("FX AI is not installed here (no packages/fx_ai.json and no $FXAI_HOME)")
        return out
    if out["fxai_home"]:
        # The launcher (mcp/houdini/brother_chat.py, loaded from $FXAI_HOME by pythonrc.py) starts claude with
        # cwd = REPO = three folders above its own file, i.e. the checkout at FXAI_HOME. Say so only when that file is
        # really there, and probe exactly that folder.
        launcher = os.path.join(out["fxai_home"], "mcp", "houdini", "brother_chat.py")
        out["launcher"] = launcher.replace(os.sep, "/") if os.path.isfile(launcher) else None
        out["launcher_root"] = (os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(launcher))))
                                .replace(os.sep, "/") if out["launcher"] else None)
        if not out["launcher"]:
            out["problems"].append("no mcp/houdini/brother_chat.py under FXAI_HOME - FX AI cannot start from it")
        out["probe"] = probe(out["launcher_root"] or out["fxai_home"])
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="repo root (default: the repo this script lives in)")
    ap.add_argument("--check", action="store_true", help="verify only; exit 1 on drift")
    ap.add_argument("--probe", metavar="DIR", help="read-only: what a client opening DIR sees")
    ap.add_argument("--fxai", nargs="?", const="", metavar="FX_AI_JSON", help="read-only: what the installed FX AI sees")
    ap.add_argument("--json", action="store_true", help="machine-readable output for --probe/--fxai")
    a = ap.parse_args(argv)
    if a.probe is not None:
        r = probe(a.probe)
        print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else _fmt_probe(r))
        return 0 if r["skills"] and not r["problems"] else 2
    if a.fxai is not None:
        r = fxai_probe(a.fxai or None)
        print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else _fmt_fxai(r))
        ok = bool(r.get("probe")) and bool(r["probe"]["skills"]) and not r["problems"] and not r["probe"]["problems"]
        return 0 if ok else 2
    root = repo_root(a.root)
    if a.check:
        problems = check(root)
        for p in problems:
            print("DRIFT:", p)
        print("skills catalog: OK" if not problems else f"skills catalog: {len(problems)} problem(s)")
        return 0 if not problems else 1
    for w in write_all(root):
        print("wrote", w)
    problems = check(root)
    return 0 if not problems else 1


def _fmt_probe(r: dict) -> str:
    lines = [f"project: {r['root']}  (git {r['git_head'] or 'n/a'})",
             f"catalog: {r['catalog'] or 'none'}",
             f"codex mirror (.agents/skills): {r.get('codex_mirror')}"]
    for s in r["skills"]:
        lines.append(f"  skill {s['name']}  content_id {s['content_id']}  version {s['version'] or '-'}  {s['path']}")
    for p in r["problems"]:
        lines.append(f"  ! {p}")
    return "\n".join(lines)


def _fmt_fxai(r: dict) -> str:
    lines = [f"FX AI package: {r['package'] or 'none'}", f"FXAI_HOME: {r['fxai_home'] or 'unset'}"]
    for p in r["problems"]:
        lines.append(f"  ! {p}")
    if r.get("probe"):
        lines.append(_fmt_probe(r["probe"]))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
