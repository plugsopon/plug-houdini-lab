"""FX AI chat - its own compaction (brother_compact.py, ported from Dremzo Code's compacter), driven
offscreen with a FAKE claude session and a FAKE summary writer (no model is called).

  hython tests/test_chat_compact.py        (sets QT_QPA_PLATFORM=offscreen itself)

Writes only to a temp folder (the compaction state root is redirected there too).
"""
import json, os, re, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mcp", "houdini"))
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
import brother_chat as bc
import brother_compact as CMP
import brother_context as CTX

TMP = tempfile.mkdtemp(prefix="fxai_cmp_test_")
bc.STATE_FILE = os.path.join(TMP, "chat_state.json")
bc.TRASH_DIR = os.path.join(TMP, "trash")
CMP.ROOT = os.path.join(TMP, "context")
PROJ = os.path.join(TMP, "proj"); os.makedirs(PROJ)
bc.project_dir = lambda cwd: PROJ
FAILS = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "   " + str(info)[:400]))
    if not ok:
        FAILS.append(name)


# ---------------------------------------------------------------- pure parts
check("tokens: Latin ~4 chars", CMP.tokens_of("a" * 400) == 101)
check("tokens: Thai counts denser", CMP.tokens_of("ก" * 400) == 201)
inj = CMP.INJECT_OPEN + "\nstuff\n" + CMP.INJECT_CLOSE + "\n\nmake it rain"
check("strip_injected keeps only Plug's words", CMP.strip_injected(inj) == "make it rain")
check("strip_injected leaves other text alone", CMP.strip_injected("<b>x</b>") == "<b>x</b>")

user_txt = ("cache the pyro to $HIP/geo/pyro_v003.bgeo.sc from /obj/geo1/pyro_sim, see https://www.sidefx.com/docs/x "
            "and commit a1b2c3d9; budget ฿1,500 and P:\\Shots\\sq010\\fx.hip")
req = CMP.required_of([{"role": "user", "text": user_txt, "tools": [], "results": []},
                       {"role": "assistant", "text": "I read /obj/other/thing and 5f00dbe7", "tools": [], "results": []}])
items = dict((x, k) for k, x in req)
check("required: commit", items.get("a1b2c3d9") == "sha", req)
check("required: $HIP path + node path + Windows path",
      "$HIP/geo/pyro_v003.bgeo.sc" in items and "/obj/geo1/pyro_sim" in items and "P:/Shots/sq010/fx.hip" in items, req)
check("required: link", "https://www.sidefx.com/docs/x" in items, req)
check("required: amount with its currency", items.get("1500") == "money", req)
check("required: Claude's own ids are not forced on the summary", "/obj/other/thing" not in items and "5f00dbe7" not in items, req)
good = ("Plug wants $HIP/geo/pyro_v003.bgeo.sc cached from sim/pyro_sim (geo1/pyro_sim), docs "
        "https://www.sidefx.com/docs/x, commit a1b2c3d9e0, budget 1500 THB, shot file P:\\Shots\\sq010\\fx.hip")
check("verify: a summary with everything passes (path tail, longer sha, backslashes)", CMP.verify_summary(good, req) == [],
      CMP.verify_summary(good, req))
check("verify: a dropped commit is caught", ("sha", "a1b2c3d9") in CMP.verify_summary(good.replace("a1b2c3d9e0", ""), req))
check("verify: a dropped amount is caught", ("money", "1500") in CMP.verify_summary(good.replace("1500", "15"), req))

B = CMP.BUDGET
st = CMP.fresh_state()
check("trigger: busy never", CMP.should_compact(st, False, 999999, 999999, 1000000)[0] is False)
check("trigger: within budget", CMP.should_compact(st, True, 100000, 140000, 1000000)[:2] == (False, "within budget"))
check("trigger: conversation over 150K", CMP.should_compact(st, True, 160000, 190000, 1000000)[0] is True)
check("trigger: safety cap on a small window", CMP.should_compact(st, True, 40000, 170000, 200000)[0] is True)
check("trigger: safety cap needs a real conversation", CMP.should_compact(st, True, 20000, 170000, 200000)[0] is False)
check("trigger: off", CMP.should_compact(dict(st, on=False), True, 160000, 190000, 1000000)[:2] == (False, "off"))
check("trigger: retry waits", CMP.should_compact(dict(st, retry_at=5, turns=3), True, 160000, 190000, 1000000)[0] is False)
check("trigger: force runs inside the budget", CMP.should_compact(st, True, 10, 10, 1000000, force=True)[0] is True)
check("trigger: ...but never during a turn", CMP.should_compact(st, False, 10, 10, 1000000, force=True)[0] is False)


