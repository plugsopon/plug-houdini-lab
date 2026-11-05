# ============================================================================
# Endless Blossom - headless check of build_endless_blossom.py against the reviewed scene (hython)
#
#   hython verify_endless_blossom.py build_endless_blossom.py REFERENCE.hipnc|.cpio [WORK_DIR] [ASSET_DIR] [REVIEWED_TEX_DIR]
#
#   ASSET_DIR         optional: folder with ASSET_entagma_curve1/2/3.bgeo (your own export). With it, both sides read the
#                     same Entagma barb curve and a second scene is saved with INPUT_CURVES = "asset" so the texture
#                     cook can be compared byte-for-byte against REVIEWED_TEX_DIR (hip/endless_blossom/tex_v051).
#                     Without it, both sides run with no Entagma files at all (the shelf user's default).
#
#   1. loads REFERENCE (the reviewed EB_full_v052bL3 export) and records: every node's type, wiring and
#      authored parm state (4 networks, recursive), rest/deformed petal P at f1 + f96, blossom P at f96,
#      Vellum emit/constraint counts, collider, rest-UV prep, the drawn-curve digest, rig_doctor warnings.
#   2. clears the scene, runs the BUILDER at /obj (TARGET="/obj", INPUT_CURVES="ai"), records the same.
#   3. reports the differences. Expected: only the CONFIG-substituted paths and INPUT_CURVES switches.
#   No sim, no render, no save. Measured below = what the reviewed artifact had.
# ============================================================================
import hou, sys, os, re, json, hashlib

builder, ref, work = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else os.getcwd())
asset_dir = sys.argv[4].replace("\\", "/") if len(sys.argv) > 4 and os.path.isdir(sys.argv[4]) else ""
reviewed_tex = sys.argv[5].replace("\\", "/") if len(sys.argv) > 5 else ""
work = work.replace("\\", "/")
NETS = ["EB_candidate", "EB_render_prep", "EB_textures", "EB_solaris"]
EXPECT_SUBST = re.compile(r"\b(file|copoutput|outputimage)$")


def sig(p):
    ks = p.keyframes()
    if ks:
        def kk(k):
            x = k.expression() if k.isExpressionSet() else None
            if not isinstance(k, hou.Keyframe):
                return (k.frame(), x)
            def g(fn):
                try:
                    return round(fn(), 4)
                except hou.KeyframeValueNotSet:
                    return None
            return (k.frame(), None if x else round(k.value(), 6), x, g(k.inSlope), g(k.slope), g(k.inAccel), g(k.accel))
        return "K" + repr([kk(k) for k in ks])
    t = p.parmTemplate().type()
    if t == hou.parmTemplateType.Data:
        return None
    if t == hou.parmTemplateType.Ramp:
        r = p.eval()
        return "R" + repr(([b.name() for b in r.basis()], [round(k, 6) for k in r.keys()], [tuple(round(c, 6) for c in v) if isinstance(v, tuple) else round(v, 6) for v in r.values()]))
    try:
        v = p.eval()
    except Exception:
        return None
    if isinstance(v, str):
        return "S" + p.unexpandedString()
    if isinstance(v, float) and abs(v) < 1e-9:
        return None   # 2.8e-15 rotations etc. are zero
    return "V" + repr(round(v, 6) if isinstance(v, float) else v)


def _anc(n, root):
    out = []
    p = n.parent()
    while p is not None and p != root:
        out.append(p)
        p = p.parent()
    return out


def snapshot():
    out = {}
    for net in NETS:
        root = hou.node("/obj/" + net)
        for n in [root] + list(root.allSubChildren()):
            # inside a locked HDA only user-added nodes count (the Vellum Source in the solver's forces subnet)
            if any(a.isLockedHDA() for a in n.parents_chain) if False else any(a.isLockedHDA() for a in _anc(n, root)):
                if n.type().name() != "vellumsource" or "/forces/" not in n.path():
                    continue
            rel = n.path()[len("/obj/" + net):] or "/"
            d = {"type": n.type().name(), "bypass": n.isBypassed() if hasattr(n, "isBypassed") else False,
                 "inputs": [(c.inputNode().name() if c.inputNode() else None, c.outputIndex(), c.inputIndex()) for c in n.inputConnections()],
                 "parms": {}}
            for p in n.parms():
                if p.isAtDefault(compare_temporary_defaults=False) and not p.keyframes():
                    continue
                s = sig(p)
                if s is not None:
                    d["parms"][p.name()] = s
            out[net + rel] = d
    return out


def digest(g):
    h = hashlib.sha256()
    h.update(str([tuple(round(c, 6) for c in pt.position()) for pt in g.points()]).encode())
    h.update(str([[v.point().number() for v in p.vertices()] for p in g.prims()]).encode())
    return h.hexdigest()[:16]


def P_at(node, f):
    g = node.geometryAtFrame(f)
    return [tuple(pt.position()) for pt in g.points()] if g else None


