"""R56: FX AI (mcp/houdini/brother_chat.py) refuses to START claude when Claude Code's own skill loader would follow a
link out of the project - BEFORE any process is created. No Houdini, no Qt, no claude.exe, no model: `hou` and PySide6
are permissive stubs, QProcess is a recorder, every fixture is owned (each has its own .git so the walk never leaves it).

    python -m unittest tests/test_fxai_native_guard.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOUDINI = os.path.join(ROOT, "mcp", "houdini")


class _Meta(type):
    def __getattr__(cls, n):
        return _Any


class _Any(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return _Any()
    def __call__(self, *a, **k): return _Any()
    def __iter__(self): return iter(())
    def __bool__(self): return False
    def __int__(self): return 0
    def __index__(self): return 0
    def __float__(self): return 0.0
    def __str__(self): return ""
    def __or__(self, o): return _Any()
    __ror__ = __and__ = __rand__ = __add__ = __radd__ = __sub__ = __mul__ = __truediv__ = __or__


class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Any


class _Proc:
    made: list = []

    def __init__(self, *a, **k):
        self.started = False
        self.args = None
        _Proc.made.append(self)

    def setArguments(self, a): self.args = list(a)
    def start(self): self.started = True
    def __getattr__(self, n): return _Any()


REAL_QT = False


def _load():
    """Real hou + PySide6 when present (hython: `hython -m unittest tests/test_fxai_native_guard.py`, with
    QT_QPA_PLATFORM=offscreen); permissive stubs otherwise (plain Python). QProcess is replaced by a recorder either way."""
    global REAL_QT
    try:
        import hou  # noqa: F401
        from PySide6 import QtCore, QtGui, QtWidgets  # noqa: F401
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])  # noqa: F841
        REAL_QT = True
    except ImportError:
        for n in ("hou", "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
            sys.modules[n] = _Mod(n)
        pyside = sys.modules["PySide6"]
        for n in ("QtCore", "QtGui", "QtWidgets"):
            setattr(pyside, n, sys.modules["PySide6." + n])
    if HOUDINI not in sys.path:
        sys.path.insert(0, HOUDINI)
    import brother_chat
    return brother_chat


BC = _load()
print("qt mode:", "REAL hou + PySide6" if REAL_QT else "stubs", file=sys.stderr)


def junction(link: str, target: str) -> None:
    subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)


@unittest.skipUnless(os.name == "nt", "junction fixtures are Windows-only")
class LauncherGuard(unittest.TestCase):

    def setUp(self) -> None:
        self.box = tempfile.mkdtemp(prefix="fxai-guard-")
        self.good = self._repo("good")
        shutil.copytree(os.path.join(ROOT, ".claude", "skills"), os.path.join(self.good, ".claude", "skills"))
        self.outside = os.path.join(self.box, "outside", "zz-outside")
        os.makedirs(self.outside)
        with open(os.path.join(self.outside, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: zz-outside-sentinel\ndescription: owned dummy\n---\nbody\n")
        self.bad = self._repo("bad")
        os.makedirs(os.path.join(self.bad, ".claude", "skills"))
        junction(os.path.join(self.bad, ".claude", "skills", "evil"), self.outside)
        self.hip = None
        _Proc.made = []
        self.patches = [
            mock.patch.object(BC, "claude_exe", lambda: "C:/fake/claude.exe"),
            mock.patch.object(BC, "mcp_config", lambda: None),
            mock.patch.object(BC, "claude_env", lambda: _Any()),
            mock.patch.object(BC.ACC, "apply_env", lambda *a, **k: None),
            mock.patch.object(BC.QtCore, "QProcess", _Proc, create=True),
            mock.patch.object(BC.hou, "hipFile", types.SimpleNamespace(path=lambda: self.hip or "untitled.hip"), create=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.box, ignore_errors=True)

    def _repo(self, name: str) -> str:
        d = os.path.join(self.box, name)
        os.makedirs(os.path.join(d, ".git"))
        return d

    def start(self, cwd: str):
        s = BC.ClaudeSession(cwd)
        s.control = lambda *a, **k: None
        try:
            s.start()
            return None
        except RuntimeError as e:
            return str(e)

    def test_contained_project_starts_normally(self) -> None:
        err = self.start(self.good)
        self.assertIsNone(err)
        self.assertEqual(len(_Proc.made), 1)
        self.assertTrue(_Proc.made[0].started)
        self.assertIn("-p", _Proc.made[0].args)
        self.assertNotIn("--setting-sources", _Proc.made[0].args)   # project settings / CLAUDE.md untouched

    def test_skill_link_out_refused_before_spawn(self) -> None:
        err = self.start(self.bad)
        self.assertIsNotNone(err)
        self.assertIn("UNSAFE_PROJECT_SKILL_PATH", err)
        self.assertIn("evil", err)
        self.assertEqual(_Proc.made, [])

    def test_hip_folder_add_dir_link_out_refused(self) -> None:
        hipdir = self._repo("hipdir")
        os.makedirs(os.path.join(hipdir, ".claude", "skills"))
        junction(os.path.join(hipdir, ".claude", "skills", "evil"), self.outside)
        self.hip = os.path.join(hipdir, "scene.hip")
        err = self.start(self.good)
        self.assertIsNotNone(err)
        self.assertIn("hipdir", err)
        self.assertEqual(_Proc.made, [])

    def test_unreadable_skills_root_refused(self) -> None:
        deny = os.path.normcase(os.path.join(self.good, ".claude", "skills"))
        real_stat, real_lstat = os.stat, os.lstat

        def raiser(real):
            def f(p, *a, **k):
                if os.path.normcase(os.path.abspath(os.fspath(p))) == deny:
                    raise PermissionError(13, "Access is denied (simulated)", os.fspath(p))
                return real(p, *a, **k)
            return f
        with mock.patch.object(os, "stat", raiser(real_stat)), mock.patch.object(os, "lstat", raiser(real_lstat)):
            err = self.start(self.good)
        self.assertIsNotNone(err)
        self.assertIn("cannot be checked", err)
        self.assertEqual(_Proc.made, [])

    def test_check_that_cannot_run_is_a_refusal(self) -> None:
        saved_mod = sys.modules.pop("skills_catalog", None)
        saved_path = list(sys.path)
        sys.path[:] = [p for p in sys.path if os.path.normcase(p) != os.path.normcase(os.path.join(ROOT, "tools"))]
        try:
            with mock.patch.object(BC, "REPO", self.box):   # no tools/ there
                err = self.start(self.good)
        finally:
            sys.path[:] = saved_path
            if saved_mod is not None:
                sys.modules["skills_catalog"] = saved_mod
        self.assertIsNotNone(err)
        self.assertIn("could not be checked", err)
        self.assertEqual(_Proc.made, [])

    def test_fixture_untouched(self) -> None:
        self.start(self.bad)
        self.assertTrue(os.path.lexists(os.path.join(self.bad, ".claude", "skills", "evil")))


if __name__ == "__main__":
    unittest.main()
