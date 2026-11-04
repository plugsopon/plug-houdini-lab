"""brother_compact - the FX AI chat's own compaction, ported from Dremzo Code (src/compacter.ts).

Why not just the CLI's /compact? The CLI summarises everything into one blob and nothing checks
what it dropped. This one, like Dremzo Code:
  1. splits the older part of the chat into stretches (the newest ~30K tokens stay word for word),
  2. has Haiku summarise the newest few stretches; older ones get a no-model index stub,
  3. CHECKS each summary: every commit, file / node path, link and amount Plug himself wrote must be
     in it, exactly - up to 3 tries, at most 4 model calls per compaction - else that stretch stays,
  4. rolls summaries up when together they pass 40K tokens,
  5. switches to a FRESH claude session whose first message carries the summaries + the recent
     turns (<room-history>), so the conversation part drops from ~150K to ~40-70K.
Nothing is deleted: the old CLI transcripts stay on disk, and the model is told where they are.

Kept out on purpose (not useful inside Houdini): GPT/opencode engines, Dremzo's recall/open_raw
archive tools (the transcript files + Read/Grep do that job), the shared-room ledger.

The trigger (after a finished turn, only when the chat is idle): the conversation part
(get_context_usage "Messages") > 150K, or the whole context > 80% of the window while the
conversation is > 30K. Anti-thrash: filling up again within 3 turns, more than twice in a row,
turns it off for that chat with a line saying so.

Layout: pure functions on top (testable without Qt or a model), then Compacter (Qt timers, a
writer callable supplied by the panel).
"""
import hashlib, json, os, re, time

from PySide6 import QtCore

BUDGET = {"conversation": 150_000, "segment": 120_000, "safety": 0.8, "summaries": 40_000, "keep_tail": 30_000,
          "min_span": 20_000, "thrash_turns": 3, "thrash_max": 2, "retry_turns": 4, "summary_tokens": 6_000}
WRITER_MODEL = "claude-haiku-4-5"
MAX_SUMMARISED = 3            # per compaction, stretches summarised by a model (the newest ones)
MAX_CALLS = 4                 # per compaction, model calls in all (summaries, rewrites, roll-ups)
MAX_ROLLUPS = 1
TRIES = 3
RAW_MAX_CHARS = 480_000       # ~120K tokens: Haiku's window is 200K
TAIL_MAX_TOKENS = 60_000
ROOT = os.path.join(os.path.expanduser("~"), ".houdini_brother", "context")
INJECT_OPEN, INJECT_CLOSE = "<room-history>", "</room-history>"

WRITER_SYSTEM = ("You write faithful, compact summaries of a chat between an FX artist and their AI assistant "
                 "inside SideFX Houdini. Plain text or Markdown only. Never invent anything, never add advice, "
                 "never call tools.")


def tokens_of(s):
    """A cheap estimate: ~4 chars a token for Latin, ~2 for Thai (Thai is denser per token)."""
    s = s or ""
    thai = sum(1 for ch in s if "฀" <= ch <= "๿")
    return (len(s) - thai) // 4 + thai // 2 + 1


def pad(n):
    return "%04d" % n


def K(n):
    return "%dK" % round(n / 1000.0) if n >= 1000 else str(int(n))


# ============================================================================ reading a transcript
def strip_injected(text):
    """A continued chat's first message carries <room-history>...</room-history> before Plug's words."""
    if text and text.startswith(INJECT_OPEN):
        i = text.find(INJECT_CLOSE)
        if i >= 0:
            return text[i + len(INJECT_CLOSE):].lstrip()
    return text


def _short(v, n):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = s.replace("\r", "")
    return s if len(s) <= n else s[:n] + " [...]"


