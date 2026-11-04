"""brother_context - the Context and Agents tabs of the FX AI chat, and the compaction divider.

Ported from Dremzo Code (web/src/ContextPane.tsx, AgentsPane.tsx, agentGraph.ts, Pinned.tsx
StretchLine), cut down to what matters inside Houdini: one chat, one CLI, no other chats in the
graph, no background commands of the app's own.

Two halves, kept apart so the logic can be tested without a screen:
  ContextTracker / AgentTracker   plain Python, fed the CLI's stream events
  ContextPane / AgentsPane / ...  PySide widgets that draw a tracker

Where the numbers come from (measured 2026-11-04 on claude 2.1.x, not from docs):
  get_context_usage -> {"categories":[{"name","tokens","isDeferred"?}], "totalTokens", "maxTokens",
                        "autocompactSource"}. "Messages" is the conversation; every other non-deferred
                        category except "Free space" is the fixed part (system prompt, tools, skills,
                        memory files, agents) - it does not shrink when the chat compacts.
  system/compact_boundary (stream)      compact_metadata {trigger, pre_tokens}
  system/compact_boundary (transcript)  compactMetadata  {trigger, preTokens, postTokens, durationMs}
  user isCompactSummary (transcript)    the summary the chat continues from
  a sub-agent's answer ends with <usage>total_tokens: N\ntool_uses: N\nduration_ms: N</usage>
"""
import re, time

from PySide6 import QtCore, QtGui, QtWidgets

SUBAGENT_TOOLS = ("Task", "Agent", "task", "agent")
FREE, MESSAGES = "Free space", "Messages"
CAT_COLORS = {"System prompt": "#8e8b85", "System tools": "#6f6c66", "MCP tools": "#4f8fd9",
              "Custom agents": "#b38be0", "Memory files": "#d98a4f", "Skills": "#d9a548",
              MESSAGES: "#ff4f9a"}
EVENT_CAP = 60


def fmt_k(n):
    """1234 -> 1.2k, 1234567 -> 1.23M - the same short form as the rest of the panel."""
    n = int(n or 0)
    if n >= 1_000_000:
        return ("%.2fM" % (n / 1e6)).replace(".00M", "M")
    if n >= 1000:
        return ("%.1fk" % (n / 1e3)).replace(".0k", "k")
    return str(n)