# ---------------------------------------------------------------- a long chat on disk
def line(o):
    return json.dumps(o, ensure_ascii=False) + "\n"


def write_chat(sid, turns, filler=4000, first_inject=None):
    """`turns` exchanges; each assistant reply ~filler chars. Turn 0's user line names ids to keep."""
    with open(os.path.join(PROJ, sid + ".jsonl"), "w", encoding="utf8") as fh:
        for i in range(turns):
            txt = ("turn %d: cache /obj/geo1/pyro_v%03d to $HIP/geo/v%03d.bgeo.sc, commit %07x" % (i, i, i, 0xabc0000 + i)
                   if i % 5 == 0 else "turn %d: keep going" % i)
            if i == 0 and first_inject:
                txt = first_inject + txt
            fh.write(line({"type": "user", "uuid": "%s-u%d" % (sid, i), "timestamp": "2026-11-01T10:%02d:00Z" % (i % 60),
                           "message": {"role": "user", "content": txt}}))
            fh.write(line({"type": "assistant", "uuid": "%s-a%d" % (sid, i), "message": {"content": [
                {"type": "text", "text": ("ok %d " % i) + "x" * filler},
                {"type": "tool_use", "id": "t%d" % i, "name": "mcp__houdini-live__houdini_node", "input": {"path": "/obj/geo1"}}]}}))
            fh.write(line({"type": "user", "uuid": "%s-r%d" % (sid, i), "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t%d" % i, "content": "node ok"}]}}))
            fh.write(line({"type": "user", "isSidechain": True, "message": {"content": "agent inside"}}))


msgs_probe = os.path.join(PROJ, "probe.jsonl")
write_chat("probe", 10, filler=400, first_inject=CMP.INJECT_OPEN + "\nold\n" + CMP.INJECT_CLOSE + "\n\n")
ms = CMP.read_messages(msgs_probe)
check("read: sub-agent lines left out, injected block stripped",
      len(ms) == 30 and ms[0]["text"].startswith("turn 0") and not any("agent inside" in m["text"] for m in ms),
      (len(ms), ms[0]["text"][:40]))
span, tail = CMP.split_tail(ms, 300)
check("split: the tail starts at a message Plug wrote", tail and tail[0]["role"] == "user" and tail[0]["text"]
      and span + tail == ms, tail[:1])
segs = CMP.split_segments(ms, 600)
check("split: stretches start where Plug writes", len(segs) > 1 and all(s[0]["role"] == "user" and s[0]["text"] for s in segs[1:]))


# ---------------------------------------------------------------- the panel
class FakeSession:
    def __init__(self):
        self.busy, self.sent, self.ctrls, self.stopped = False, [], [], 0
        self.commands, self.parked, self.init = [], False, None

    def send(self, text, imgs=()):
        self.sent.append(text); self.busy = True; return True

    def control(self, subtype, **kw):
        self.ctrls.append((subtype, kw)); return "r%d" % len(self.ctrls)

    def running(self):
        return True

    def stop(self):
        self.stopped += 1

    def refuse(self, *a):
        pass


def fake_start(self):
    if self.session is None or self.session.stopped:
        self.session = FakeSession(); self.session.owner = self
        self.sid = self.sid or ("sid-%d" % id(self))


bc.Convo.start = fake_start
bc.Convo.ask_context = lambda self: None
QtWidgets.QApplication.alert = staticmethod(lambda w, ms=0: None)

CALLS = []
MODE = {"drop": None, "fail": False}


def fake_writer(self, prompt, system, done):
    """Extractive, like Dremzo Code's fakeSummary: lists what the prompt says must be kept."""
    CALLS.append(prompt)
    if MODE["fail"]:
        return done(None, "network down")
    keep = re.search(r"EXACTLY as written:\n(.*?)\n\n", prompt, re.S)
    missed = re.search(r"left these out - include every one: (.*)\n", prompt)
    items = [l[2:] for l in (keep.group(1).split("\n") if keep else []) if l.startswith("- ")]
    items += missed.group(1).split(", ") if missed else []
    items = [i.replace(" (an amount, with its currency)", " THB") for i in items]
    if MODE["drop"]:
        items = [i for i in items if MODE["drop"] not in i]
    done("## Summary\n- Plug asked for pyro caches\n- kept: " + ", ".join(items))


bc.Convo._write_summary = fake_writer

main = QtWidgets.QMainWindow(); main.resize(1500, 900)
p = bc.ChatPanel(main); p.resize(1300, 820); p.show(); app.processEvents()
p.timer.stop()
c = p.cur; c.start(); fs = c.session
c.title = "Pyro shelf chat"
old_sid = c.sid
write_chat(old_sid, 220)                       # ~220 x 1.1K tokens: well over the 150K budget


