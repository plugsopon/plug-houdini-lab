"""FX AI chat - the Context tab, the Agents tab and the compaction divider (brother_context.py),
driven offscreen with a FAKE claude session.

  hython tests/test_chat_context_agents.py        (sets QT_QPA_PLATFORM=offscreen itself)

Never starts the CLI, never touches a live Houdini, writes only to a temp folder. The
get_context_usage payload below is a real answer, measured 2026-11-04 (tests/probe_context_usage.py).
"""
import json, os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mcp", "houdini"))
from PySide6 import QtWidgets, QtCore
from PySide6.QtTest import QTest
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
import brother_chat as bc
import brother_context as CTX

TMP = tempfile.mkdtemp(prefix="fxai_ctx_test_")
bc.STATE_FILE = os.path.join(TMP, "chat_state.json")
bc.TRASH_DIR = os.path.join(TMP, "trash")
PROJ = os.path.join(TMP, "proj"); os.makedirs(PROJ)
bc.project_dir = lambda cwd: PROJ
FAILS = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "   " + str(info)))
    if not ok:
        FAILS.append(name)


class FakeSession:
    def __init__(self):
        self.busy, self.sent, self.ctrls = False, [], []
        self.commands, self.parked, self.init = [], False, None

    def send(self, text, imgs=()):
        self.sent.append(text); self.busy = True; return True

    def control(self, subtype, **kw):
        self.ctrls.append(subtype); return "r%d" % len(self.ctrls)

    def running(self):
        return True

    def stop(self):
        pass

    def refuse(self, *a):
        pass


def fake_start(self):
    if self.session is None:
        self.session = FakeSession(); self.session.owner = self
        self.sid = self.sid or ("sid-%d" % id(self))


bc.Convo.start = fake_start
QtWidgets.QApplication.alert = staticmethod(lambda w, ms=0: None)

USAGE = {"categories": [
    {"name": "System prompt", "tokens": 3619}, {"name": "System tools", "tokens": 10493},
    {"name": "MCP tools (deferred)", "tokens": 33413, "isDeferred": True},
    {"name": "System tools (deferred)", "tokens": 13725, "isDeferred": True},
    {"name": "Custom agents", "tokens": 1549}, {"name": "Memory files", "tokens": 649},
    {"name": "Skills", "tokens": 9953}, {"name": "Messages", "tokens": 1326},
    {"name": "Free space", "tokens": 972411}],
    "totalTokens": 27589, "maxTokens": 1000000, "rawMaxTokens": 1000000, "autocompactSource": "auto", "percentage": 3}

# ---------------------------------------------------------------- trackers, no screen
ct = CTX.ContextTracker()
check("ctx: a real get_context_usage answer is taken", ct.usage(USAGE))
check("ctx: conversation = Messages", ct.conversation == 1326, ct.conversation)
check("ctx: fixed part = every other counted category", ct.fixed == 3619 + 10493 + 1549 + 649 + 9953, ct.fixed)
check("ctx: deferred tools are kept apart", ct.deferred == 33413 + 13725, ct.deferred)
check("ctx: percentage", abs(ct.pct - 2.7589) < 1e-6, ct.pct)
check("ctx: an answer without maxTokens is ignored", not ct.usage({"totalTokens": 5}) and ct.max == 1000000)
check("ctx: 'Prompt is too long' is named", ct.error("API Error: 400 prompt is too long: 1,012,345 tokens > 1000000 maximum")
      and ct.events[-1]["kind"] == "too_long" and "1.01M" in ct.events[-1]["text"], ct.events[-1:])
check("ctx: another error is not a context problem", not ct.error("overloaded_error"))
check("meta: stream shape", CTX.compact_meta({"compact_metadata": {"trigger": "auto", "pre_tokens": 156000}})
      == {"trigger": "auto", "pre": 156000, "post": 0, "ms": 0})
