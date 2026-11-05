# ============================================================================
# Endless Blossom - bake the 5 petal maps from the Copernicus network (hython, headless)
#
#   hython eb_cook_textures.py SCENE.hipnc [PREFIX] [OUT_DIR]
#
#   Cooks <PREFIX>_textures/EB_cop/write_{diffuse,rough_sss,normal,opacity,sss} (rop_image) and
#   writes PNGs to OUT_DIR (default = the folder the builder's TEX_DIR resolved to). The maps are
#   baked from the REST petal (petal_surface, before the rig), so they need no sim cache.
#   The copnet is 1024x1024: Houdini Apprentice refuses to save Copernicus output above 1920x1080.
#   Measured on 21.0.671: all five maps in about 10 s. This script never saves the scene.
# ============================================================================
import hou, os, sys, time

scene = sys.argv[1]
prefix = sys.argv[2] if len(sys.argv) > 2 else "EB"
hou.hipFile.load(scene, suppress_save_prompt=True, ignore_load_warnings=True)
tex = hou.node("/obj/%s_textures" % prefix)
if tex is None:
    sys.exit("no /obj/%s_textures in %s" % (prefix, scene))
cop = tex.node("EB_cop")
outdir = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(cop.node("write_diffuse").parm("copoutput").eval())
os.makedirs(outdir, exist_ok=True)
uv, rim = tex.node("UV").geometry(), tex.node("RIM").geometry()
print("rest petal UV pts %d, RIM pts %d, res %s" % (len(uv.points()), len(rim.points()), cop.parmTuple("res").eval()))
for w in ("diffuse", "rough_sss", "normal", "opacity", "sss"):
    r = cop.node("write_" + w)
    path = "%s/%s.png" % (outdir, w)
    r.parm("copoutput").set(path)
    t = time.time()
    r.render()
    ok = os.path.exists(path) and os.path.getsize(path) > 0
    print("wrote %-10s %s %.1fs exists=%s errors=%s" % (w, path, time.time() - t, ok, r.errors() or cop.node("OUT_" + w).errors()), flush=True)
    if not ok:
        sys.exit("map %s was not written" % w)
print("DONE -> %s (%s)" % (outdir, hou.applicationVersionString()))
