---
name: houdini-flower-endless-blossom
description: Use whenever Plug wants a procedural flower / petal / blossom / bloom in Houdini - petals that open on a rig, a blossom that keeps growing in a loop, petals falling with Vellum, procedural petal textures in Copernicus, a Karma flower look - or asks to reuse, extend, re-render or version the "Endless Blossom → procedural flower" technique on the Houdini Snippet Shelf. Also use for any Feather-tool petal, golden-angle copy loop, time-offset blossom, "endless loop" of cached sim copies, or a flower-shaped Vellum emission even when the word flower is not said. It routes to the builder/verify/publish skills and carries the measured traps.
---

# Endless Blossom → procedural flower (reuse guide)

ดอกไม้บานไม่รู้จบจาก tutorial ของ Entagma (Christopher Kopic, 2025) สร้างใหม่ทั้งระบบใน Houdini 21.0.671
ผ่าน MCP (benchmark 2026-11-05) แล้ว export เป็น technique บน shelf. Skill นี้บอกว่า **ของอยู่ตรงไหน
ใช้ยังไง ปรับตรงไหน และกับดักที่วัดมาแล้ว** — code เป็นภาษาอังกฤษ โน้ตเป็นไทย.

## Where everything is

| what | where |
|---|---|
| shelf technique (id `endless-blossom-flower`) | `techniques/Endless_Blossom_to_procedural_flower/` — README + 6 Python + 5 VEX |
| the builder to paste | `build_endless_blossom.py` (paste at `/obj`; builds `EB_candidate`, `EB_render_prep`, `EB_textures`, `EB_solaris`) |
| hython steps after pasting | `eb_sim_cache.py` → `eb_cook_textures.py` → `eb_render_karma.py` |
| Entagma curves (optional, `INPUT_CURVES = "asset"`) | `eb_extract_asset_curves.py` on YOUR download of the project file — the curves are not in the repo |
| the check | `verify_endless_blossom.py` (also `tests/hython_endless_blossom.py`) |
| reviewed scene + media + the 5 reviewed maps | `hip/endless_blossom/` (`README.md` there = provenance + hashes + limits) |
| recipe, stage by stage, with the numbers | [references/pipeline.md](references/pipeline.md) |
| traps that cost a round each, with what was measured | [references/lessons.md](references/lessons.md) |

## Which skill does what