def read_messages(path):
    """A CLI transcript as messages: {id, role, t, text, tools[(name, input)], results[text]}.
    Sub-agent lines, meta lines and the CLI's own compact summaries are left out."""
    out = []
    try:
        fh = open(path, encoding="utf8", errors="replace")
    except OSError:
        return out
    with fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not isinstance(o, dict) or o.get("isSidechain") or o.get("isMeta") or o.get("isCompactSummary"):
                continue
            typ = o.get("type")
            if typ not in ("user", "assistant"):
                continue
            msg = o.get("message") if isinstance(o.get("message"), dict) else {}
            content = msg.get("content")
            m = {"id": o.get("uuid") or "m%d" % len(out), "role": typ, "t": o.get("timestamp"), "text": "",
                 "tools": [], "results": []}
            texts = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and isinstance(b.get("text"), str):
                        texts.append(b["text"])
                    elif b.get("type") == "tool_use":
                        m["tools"].append((b.get("name") or "?", b.get("input")))
                    elif b.get("type") == "tool_result":
                        c = b.get("content")
                        if isinstance(c, list):
                            c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
                        m["results"].append(c if isinstance(c, str) else "")
            text = "\n".join(texts)
            if typ == "user":
                if text.startswith("<") and not text.startswith(INJECT_OPEN):
                    text = ""                       # local-command echoes, reminders: not said by anyone
                text = strip_injected(text)
            m["text"] = text
            if m["text"] or m["tools"] or m["results"]:
                out.append(m)
    return out


def render_msg(m):
    head = "── %s · %s%s" % (m["id"], m["role"], (" · %s" % m["t"]) if m.get("t") else "")
    lines = [head]
    if m["text"]:
        lines.append(m["text"])
    for name, inp in m["tools"]:
        lines.append("[tool %s: %s]" % (name, _short(inp, 600)))
    for r in m["results"]:
        if r:
            lines.append("[result: %s]" % _short(r, 1200))
    return "\n".join(lines)


def msg_tokens(m):
    return tokens_of(render_msg(m))


def split_tail(msgs, keep_tail):
    """(span, tail): the tail = the newest messages worth ~keep_tail tokens, starting at a message
    Plug wrote, so a turn is never cut in half."""
    if not msgs:
        return [], []
    total, k = 0, len(msgs)
    while k > 0 and total < keep_tail:
        k -= 1
        total += msg_tokens(msgs[k])
    while k > 0 and not (msgs[k]["role"] == "user" and msgs[k]["text"]):
        k -= 1
    return msgs[:k], msgs[k:]


def split_segments(span, max_tokens):
    """Stretches of at most ~max_tokens each, cut where Plug starts a new message."""
    segs, cur, size = [], [], 0
    for m in span:
        t = msg_tokens(m)
        if cur and size + t > max_tokens and m["role"] == "user" and m["text"]:
            segs.append(cur); cur, size = [], 0
        cur.append(m); size += t
    if cur:
        segs.append(cur)
    return segs


# ============================================================================ what a summary must keep
SHA = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
URL = re.compile(r"https?://[^\s)>\]\"'`]+")
WINPATH = re.compile(r"\b[A-Za-z]:[\\/][^\s\"'<>|*?`]+")
UNIXPATH = re.compile(r"(?<![\w.:/$-])(?:\$[A-Z]+|~)?/(?:[\w.$@-]+/)+[\w.$@-]+")      # /obj/geo1/pyro, $HIP/geo/x.bgeo.sc
MONEY = re.compile(r"(?:[$€£฿]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|THB|EUR|GBP|JPY|baht|dollars?|บาท|ดอลลาร์)(?![A-Za-z]))",
                   re.I | re.U)


def _clean_path(p):
    return p.rstrip(".,;:)]}'\"`").replace("\\", "/")


def extract_ids(text):
    text = text or ""
    urls = [u.rstrip(".,;:") for u in URL.findall(text)]
    rest = URL.sub(" ", text)
    paths = [_clean_path(p) for p in WINPATH.findall(rest)]
    rest2 = WINPATH.sub(" ", rest)
    paths += [_clean_path(p) for p in UNIXPATH.findall(rest2)]
    shas = SHA.findall(rest2)
    return {"sha": _uniq(shas), "path": _uniq(p for p in paths if len(p) > 3), "url": _uniq(urls)}


def money_nums(text):
    out = []
    for m in MONEY.findall(text or ""):
        n = re.search(r"\d[\d,]*(?:\.\d+)?", m)
        if n:
            out.append(n.group(0).replace(",", ""))
    return _uniq(out)


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def required_of(msgs):
    """What a summary of these messages must keep word for word: every commit, path, node path, link
    and amount PLUS anything Plug wrote himself. Ids that only appeared in Claude's words or in tool
    output go in the stretch's index line instead (the program writes that, not the model)."""
    req, seen = [], set()
    for m in msgs:
        if m["role"] != "user":
            continue
        ids = extract_ids(m["text"])
        for kind in ("sha", "path", "url"):
            for x in ids[kind]:
                if (kind, x) not in seen:
                    seen.add((kind, x)); req.append((kind, x))
    for m in msgs:
        for n in money_nums(m["text"]):
            if ("money", n) not in seen:
                seen.add(("money", n)); req.append(("money", n))
    return req