check("meta: transcript shape", CTX.compact_meta({"compactMetadata": {"trigger": "manual", "preTokens": 735428,
                                                                       "postTokens": 10306, "durationMs": 51671}})
      == {"trigger": "manual", "pre": 735428, "post": 10306, "ms": 51671})
t = CTX.compact_title({"trigger": "auto", "pre": 735428, "post": 10306})
check("divider words", "compacted automatically" in t and "735.4k → 10.3k" in t, t)
u, ans = CTX.parse_agent_usage("Found 3 files.\n<usage>total_tokens: 18234\ntool_uses: 7\nduration_ms: 41250</usage>")
check("agent usage tail is read and stripped", u == {"tokens": 18234, "tool_uses": 7, "duration_ms": 41250}
      and ans == "Found 3 files.", (u, ans))
check("no usage tail -> nothing invented", CTX.parse_agent_usage("plain") == ({}, "plain"))

# ---------------------------------------------------------------- the panel
main = QtWidgets.QMainWindow(); main.resize(1500, 900)
p = bc.ChatPanel(main); p.resize(1300, 820); p.show(); app.processEvents()
p.timer.stop()
c = p.cur
c.start(); fs = c.session

check("inspector closed at first", not p.inspector.isVisible())
p.ring.clicked.emit(); app.processEvents()
check("ring click opens the Context tab", p.inspector.isVisible() and p.inspector.tabs.currentIndex() == 0)
txt = lambda w: " ".join(l.text() for l in w.findChildren(QtWidgets.QLabel))
check("context tab before the first reply says so", "after the first reply" in txt(p.inspector.context), txt(p.inspector.context))

c.ctrl["rx"] = ("context",)
c.on_event({"type": "control_response", "response": {"subtype": "success", "request_id": "rx", "response": USAGE}})
app.processEvents()
ctx_txt = txt(p.inspector.context)
check("context tab shows conversation and fixed part", "1.3k" in ctx_txt and "26.3k" in ctx_txt and "Fixed part" in ctx_txt,
      ctx_txt[:300])
check("context tab lists the categories", "Skills" in ctx_txt and "Memory files" in ctx_txt)
check("ring follows the same answer", p.ring.pct is not None and abs(p.ring.pct - 2.7589) < 1e-3, p.ring.pct)

# ---- compaction, live
before_users = len(c.scroll.widget().findChildren(QtWidgets.QFrame, "user"))
c.on_event({"type": "system", "subtype": "status", "status": "compacting"})
c.on_event({"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "manual", "pre_tokens": 412000}})
summary = "This session is being continued from a previous conversation...\n\nSummary:\n1. pyro shelf"
c.on_event({"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": summary}})
app.processEvents()
divs = c.scroll.widget().findChildren(CTX.CompactDivider)
check("live: a divider in the feed", len(divs) == 1 and "by /compact" in divs[0].title.text(), [d.title.text() for d in divs])
check("live: the summary is in the divider, not a bubble of Plug's",
      divs and divs[0].summary == summary and len(c.scroll.widget().findChildren(QtWidgets.QFrame, "user")) == before_users)
check("live: the Context tab's history has it", any(e["kind"] == "compact" for e in c.ctx.events)
      and "Compacting" in txt(p.inspector.context))

# ---- too long
fs.busy = True
c.on_event({"type": "result", "is_error": True, "result": "Prompt is too long: 1012345 tokens > 1000000", "usage": {}})
notes = [w.text() for w in c.scroll.widget().findChildren(QtWidgets.QLabel)]
check("too long: the feed says what to do", any("too long for the model" in n for n in notes))
check("too long: the history names it", c.ctx.events[-1]["kind"] == "too_long")

# ---- Compact now
fs.busy = False; app.processEvents()
p.compact_now()
check("Compact now sends /compact when idle", fs.sent and fs.sent[-1] == "/compact", fs.sent)
n = len(fs.sent)
p.compact_now()
check("...and does nothing during a turn", len(fs.sent) == n, fs.sent)
fs.busy = False

# ---- agents
p.toggle_inspector("agents"); app.processEvents()
check("Agents tab opens", p.inspector.isVisible() and p.inspector.tabs.currentIndex() == 1)
check("no agents yet -> explains itself", "No sub-agents" in txt(p.inspector.agents))
fs.busy = True
c.on_event({"type": "stream_event", "event": {"type": "content_block_start", "content_block":
            {"type": "tool_use", "id": "ag1", "name": "Agent", "input": {}}}})
c.on_event({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "ag1", "name": "Agent", "input":
            {"subagent_type": "Explore", "description": "Find the pyro HDAs", "prompt": "List every pyro HDA"}}]}})
