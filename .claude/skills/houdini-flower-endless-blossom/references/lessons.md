# Endless Blossom — traps that each cost a round, with what was measured

Each entry: what went wrong, how it was found, what fixed it. Numbers are from the benchmark record
(`HB_INDEX_v052b.md`, `provenance/PETAL_SOURCE_PARITY_v051.md`), not estimates.

## Petal + rig
1. **Template density decides the UVs.** barbdensity 100 / shaftdensity 1 (our reading of the preset) vs Entagma's
   500 / 50 moved the whole surface (dP max 0.132, duv 0.128) and therefore every Copernicus map. Substituting the
   template parms alone took duv to 0. Read the density off the reference, not the shelf preset.
2. **In-plane feather noise folds the petal.** Tangent/bitangent displacement on the high-frequency noise gave 126 folded
   faces of 2136; normal-only gave 0. Entagma's file uses tangent/bitangent 1.0 on the LARGE noise and the petal still
   matches — the fold count is a property of our amplitude guide, which is why `amp_u_guide_attr` is bypassed.
3. **A rig cycle is silent.** A narrow outline (tip 0.01) fused near-tip barbs into the shaft; `rig_doctor` reported
   `FoundCycle` and `bone_deform` returned None — the sim script then crashed on `saveToFile`. Check
   `rig_doctor.warnings()` before anything downstream.
4. **"Fix" nodes drift you away from the reference.** `petal_crease_relax` (attribblur ×2) and `petal_relax_normal`
   reduced creases on our petal but moved it 0.004–0.010 from Entagma's; with the right template parms they were not
   needed. Bypassed, kept for the record.
5. **The hand-shaped curve has no numbers.** Transcript 12:13 "bring the end level down" — only the asset gives
   f96 = 0.8565 with slope 0.0442. Any other value is a guess; label it.

## Loop + Vellum
6. **H21 Vellum Solver SOP emits once by default.** Its internal `sources/defaultsource` has `activate = $SF==1`; the
   first sim produced 0 points on every frame. Entagma's way: leave the HDA locked and add a Vellum Source DOP in the
   editable `dopnet1/forces` subnet (emit each frame). Unlocking the HDA to edit the default source works but makes the
   node un-upgradeable; the final build is relocked.
7. **Cloth stiffness has an exponent field.** "bend 100" with exponent −1 is 10; Entagma's 1.0 × 10^2 is 100. Compare
   the evaluated value, not the slider.
8. **Emitted petals need `v`.** A `pointvelocity` (inc 2) before the loop; without it the first-step drift is missing
   (|v| mean 0.058 → 0.0012 per step at timescale 0.5). Withdrawn as "the first cause": the v052 variant fixed v,
   cloth, friction, source and collider together and only the combined effect was measured
   (f133 mean 0.050 → 0.000165).
9. **Carve on the oriented curve, endcaps 2.** The collider's N/up travel through the carve into the sweep; endcap
   type changes the point count (362/368 vs 328/322 before the fix) and the bbox top (1.335 vs 1.309).
10. **The sparse flower was a missing node, not lighting.** Tutorial 18:57: blast `anim` and merge with the solver
    output. Found after two rounds of material and light tuning.
11. **Cross-time intersections are the technique.** 5 cached copies at +44 frames overlap where a falling petal meets
    the next bloom; the reference network has the same seam (251–898 points visible vs ours 139–193). Visibility is a
    ray-cast question (eye → point, occluded or not), never a raw count.
12. **A `.geometry()` on anything downstream of a solver is a sim cook.** One diagnostic cooked the reference solver in
    memory to f100 against the rules. Guard reads with an allowlist that rejects solver / DOP / sim-cache ancestry
    before cooking (benchmark `scripts/geo_guard.py`, self-tested both directions).

## Copernicus maps + material
13. **A bypass flag is not a parm.** `invert6` is bypassed in Entagma's copnet; a parm dump misses it and the sss map
    comes out inverted (r = −0.96). Diff flags as well as values.
14. **Rasterize Geometry attribute count.** `rasterizegeo2` must carry 2 attributes (cost + intrinsic:alpha).
15. **Signature is the biggest shader error.** roughness / opacity / sss `mtlximage` and their remaps are `float`;
    color3 there took the head error from 7.5 to 12.2 (/255). Read `signature` on every image/remap node.
16. **Apprentice caps Copernicus output** at 1920×1080 → 1024², Entagma 4096². Veins at 1024² are coarser; a
    shader-space vein (`st.x × 90 → 1 − |sin| ^ 4 × 0.35`) was the earlier AI route because point Cd (775/petal)
    aliased 65 stripes away.
17. **Entagma's JPGs are an H20.5 export no H21 OCIO transform reproduces.** Raw buffers identical (max 0); the JPG
    differs (Pearson 0.979 on diffuse, head mean R −5.5 / G +3.4). A control that swapped only the diffuse file
    closed the head gap (4.42 → 2.12). Document; never grade to match.

## Solaris, camera, render
18. **Prove the camera from the stage, not the node.** USD focal 0.5 / aperture 0.20955 are the node's 50 / 20.955
    × 0.01; only the ratio matters. Read `/Render/rendersettings.camera` to know which camera renders.
19. **Frame by projection.** Project the SUBJECT points (head only; the falling petals pulled the head small) through
    focal/aperture, binary-search the distance to an 8 % margin, then re-check margins on several loop frames —
    a pass on f1 says nothing about f34.
20. **Aim at the flower, not the bbox centre** (sim bbox centre x = 2.35 while the flower sat at x = 0).
21. **Empty selections give NaN transforms.** A stale file SOP in the live session made the camera NaN; reload the
    file SOP after a cache is written and measure in hython.
22. **Karma PNG keeps the dome as alpha 0** → viewers show white. Composite over black to inspect.
23. `karmarendersettings` with `res_mode = autoheight` locks `resolutiony` (PermissionError) — set `resolutionx`.
24. LOP lights (`light::2.0`) use `xn__inputs<name>_…` parms; `spotlightenable` must be 1 or the cone is not
    authored. The Karma API toggles (`KarmaLightAPI_*`) grow their spare parms through callbacks.
25. **Linear vs sRGB.** A pale flower was colour management (ramp authored as if sRGB) plus an over-strong warm
    backlight — not geometry. Render an emission-only Cd pass and solo lights before relighting.
26. **Diagnose dark patches three ways**; none proves the others: rest folds (face normal vs up on the undeformed
    mesh), deformed creases (adjacent normals dot < −0.3 at several frames), shading (unlit Cd + solo lights).

## Layout + files
27. **Top-down, boxed, measured.** 0 upward/level wires, 0 node overlaps, 0 box overlaps across all networks; audit
    VOPs by their DRAWN footprint (header 0.45 above, body `size().y` below, label 2.9 wide) — a generic tile check
    reports 7 false overlaps in the material net.
28. **A node added later sits outside every box.** `petal_point_velocity` landed on top of `petal_out`; the fix
    moved the column 0.8 down (1.4 made `loop_end` lower than its consumer and created an upward wire).
29. **Positions-only layout versions must prove zero semantics**: sem diff 0 lines, flags equal, stash digest equal,
    reopen clean — then the reviewed media stay valid without a re-render.
30. **Never save the live session.** Export with `saveItemsToFile` to `.cpio`, sim/cook/render in hython on that;
    `hipFile.save` in hython only to a NEW name after `assert not os.path.exists(path)`.
31. **Hash what you hand over.** Every delivered file in a MANIFEST (sha256); re-check old manifests after each step
    — the only thing that ever changed was the report being appended to.