def index_of(msgs, cap=12):
    """The no-model index of a stretch: the ids Claude and the tools touched."""
    ids = {"sha": [], "path": [], "url": []}
    for m in msgs:
        src = "\n".join([m["text"]] + ["%s %s" % (n, _short(i, 600)) for n, i in m["tools"]] + m["results"])
        got = extract_ids(src)
        for k in ids:
            ids[k] += got[k]
    return {k: _uniq(v) for k, v in ids.items()}


def index_line(ix, cap=12):
    parts = []
    for k, label in (("path", "Files / nodes"), ("sha", "Commits"), ("url", "Links")):
        v = ix.get(k) or []
        if v:
            parts.append("%s: %s%s" % (label, ", ".join(v[:cap]), (" (+%d more)" % (len(v) - cap)) if len(v) > cap else ""))
    return ("Index — " + "; ".join(parts)) if parts else ""


def _path_tail(p):
    parts = p.strip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else p


def verify_summary(summary, req):
    """The program's check. Returns the items still missing (empty = it passes)."""
    s = summary or ""
    low = s.lower().replace("\\", "/")
    shas = SHA.findall(s.lower())
    money = set(money_nums(s)) | set(re.findall(r"\d[\d,]*(?:\.\d+)?", s.replace(",", "")))
    missing = []
    for kind, item in req:
        if kind == "sha":
            ok = item.lower() in low or any(len(x) >= 7 and (item.startswith(x) or x.startswith(item)) for x in shas)
        elif kind == "path":
            it = item.lower()
            ok = it in low or _path_tail(it) in low
        elif kind == "url":
            ok = item.lower() in low
        else:
            ok = item in money
        if not ok:
            missing.append((kind, item))
    return missing


def _label(r):
    return "%s (an amount, with its currency)" % r[1] if r[0] == "money" else r[1]


# ============================================================================ prompts
def segment_prompt(n, msgs, must_keep, max_tokens, missed=()):
    first, last = msgs[0]["id"], msgs[-1]["id"]
    body = "\n".join(render_msg(m) for m in msgs)
    if len(body) > RAW_MAX_CHARS:
        body = body[:RAW_MAX_CHARS] + "\n[... the rest of this stretch is in the transcript file ...]"
    keep = ""
    if must_keep:
        keep = ("\nA program checks the summary. Every one of these must appear in it EXACTLY as written:\n"
                + "\n".join("- " + _label(r) for r in list(must_keep)[:300]) + "\n")
    miss = ("\nYour previous summary left these out - include every one: %s\n" % ", ".join(_label(r) for r in missed)) if missed else ""
    return """Summarise ONE stretch of a long chat. From now on this summary REPLACES the stretch in the AI's context; the real messages stay in the transcript files on this computer.

Write in the language(s) the conversation uses. Keep, as short bullet points under short headings:
- Plug's instructions, rules and preferences (quote short ones word for word);
- decisions made and why; approvals given; things rejected;
- what was built or changed in Houdini and on disk: node paths, parameters and their values, hip files, caches and their versions, scripts, commits;
- open todos and unresolved problems at the end of the stretch;
- numbers that matter (frame ranges, resolutions, counts, versions, amounts with their currency).
After each point give its reference, like §%s:%s or §%s:%s-%s.
Do not invent anything. At most about %d tokens.
%s%s
<stretch ref="§%s" from="%s" to="%s">
%s
</stretch>""" % (pad(n), first, pad(n), first, last, max_tokens, keep, miss, pad(n), first, last, body)