for i in range(3):
    c.on_event({"type": "assistant", "parent_tool_use_id": "ag1", "message": {"content": [
        {"type": "tool_use", "id": "in%d" % i, "name": "mcp__houdini-live__houdini_network", "input": {}}]}})
c.on_event({"type": "assistant", "parent_tool_use_id": "ag1", "message": {"content": [
    {"type": "tool_use", "id": "in0", "name": "Read", "input": {}}]}})            # the same step again: once
p.refresh_inspector(); app.processEvents()
a = c.agents.agents.get("ag1")
check("agent: one card, running, 3 steps", a and a["state"] == "running" and a["steps"] == 3 and a["type"] == "Explore", a)
check("agent tab: running count on the tab", "1" in p.inspector.tabs.tabText(1), p.inspector.tabs.tabText(1))
check("agent card: says what it does now", "houdini:houdini_network" in txt(p.inspector.agents), txt(p.inspector.agents))
c.on_event({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "ag1", "content": [
    {"type": "text", "text": "pyro_shelf_v2, pyro_burst.\n<usage>total_tokens: 18234\ntool_uses: 7\nduration_ms: 41250</usage>"}]}]}})
app.processEvents()
at = txt(p.inspector.agents)
check("agent: done with the CLI's own numbers", a["state"] == "done" and "18.2k tokens" in at and "7 tool uses" in at
      and "41s" in at and "Explore" in at, at)
check("agent: the answer has no usage tail", a["answer"] == "pyro_shelf_v2, pyro_burst.", a["answer"])
check("agent tab: no running count once done", p.inspector.tabs.tabText(1) == "Agents", p.inspector.tabs.tabText(1))

c.on_event({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "ag2", "name": "Task", "input":
            {"subagent_type": "general-purpose", "description": "Bake the sim", "run_in_background": True}}]}})
c.on_event({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "ag2",
            "content": "Async agent launched successfully. agentId: a77f"}]}})
c.on_event({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "ag3", "name": "Agent", "input":
            {"description": "Never answers"}}]}})
c.on_event({"type": "result", "usage": {}, "duration_ms": 900})
check("background agent keeps running after the turn", c.agents.agents["ag2"]["state"] == "running")
check("a foreground agent with no answer is 'stopped' at the turn's end", c.agents.agents["ag3"]["state"] == "stopped")
c.on_event({"type": "system", "subtype": "task_notification", "task_id": "a77f", "status": "completed",
            "summary": "Sim baked to $HIP/geo"})
check("background agent: finished by its notification", c.agents.agents["ag2"]["state"] == "done"
      and c.agents.agents["ag2"]["answer"] == "Sim baked to $HIP/geo")
p.refresh_inspector(force=True); app.processEvents()
cards = p.inspector.agents.findChildren(CTX.AgentCard)
check("agents tab: newest first, three cards", len(cards) == 3 and "Never answers" in txt(cards[0]), [txt(x)[:60] for x in cards])

