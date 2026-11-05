# Endless Blossom — reviewed scene + media

The scene the shelf technique **Endless Blossom → procedural flower** was exported from, and the media rendered
from it. Built 2026-11-05 as a Houdini MCP benchmark (Dremzo Code driving Houdini 21.0.671 Apprentice through
the `houdini-live` MCP), reconstructing Entagma's *Endless Blossom* tutorial (Christopher Kopic, 2025:
<https://www.youtube.com/watch?v=h9XpRaTsKI4> part 1, <https://www.youtube.com/watch?v=CT27JuZlxOw> shading).
Technique notes are in Thai on the shelf page; this file is the provenance record.

## Files

| file | sha256 (16) | what |
|---|---|---|
| `EB_full_v052bL3_layout.hipnc` | `cb4ade3d5a2a2857` | the reviewed scene (final candidate v052b + layout-only pass L3), saved headless by hython, reopened and checked (cache sim_v052, 0 node errors, solver locked). **Its file paths still point at the author's machine** (`P:/Project/Dremzo/temp/endless-blossom/...`); the builder on the shelf replaces every one of them with `$HIP` CONFIG paths. |
| `media/EB_karma_final_v052b_f0012.png` | `5473e15ae22374c7` | final still, frame 12, 720², 32 spp, Karma CPU, 88.9 s |
| `media/EB_karma_loop44x3_v052b.mp4` | `cd122f1175126ec6` | the 44-frame loop played 3×, 360², 6 spp, 24 fps, 5.5 s (ffprobe: 132 frames) |
| `media/karma_v052b_contact_every4.png` | `1738d00b6b8d5638` | every 4th loop frame |
| `media/karma_v052b_loop_boundary_f44_f1_f2.png` | `f15b38f9a96468ad` | loop seam f44 → f1 → f2 (mean abs diff 5.24/255; consecutive frames 4.21–5.89) |
| `media/final_v052b_vs_TEACHERrender_f12.png` | `ce3b74dbc25e30d5` | left: Entagma's own scene rendered headless, read-only, 6 spp · right: ours. whole-frame 2.23, head 4.42 (mean abs/255) |
| `media/01_candidate_overview.png`, `02_pv_blossom_column_detail.png` | `7eb4952f768d6821`, `3c6368f571a3014e` | HEADLESS SOURCE DIAGRAMS of the candidate graph drawn from the saved node data (SVG → PNG). Not native Houdini screenshots. |
| `media/preview_480.jpg` | `4ee123542896aa52` | 480² JPEG of the still; embedded in the shelf page as the card `previewImage` (data URI) |
| `media/card_endless_blossom.png`, `media/page_endless_blossom_selected.png` | `dde67804d2f3e8a2`, `0fa12304c28db24e` | screenshots of the built page served locally: the card and the selected technique with its preview (480×480 decoded). Other cards' `/_blob/` images do not load there because they live on the artifact host |
| `tex_v051/{diffuse,rough_sss,normal,opacity,sss}.png` | `30682be124b3a872`, `5064060e79f83ced`, `96224d0771852196`, `066d0bfd091bbb3c`, `d897e6462bc2cfd3` | the five reviewed Copernicus maps (1024², our network, Entagma curves). `verify_endless_blossom.py` with an ASSET_DIR re-bakes them from the builder and they come out byte-identical. Also usable as ready-made maps (`TEX_DIR`) if you do not want to cook. |

The "Houdini" mark in every frame is the Apprentice watermark.

## What is ours and what was read from Entagma's project

- **Ours:** every node, wire and network box (built one MCP call at a time, 247 calls on record), the AI-drawn
  petal outline / barb / stem curves (`INPUT_CURVES = "ai"`), the two-sided AI look, the AI light rig, every
  script on the shelf, the layout, the verification.