def rollup_prompt(units, must_keep, max_tokens, missed=()):
    keep = ""
    if must_keep:
        keep = ("\nA program checks it. Every one of these must appear in it EXACTLY as written:\n"
                + "\n".join("- " + _label(r) for r in list(must_keep)[:300]) + "\n")
    miss = ("\nYour previous version left these out - include every one: %s\n" % ", ".join(_label(r) for r in missed)) if missed else ""
    return ("Several summaries of consecutive stretches of a long chat are below, oldest first. Merge them into ONE "
            "shorter summary that replaces them in the AI's context (the real messages stay in the transcript files). "
            "Keep Plug's standing instructions, decisions, approvals, open todos and the outcomes; drop what was later "
            "superseded; keep the references (§NNNN:...) of the points you keep. At most about %d tokens. Do not invent "
            "anything.\n%s%s\n%s" % (max_tokens, keep, miss,
                                      "\n".join('<summary refs="%s">\n%s\n</summary>' % (u["refs"], u["text"]) for u in units)))


def history_head(files):
    where = "\n".join("- %s" % f for f in files) if files else "- (none)"
    return ("This chat is long, so its older part is no longer in this conversation. Below are verified summaries of "
            "it (oldest first), then the most recent turns word for word. Nothing was deleted: the full earlier "
            "transcripts (JSON lines) are on this computer:\n%s\nWhen Plug says you talked about something before, or "
            "you need a detail a summary left out, search those files with Grep and read them with Read (references "
            "look like §0007:<message uuid>). Never guess what was said - say where you found it." % where)


def injected_text(files, units, tail_msgs):
    """What the fresh session's first message carries before Plug's words."""
    tail, tok = render_tail(tail_msgs)
    return "%s\n%s\n\n<summaries>\n%s\n</summaries>\n\n<recent-turns>\n%s\n</recent-turns>\n%s\n\n" % (
        INJECT_OPEN, history_head(files), "\n\n".join(u["text"].strip() for u in units), tail or "(none)", INJECT_CLOSE)


def render_tail(msgs):
    parts = [render_msg(m) for m in msgs]
    tok, k = 0, len(parts)
    while k > 0 and tok + tokens_of(parts[k - 1]) <= TAIL_MAX_TOKENS:
        tok += tokens_of(parts[k - 1]); k -= 1
    text = ("[... %d older recent message(s) not shown - they are in the transcript ...]\n" % k if k else "") + "\n".join(parts[k:])
    return text, tok


def compact_line(a, b, conv, after, summarised, indexed=0, fixed=0):
    rng = "stretch %d" % a if a == b else "stretches %d-%d" % (a, b)
    return ("↻  New stretch - compacted %s: %d summarised%s (conversation ~%s → ~%s tokens%s). The earlier messages stay "
            "on disk and Claude knows where." % (rng, summarised, (", %d indexed" % indexed) if indexed else "",
                                                K(conv), K(after), ("; fixed part ~%s unchanged" % K(fixed)) if fixed else ""))


def stop_line(n, turns):
    return ("↻  Automatic compaction stopped for this chat: it filled up again within %d turns of being compacted, %d "
            "times in a row. This chat's work is too large for one conversation - consider a new chat per task. Turn it "
            "back on in the Context tab." % (turns, n))


def should_compact(st, idle, conv, total, window, b=BUDGET, force=False):
    """(go, why, over). Pure - the caller gives the facts."""
    if not idle:
        return False, "busy", False
    if force:
        return True, "asked for", False
    if not st.get("on", True):
        return False, "off", False
    if st.get("stopped"):
        return False, "stopped", False
    if not window:
        return False, "no measurement yet", False
    over = conv > b["conversation"]
    safety = not over and total > b["safety"] * window and conv > b["keep_tail"]
    if not over and not safety:
        return False, "within budget", False
    if st.get("retry_at") is not None and st.get("turns", 0) < st["retry_at"]:
        return False, "waiting after a refused compaction", over
    return True, ("conversation %d > %d" % (conv, b["conversation"]) if over
                  else "context %d > %d (safety cap)" % (total, int(b["safety"] * window))), over


# ============================================================================ state on disk
def _safe(key):
    return re.sub(r"[^A-Za-z0-9_-]", "_", key or "none")


def state_dir(root_id):
    return os.path.join(ROOT, _safe(root_id))


def fresh_state():
    return {"version": 1, "on": True, "stopped": None, "turns": 0, "refills": 0, "retry_at": None,
            "last_compact_turn": None, "next_n": 1, "units": [], "events": [], "sessions": []}


