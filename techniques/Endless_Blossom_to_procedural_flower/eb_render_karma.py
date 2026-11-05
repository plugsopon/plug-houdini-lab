# ============================================================================
# Endless Blossom - render frames with Karma CPU (hython, headless, bounded)
#
#   hython eb_render_karma.py SCENE.hipnc [PREFIX] [FRAMES] [RES] [SPP] [OUT_DIR]
#
#   FRAMES   "12" or "1,2,3" or "1-44" (default 12)
#   RES      square resolution (default 480; the Entagma camera is 1:1; Apprentice caps at 1280x720 - keep <= 720)
#   SPP      samples per pixel (default 6; the reviewed still used 32 at 720, the loop 6 at 360)
#   OUT_DIR  default = the builder's RENDER_DIR
#
#   Needs the sim cache (eb_sim_cache.py) and the maps (eb_cook_textures.py) first, or the petals are empty.
#   Measured on 21.0.671 Apprentice CPU: 480^2 6spp = 20 s/frame, 360^2 6spp = 17 s, 720^2 32spp = 89 s.
#   The "Houdini" mark in every frame is the Apprentice watermark. This script never saves the scene.
# ============================================================================
import hou, os, sys, time

scene = sys.argv[1]
prefix = sys.argv[2] if len(sys.argv) > 2 else "EB"
spec = sys.argv[3] if len(sys.argv) > 3 else "12"
res = int(sys.argv[4]) if len(sys.argv) > 4 else 480
spp = int(sys.argv[5]) if len(sys.argv) > 5 else 6
frames = []
for part in spec.split(","):
    if "-" in part:
        a, b = part.split("-")
        frames += list(range(int(a), int(b) + 1))
    else:
        frames.append(int(part))
hou.hipFile.load(scene, suppress_save_prompt=True, ignore_load_warnings=True)
lop = hou.node("/obj/%s_solaris" % prefix)
if lop is None:
    sys.exit("no /obj/%s_solaris in %s" % (prefix, scene))
krs, rop = lop.node("karma_settings"), lop.node("karma_rop")
outdir = sys.argv[6] if len(sys.argv) > 6 else os.path.dirname(rop.parm("outputimage").eval())
os.makedirs(outdir, exist_ok=True)
krs.parm("resolutionx").set(res)          # resolutiony follows the camera aspect (res_mode autoheight)
krs.parm("samplesperpixel").set(spp)
rop.parm("outputimage").set(outdir + "/eb_karma.$F4.png")
rop.parm("trange").set(0)
for f in frames:
    hou.setFrame(f)
    t = time.time()
    rop.render(verbose=False)
    path = "%s/eb_karma.%04d.png" % (outdir, f)
    print("frame %d res %dx%d spp %d engine %s %.1fs exists=%s" % (
        f, res, krs.parm("resolutiony").eval(), spp, krs.parm("engine").eval(), time.time() - t, os.path.exists(path)), flush=True)
print("DONE %d frames -> %s (%s)" % (len(frames), outdir, hou.applicationVersionString()))
