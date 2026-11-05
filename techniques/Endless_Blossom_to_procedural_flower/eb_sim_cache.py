# ============================================================================
# Endless Blossom - write the Vellum sim cache (hython, headless, bounded)
#
#   hython eb_sim_cache.py SCENE.hipnc [PREFIX] [FIRST LAST] [OUT_DIR]
#
#   SCENE.hipnc  your scene after pasting build_endless_blossom.py (saved by you; this script never saves it)
#   PREFIX       the builder's PREFIX (default EB)
#   FIRST LAST   frame range (default 1 225: petals emit from f96, the endless loop needs +176 frames of cache)
#   OUT_DIR      default = the CACHE_DIR the builder wrote into <PREFIX>_candidate/sim_cache_read
#
# Cooks <PREFIX>_candidate/OUT_SIM_PREVIEW frame by frame in a SEPARATE hython process and writes
# sim.NNNN.bgeo.sc. Refuses to overwrite a folder that already has frames (delete it yourself).
# Measured on 21.0.671 Apprentice: 225 frames = 68 s, 7,750 points per frame (10 petals x 775).
# ============================================================================
import hou, os, sys, time

scene = sys.argv[1]
prefix = sys.argv[2] if len(sys.argv) > 2 else "EB"
f0, f1 = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (1, 225)
hou.hipFile.load(scene, suppress_save_prompt=True, ignore_load_warnings=True)
cand = hou.node("/obj/%s_candidate" % prefix)
if cand is None:
    sys.exit("no /obj/%s_candidate in %s" % (prefix, scene))
out = cand.node("OUT_SIM_PREVIEW")
outdir = sys.argv[5] if len(sys.argv) > 5 else os.path.dirname(cand.node("sim_cache_read").parm("file").eval())
if os.path.isdir(outdir) and any(f.endswith(".bgeo.sc") for f in os.listdir(outdir)):
    sys.exit("%s already holds frames - refusing to overwrite" % outdir)
os.makedirs(outdir, exist_ok=True)
t0 = time.time()
for f in range(f0, f1 + 1):
    hou.setFrame(f)
    t = time.time()
    g = out.geometry()
    if g is None:
        sys.exit("frame %d: OUT_SIM_PREVIEW cooked no geometry - %s" % (f, out.errors()))
    g.saveToFile("%s/sim.%04d.bgeo.sc" % (outdir, f))
    print("frame %d pts %d %.2fs total %.1fs" % (f, len(g.points()), time.time() - t, time.time() - t0), flush=True)
print("DONE %d frames in %.1fs -> %s (%s)" % (f1 - f0 + 1, time.time() - t0, outdir, hou.applicationVersionString()))