def load_state(root_id):
    try:
        with open(os.path.join(state_dir(root_id), "compact.json"), encoding="utf8") as fh:
            st = json.load(fh)
        if isinstance(st, dict):
            base = fresh_state(); base.update(st)
            return base
    except (OSError, ValueError):
        pass
    return fresh_state()


def save_state(root_id, st):
    d = state_dir(root_id)
    os.makedirs(d, exist_ok=True)
    st["events"] = st.get("events", [])[-200:]
    tmp = os.path.join(d, "compact.json.tmp")
    with open(tmp, "w", encoding="utf8") as fh:
        json.dump(st, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, "compact.json"))


def write_unit(root_id, name, text):
    d = os.path.join(state_dir(root_id), "units")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf8") as fh:
        fh.write(text)
    return path, hashlib.sha256(text.encode("utf8")).hexdigest()


def unit_text(u):
    """A unit as it is now on disk - a file changed by hand is not trusted (named instead)."""
    try:
        with open(u["file"], encoding="utf8") as fh:
            body = fh.read()
    except OSError:
        return "[summary %s is missing on disk - read the transcript for that stretch]" % u["refs"]
    if hashlib.sha256(body.encode("utf8")).hexdigest() != u["sha256"]:
        return "[summary %s was changed on disk and is not used - read the transcript for that stretch]" % u["refs"]
    return body


