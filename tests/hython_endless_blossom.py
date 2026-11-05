"""Endless Blossom: re-run the builder-vs-reviewed-scene check.

  "C:\\Program Files\\Side Effects Software\\Houdini 21.0.671\\bin\\hython.exe" tests\\hython_endless_blossom.py [WORK_DIR] [ASSET_DIR]

Runs techniques/Endless_Blossom_to_procedural_flower/verify_endless_blossom.py against
hip/endless_blossom/EB_full_v052bL3_layout.hipnc (loaded as the reference). Writes new scenes into WORK_DIR
(default: a fresh folder under %TEMP%); never touches an existing file.
ASSET_DIR (optional) = your own export of Entagma's curves (eb_extract_asset_curves.py); with it the five
Copernicus maps are re-baked and compared byte-for-byte with hip/endless_blossom/tex_v051.
Expected: RESULT PASS, 205 nodes, dP 0.0 on petal_out f1/f96 and blossom f96, only CONFIG path parms differ
(18 without ASSET_DIR, 12 with), and with ASSET_DIR 5/5 maps SAME.
"""
import os, sys, tempfile, runpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tech = os.path.join(ROOT, "techniques", "Endless_Blossom_to_procedural_flower")
builder = os.path.join(tech, "build_endless_blossom.py")
verify = os.path.join(tech, "verify_endless_blossom.py")
ref = os.path.join(ROOT, "hip", "endless_blossom", "EB_full_v052bL3_layout.hipnc")
reviewed_tex = os.path.join(ROOT, "hip", "endless_blossom", "tex_v051")
work = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="eb_verify_")
asset_dir = sys.argv[2] if len(sys.argv) > 2 else ""
sys.argv = [verify, builder, ref, work] + ([asset_dir, reviewed_tex] if asset_dir else [])
runpy.run_path(verify, run_name="__main__")