def usage(conv, total=None, mx=1000000):
    c.ctx.usage({"categories": [{"name": "System prompt", "tokens": 5000}, {"name": "Messages", "tokens": conv},
                                {"name": "Free space", "tokens": mx}], "totalTokens": total or conv + 5000, "maxTokens": mx})


usage(100000)
check("run: within budget nothing happens", c.compacter.maybe_run() == "within budget" and not CALLS)
usage(230000)
fs.busy = True
check("run: never during a turn", c.compacter.maybe_run() == "busy" and not CALLS)
fs.busy = False
c.compacter.turn_finished()
res = c.compacter.maybe_run(); app.processEvents()
st = c.compacter.st
check("run: over budget it compacts", res == "started" and st["events"][-1]["kind"] == "compacted", st["events"][-1:])
check("run: at most 3 stretches summarised by a model, the rest indexed",
      1 <= len(CALLS) <= CMP.MAX_CALLS and sum(1 for u in st["units"] if u["kind"] == "summary") <= CMP.MAX_SUMMARISED,
      (len(CALLS), [u["kind"] for u in st["units"]]))
check("run: summary files on disk with their hash", st["units"] and all(os.path.exists(u["file"]) for u in st["units"])
      and all(CMP.unit_text(u) and not CMP.unit_text(u).startswith("[summary") for u in st["units"]))
check("switch: a fresh session id, the old one recorded as continued",
      c.sid != old_sid and p.state["continued"].get(old_sid) == c.sid and not c.has_history, (c.sid, p.state["continued"]))
check("switch: the old process was closed", fs.stopped >= 1)
inject = c.pending_inject or ""
check("switch: the next message will carry history head + summaries + recent turns",
      inject.startswith(CMP.INJECT_OPEN) and "<summaries>" in inject and "<recent-turns>" in inject
      and os.path.join(PROJ, old_sid + ".jsonl") in inject and "turn 219" in inject, inject[:300])
check("switch: what Plug wrote is kept (verified)", "/obj/geo1/pyro_v000" in inject or "§0001" in inject)
divs = c.scroll.widget().findChildren(CTX.CompactDivider)
check("feed: a 'New stretch' line with numbers", divs and "New stretch" in divs[-1].title.text()
      and "conversation ~" in divs[-1].title.text() and divs[-1].summary, [d.title.text() for d in divs])
check("context tab history has it", any(e["kind"] == "compacted" for e in c.ctx.events))

# the first message after the switch
p.composer.setPlainText("now render it"); p.send(); app.processEvents(); QtCore.QCoreApplication.processEvents()
fs2 = c.session
check("send: the fresh session's first message = history + Plug's words",
      fs2.sent and fs2.sent[-1].startswith(CMP.INJECT_OPEN) and fs2.sent[-1].endswith("now render it"), fs2.sent[-1:][:1])
users = [f.sent_text for f in c.scroll.widget().findChildren(QtWidgets.QFrame, "user")]
check("send: the bubble shows only Plug's words", users[-1:] == ["now render it"], users[-1:])
check("send: the fresh session keeps the chat's name", any(k == "rename_session" and kw.get("title") == "Pyro shelf chat"
                                                          for k, kw in fs2.ctrls), fs2.ctrls)
check("send: history is sent once", c.pending_inject is None)

# what the CLI writes for the new session, then the sidebar and a reload
with open(os.path.join(PROJ, c.sid + ".jsonl"), "w", encoding="utf8") as fh:
    fh.write(line({"type": "user", "uuid": "n-u0", "timestamp": "2026-11-02T09:00:00Z",
                   "message": {"role": "user", "content": fs2.sent[-1]}}))
    fh.write(line({"type": "assistant", "uuid": "n-a0", "message": {"content": [{"type": "text", "text": "rendering"}]}}))
p.refresh_sessions(); app.processEvents()
listed = [p.list.item(i).data(QtCore.Qt.UserRole) for i in range(p.list.count())]
check("sidebar: one row for the chat, under the new session", c.sid in listed and old_sid not in listed, listed)
check("sidebar: its title is Plug's words, not the injected history",
      bc.session_title(os.path.join(PROJ, c.sid + ".jsonl")) == "now render it")
