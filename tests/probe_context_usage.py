"""Probe: what does the CLI's get_context_usage control answer look like? No model call is made.

  python tests/probe_context_usage.py [path-to-claude.exe]
"""
import glob, json, os, subprocess, sys, threading, time, uuid


def find_exe():
    if len(sys.argv) > 1:
        return sys.argv[1]
    roots = [os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code")]
    roots += glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Claude_*",
                                    "LocalCache", "Roaming", "Claude", "claude-code"))
    best = None
    for d in [d for r in roots for d in glob.glob(os.path.join(r, "*"))]:
        for exe in [os.path.join(d, "claude.exe")] + glob.glob(os.path.join(d, "*", "claude.exe")):
            if os.path.exists(exe) and (best is None or os.path.getmtime(exe) > os.path.getmtime(best)):
                best = exe
    return best


exe = find_exe()
env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") or k == "CLAUDE_CODE_OAUTH_TOKEN"}
p = subprocess.Popen([exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                      "--session-id", str(uuid.uuid4())], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, env=env, cwd=os.path.dirname(os.path.abspath(__file__)))
out = []


def reader():
    for line in p.stdout:
        out.append(line.decode("utf8", "replace"))


threading.Thread(target=reader, daemon=True).start()
for sub in ("initialize", "get_context_usage"):
    p.stdin.write((json.dumps({"type": "control_request", "request_id": sub,
                               "request": {"subtype": sub}}) + "\n").encode()); p.stdin.flush()
    time.sleep(6)
p.stdin.close(); time.sleep(1); p.kill()
print("exe", exe)
for line in out:
    try:
        o = json.loads(line)
    except ValueError:
        continue
    if o.get("type") == "control_response" and (o.get("response") or {}).get("request_id") == "get_context_usage":
        print(json.dumps(o, indent=1)[:6000])