- **New or changed builder code** → `houdini-builder-script` (CONFIG block, `mk()` below existing nodes, never move
  Plug's nodes, one print at the end). The flower builder follows it, with one honest deviation: it only runs at an
  Object network, because the technique is four networks.
- **Any claim about geometry, parity or "it works"** → `houdini-hython-verify`. For this technique the check is
  already written: `verify_endless_blossom.py` (below). Add measurements, do not replace them with words.
- **Putting a new version on the shelf** → `houdini-shelf-publish` (`shelf.py add` from the LIVE artifact, diff,
  export, git, Artifact publish). Media that must survive a re-export live in `hip/endless_blossom/`, never in the
  technique folder (`shelf.py export` deletes and rewrites that folder).
- **Live Houdini through MCP**: build in your own `/obj/<PREFIX>_*`, export with `saveItemsToFile` to a `.cpio`,
  and run sims/cooks/renders in a separate hython on that export. Never `hipFile.save()` the live session.

## Recipe A — rebuild the flower as reviewed (≈ 3 minutes before any render)

```
1. Houdini: open /obj, paste build_endless_blossom.py           -> 4 networks, 205 nodes, display on copy_blossom_to_stem_tip
2. Save YOUR scene (e.g. $HIP/flower_v001.hipnc)
3. hython eb_sim_cache.py    flower_v001.hipnc                   -> $HIP/geo/eb_sim/sim.0001-0225.bgeo.sc   (68 s, 7,750 pts/frame)
4. hython eb_cook_textures.py flower_v001.hipnc                  -> $HIP/tex/eb_cop/{diffuse,rough_sss,normal,opacity,sss}.png (≈10 s)
5. hython eb_render_karma.py flower_v001.hipnc EB 12 480 6       -> $HIP/render/eb/eb_karma.0012.png (20 s)
   loop: ... EB 1-44 360 6 ; still: ... EB 12 720 32 (89 s)
```
- Until step 3/4 exist, `LOOP_OUT` and the Solaris petals are EMPTY on purpose (`missingframe = No Geometry`).
  That is the no-cook default, not a bug.
- The reviewed media were rendered with `INPUT_CURVES = "asset"` (Entagma's curves). The bundled `"ai"` curves give
  a narrower petal. Say which one a render used.
- Loop maths: petal i is rotated 137.5°·i, lifted 0.005·i, time-shifted −4·i frames (10 petals); the endless loop
  reads the cache 5× at +44·k frames, so the cache must reach f225 for a 44-frame loop.

## Recipe B — adapt it to another flower

Change in this order and re-run `verify` + a 480² f12 render after each group; the stages downstream of a change
are listed so you know what to re-cook.

| want | change | then re-cook |
|---|---|---|
| another petal outline | `petal_shape_curves` (3 open Bézier, order 4, petal along −Z, tip at z = −1) or `INPUT_CURVES = "asset"` + your own bgeo | everything (rig capture, loop, sim, maps) |
| petal detail / density | `feather_template` barbdensity 500 · shaftdensity 50 · `feather_resample` shaft 30 / barbs 12 | everything |
| how far it opens | `pose_A_closed` / `pose_B_open` rig poses; `pose_blend.weight1` keys (f1 = 0 → f96 = 0.8565) | loop, sim |
| when petals let go | `petal_state_groups` spare `end_frame` (= the frame the blend reaches its end) | sim cache |
| how many petals / spacing | `loop_end` iterations (10) · `petal_rotate_offset` ry 137.5·it, ty 0.005·it · `petal_timeshift` −4·it | sim cache |
| fall / wind | `vellum_solver` timescale 0.5, niter 300, wind (1, 0, 0.2) × speed 3, friction 0 · `vellum_configure_cloth` bend 1e2 | sim cache |
| loop length | `loop2_end` iterations (5) and `loop2_timeshift` +44·it; cache must cover 225 + any extra | nothing (reads cache) |
| petal colour / veins | Copernicus `EB_cop` (hsv1 hueshift 234.5, monotorgb1 ramp) · material `ent_cc_base` saturation 1.5 | maps, render |
| camera / light | `ent_cam` 80 mm f/0.35 focus 9.74 · `ent_spot*` (3 white spots, intensities 2516 / 3087 / 15) | render |

Keep the "one declared source" habit: a value that exists on the box AND in a script will drift. Every number above
lives on the node; the builder is generated from the scene (`gen_builder.py` in the benchmark), not typed.

## Recipe C — the check (run it before saying anything matched)

```
hython verify_endless_blossom.py build_endless_blossom.py hip/endless_blossom/EB_full_v052bL3_layout.hipnc WORK_DIR [ASSET_DIR] [hip/endless_blossom/tex_v051]
```
Expected (21.0.671): `BUILT nodes 205`, `OTHER 0` (only CONFIG path parms differ), `petal_out f1/f96 max dP 0.0`,
`blossom_f96 ... 0.0`, Vellum geo 775 / constraints 4,320, `rig_warnings []`, `NOASSET ... SOP errors 0`, and with
`ASSET_DIR` the five maps `SAME` (sha256) → `RESULT PASS`. It writes new scenes into WORK_DIR only; it never saves
over anything. No sim and no render inside the check — those are Recipe A, bounded, in their own process.

## What is measured vs what is still open

- Petal and blossom: bit-identical to Entagma's chain at the same inputs (f48 1.39e-05). Maps: identical buffers.
- Sim vs Entagma's cache: f89 max 1.3e-05, f133 mean 0.000165 / max 0.0116; nothing to compare after f133.
- Render f12 vs Entagma's scene: whole 2.23, head 4.42 (/255). The head tone gap is Entagma's H20.5 diffuse JPG
  (control: swapping only that file → 1.33 / 2.12). Do not "grade to match".
- Open: cross-time petal intersections of the endless loop (visible, also in Entagma's file), the hand-shaped
  pose curve at 12:13 (substituted keys), bend rest-angle float residual ≤ 0.028°, Houdini 20.5 untested
  (Vellum source default, Feather Resample slider, Copernicus differ), Apprentice caps (1024² COP, ≤720 render).

## Rules of this technique (why, in one line each)

- Build in an isolated `/obj/<PREFIX>_*`; refuse to run if the name exists. A paste must never rename Plug's nodes.
- Every measurement comes from a separate hython on an exported file. A `.geometry()` call on a node downstream of
  a solver IS a sim cook — guard it (the benchmark's `geo_guard.py` idea: allowlist + reject solver/cache ancestry).
- Version numbers are claims about a moment: re-read `preset`-like values (switch inputs, cache path, tex_src) from
  the file before building on a sentence in a report.
- Entagma's inputs are attributed and never bundled; our curves are ours. Keep both switches so the two never mix
  silently (`INPUT_CURVES_*_src`, `STEM_src`, `tex_src`, `PETAL_SHELL_src`, `LOOK_RIG_src` are all 0 = ours, 1 = Entagma recipe).