def fmt_secs(s):
    s = int(max(0, s or 0))
    return ("%dm %02ds" % (s // 60, s % 60)) if s >= 60 else "%ds" % s


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


_USAGE = re.compile(r"<usage>(.*?)</usage>", re.S)
_TOO_LONG = re.compile(r"prompt is too long:?\s*([\d,]+)\s*tokens?\s*>\s*([\d,]+)", re.I)


def parse_agent_usage(text):
    """The <usage> tail Claude adds to a sub-agent's answer -> ({tokens, tool_uses, duration_ms}, answer
    without the tail). Missing fields stay None; no tail -> ({}, text)."""
    m = _USAGE.search(text or "")
    if not m:
        return {}, text or ""
    out = {}
    for key, name in (("total_tokens", "tokens"), ("tool_uses", "tool_uses"), ("duration_ms", "duration_ms")):
        mm = re.search(r"%s\s*:\s*(\d+)" % key, m.group(1))
        out[name] = int(mm.group(1)) if mm else None
    return out, (text[:m.start()] + text[m.end():]).strip()


def compact_meta(o):
    """trigger / pre / post tokens of a compact_boundary, from the stream (snake) or the transcript (camel)."""
    m = o.get("compact_metadata") or o.get("compactMetadata") or {}
    return {"trigger": m.get("trigger") or "?",
            "pre": m.get("pre_tokens") or m.get("preTokens") or 0,
            "post": m.get("post_tokens") or m.get("postTokens") or 0,
            "ms": m.get("duration_ms") or m.get("durationMs") or 0}


def compact_title(meta):
    """The divider's words - Dremzo Code's '↻ Conversation compacted', in the panel's voice."""
    how = "automatically" if meta.get("trigger") == "auto" else "by /compact" if meta.get("trigger") == "manual" else ""
    size = ""
    if meta.get("pre") and meta.get("post"):
        size = " (%s → %s tokens)" % (fmt_k(meta["pre"]), fmt_k(meta["post"]))
    elif meta.get("pre"):
        size = " (it was %s tokens)" % fmt_k(meta["pre"])
    return "↻  Conversation compacted%s%s — the chat keeps going from a summary." % (
        (" " + how) if how else "", size)


# ============================================================================ trackers (no Qt)
class ContextTracker:
    """What fills this chat's context, and what happened to it (compactions, overflows, retries)."""

    def __init__(self):
        self.categories = []        # [(name, tokens, deferred)]
        self.total = 0
        self.max = 0
        self.source = None          # autocompactSource
        self.events = []            # {"t", "kind", "text", "level"}; newest last
        self.compactions = []       # compact metas, oldest first
        self.measured_at = None

    # -------------------------------------------------------------- inputs
    def usage(self, body):
        """A get_context_usage answer."""
        if not isinstance(body, dict) or not body.get("maxTokens"):
            return False
        cats = []
        for c in body.get("categories") or []:
            if isinstance(c, dict) and isinstance(c.get("tokens"), (int, float)):
                cats.append((str(c.get("name") or "?"), int(c["tokens"]), bool(c.get("isDeferred"))))
        self.categories = cats
        self.total = int(body.get("totalTokens") or 0)
        self.max = int(body["maxTokens"])
        self.source = body.get("autocompactSource")
        self.measured_at = time.time()
        return True

    def event(self, kind, text, level="info", t=None):
        self.events.append({"t": t or time.time(), "kind": kind, "text": text, "level": level})
        del self.events[:-EVENT_CAP]

    def compacted(self, meta, t=None):
        self.compactions.append(dict(meta, t=t or time.time()))
        self.event("compact", compact_title(meta).replace("  ", " "), "info", t)

    def error(self, why, t=None):
        """A failed turn. 'Prompt is too long' is the one context problem worth naming."""
        m = _TOO_LONG.search(why or "")
        if m:
            used, mx = (int(x.replace(",", "")) for x in m.groups())
            self.event("too_long", "Too long for the model: %s > %s tokens. Type /compact, or start a new chat."
                       % (fmt_k(used), fmt_k(mx)), "error")
            return True
        return False

    # -------------------------------------------------------------- readings
    @property
    def conversation(self):
        return sum(t for n, t, _d in self.categories if n == MESSAGES)

    @property
    def fixed(self):
        return sum(t for n, t, d in self.categories if not d and n not in (FREE, MESSAGES))

    @property
    def deferred(self):
        return sum(t for n, t, d in self.categories if d)

    @property
    def pct(self):
        return 100.0 * self.total / self.max if self.max else None

    def parts(self):
        """Non-deferred, non-free categories, biggest first: what the bar is made of."""
        rows = [(n, t) for n, t, d in self.categories if not d and n != FREE and t > 0]
        return sorted(rows, key=lambda r: -r[1])


class AgentTracker:
    """Every sub-agent this chat started: what it was asked, how it went, what it cost."""

    def __init__(self):
        self.agents = {}            # tool_use_id -> dict
        self.order = []

    def _get(self, tid):
        return self.agents.get(tid)

    def tool_use(self, block, parent=None, t=None):
        """A tool_use block. A Task/Agent at the top level is a new agent; anything inside an agent
        counts as one of its steps."""
        if not isinstance(block, dict):
            return
        tid, name = block.get("id"), block.get("name")
        if parent and parent in self.agents:
            a = self.agents[parent]
            if tid and tid not in a["step_ids"]:
                a["step_ids"].add(tid)
                a["steps"] += 1
                a["last"] = name or "?"
            return
        if name not in SUBAGENT_TOOLS or not tid:
            return
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        a = self.agents.get(tid)
        if a is None:
            a = {"id": tid, "type": "general-purpose", "desc": "", "prompt": "", "background": False,
                 "state": "running", "t0": t or time.time(), "t1": None, "steps": 0, "step_ids": set(),
                 "last": None, "usage": {}, "answer": "", "task_id": None}
            self.agents[tid] = a
            self.order.append(tid)
        if inp:
            a["type"] = inp.get("subagent_type") or a["type"]
            a["desc"] = inp.get("description") or a["desc"]
            a["prompt"] = inp.get("prompt") or a["prompt"]
            a["background"] = bool(inp.get("run_in_background")) or a["background"]

    def tool_result(self, block, t=None):
        a = self._get(block.get("tool_use_id")) if isinstance(block, dict) else None
        if a is None:
            return
        text = _text(block.get("content"))
        usage, answer = parse_agent_usage(text)
        if a["background"] and not usage and a["state"] == "running":
            a["answer"] = answer           # "launched in the background" - the real end comes later
            m = re.search(r"\b(?:agentId|task_id|taskId)\W+([\w-]+)", text)
            if m:
                a["task_id"] = m.group(1)
            return
        a["usage"] = usage or a["usage"]
        a["answer"] = answer
        a["state"] = "error" if block.get("is_error") else "done"
        a["t1"] = t or time.time()

    def task_notification(self, o, t=None):
        """A background agent finished (system/task_notification)."""
        tid = o.get("tool_use_id")
        a = self._get(tid)
        if a is None:
            for x in self.agents.values():
                if x["background"] and x["state"] == "running" and (
                        (o.get("task_id") and x["task_id"] == o.get("task_id"))
                        or (o.get("description") and x["desc"] == o.get("description"))):
                    a = x
                    break
        st = o.get("status")
        if a is None or st in ("running", "pending", None):
            return
        a["state"] = "done" if st in ("completed", "done", "success") else "error" if st in ("failed", "error") else st
        a["t1"] = t or time.time()
        if o.get("summary"):
            a["answer"] = o["summary"]

    def turn_ended(self, t=None, everything=False):
        """The turn is over: a foreground agent still 'running' was stopped with it. everything=True
        (a chat reloaded from disk, or claude exited) ends the background ones too."""
        for a in self.agents.values():
            if a["state"] == "running" and (everything or not a["background"]):
                a["state"] = "stopped"
                a["t1"] = t or time.time()

    def running(self):
        return [self.agents[i] for i in self.order if self.agents[i]["state"] == "running"]

    def all(self):
        return [self.agents[i] for i in reversed(self.order)]       # newest first


# ============================================================================ widgets
class CompactDivider(QtWidgets.QFrame):
    """The '↻ Conversation compacted' line in the transcript (Dremzo Code's StretchLine): a left
    border, the words, and - when the summary is known - a fold that opens it."""

    def __init__(self, meta, summary=None, parent=None):
        super().__init__(parent)
        self.setObjectName("stretch")
        self.setStyleSheet("QFrame#stretch{border:none;border-left:2px solid #6aa5ff;background:transparent;}")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(10, 2, 0, 2); lay.setSpacing(4)
        self.title = QtWidgets.QLabel(compact_title(meta)); self.title.setWordWrap(True)
        self.title.setStyleSheet("color:#6aa5ff;font-size:12px;")
        lay.addWidget(self.title)
        self.fold = QtWidgets.QPushButton("Show the summary", objectName="flat")
        self.fold.setStyleSheet("text-align:left;color:#77756f;font-size:11px;")
        self.body = QtWidgets.QTextBrowser(); self.body.hide()
        self.body.setStyleSheet("QTextBrowser{background:#1f1e1d;color:#a6a39d;border:1px solid #2f2e2b;"
                                "border-radius:8px;font-size:12px;}")
        self.body.setFixedHeight(220)
        self.fold.clicked.connect(self._flip)
        lay.addWidget(self.fold, 0, QtCore.Qt.AlignLeft); lay.addWidget(self.body)
        self.set_summary(summary)

    def set_summary(self, text):
        self.summary = text or None
        self.fold.setVisible(bool(self.summary))
        if self.summary:
            self.body.setPlainText(self.summary)

    def _flip(self):
        on = not self.body.isVisible()
        self.body.setVisible(on)
        self.fold.setText("Hide the summary" if on else "Show the summary")


class _Bar(QtWidgets.QWidget):
    """A thin stacked bar: [(color, value)] over a maximum."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self.parts, self.max = [], 1

    def set(self, parts, mx):
        self.parts, self.max = parts, max(1, mx)
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        try:
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            path = QtGui.QPainterPath(); path.addRoundedRect(r, 4, 4)
            p.setClipPath(path)
            p.fillRect(r, QtGui.QColor("#2f2e2b"))
            x = r.left()
            for col, v in self.parts:
                w = r.width() * v / self.max
                if w > 0:
                    p.fillRect(QtCore.QRectF(x, r.top(), max(1.0, w), r.height()), QtGui.QColor(col))
                    x += w
        finally:
            p.end()


def _label(text="", color="#a6a39d", size=12, wrap=True, bold=False):
    l = QtWidgets.QLabel(text); l.setWordWrap(wrap)
    l.setStyleSheet("color:%s;font-size:%dpx;%s" % (color, size, "font-weight:600;" if bold else ""))
    l.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    return l


def _clear(lay):
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide(); w.setParent(None)        # out of the tree now, not at the next event loop turn
            w.deleteLater()
        elif it.layout() is not None:
            _clear(it.layout())


class ContextPane(QtWidgets.QScrollArea):
    """How full the chat is, what it is made of, and its history - Dremzo Code's Context tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        host = QtWidgets.QWidget(objectName="ctxhost"); host.setStyleSheet("QWidget#ctxhost{background:transparent;}")
        self.lay = QtWidgets.QVBoxLayout(host); self.lay.setContentsMargins(14, 12, 14, 12); self.lay.setSpacing(8)
        self.setWidget(host)
        self.compact_handler = None        # set by the panel: the "Compact now" button
        self.compactor_info = None         # set by the panel: (phase 2) the chat's own compacter state

    def show_tracker(self, ct, busy=False, model=None, extra=None, force=False, extra_sig=None):
        sig = (id(ct), ct.total, ct.max, ct.measured_at, len(ct.events), busy, model, extra_sig)
        if sig == getattr(self, "_sig", None) and not force:
            return                                 # nothing moved: keep the scroll where it is
        self._sig = sig
        _clear(self.lay)
        L = self.lay
        L.addWidget(_label("Context window%s" % ("  ·  %s" % model if model else ""), "#ece9e3", 13, bold=True))
        if not ct.max:
            L.addWidget(_label("Shown after the first reply - the CLI reports it once a turn has run."))
        else:
            pct = ct.pct
            col = "#e5675f" if pct > 85 else "#d9a548" if pct > 65 else "#6aa5ff"
            L.addWidget(_label("<span style='color:%s;font-size:20px;font-weight:600'>%d%%</span>"
                               "&nbsp;&nbsp;%s of %s tokens" % (col, round(pct), fmt_k(ct.total), fmt_k(ct.max)),
                               "#a6a39d", 12))
            bar = _Bar(); bar.set([(CAT_COLORS.get(n, "#8e8b85"), t) for n, t in ct.parts()], ct.max)
            L.addWidget(bar)
            L.addWidget(_label("<b style='color:#ff4f9a'>Conversation</b> %s &nbsp;·&nbsp; "
                               "<b style='color:#a6a39d'>Fixed part</b> %s" % (fmt_k(ct.conversation), fmt_k(ct.fixed)),
                               "#a6a39d", 12))
            L.addWidget(_label("Compacting shrinks only the conversation; the fixed part (system prompt, tools, "
                               "skills, memory files) stays the same.", "#77756f", 11))
            for n, t in ct.parts():
                row = QtWidgets.QHBoxLayout(); row.setSpacing(6)
                dot = QtWidgets.QLabel("■"); dot.setStyleSheet("color:%s;font-size:10px;" % CAT_COLORS.get(n, "#8e8b85"))
                row.addWidget(dot); row.addWidget(_label(n, "#a6a39d", 12, wrap=False), 1)
                row.addWidget(_label(fmt_k(t), "#77756f", 12, wrap=False))
                L.addLayout(row)
            if ct.deferred:
                L.addWidget(_label("+ %s of tools loaded only when used (not counted)." % fmt_k(ct.deferred),
                                   "#77756f", 11))
        if extra:
            for w in extra:
                L.addWidget(w)
        btn = QtWidgets.QPushButton("↻  Compact now", objectName="bar")
        btn.setToolTip("Summarise the conversation so far to free up context (the chat keeps going)")
        btn.setEnabled(not busy and self.compact_handler is not None and bool(ct.max))
        if busy:
            btn.setToolTip("Waits until the turn is over")
        if self.compact_handler is not None:
            btn.clicked.connect(self.compact_handler)
        L.addWidget(btn, 0, QtCore.Qt.AlignLeft)

        L.addSpacing(6)
        L.addWidget(_label("History", "#ece9e3", 13, bold=True))
        if not ct.events:
            L.addWidget(_label("Nothing yet - compactions and context problems show here.", "#77756f", 11))
        colors = {"error": "#e5675f", "warn": "#d9a548", "info": "#a6a39d"}
        for e in reversed(ct.events):
            when = time.strftime("%H:%M", time.localtime(e["t"]))
            L.addWidget(_label("<span style='color:#77756f'>%s</span>&nbsp;&nbsp;%s"
                               % (when, _esc(e["text"])), colors.get(e["level"], "#a6a39d"), 12))
        L.addStretch(1)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class AgentCard(QtWidgets.QFrame):
    """One sub-agent: 'Sub-agent · type · background · state · time · tokens · N tool uses', its task,
    and (folded) its answer."""

    STATE_COL = {"running": "#d9a548", "done": "#5fb87a", "error": "#e5675f", "stopped": "#77756f"}

    def __init__(self, a, now=None, parent=None):
        super().__init__(parent)
        self.setObjectName("agentcard")
        self.setStyleSheet("QFrame#agentcard{border:1px solid #3a3935;border-radius:10px;background:#242321;}")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(10, 8, 10, 8); lay.setSpacing(4)
        now = now or time.time()
        secs = ((a["t1"] or now) - a["t0"]) if a.get("t0") else 0
        if a["usage"].get("duration_ms"):
            secs = a["usage"]["duration_ms"] / 1000.0
        steps = a["usage"].get("tool_uses") if a["usage"].get("tool_uses") is not None else a["steps"]
        bits = ["Sub-agent", a["type"]] + (["background"] if a["background"] else [])
        bits.append("<span style='color:%s'>%s</span>" % (self.STATE_COL.get(a["state"], "#a6a39d"), a["state"]))
        bits.append(fmt_secs(secs))
        if a["usage"].get("tokens"):
            bits.append("%s tokens" % fmt_k(a["usage"]["tokens"]))
        bits.append("%d tool use%s" % (steps, "" if steps == 1 else "s"))
        lay.addWidget(_label(" &nbsp;·&nbsp; ".join(bits), "#77756f", 11))
        lay.addWidget(_label(_esc(a["desc"] or "(no description)"), "#ece9e3", 13))
        if a["state"] == "running" and a.get("last"):
            lay.addWidget(_label("now: %s" % _esc(a["last"].replace("mcp__houdini-live__", "houdini:")),
                                 "#d9a548", 11))
        self.body = QtWidgets.QTextBrowser(); self.body.hide(); self.body.setFixedHeight(200)
        self.body.setStyleSheet("QTextBrowser{background:#1f1e1d;color:#a6a39d;border:1px solid #2f2e2b;"
                                "border-radius:8px;font-size:12px;}")
        text = ""
        if a["prompt"]:
            text += "TASK\n" + a["prompt"].strip() + "\n\n"
        if a["answer"]:
            text += "ANSWER\n" + a["answer"].strip()
        if text:
            self.body.setPlainText(text)
            fold = QtWidgets.QPushButton("Show the task and answer", objectName="flat")
            fold.setStyleSheet("text-align:left;color:#77756f;font-size:11px;")
            fold.clicked.connect(lambda: (self.body.setVisible(not self.body.isVisible()),
                                          fold.setText("Hide" if self.body.isVisible() else "Show the task and answer")))
            lay.addWidget(fold, 0, QtCore.Qt.AlignLeft)
        lay.addWidget(self.body)


class AgentsPane(QtWidgets.QScrollArea):
    """Every sub-agent the chat started, newest first - Dremzo Code's Agents tab, chat-local."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        host = QtWidgets.QWidget(objectName="aghost"); host.setStyleSheet("QWidget#aghost{background:transparent;}")
        self.lay = QtWidgets.QVBoxLayout(host); self.lay.setContentsMargins(14, 12, 14, 12); self.lay.setSpacing(8)
        self.setWidget(host)
        self._sig = None

    def show_tracker(self, at, force=False):
        rows = at.all()
        sig = tuple((a["id"], a["state"], a["steps"], a["last"], bool(a["answer"]), a["state"] == "running" and
                     int(time.time() - a["t0"]) // 5) for a in rows)
        if sig == self._sig and not force:
            return                                 # nothing moved: keep scroll and open folds
        self._sig = sig
        _clear(self.lay)
        run = len(at.running())
        self.lay.addWidget(_label("Agents" + ("  ·  %d running" % run if run else ""), "#ece9e3", 13, bold=True))
        if not rows:
            self.lay.addWidget(_label("No sub-agents in this chat yet. When Claude hands part of the work to a "
                                      "sub-agent (the Agent tool) it shows here: what it was asked, how long it "
                                      "took, what it cost, and its answer.", "#77756f", 11))
        for a in rows:
            self.lay.addWidget(AgentCard(a))
        self.lay.addStretch(1)


class Inspector(QtWidgets.QFrame):
    """The right-hand pane: Context | Agents tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspector")
        self.setStyleSheet("QFrame#inspector{border:none;border-left:1px solid #2f2e2b;background:#1f1e1d;}"
                           "QTabBar::tab{background:transparent;color:#77756f;padding:8px 14px;border:none;"
                           "font-size:13px;}"
                           "QTabBar::tab:selected{color:#ece9e3;border-bottom:2px solid #ff4f9a;}"
                           "QTabWidget::pane{border:none;}")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(0, 4, 0, 0); lay.setSpacing(0)
        self.tabs = QtWidgets.QTabWidget(); self.tabs.setDocumentMode(True)
        self.context = ContextPane(); self.agents = AgentsPane()
        self.tabs.addTab(self.context, "Context"); self.tabs.addTab(self.agents, "Agents")
        lay.addWidget(self.tabs)
        self.setFixedWidth(320)

    def open_tab(self, name):
        self.tabs.setCurrentIndex(0 if name == "context" else 1)
        self.show()

    def set_agent_count(self, n):
        self.tabs.setTabText(1, "Agents%s" % ("  %d" % n if n else ""))
