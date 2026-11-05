# Endless Blossom — the recipe, stage by stage (as built in EB_full_v052bL3, Houdini 21.0.671)

Tutorial timestamps are Entagma part 1 (<https://www.youtube.com/watch?v=h9XpRaTsKI4>, 24:36) and the shading
episode (<https://www.youtube.com/watch?v=CT27JuZlxOw>). "ASSET" = value read from Entagma's project file at build
time, not typed. Node names are the ones the builder creates.

## 1. Petal (0:30–3:24) — `EB_candidate`, box PETAL

| node | type | values |
|---|---|---|
| `petal_shape_curves` | curve::2.0 (stash) | 3 open Bézier curves, order 4: shaft (0,0,0)→(0,0,−1) and two outline curves ±x; petal lies along −Z, tip at z = −1. Ours (AI-drawn). |
| `ASSET_entagma_curve1_shape` / `curve2_barbs` | file | Entagma's outline + barb guide (ASSET, optional). `missingframe = No Geometry` |
| `INPUT_CURVES_shape_src` / `_barb_src` | switch | 0 = ours, 1 = Entagma |
| `feathershapeorg1` → `feather_template` | feathershapeorg, feathertemplatefromshape | rachis width 0.005/0.005, shapebarbstart 0, **barbdensity 500, shaftdensity 50** (ASSET; our first guess 100/1 moved every UV) |
| `feather_resample` | featherresample | shaft 30 segs, barbs 12 (slider max shows 9; 12 is accepted) |
| `amp_u_guide_attr` | wrangle, **bypassed** | our amplitude-ramp guide; isolation showed it moves the petal away from Entagma's |
| `feather_noise_large` | feathernoise | amplitude 0.02 (tangent/bitangent 1.0 as ASSET) |
| `feather_noise_hf` | feathernoise | amplitude 0.03, normal only (tangent/bitangent 0), shaft freq 6.7, barb freq 10, amplitude ramp (0.31→0, 0.68→1, 0.88→1, 1→?) |
| `petal_surface` | feathersurface | shaft output none |
| `petal_normal` | normal | cusp 180 |

Measured: 775 points per petal; rest + deformed petal bit-identical to Entagma's chain once the template density
matched (surface dP 0.132 → 0).

## 2. KineFX rig + poses (3:24–8:49) — boxes KINEFX RIG, PETAL ANIMATION

| node | values |
|---|---|
| `feather_uncondense` (create shaft group) → `orient_along_curve` (Y up, 3×3 transform out) → `fuse_barbs_to_shaft` → `shaft_group_to_points` → `rig_doctor` | rig_doctor must report 0 warnings. A `FoundCycle` here (petal outline too narrow at the tip, barbs fused into the shaft) silently yields None geometry at bone_deform |
| `upper_shaft_group` (VEX) | `i@group_upper_shaft = shaft && -P.z > 0.55` — stand-in for Entagma's hand selection at 6:48 |
| `pose_A_closed` (rigpose, 4 rows) | root scale 0.5, shaft rx −12, barbs rx −11 and scale 0.85, upper 0 |
| `pose_B_open` | root tz 0.1, shaft rx −1.2, barbs rx −1.2, upper rx 7.5 |
| `pose_blend` (skeletonblend 3.0) | weight1 keys f1 = 0 → f96 = 0.8565 bezier, slope 0.0442, accel .6285/2.4208 (ASSET; 12:13 "shape the curve by hand" has no numbers) |
| `bone_capture_proximity` → `bone_deform` | |
| `petal_crease_relax`, `petal_relax_normal` | **bypassed** (our fold fix; not in Entagma's chain) |

## 3. Petal state + blossom loop (8:49–14:54) — box BLOSSOM LOOP

| node | values |
|---|---|
| `petal_state_groups` (VEX, spare `end_frame` 96) | `group_anim = @Frame < ef`, `group_volume_source = @Frame == ef` — runs at the loop's shifted time, so each petal reaches ef 4 frames after the previous |
| `color_anim_pink`, `color_volsrc_purple` | debug colours |
| `petal_point_velocity` | pointvelocity inc 2 (ASSET) — without `v` the emitted petals have no first-step drift |
| `petal_out` → `loop_begin` (fetch input) / `MD` (metadata) | |
| `petal_rotate_offset` | ry `137.5*detail("../MD","iteration",0)`, ty `0.005*iteration` (golden angle; +ty, the transcript says "a tiny bit up") |
| `petal_timeshift` | `$FF-detail("../MD","iteration",0)*4` |
| `loop_end` | 10 iterations, merge |
| `flower_axis_fix` | rx 90 (Entagma's curve needs −90; ours is base→head) |

Measured: exactly one petal in `volume_source` at f96, 100, 104 …; 7,750 points at f96.

## 4. Stem + Vellum (14:54–21:44) — box STEM + VELLUM SIM

| node | values |
|---|---|
| `stem_curve` (VEX polyline, ours) / `ASSET_entagma_curve3_stem` → `ASSET_curve3_base_to_head` (reverse) / `STEM_src` | Entagma's curve runs head→base; ours base→head |
| `stem_resample` → `stem_orient` (orient along curve, N/up) | |
| `copy_blossom_to_stem_tip` | target group `` `npoints("../stem_orient")-1` `` (last point) |
| `keep_volume_source_only` (blast !volume_source) → `vellum_configure_cloth` | cloth; **bend 1.0 × 10^2** (exp 2), mass 3, thickness 2, compress 1, stretch/bend groups (ASSET). Our first bend "100" with exp −1 was 10× softer |
| `VELLUM_GEO`, `VELLUM_CONSTRAINTS` nulls | the Vellum Source DOP points here |
| `stem_carve_shorter` → `stem_sweep` | carve **on the oriented curve** (N/up travel into the sweep), second U 0.966 (= Entagma's 0.034 from the head); sweep radius 0.05, **endcap 2** → 290 pts / 296 prims collider |
| `vellum_solver` (locked HDA) | timescale 0.5, constraint iters 300, wind on (1, 0, 0.2) × speed 3 (z ASSET), friction 0, selffriction 0. Inputs: EMPTY_IN, EMPTY_IN, stem_sweep |
| `vellum_solver/dopnet1/forces/vellumsource1` | Vellum Source DOP, emit each frame, geo = VELLUM_GEO, constraints = VELLUM_CONSTRAINTS, wired to SOURCE. **Keep the HDA locked** — unlocking it and editing `sources/defaultsource` was our first (wrong) route |
| `keep_anim_only` (blast !anim) + `merge_anim_and_sim` → `OUT_SIM_PREVIEW` | tutorial 18:57 — without this merge the flower is sparse (it is not a lighting problem) |

Measured: emitted petal P max 1.1e-06 vs Entagma at f96/f100; sim f89 max 1.3e-05, f133 mean 0.000165.
H21 trap: a fresh Vellum Solver SOP's default source has `activate = $SF==1` (emits once); the Entagma way is
the extra source in `forces`.

## 5. Endless loop (21:44–23:46) — box ENDLESS LOOP

`sim_cache_read` (file, `CACHE_DIR/sim.`padzero(4,$F)`.bgeo.sc`, missingframe No Geometry) → `loop2_begin` /
`MD2` → `loop2_timeshift` `$FF+44*iteration` → `loop2_end` 5 iterations → `LOOP_OUT`.
The cache must reach f225 (= 44 × 4 + 49). Cross-time intersections between copies are inherent to the technique.

## 6. Render prep — `EB_render_prep`

- `petals_in` (object merge LOOP_OUT) → `petal_single_shell_subdiv` (subdivide 2, keeps vertex N → faceVarying on
  stage) → `PETAL_SHELL_src` = 1 → `OUT_PETALS`. Input 0 of the switch is our two-shell look (`petal_side_normal`,
  ±0.0015 peak, `tag_inner/outer`, `petal_look_color` VEX, Cd authored sRGB → pow 2.2).
- `stem_in` → `stem_render_tube` (sweep r 0.035) → `stem_color` → `name_stem` → `OUT_STEM`.
- `backdrop_sphere` (r 30, 48 rows, ty 3) → `backdrop_face_in` (reverse) → `backdrop_gradient` VEX → `OUT_BACKDROP`.
- Entagma stem + fur (ASSET values): `ent_stem_curve_in` (object merge stem_resample) → reverse → orient → subdivide 2
  → `ent_stem_sweep` (r 0.1277, 16 cols, scale ramp, caps) → `OUT_STEM_ent`; `ent_fur_hairgen` (density 500k,
  length 0.01, 2 segs) → `ent_fur_guides` (bend, length randomise 0.24) → `OUT_FUR_ent` (602,974 prims).

## 7. Petal maps — `EB_textures` (Copernicus, shading episode)

SOP prep: `petal_rest_in` (object merge **petal_surface**, the rest petal) → `pointwrangle2` `v@P = v@uv*2-{1,1,0}`
→ `attribcopy1` uv from a 31×25 grid `uvtexture1` → `UV`; `remesh2` (target 0.015, hard points) → `group3`
(unshared edges, vein_end 24.7 %) → `pointwrangle4` `f@cost = 1` → `attribblur2` cost ×74 → `RIM`.
COP `EB_cop` 1024² (Apprentice refuses > 1920×1080; Entagma 4096²): `sopimport1/2` → `rasterizegeo1` (uv) /
`rasterizegeo2` (cost + intrinsic:alpha, **2 attributes**) → worley (0.003) → remap → invert → remap max 0.15;
fractal noise 0.05 (tiles 1×5) and 0.015 (rough 0.425, tiles 1×10) → remaps → blends (0.2 / 0.5 masks, mode 3) →
`fill1` with the inverted alpha → `blend4` (0.25) → `monotorgb1` ramp (0.573,0.146,0 → 1,0.325,0.1 → …) →
`hsv1` (hue 234.5, sat ×0.967 −0.049, val ×0.66 −0.145) → `OUT_diffuse`; `rough_sss` = blend4; `OUT_normal` =
height-to-normal of `blend1`; `OUT_opacity` = remap4 of blend6 (0.833–0.866 → 1–0); `OUT_sss` = invert6 of blend1
with **invert6 bypassed** (a flag in Entagma's file, found from the flipped sss map). Writers: diffuse with
colour conversion 1 (sRGB display / ACES SDR view), the others 2.
Measured: raw buffers identical to Entagma's network cooked in H21 (6 layers, max 0).

## 8. Solaris — `EB_solaris`

`import_petals` / `import_stem` / `import_backdrop` (sopimport, `/EB/geo/*`) → `petal_materials`
(materiallibrary, `/EB/materials/`, spare `tex_src` 1 = our maps) → `assign_mats` → `render_cam` (ours) →
`key_back_warm` (exp 4.5) / `fill_cool` / `rim_top` / `key_top_violet` / `env_navy` dome → `LOOK_RIG_src`.
Entagma branch (= 1): `ent_cam` (80 mm, f/0.35, focus 9.74, aperture 1:1) → 3 white sphere spots
(`spotlightenable` 1; cone 5.75° / 4.75° / 15.15°, intensities 2516 / 3087 / 15.3, radius 0.37–0.65) → prune
backdrop + our stem → `ent_import_stem` / `ent_import_fur` → `ent_assign_stem_fur`.
Material `petal_mtl_entagma` (mtlxstandard_surface, thin-walled, sheen 0.201 / 0.328): base = `ent_cc_base`
(diffuse, sat 1.5, gain 0.729); specular rough = remap(roughness 0→0.5 → 0.1→0.6); subsurface + transmission colour =
`ent_cc_sss_trans` (lift 0.08, sat 0.9); subsurface = remap(sss 0.25→1 → 0→0.75); sheen rough = remap(rough →
0.4–0.6); opacity = opacity map; normal = normalmap scale 0.035. **roughness / opacity / sss images and their
remaps are `float` signatures** — color3 there was the single biggest error (head diff 12.2 → 7.5).
`karma_settings` (camera `/EB/cam/ent_cam`, resolutionx 640, res_mode autoheight, spp 16, CPU) → `karma_rop`
(`RENDER_DIR/eb_karma.$F4.png`).