def measure():
    c = hou.node("/obj/EB_candidate")
    m = {}
    m["curves"] = digest(c.node("petal_shape_curves").geometry())
    m["petal_out_f1"] = P_at(c.node("petal_out"), 1)
    m["petal_out_f96"] = P_at(c.node("petal_out"), 96)
    m["blossom_f96"] = P_at(c.node("copy_blossom_to_stem_tip"), 96)
    def npts(node, f, prims=False):
        g = node.geometryAtFrame(f)
        if g is None:
            return "ERROR %s" % (node.errors() or node.warnings() or [i.name() + ":" + str(i.errors()) for i in node.inputAncestors() if i.errors()])[:2]
        return len(g.prims()) if prims else len(g.points())
    m["vellum_geo_f96"] = npts(c.node("VELLUM_GEO"), 96)
    m["vellum_con_f96"] = npts(c.node("VELLUM_CONSTRAINTS"), 96, True)
    m["collider"] = (npts(c.node("stem_sweep"), 1), npts(c.node("stem_sweep"), 1, True))
    m["rig_warnings"] = list(c.node("rig_doctor").warnings())
    t = hou.node("/obj/EB_textures")
    m["uv_pts"] = npts(t.node("UV"), 1)
    m["rim_pts"] = npts(t.node("RIM"), 1)
    errs = []
    for net in NETS:
        for n in hou.node("/obj/" + net).allSubChildren():
            if n.errors() and n.type().category().name() != "Lop":
                errs.append((n.path(), n.errors()[0][:80]))
    m["sop_errors"] = errs
    return m


def pmax(a, b):
    if a is None or b is None or len(a) != len(b):
        return "count %s vs %s" % (None if a is None else len(a), None if b is None else len(b))
    return max(((x[0] - y[0]) ** 2 + (x[1] - y[1]) ** 2 + (x[2] - y[2]) ** 2) ** 0.5 for x, y in zip(a, b))


# ---- 1. reference
hou.hipFile.clear(suppress_save_prompt=True)
if ref.lower().endswith(".cpio"):
    hou.node("/obj").loadItemsFromFile(ref)
else:
    hou.hipFile.load(ref, suppress_save_prompt=True, ignore_load_warnings=True)
# the reference reads the Entagma curves through switches set to 1; compare the builder's "ai" default against input 0,
# and point the reference's three asset File SOPs at ASSET_DIR (or at nothing, No Geometry) so both sides see the same files
for sw in ("INPUT_CURVES_shape_src", "INPUT_CURVES_barb_src", "STEM_src"):
    hou.node("/obj/EB_candidate/" + sw).parm("input").set(0)
for i, tag in ((1, "shape"), (2, "barbs"), (3, "stem")):
    fn = hou.node("/obj/EB_candidate/ASSET_entagma_curve%d_%s" % (i, tag))
    fn.parm("file").set(asset_dir + "/ASSET_entagma_curve%d.bgeo" % i if asset_dir else "")
    fn.parm("missingframe").set(1)
snap_ref, meas_ref = snapshot(), measure()
print("REF nodes %d, petal_out f96 pts %s, blossom f96 pts %s, rig warnings %s" % (
    len(snap_ref), len(meas_ref["petal_out_f96"] or []), len(meas_ref["blossom_f96"] or []), meas_ref["rig_warnings"]))

# ---- 2. builder
hou.hipFile.clear(suppress_save_prompt=True)
hou.hipFile.setName(work + "/verify_scene.hipnc")   # so $HIP resolves; saved only at the end, as a NEW file
code = open(builder, encoding="utf8").read()
code = code.replace('TARGET          = ""', 'TARGET          = "/obj"', 1)
assert 'TARGET          = "/obj"' in code
code_noasset = code
if asset_dir:
    code = code.replace('ASSET_DIR       = "$HIP/eb_assets"', 'ASSET_DIR       = %r' % asset_dir, 1)
    assert code != code_noasset, "ASSET_DIR line not found"
print("ASSET_DIR for this run:", asset_dir or "(none - no Entagma files on either side)")
ns = {}
exec(compile(code, builder, "exec"), ns)
for sw in ("INPUT_CURVES_shape_src", "INPUT_CURVES_barb_src", "STEM_src"):
    assert hou.node("/obj/EB_candidate/" + sw).parm("input").eval() == 0
snap_new, meas_new = snapshot(), measure()
print("BUILT nodes %d, skipped parm sets %d" % (len(snap_new), len(ns["skipped"])))

# ---- 3. compare
diffs = []
for k in sorted(set(snap_ref) | set(snap_new)):
    a, b = snap_ref.get(k), snap_new.get(k)
    if a is None or b is None:
        diffs.append((k, "MISSING in %s" % ("built" if b is None else "reference")))
        continue
    for f in ("type", "bypass", "inputs"):
        if a[f] != b[f]:
            diffs.append((k, f, a[f], b[f]))
    for pn in sorted(set(a["parms"]) | set(b["parms"])):
        x, y = a["parms"].get(pn), b["parms"].get(pn)
        if x != y:
            diffs.append((k, "parm " + pn, (x or "")[:90], (y or "")[:90]))
expected = [d for d in diffs if len(d) == 4 and d[1].startswith("parm ") and (EXPECT_SUBST.search(d[1].split()[1])
            or (d[1] == "parm missingframe" and "/ASSET_entagma_" in d[0] and d[3] == "V1"))]   # builder: No Geometry when the Entagma curves are absent
