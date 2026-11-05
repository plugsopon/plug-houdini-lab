# Read-only audit of the archival HIP: does it EMBED any geometry/data (vs only referencing files)?
# Loads the file, never cooks a SOP output (no .geometry() on any node), never saves.
# Reads only: Data parms (stash / savedstashgeo), hard/soft-locked SOP flags, embedded HDA definitions, file-path parms,
# and compares any embedded geometry with the Entagma curve exports by point positions.
import hou, sys, hashlib, re

hip, asset_dir = sys.argv[1], sys.argv[2]
hou.hipFile.load(hip, suppress_save_prompt=True, ignore_load_warnings=True)


def pts(g):
    return sorted(tuple(round(c, 5) for c in p.position()) for p in g.points())


ent = {}
for i in (1, 2, 3):
    g = hou.Geometry(); g.loadFromFile("%s/ASSET_entagma_curve%d.bgeo" % (asset_dir, i)); ent["curve%d" % i] = pts(g)
embedded, locked, refs = [], [], []
for n in hou.node("/obj").allSubChildren():
    for p in n.parms():
        t = p.parmTemplate().type()
        if t == hou.parmTemplateType.Data:
            try:
                v = p.eval()
            except Exception:
                continue
            if isinstance(v, hou.Geometry) and len(v.points()):
                P = pts(v)
                match = [k for k, e in ent.items() if e == P]
                embedded.append((n.path(), p.name(), len(v.points()), len(v.prims()), match or "no Entagma match"))
        elif t == hou.parmTemplateType.String:
            try:
                s = p.unexpandedString()
            except hou.OperationFailed:
                s = ' '.join(k.expression() for k in p.keyframes() if k.isExpressionSet())
            if re.search(r"\.(bgeo|bgeo\.sc|jpg|png|usdc?|hiplc|hip)\b", s):
                refs.append((n.path(), p.name(), s[:110]))
    if n.type().category() == hou.sopNodeTypeCategory():
        try:
            if n.isHardLocked() or n.isSoftLocked():
                locked.append((n.path(), "hard" if n.isHardLocked() else "soft"))
        except Exception:
            pass
emb_defs = sorted({(t.name(), t.definition().libraryFilePath()) for n in hou.node("/obj").allSubChildren() for t in [n.type()] if t.definition() is not None and t.definition().libraryFilePath() == "Embedded"})
print("EMBEDDED_GEOMETRY", len(embedded))
for e in embedded:
    print("  ", e)
print("LOCKED_SOPS", locked)
print("EMBEDDED_HDA_DEFS", emb_defs)
print("FILE_REFS", len(refs))
for r in refs:
    print("  ", r)
raw = open(hip, "rb").read()
print("RAW bytes", len(raw), "contains 'Endless_Blossom_2025'", raw.count(b"Endless_Blossom_2025"), "'ASSET_entagma_curve'", raw.count(b"ASSET_entagma_curve"))
print("unsaved", hou.hipFile.hasUnsavedChanges(), "(nothing saved)")
