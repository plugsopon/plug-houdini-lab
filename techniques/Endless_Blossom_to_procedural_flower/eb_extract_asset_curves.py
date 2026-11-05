# ============================================================================
# Endless Blossom - export the 3 input curves from YOUR copy of the Entagma project file (hython, read-only)
#
#   hython eb_extract_asset_curves.py Endless_Blossom_2025_Part-1.hiplc OUT_DIR
#
#   The Entagma project (entagma.com, "Endless Blossom" by Christopher Kopic, 2025 - free download on the post)
#   draws the petal outline (curve1), the barb guide (curve2) and the stem (curve3) by hand in /obj/geo1.
#   This writes them as ASSET_entagma_curve1/2/3.bgeo into OUT_DIR for the builder's INPUT_CURVES = "asset".
#   Those curves are Entagma's, not ours: they are NOT bundled with the shelf technique - export your own.
#   Only the three Curve SOPs are cooked (no solver, nothing saved, the project file is not modified).
# ============================================================================
import hou, os, sys, hashlib

src, outdir = sys.argv[1], sys.argv[2]
print("project sha256", hashlib.sha256(open(src, "rb").read()).hexdigest()[:16])
hou.hipFile.load(src, suppress_save_prompt=True, ignore_load_warnings=True)
os.makedirs(outdir, exist_ok=True)
for n in ("curve1", "curve2", "curve3"):
    node = hou.node("/obj/geo1/" + n)
    if node is None:
        sys.exit("/obj/geo1/%s not found - is this the Part-1 project file?" % n)
    g = node.geometry()
    path = "%s/ASSET_entagma_%s.bgeo" % (outdir, n)
    g.saveToFile(path)
    print("wrote", path, "pts", len(g.points()), "prims", [p.type().name() for p in g.prims()])
print("unsaved changes to the project file:", hou.hipFile.hasUnsavedChanges(), "(nothing is written back)")
