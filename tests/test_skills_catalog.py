"""tools/skills_catalog.py — the Lab's skill catalog and Codex mirrors stay equal to the canonical
.claude/skills, and a probe answers honestly for a folder with and without skills.

    python -m unittest tests.test_skills_catalog -v        (from the repo root; stdlib only, no Houdini)

Every case works on a COPY of the repo's skills in a temp folder: the real repo is never written.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "skills_catalog.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import skills_catalog as sc  # noqa: E402


def run(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


class Fixture(unittest.TestCase):
    """A clean copy of the repo's canonical skills (no .git, no catalog, no mirrors) — what a fresh clone's
    skills look like before the tool runs."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="lab-skills-")
        shutil.copytree(os.path.join(ROOT, ".claude", "skills"), os.path.join(self.tmp, ".claude", "skills"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repo_itself_is_clean(self) -> None:
        """The committed catalog and mirrors equal the canonical skills (what CI/root checks)."""
        self.assertEqual(sc.check(ROOT), [], "run: python tools/skills_catalog.py")
        code, out = run("--check")
        self.assertEqual(code, 0, out)

    def test_generate_then_check(self) -> None:
        self.assertNotEqual(sc.check(self.tmp), [])  # fresh copy: no catalog, no mirrors yet
        sc.write_all(self.tmp)
        self.assertEqual(sc.check(self.tmp), [])
        doc = json.load(open(os.path.join(self.tmp, "skills", "CATALOG.json"), encoding="utf-8"))
        names = [s["name"] for s in doc["skills"]]
        self.assertIn("houdini-flower-endless-blossom", names)
        self.assertEqual(sorted(names), sorted(os.listdir(os.path.join(self.tmp, ".agents", "skills"))))
        for s in doc["skills"]:
            self.assertRegex(s["content_id"], r"^[0-9a-f]{12}$")
            self.assertIn("SKILL.md", s["files"])
            self.assertEqual(s["skill_md_sha256"], s["files"]["SKILL.md"])
            mark = open(os.path.join(self.tmp, ".agents", "skills", s["folder"], ".mirror-source"), encoding="utf-8").read()
            self.assertIn(s["skill_md_sha256"], mark)
            self.assertIn(s["content_id"], mark)
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".agents", "skills", s["folder"], "agents", "openai.yaml")))

    def test_same_files_same_content_id(self) -> None:
        """Identity is content, not location: the fixture copy and the repo give the same content_id."""
        mine = {s["name"]: s["content_id"] for s in sc.scan(self.tmp)}
        repo = {s["name"]: s["content_id"] for s in sc.scan(ROOT)}
        self.assertEqual(mine, repo)

    def test_mirror_keeps_frontmatter_and_points_references_at_canonical(self) -> None:
        sc.write_all(self.tmp)
        m = open(os.path.join(self.tmp, ".agents", "skills", "houdini-flower-endless-blossom", "SKILL.md"), encoding="utf-8").read()
        c = open(os.path.join(self.tmp, ".claude", "skills", "houdini-flower-endless-blossom", "SKILL.md"), encoding="utf-8").read()
        self.assertEqual(m.split("---")[1], c.split("---")[1], "frontmatter (name/description) must be identical")
        self.assertIn("GENERATED MIRROR", m)
        self.assertIn("](../../../.claude/skills/houdini-flower-endless-blossom/references/pipeline.md)", m)
        self.assertNotIn("](references/pipeline.md)", m)
        self.assertNotIn("[../../../", m, "link TEXT must stay readable; only the target is rewritten")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".agents", "skills", "houdini-flower-endless-blossom", "references")), "references are not copied")

    def test_drift_is_caught(self) -> None:
        sc.write_all(self.tmp)
        mirror = os.path.join(self.tmp, ".agents", "skills", "houdini-flower-endless-blossom", "SKILL.md")
        with open(mirror, "a", encoding="utf-8") as f:
            f.write("\nedited by hand\n")
        self.assertTrue(any("drifted mirror" in p for p in sc.check(self.tmp)), sc.check(self.tmp))
        sc.write_all(self.tmp)
        canon = os.path.join(self.tmp, ".claude", "skills", "houdini-flower-endless-blossom", "references", "lessons.md")
        with open(canon, "a", encoding="utf-8") as f:
            f.write("\nlesson 32\n")
        problems = sc.check(self.tmp)
        self.assertTrue(any("stale skills/CATALOG.json" in p for p in problems), problems)  # content_id moved
        sc.write_all(self.tmp)
        os.remove(os.path.join(self.tmp, "skills", "CATALOG.json"))
        self.assertTrue(any("missing skills/CATALOG.json" in p for p in sc.check(self.tmp)))
        sc.write_all(self.tmp)
        os.makedirs(os.path.join(self.tmp, ".agents", "skills", "stray"))
        with open(os.path.join(self.tmp, ".agents", "skills", "stray", "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: stray\n---\n")
        self.assertTrue(any("mirror without a canonical skill" in p for p in sc.check(self.tmp)))

    def test_removed_skill_removes_only_its_own_mirror(self) -> None:
        sc.write_all(self.tmp)
        shutil.rmtree(os.path.join(self.tmp, ".claude", "skills", "houdini-shelf-publish"))
        hand = os.path.join(self.tmp, ".agents", "skills", "hand-written")
        os.makedirs(hand)
        with open(os.path.join(hand, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: hand-written\n---\nmine\n")
        sc.write_all(self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".agents", "skills", "houdini-shelf-publish")))
        self.assertTrue(os.path.exists(os.path.join(hand, "SKILL.md")), "a folder without .mirror-source is never deleted")

    def test_probe_right_and_wrong_folder(self) -> None:
        sc.write_all(self.tmp)
        r = sc.probe(self.tmp)
        self.assertEqual(r["problems"], [])
        self.assertEqual({s["name"] for s in r["skills"]}, {s["name"] for s in sc.scan(ROOT)})
        code, out = run("--probe", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("houdini-flower-endless-blossom", out)
        wrong = tempfile.mkdtemp(prefix="lab-wrong-")
        try:
            r2 = sc.probe(wrong)
            self.assertEqual(r2["skills"], [])
            self.assertTrue(any("no skills" in p for p in r2["problems"]))
            code, out = run("--probe", wrong)
            self.assertEqual(code, 2, out)
            code, out = run("--probe", os.path.join(wrong, "does-not-exist"))
            self.assertEqual(code, 2, out)
            self.assertIn("does not exist", out)
        finally:
            shutil.rmtree(wrong, ignore_errors=True)

    def test_probe_reports_catalog_mismatch(self) -> None:
        sc.write_all(self.tmp)
        with open(os.path.join(self.tmp, ".claude", "skills", "houdini-builder-script", "SKILL.md"), "a", encoding="utf-8") as f:
            f.write("\nchanged after the catalog\n")
        r = sc.probe(self.tmp)
        self.assertTrue(any("houdini-builder-script: catalog content_id" in p for p in r["problems"]), r["problems"])

    def test_fxai_probe_reads_a_package_and_fails_honestly(self) -> None:
        sc.write_all(self.tmp)
        pkg = os.path.join(self.tmp, "fx_ai.json")
        with open(pkg, "w", encoding="utf-8") as f:
            json.dump({"env": [{"FXAI_HOME": self.tmp.replace("\\", "/")}]}, f)
        r = sc.fxai_probe(pkg)
        self.assertEqual(r["fxai_home"], self.tmp.replace("\\", "/"))
        self.assertEqual(r["probe"]["problems"], [])
        self.assertIn("houdini-flower-endless-blossom", {s["name"] for s in r["probe"]["skills"]})
        with open(pkg, "w", encoding="utf-8") as f:
            json.dump({"env": [{"FXAI_HOME": os.path.join(self.tmp, "nowhere")}]}, f)
        r = sc.fxai_probe(pkg)
        self.assertTrue(any("does not exist" in p for p in r["probe"]["problems"]))
        code, out = run("--fxai", os.path.join(self.tmp, "missing.json"))
        self.assertEqual(code, 2, out)
        self.assertIn("not installed", out)


if __name__ == "__main__":
    unittest.main()
