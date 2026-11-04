"""LIVE: one real Haiku summary of a real FX AI transcript, through the panel's own writer (QProcess),
checked by the program like a real compaction. Costs one or a few small Haiku calls (~$0.01-0.05).

  hython tests/live_compact_writer.py [transcript.jsonl]

Picks the largest transcript of this repo's chats when none is given. Writes nothing but the
summary to a temp file.
"""
import glob, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mcp", "houdini"))
from PySide6 import QtCore, QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
import brother_chat as bc
import brother_compact as CMP

if sys.argv[1:] == ["--synthetic"]:      # Plug's real Houdini chats are mostly dictated Thai with few ids:
    import json                          # this stretch carries ids Plug typed, so the check has work to do
    path = os.path.join(tempfile.gettempdir(), "fxai_synthetic.jsonl")
    with open(path, "w", encoding="utf8") as fh:
        for i in range(24):
            say = ("ช่วย cache /obj/geo1/pyro_v%03d ไปที่ $HIP/geo/pyro_v%03d.bgeo.sc แล้ว commit %07x ให้หน่อย งบ ฿%d"
                   % (i, i, 0xbeef000 + i, 500 + i) if i % 4 == 0 else "ปรับ dissipation เป็น 0.%d แล้วลองใหม่" % i)
            fh.write(json.dumps({"type": "user", "uuid": "u%d" % i, "message": {"content": say}}, ensure_ascii=False) + "\n")
            fh.write(json.dumps({"type": "assistant", "uuid": "a%d" % i, "message": {"content": [
                {"type": "text", "text": "ทำแล้วครับ " + "รายละเอียด sim " * 60}]}}, ensure_ascii=False) + "\n")
    sys.argv = sys.argv[:1] + [path]

path = sys.argv[1] if len(sys.argv) > 1 else max(
    [p for k in ("*plug-houdini-lab*", "*Houdini-Snippet-Shelf*")     # new folder name, + transcripts from before the rename
     for p in glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "projects", k, "*.jsonl"))],
    key=os.path.getsize)
msgs = CMP.read_messages(path)
# the ~25K-token stretch where Plug himself wrote the most ids: the check has something to check
best = None
for seg_ in CMP.split_segments(msgs, 25000):
    r_ = CMP.required_of(seg_)
    if best is None or len(r_) > len(best[1]):
        best = (seg_, r_)
seg, req = best
size = sum(CMP.msg_tokens(m) for m in seg)
print("transcript", path, "\nstretch: %d messages, ~%d tokens, %d items must be kept" % (len(seg), size, len(req)))


class Host(QtCore.QObject):
    account = None
    _writers = []


host = Host()
out = {}
tries = []


def attempt(missed=()):
    t0 = time.time()

    def done(text, err=None):
        tries.append((time.time() - t0, err))
        if text is None:
            out["err"] = err; app.quit(); return
        miss = CMP.verify_summary(text, req)
        out["text"], out["missing"] = text, miss
        if miss and len(tries) < CMP.TRIES:
            return attempt(miss)
        app.quit()
    bc.Convo._write_summary(host, CMP.segment_prompt(1, seg, req, CMP.BUDGET["summary_tokens"], missed),
                            CMP.WRITER_SYSTEM, done)


QtCore.QTimer.singleShot(0, attempt)
app.exec()
print("tries:", ["%.1fs%s" % (t, (" err=%s" % e) if e else "") for t, e in tries])
if "err" in out:
    print("WRITER FAILED:", out["err"]); sys.exit(1)
f = os.path.join(tempfile.gettempdir(), "fxai_live_summary.md")
open(f, "w", encoding="utf8").write(out["text"])
print("summary: ~%d tokens -> %s" % (CMP.tokens_of(out["text"]), f))
print("still missing after %d tries: %s" % (len(tries), out["missing"] or "nothing - VERIFIED"))
sys.exit(0 if not out["missing"] else 2)