rc = bc.Convo(p, resume=c.sid, title="reload", model=None); p.convos.append(rc)
rc.load(c.sid); app.processEvents()
rusers = [f.sent_text for f in rc.scroll.widget().findChildren(QtWidgets.QFrame, "user")]
rdiv = rc.scroll.widget().findChildren(CTX.CompactDivider)
check("reload: the whole chat - the old session's turns, then the new", rusers[0].startswith("turn 0")
      and rusers[-1] == "now render it" and len(rusers) == 221, (len(rusers), rusers[:1], rusers[-1:]))
check("reload: no bubble carries the injected history", not any(CMP.INJECT_OPEN in u for u in rusers))
check("reload: one 'New stretch' line with the summaries", len(rdiv) == 1 and "New stretch" in rdiv[0].title.text()
      and rdiv[0].summary, [d.title.text() for d in rdiv])
check("reload: same compaction state (the first session is the key)", rc.compacter.root == old_sid == c.root_id())

# ---------------------------------------------------------------- a summary that keeps dropping something
CALLS.clear()
p.new_session(); d = p.cur; d.start(); d.title = "Refusals"
write_chat(d.sid, 60)
d.ctx.usage({"categories": [{"name": "Messages", "tokens": 200000}], "totalTokens": 205000, "maxTokens": 1000000})
MODE["drop"] = "abc0000"                       # turn 0's commit (%07x of 0xabc0000)
sid_before = d.sid
d.compacter.maybe_run(); app.processEvents()
ev = d.compacter.st["events"][-1]
check("refuse: a summary that keeps dropping a commit is not used", ev["kind"] == "refused" and "abc0000" in ev["text"]
      and d.sid == sid_before and d.pending_inject is None, ev)
check("refuse: exactly 3 tries", len(CALLS) == CMP.TRIES, len(CALLS))
check("refuse: tries again only after 4 more turns", d.compacter.st["retry_at"] == d.compacter.st["turns"] + 4)
check("refuse: the next check waits", d.compacter.maybe_run() == "waiting after a refused compaction")
MODE["drop"] = None

# ---------------------------------------------------------------- the writer fails
d.compacter.st["retry_at"] = None
MODE["fail"] = True
d.compacter.maybe_run(); app.processEvents()
check("error: a failed writer keeps the full chat and says so", d.compacter.st["events"][-1]["kind"] == "error"
      and d.sid == sid_before and not d.compacter.running, d.compacter.st["events"][-1])
MODE["fail"] = False

# ---------------------------------------------------------------- anti-thrash
# Dremzo Code's numbers, written out: refilled within 3 turns, the THIRD time in a row stops it
d.compacter.st.update(retry_at=None, last_compact_turn=d.compacter.st["turns"] - 3, refills=2)
check("thrash: filling up again soon, too often, stops it", d.compacter.maybe_run() == "stopped"
      and d.compacter.st["stopped"] and "stopped for this chat" in d.compacter.st["events"][-1]["text"])
check("thrash: and it stays stopped", d.compacter.maybe_run() == "stopped")
check("thrash: stopped means no run", CMP.should_compact(d.compacter.st, True, 300000, 300000, 1000000)[:2] == (False, "stopped"))

# ---------------------------------------------------------------- the Context tab switch + Compact now
p.toggle_inspector("context"); p.refresh_inspector(force=True); app.processEvents()
box = [b for b in p.inspector.context.findChildren(QtWidgets.QCheckBox) if b.text() == "Compaction (automatic)"]
check("tab: the automatic switch is there", len(box) == 1)
if box:
    box[0].setChecked(True); app.processEvents()           # it was stopped: turning it on clears that
    check("tab: turning it on clears the stop", d.compacter.st["on"] and not d.compacter.st["stopped"])
    box = [b for b in p.inspector.context.findChildren(QtWidgets.QCheckBox) if b.text() == "Compaction (automatic)"]
    box[0].setChecked(False); app.processEvents()
    check("tab: off really turns it off", d.compacter.st["on"] is False and d.compacter.maybe_run() == "off")
CALLS.clear()
d.ctx.usage({"categories": [{"name": "Messages", "tokens": 1000}], "totalTokens": 6000, "maxTokens": 1000000})
d.compacter.st["refills"] = 0
p.compact_now(); app.processEvents()
check("Compact now: runs even when off and within budget", CALLS and d.compacter.st["events"][-1]["kind"] == "compacted"
      and d.sid != sid_before, d.compacter.st["events"][-1:])

# ---------------------------------------------------------------- state survives a restart
reloaded = CMP.load_state(old_sid)
check("state: on disk, per chat", reloaded["units"] and reloaded["events"][-1]["kind"] == "compacted")
st_disk = json.load(open(bc.STATE_FILE, encoding="utf8"))
check("state: the continuation is in chat_state.json", st_disk["continued"].get(old_sid) == c.sid)

print("\n%d failed" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