other = [d for d in diffs if d not in expected]
print("DIFF total %d | path substitutions (expected) %d | OTHER %d" % (len(diffs), len(expected), len(other)))
for d in expected:
    print("  subst", d[0], d[1], "|", d[2], "->", d[3])
for d in other:
    print("  OTHER", d)
print("GEOM curves digest ref %s built %s" % (meas_ref["curves"], meas_new["curves"]))
for key in ("petal_out_f1", "petal_out_f96", "blossom_f96"):
    print("GEOM %s pts %s max dP %s" % (key, len(meas_ref[key] or []), pmax(meas_ref[key], meas_new[key])))
for key in ("vellum_geo_f96", "vellum_con_f96", "collider", "uv_pts", "rim_pts", "rig_warnings", "sop_errors"):
    print("GEOM %s ref %s built %s %s" % (key, meas_ref[key], meas_new[key], "OK" if meas_ref[key] == meas_new[key] else "DIFFERENT"))
ok = not other and meas_ref["curves"] == meas_new["curves"] and all(
    isinstance(pmax(meas_ref[k], meas_new[k]), float) and pmax(meas_ref[k], meas_new[k]) < 1e-5 for k in ("petal_out_f1", "petal_out_f96", "blossom_f96")) \
    and all(meas_ref[k] == meas_new[k] for k in ("vellum_geo_f96", "vellum_con_f96", "collider", "uv_pts", "rim_pts", "rig_warnings")) and not meas_new["sop_errors"] and not ns["skipped"]
# ---- 4. mode B: INPUT_CURVES = "ai" with NO Entagma files anywhere (the shelf user's default situation)
hou.hipFile.clear(suppress_save_prompt=True)
hou.hipFile.setName(work + "/verify_scene_noasset.hipnc")
ns2 = {}
exec(compile(code_noasset, builder, "exec"), ns2)
c = hou.node("/obj/EB_candidate")
errs_b = [(n.path(), n.errors()[0][:70]) for net_ in NETS for n in hou.node("/obj/" + net_).allSubChildren() if n.errors() and n.type().category().name() != "Lop"]
pb = c.node("petal_out").geometryAtFrame(96)
bb = c.node("copy_blossom_to_stem_tip").geometryAtFrame(96)
print("NOASSET petal_out f96 pts %s, blossom f96 pts %s, SOP errors %d %s, skipped %d" % (
    len(pb.points()) if pb else None, len(bb.points()) if bb else None, len(errs_b), errs_b[:3], len(ns2["skipped"])))
ok = ok and pb is not None and len(pb.points()) > 0 and bb is not None and len(bb.points()) == 10 * len(pb.points()) and not errs_b and not ns2["skipped"]
# keep a reopenable copy of mode A (a NEW file; nobody's scene is overwritten)
hou.hipFile.clear(suppress_save_prompt=True)
hou.hipFile.setName(work + "/verify_scene.hipnc")
exec(compile(code, builder, "exec"), {})
out_hip = work + "/verify_scene.hipnc"
assert not os.path.exists(out_hip), out_hip + " exists - refusing to overwrite"
hou.hipFile.save(out_hip)
print("SAVED mode-A scene:", out_hip)
# ---- 5. with ASSET_DIR: INPUT_CURVES = "asset" scene + the 5 Copernicus maps against the reviewed maps (byte for byte)
if asset_dir:
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.hipFile.setName(work + "/verify_scene_asset.hipnc")
    code_c = code.replace('INPUT_CURVES    = "ai"', 'INPUT_CURVES    = "asset"', 1)
    assert code_c != code
    exec(compile(code_c, builder, "exec"), {})
    out_c = work + "/verify_scene_asset.hipnc"
    assert not os.path.exists(out_c), out_c + " exists - refusing to overwrite"
    hou.hipFile.save(out_c)
    cop = hou.node("/obj/EB_textures/EB_cop")
    texdir = work + "/tex_asset"
    os.makedirs(texdir, exist_ok=True)
    same = 0
    for w in ("diffuse", "rough_sss", "normal", "opacity", "sss"):
        r = cop.node("write_" + w)
        r.parm("copoutput").set("%s/%s.png" % (texdir, w))
        r.render()
        a = hashlib.sha256(open("%s/%s.png" % (texdir, w), "rb").read()).hexdigest()[:16]
        rv = "%s/%s.png" % (reviewed_tex, w) if reviewed_tex else ""
        b = hashlib.sha256(open(rv, "rb").read()).hexdigest()[:16] if rv and os.path.exists(rv) else "(no reviewed map given)"
        same += a == b
        print("TEX %-10s built %s reviewed %s %s" % (w, a, b, "SAME" if a == b else "DIFF"))
    print("SAVED asset-mode scene:", out_c, "| maps identical to the reviewed set: %d/5" % same)
    if reviewed_tex:
        ok = ok and same == 5
print("RESULT", "PASS" if ok else "FAIL", hou.applicationVersionString())
sys.exit(0 if ok else 1)