# ============================================================================ the run
class Compacter(QtCore.QObject):
    """One per chat. `host` is the Convo: it supplies idle(), the transcript path(s), the context
    numbers, and continue_fresh(text, line) for the switch. `writer(prompt, system, done)` runs
    one model call and calls done(text or None, error)."""
    changed = QtCore.Signal()

    def __init__(self, host, writer, parent=None):
        super().__init__(parent)
        self.host, self.writer = host, writer
        self.running = False
        self.root = None
        self.st = fresh_state()
        self.status = ""                       # what it is doing now, for the Context tab
        self._timer = QtCore.QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(1500)
        self._timer.timeout.connect(lambda: self.maybe_run())

    # -------------------------------------------------------------- state
    def bind(self, root_id):
        if root_id and root_id != self.root:
            self.root = root_id
            self.st = load_state(root_id)

    def save(self):
        if self.root:
            save_state(self.root, self.st)

    def log_event(self, kind, text, **kw):
        e = dict(kw, at=time.time(), kind=kind, text=text)
        self.st["events"].append(e)
        self.save()
        ctx = getattr(self.host, "ctx", None)
        if ctx is not None:                        # the Context tab's history shows it too
            ctx.event(kind, text.replace("↻  ", "↻ "), {"error": "error", "refused": "warn", "stopped": "warn"}.get(kind, "info"))
        self.changed.emit()
        return e

    def set_on(self, on):
        self.st["on"] = bool(on)
        if on:
            self.st["stopped"] = None; self.st["refills"] = 0
        self.log_event("switch", "Automatic compaction turned %s." % ("on" if on else "off"))

    # -------------------------------------------------------------- trigger
    def turn_finished(self):
        self.st["turns"] = self.st.get("turns", 0) + 1
        self.save()

    def soon(self):
        """After a finished turn's context measurement: decide in a moment, when nothing else moves."""
        self._timer.start()

    def maybe_run(self, force=False):
        if not self.root and getattr(self.host, "sid", None):
            self.bind(self.host.root_id())
        if self.running or not self.root:
            return None
        h = self.host
        ct = h.ctx
        go, why, over = should_compact(self.st, h.idle(), ct.conversation, ct.total, ct.max, force=force)
        if not go:
            return why
        if not force and over and self.st.get("last_compact_turn") is not None \
                and self.st["turns"] - self.st["last_compact_turn"] <= BUDGET["thrash_turns"]:
            self.st["refills"] = self.st.get("refills", 0) + 1
            if self.st["refills"] > BUDGET["thrash_max"]:
                self.st["stopped"] = {"at": time.time(), "reason": "over budget again within %d turns, %d times in a row"
                                      % (BUDGET["thrash_turns"], self.st["refills"])}
                e = self.log_event("stopped", stop_line(self.st["refills"], BUDGET["thrash_turns"]))
                h.compact_note(e["text"], "#d9a548")
                return "stopped"
        else:
            self.st["refills"] = 0
        self.start(why)
        return "started"

    # -------------------------------------------------------------- the work
    def start(self, why):
        h = self.host
        msgs = read_messages(h.transcript_path())
        span, tail = split_tail(msgs, BUDGET["keep_tail"])
        span_tok = sum(msg_tokens(m) for m in span)
        if span_tok < BUDGET["min_span"]:
            self.st["retry_at"] = self.st["turns"] + BUDGET["retry_turns"]
            e = self.log_event("refused", "Nothing compacted: the older part is only ~%s tokens (the newest ~%s stay word for "
                                      "word)." % (K(span_tok), K(BUDGET["keep_tail"])))
            h.compact_note(e["text"])
            return
        self.running = True
        self.status = "Compacting - summarising the older part (%s)..." % why
        self.changed.emit()
        h.compact_note("Compacting the conversation - the chat stays usable; it switches when the turn is over.")
        segs = split_segments(span, BUDGET["segment"])
        n0 = self.st.get("next_n", 1)
        jobs = [(n0 + i, s) for i, s in enumerate(segs)]
        model_n = max(1, min(MAX_SUMMARISED, BUDGET["summaries"] // max(1, BUDGET["summary_tokens"])))
        older, newest = jobs[:max(0, len(jobs) - model_n)], jobs[max(0, len(jobs) - model_n):]
        self.job = {"why": why, "span": span, "tail": tail, "new": [], "calls": 0, "queue": list(newest),
                    "conv_before": h.ctx.conversation, "fixed": h.ctx.fixed, "segs": (jobs[0][0], jobs[-1][0])}
        for n, msgs_ in older:                             # no-model index stubs
            ix = index_of(msgs_)
            text = "### §%s:%s-%s · %d messages · INDEX STUB (not summarised)\n%s\n" % (
                pad(n), msgs_[0]["id"], msgs_[-1]["id"], len(msgs_), index_line(ix, 20) or "(no ids)")
            self._add_unit("stub", n, n, text, "§%s" % pad(n))
        self._next_segment()

    def _add_unit(self, kind, a, b, text, refs):
        path, sha = write_unit(self.root, "%s-%s.%s.md" % (pad(a), pad(b), kind), text)
        self.job["new"].append({"kind": kind, "from": a, "to": b, "file": path, "sha256": sha, "tokens": tokens_of(text),
                                "refs": refs, "text": text})

    def _next_segment(self):
        q = self.job["queue"]
        if not q:
            return self._rollup()
        n, msgs = q[0]
        req = required_of(msgs)
        self._write_verified(lambda missed: segment_prompt(n, msgs, req, BUDGET["summary_tokens"], missed), req,
                             lambda text: self._segment_done(n, msgs, text), lambda missing, capped: self._segment_refused(n, missing, capped))

    def _segment_done(self, n, msgs, text):
        self.job["queue"].pop(0)
        ix = index_line(index_of(msgs))
        body = "### §%s:%s-%s · %d messages · ~%s raw tokens\n%s\n%s\n" % (
            pad(n), msgs[0]["id"], msgs[-1]["id"], len(msgs), K(sum(msg_tokens(m) for m in msgs)), text.strip(), ix)
        self._add_unit("summary", n, n, body, "§%s" % pad(n))
        self._next_segment()

    def _segment_refused(self, n, missing, capped):
        why = ("this compaction's %d model calls are used up" % MAX_CALLS if capped else
               "its summary still left out %d item(s) after %d tries (%s)" % (
                   len(missing), TRIES, ", ".join(_label(r) for r in missing[:5])))
        done = [u for u in self.job["new"] if u["to"] < n]
        if not done:
            self.st["retry_at"] = self.st["turns"] + BUDGET["retry_turns"]
            self._finish()
            e = self.log_event("refused", "Stretch %d was kept in full: %s. Tries again in %d turns." % (n, why, BUDGET["retry_turns"]))
            self.host.compact_note(e["text"], "#d9a548")
            return
        self.log_event("refused", "Stretch %d and later stay in full for now: %s." % (n, why))
        # what was verified so far is used; the rest of the span stays raw in the recent turns
        cut = next((i for i, m in enumerate(self.job["span"]) if m["id"] == self.job["queue"][0][1][0]["id"]), None)
        if cut is not None:
            self.job["tail"] = self.job["span"][cut:] + self.job["tail"]
        self.job["queue"] = []
        self._rollup()

    def _write_verified(self, prompt_of, req, ok, refused, missed=(), tries=0):
        if tries >= TRIES:
            return refused(list(missed), False)
        if self.job["calls"] >= MAX_CALLS:
            return refused(list(missed), True)
        self.job["calls"] += 1

        def done(text, err=None):
            if text is None:
                return self._fail(err or "the summary writer failed")
            miss = verify_summary(text, req)
            if not miss:
                return ok(text)
            self._write_verified(prompt_of, req, ok, refused, miss, tries + 1)
        self.writer(prompt_of(list(missed)), WRITER_SYSTEM, done)

    def _rollup(self):
        units = list(self.st["units"]) + self.job["new"]
        for u in units:
            u.setdefault("text", unit_text(u))
        total = sum(u["tokens"] for u in units)
        summaries = [i for i, u in enumerate(units) if u["kind"] != "stub"]
        if total <= BUDGET["summaries"] or len(summaries) < 3 or self.job["calls"] >= MAX_CALLS or self.job.get("rolled"):
            return self._switch(units)
        # merge the oldest summaries (never the newest one) until the total is about half the budget
        goal, take, group = total - BUDGET["summaries"] / 2, 0, []
        for i in summaries[:-1]:
            if take >= goal and len(group) >= 2:
                break
            group.append(i); take += units[i]["tokens"]
        self.job["rolled"] = True
        texts = [{"refs": units[i]["refs"], "text": units[i]["text"]} for i in group]
        req = []
        for t in texts:
            for kind, items in extract_ids(t["text"]).items():
                req += [(kind, x) for x in items if (kind, x) not in req]
        req = req[:300]

        def ok(text):
            a, b = units[group[0]]["from"], units[group[-1]]["to"]
            body = "### §%s-§%s (roll-up of %d summaries)\n%s\n" % (pad(a), pad(b), len(group), text.strip())
            path, sha = write_unit(self.root, "%s-%s.rollup.md" % (pad(a), pad(b)), body)
            merged = {"kind": "rollup", "from": a, "to": b, "file": path, "sha256": sha, "tokens": tokens_of(body),
                      "refs": "§%s-§%s" % (pad(a), pad(b)), "text": body}
            self._switch([merged] + [u for i, u in enumerate(units) if i not in group])

        self._write_verified(lambda missed: rollup_prompt(texts, req, BUDGET["summaries"] // 3, missed), req, ok,
                             lambda missing, capped: self._switch(units))

    def _switch(self, units):
        h = self.host
        new = self.job["new"]
        if not new:
            self._finish()
            return
        if not h.idle():                       # never mid-turn: wait for the next pause
            self.status = "Summaries are ready - the switch waits for the turn to end."
            self.changed.emit()
            QtCore.QTimer.singleShot(1500, lambda: self._switch(units))
            return
        files = h.transcript_files()
        inject = injected_text(files, units, self.job["tail"])
        after = tokens_of(inject)
        a, b = new[0]["from"], new[-1]["to"]
        indexed = sum(1 for u in new if u["kind"] == "stub")
        line = compact_line(a, b, self.job["conv_before"], after, len(new) - indexed, indexed, self.job["fixed"])
        for u in units:
            u.pop("text", None)
        self.st["units"] = units
        self.st["next_n"] = b + 1
        self.st["last_compact_turn"] = self.st["turns"]
        self.st["retry_at"] = None
        self.st["sessions"] = files
        summary_view = "\n\n".join(unit_text(u).strip() for u in units)
        self._finish()
        self.log_event("compacted", line, segments=[a, b], before=self.job["conv_before"], after=after, calls=self.job["calls"])
        h.continue_fresh(inject, line, summary_view, {"trigger": "fx", "pre": self.job["conv_before"], "post": after})

    def _fail(self, why):
        self.st["retry_at"] = self.st["turns"] + BUDGET["retry_turns"]
        self._finish()
        e = self.log_event("error", "Compaction did not run: %s. The chat keeps its full history; it tries again in %d turns."
                       % (str(why)[:200], BUDGET["retry_turns"]))
        self.host.compact_note(e["text"], "#e5675f")

    def _finish(self):
        self.running = False
        self.status = ""
        self.save()
        self.changed.emit()