# ---- reload a chat from disk: divider + summary, agent cards, no fake bubble
sid = "reload1"
lines = [
    {"type": "user", "timestamp": "2026-11-01T10:00:00Z", "uuid": "u1", "message": {"role": "user", "content": "make pyro"}},
    {"type": "assistant", "timestamp": "2026-11-01T10:00:05Z", "message": {"content": [
        {"type": "tool_use", "id": "rA", "name": "Agent", "input": {"subagent_type": "Explore", "description": "scan scene"}}]}},
    {"type": "user", "isSidechain": True, "message": {"content": "inside the agent"}},
    {"type": "user", "timestamp": "2026-11-01T10:00:20Z", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "rA", "content": "ok\n<usage>total_tokens: 900\ntool_uses: 2\nduration_ms: 3000</usage>"}]}},
    {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-11-01T11:00:00Z",
     "compactMetadata": {"trigger": "auto", "preTokens": 735428, "postTokens": 10306}},
    {"type": "user", "isCompactSummary": True, "timestamp": "2026-11-01T11:00:01Z",
     "message": {"role": "user", "content": "This session is being continued... Summary: pyro"}},
    {"type": "user", "timestamp": "2026-11-01T11:05:00Z", "uuid": "u2", "message": {"role": "user", "content": "now render"}},
]
with open(os.path.join(PROJ, sid + ".jsonl"), "w", encoding="utf8") as fh:
    for o in lines:
        fh.write(json.dumps(o) + "\n")
kinds = [k for k, _v in bc.load_transcript("x", sid)]
check("transcript: compact + summary events, sidechain skipped",
      kinds == ["user", "tool_use", "tool_result", "compact", "summary", "user"], kinds)
rc = bc.Convo(p, resume=sid, title="reload", model=None); p.convos.append(rc)
rc.load(sid); app.processEvents()
users = [f.sent_text for f in rc.scroll.widget().findChildren(QtWidgets.QFrame, "user")]
rdiv = rc.scroll.widget().findChildren(CTX.CompactDivider)
check("reload: only Plug's two messages are bubbles", users == ["make pyro", "now render"], users)
check("reload: divider with its summary and real numbers", len(rdiv) == 1 and rdiv[0].summary.startswith("This session")
      and "735.4k → 10.3k" in rdiv[0].title.text(), [d.title.text() for d in rdiv])
check("reload: the compaction keeps its time", rc.ctx.compactions and abs(rc.ctx.compactions[0]["t"]
      - bc._iso_ts("2026-11-01T11:00:00Z")) < 1, rc.ctx.compactions)
check("reload: the agent card is back, finished", rc.agents.agents.get("rA", {}).get("state") == "done"
      and rc.agents.agents["rA"]["usage"]["tokens"] == 900)

# ---- Ctrl+I toggles
p.inspector.hide()
QTest.keyClick(p, QtCore.Qt.Key_I, QtCore.Qt.ControlModifier); app.processEvents()
shown = p.inspector.isVisible()
QTest.keyClick(p, QtCore.Qt.Key_I, QtCore.Qt.ControlModifier); app.processEvents()
check("Ctrl+I toggles the pane", shown and not p.inspector.isVisible())

SHOT = os.environ.get("FXAI_SHOT")        # a folder: save what the two tabs look like
if SHOT:
    os.makedirs(SHOT, exist_ok=True)
    p._show(c); p.resize(1300, 820)
    for tab in ("context", "agents"):
        p.toggle_inspector(tab); p.refresh_inspector(force=True); app.processEvents(); QTest.qWait(50)
        p.grab().save(os.path.join(SHOT, "fxai_%s_tab.png" % tab))
    p.inspector.hide(); app.processEvents()
    c.to_bottom(); app.processEvents()
    sb = c.scroll.verticalScrollBar()
    d0 = c.scroll.widget().findChildren(CTX.CompactDivider)[0]
    sb.setValue(max(0, d0.mapTo(c.scroll.widget(), QtCore.QPoint(0, 0)).y() - 120)); app.processEvents()
    p.grab().save(os.path.join(SHOT, "fxai_compact_divider.png"))

print("\n%d failed" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
