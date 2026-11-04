"""Break the compaction's guards one at a time and assert test_chat_compact.py goes RED for each.

  hython tests/sabotage_chat_compact.py

A guard whose test still passes when the guard is gone protects nothing.
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEST = os.path.join(HERE, "test_chat_compact.py")
CASES = {
    "verify passes everything": "CMP.verify_summary = lambda s, r: []",
    "injected history shown as Plug's words": "CMP.strip_injected = lambda t: t",
    "no anti-thrash": "CMP.BUDGET['thrash_max'] = 10**6",
    "compacts during a turn": "_sc = CMP.should_compact\nCMP.should_compact = lambda st, idle, *a, **k: _sc(st, True, *a, **k)",
}
RUNNER = """import sys, os
sys.path.insert(0, os.path.join(%r, "mcp", "houdini"))
import brother_compact as CMP
%s
sys.argv = [%r]
exec(compile(open(%r, encoding="utf8").read(), %r, "exec"), {"__name__": "__main__", "__file__": sys.argv[0]})
"""
bad = []
for name, patch in CASES.items():
    code = RUNNER % (os.path.dirname(HERE), patch, TEST, TEST, TEST)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf8", errors="replace")
    if "PASS " not in r.stdout:                        # the test never ran: that proves nothing either way
        print("BROKEN " + name + "  (exit %s)\n%s" % (r.returncode, (r.stderr or r.stdout)[-1500:]))
        bad.append(name)
        continue
    red = r.returncode != 0 and "FAIL " in r.stdout
    fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL ")]
    print(("RED   " if red else "GREEN ") + name + ("   <- caught by: " + fails[0][5:80] if fails else ""))
    if not red:
        bad.append(name)
print("\nevery sabotage caught" if not bad else "\nNOT caught: %s" % bad)
sys.exit(1 if bad else 0)