- **Read from Entagma's project file (ASSET-DERIVED values, not typed):** the three input curves when
  `INPUT_CURVES = "asset"` (you export them yourself with `eb_extract_asset_curves.py`; they are **not** in this
  repo), `pose_blend` weight keys (f1 = 0 → f96 = 0.8565 with its tangents), wind z 0.2, the cloth recipe
  (bend 1e2, mass/thickness/compress groups), the Vellum source placement (locked solver + Vellum Source DOP in
  `forces`), the collider carve/endcap, the whole Copernicus texture recipe, the MaterialX petal material,
  the Entagma stem + fur recipe, three spot lights and the 80 mm f/0.35 camera.
- **Not in this repo:** Entagma's `.hiplc` files, textures, `Scene.usdc`, petal geometry, the three input curves.
  Redistribution rights for those were never stated on the download page, so none of their files is bundled; the
  links above are the source. We make no broader rights claim than that.
- **Derived from Entagma inputs (labelled, not their files):** the reviewed media and the five `tex_v051` maps
  were produced by OUR network with `INPUT_CURVES = "asset"`, i.e. from Entagma's petal/stem curves. They are
  outputs, not copies of Entagma files — but the petal shape you see in them comes from those curves.

## Archival HIP content audit (read-only, 2026-11-05)

`hip_content_audit.py` loaded `EB_full_v052bL3_layout.hipnc` in hython, read every Data parm, lock flag, HDA
definition and file-path parm, cooked no SOP output and saved nothing:

| check | result |
|---|---|
| geometry embedded in the file (stash / Data parms) | 1: `EB_candidate/petal_shape_curves.savedstashgeo`, 12 pts / 3 Bézier — **our AI-drawn curves**; point positions match none of Entagma's curve1/2/3 |
| hard- or soft-locked SOPs (frozen geometry) | none |
| embedded HDA definitions | none |
| Entagma inputs | referenced by **path only** (`ASSET_entagma_curve1/2/3.bgeo`, and the optional teacher-texture branch of the five `ent_tex_*` expressions); not stored |
| raw text | the string `Endless_Blossom_2025` occurs 3× (node comments naming the source file / a Vellum checkpoint path label) — metadata, no data |

The paths in the file are the author's machine paths; opening it elsewhere gives empty asset/cache/texture reads
(the shelf builder is the portable way).

## Measured (hython 21.0.671, from the benchmark record)

| check | result |
|---|---|
| rest + deformed petal vs Entagma's chain, same inputs | bit-identical (f48 max 1.39e-05) |
| the 5 Copernicus maps vs Entagma's network cooked in H21 | raw buffers identical (max 0) |
| Vellum sim vs Entagma's cached frames | f89 max 1.3e-05 · f133 mean 0.000165, max 0.0116 (no teacher frames after f133) |
| render f12 vs Entagma's scene (6 spp) | whole 2.23 · head 4.42 (mean abs/255) |
| diffuse control (only the diffuse JPG swapped for Entagma's H20.5 export) | whole 1.33 · head 2.12 → the head-tone gap is the historical JPG export, not shader/geometry/lights |
| builder vs this scene (`verify_endless_blossom.py`) | 205 nodes, 18 CONFIG path diffs only, petal/blossom dP 0.0, maps sha256 identical |

## Known limits (not waived)

- Entagma's H20.5 diffuse JPG cannot be reproduced by any H21 OCIO transform; no grading was applied.
- Cross-time petal intersections of the endless loop are visible (Entagma's own file has them too).
- The hand-shaped pose curve at 12:13 is a substitution (keys from the asset, no spoken numbers).
- Bend rest-angle float residual up to 0.028° on near-flat dihedrals; cause is a hypothesis.
- Houdini 20.5 (Framestore) untested: Vellum Solver source default, Feather Resample slider and Copernicus differ.
- Apprentice: watermark, Copernicus output capped (1024² used), renders kept ≤ 720.
- Process record of the benchmark: one web-fetch subagent was used against the "no new agents" rule, and one
  diagnostic cooked the reference solver in memory against the "no teacher cook" rule. Both are recorded in the
  benchmark index (`HB_INDEX_v052b.md`, kept with the benchmark, not here) and were not waived.
