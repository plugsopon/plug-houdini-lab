# Endless Blossom → procedural flower

Category: Vellum & Solaris · Type: Object · Latest: v001 (2026-11-05)
All versions: v001 (older versions live in the shelf page)

## Notes

v001: ดอกไม้บานไม่รู้จบ (Entagma "Endless Blossom", Christopher Kopic 2025) สร้างใหม่ทั้งระบบผ่าน Houdini MCP ใน Dremzo Code (benchmark 2026-11-05) แล้ว export เป็น builder ที่ paste ได้
• ได้ 4 network ใต้ /obj: EB_candidate (กลีบจาก Feather tools → KineFX rig 2 ท่า → loop มุมทอง 137.5° + time offset 4 เฟรม/กลีบ → ก้าน → Vellum cloth ปล่อยกลีบทุก 4 เฟรม → endless loop 5 ชุด +44 เฟรม), EB_render_prep (shell สำหรับ render, ก้าน, backdrop, ก้าน+ขน recipe Entagma), EB_textures (Copernicus อบ 5 map จากกลีบท่า rest: diffuse / rough_sss / normal / opacity / sss 1024²), EB_solaris (MaterialX, กล้อง, ไฟ, Karma)
• ลำดับใช้งาน: paste build_endless_blossom.py ที่ /obj → save scene ของตัวเอง → hython eb_sim_cache.py (225 เฟรม ≈ 68 วิ) → hython eb_cook_textures.py (≈10 วิ) → hython eb_render_karma.py (480² 6spp ≈ 20 วิ/เฟรม) · ก่อนมี cache/map: LOOP_OUT กับกลีบใน Solaris ว่างเปล่าโดยตั้งใจ (missingframe = No Geometry) display flag อยู่ที่ copy_blossom_to_stem_tip จึงไม่ cook sim เอง
• INPUT_CURVES = "ai" (default) ใช้เส้นกลีบ/ก้านที่ AI วาด (แนบมาในสคริปต์) · "asset" ใช้เส้นจาก project ของ Entagma ที่ export เอง (eb_extract_asset_curves.py) → ทรงกลีบตรงกับคลิป media ทั้งหมด render จากโหมด asset

วัดผลแล้ว (verify_endless_blossom.py, hython 21.0.671, ไม่ sim ไม่ render): builder เทียบกับ scene ที่ผ่าน review (EB_full_v052bL3): node 205 ตัวเท่ากัน · parm ต่างเฉพาะ path ที่ย้ายมา CONFIG (12 ค่าเมื่อทั้งสองฝั่งอ่านเส้น Entagma, 18 ค่าเมื่อไม่มีไฟล์) · กลีบ petal_out f1/f96 (775 pt) dP 0.0 · blossom f96 (7,750 pt) dP 0.0 · Vellum geo 775 / constraint 4,320 เท่ากัน · collider 290/296 เท่ากัน · rig_doctor 0 warning · texture 5 แผ่นจาก builder sha256 ตรงกับชุดที่ review ทุกแผ่น (โหมด asset) · โหมด ai ไม่มีไฟล์ Entagma เลย: สร้างได้ 0 error, กลีบ 775 pt / blossom 7,750 pt
ผลของ scene ต้นฉบับจาก benchmark (ไม่ได้ render ใหม่): sim เทียบ cache ของครู f89 max 1.3e-5, f133 mean 0.000165 max 0.0116 · render f12 เทียบ scene ของครู ทั้งภาพ 2.23 หัวดอก 4.42 (mean abs/255) · loop seam f44→f1 5.24 (เฟรมติดกัน 4.21–5.89)
ทดสอบกับ H21.0.671 Apprentice · ยังไม่ได้ลองกับ 20.5 (Feather tools, Copernicus, Vellum Solver source default ต่างกันระหว่างเวอร์ชัน)

ที่มา (provenance) ตรงไปตรงมา: โครง node/wire ทั้งหมดสร้างเอง แต่ค่าหลายจุดอ่านมาจาก project file ของ Entagma (ASSET-DERIVED): เส้นกลีบ/ก้าน (ไม่แนบมา — export เองจากไฟล์ที่โหลดเอง), key ของ pose_blend (f96 = 0.8565), wind z 0.2, cloth stiffness/mass/thickness, ค่าใน COP, material, ไฟ 3 ดวง, กล้อง 80mm f/0.35 · Houdini ของครูเป็น 20.5 · ไม่มีไฟล์ .hiplc / texture / geometry ของครูในแพ็กนี้
ข้อจำกัดที่ยังอยู่ (ไม่ใช่ 100%): diffuse JPG ที่ครู export จาก H20.5 ทำซ้ำใน H21 ไม่ได้ (สีหัวดอกเรายังจางกว่า, พิสูจน์ด้วย control ที่สลับแค่ diffuse) · กลีบที่ตกทับกันข้ามชุดเวลาของ endless loop มองเห็นได้ (ไฟล์ครูก็มี) · curve ที่ปั้นมือที่ 12:13 เป็นค่าแทน · Apprentice: ลายน้ำ, COP ได้แค่ 1024², render ≤720 · โหมด ai ให้กลีบแคบกว่าของครู
media + scene ที่ review: hip/endless_blossom/ (README.md บอก hash ทุกไฟล์)

## Files

### build_endless_blossom.py — Endless Blossom builder (4 networks)

- Where: Python Shell · เปิด /obj
- Tested: Houdini 21.0.671 Apprentice · verify PASS (dP 0, maps bit-identical)

สร้าง EB_candidate / EB_render_prep / EB_textures / EB_solaris ครบทั้ง 205 node พร้อม wire, parm, ramp, keyframe, bypass, network box และ sticky note ตาม scene ที่ review ไม่แตะ node เดิมของพี่ ถ้า /obj/<PREFIX>_candidate มีอยู่แล้วจะหยุดทันที (เปลี่ยน PREFIX)

CONFIG: PREFIX, TARGET, SET_DISPLAY, INPUT_CURVES (ai/asset), ASSET_DIR, CACHE_DIR, TEX_DIR, TEACHER_TEX_DIR, RENDER_DIR — path ทุกตัวเป็น $HIP ไม่มี path เครื่องผู้เขียน · display flag ไป copy_blossom_to_stem_tip (ไม่ cook Vellum) · LOOP_OUT อ่าน cache จาก CACHE_DIR, material อ่าน map จาก TEX_DIR (ว่างจนกว่าจะรันสคริปต์ hython 2 ตัว) · สร้างโดย gen_builder.py จาก EB_full_v052bL3 ไม่ได้พิมพ์จากความจำ · ถ้ามี SKIPPED พิมพ์ออกมาแปลว่า parm นั้นไม่มีในเวอร์ชันที่ใช้ (20.5 ยังไม่ได้ลอง)

### eb_sim_cache.py — Vellum sim cache (hython)

- Where: hython (command line) · scene ที่ save แล้ว
- Tested: Houdini 21.0.671 · 225 เฟรม 68 วิ, 7,750 pt/เฟรม

cook EB_candidate/OUT_SIM_PREVIEW ทีละเฟรมใน process แยก แล้วเขียน sim.NNNN.bgeo.sc ลง CACHE_DIR ไม่ยอมเขียนทับโฟลเดอร์ที่มีเฟรมอยู่แล้ว

hython eb_sim_cache.py SCENE.hipnc [PREFIX] [FIRST LAST] [OUT_DIR] · กลีบเริ่มปล่อยที่ f96, endless loop ต้องการ cache ถึง f225 (+44×4) · ไม่ save scene

### eb_cook_textures.py — Bake 5 petal maps in Copernicus (hython)

- Where: hython (command line) · scene ที่ save แล้ว
- Tested: Houdini 21.0.671 · 5 แผ่น ≈ 10 วิ · sha256 ตรงกับชุด review

cook rop_image 5 ตัวใน EB_textures/EB_cop (diffuse, rough_sss, normal, opacity, sss) จากกลีบท่า rest ลง TEX_DIR ไม่ต้องมี sim cache

hython eb_cook_textures.py SCENE.hipnc [PREFIX] [OUT_DIR] · copnet 1024² เพราะ Apprentice ไม่ยอม save Copernicus เกิน 1920×1080 (ครูใช้ 4096²) · invert6 ถูก bypass ตามไฟล์ครู (flag ไม่ใช่ parm — หาเจอจาก sss map กลับด้าน)

### eb_render_karma.py — Karma CPU render (hython)

- Where: hython (command line) · scene ที่ save แล้ว
- Tested: Houdini 21.0.671 Apprentice · 480² 6spp 20 วิ, 720² 32spp 89 วิ

render เฟรมที่ระบุจาก EB_solaris/karma_rop ตั้ง resolution/spp ชั่วคราวใน process แยก ต้องมี cache + map ก่อน

hython eb_render_karma.py SCENE.hipnc [PREFIX] [FRAMES] [RES] [SPP] [OUT_DIR] · FRAMES เช่น 12 หรือ 1-44 · กล้อง Entagma เป็น 1:1 · ลายน้ำ Houdini มาจาก Apprentice

### eb_extract_asset_curves.py — Export the 3 Entagma input curves (hython, read-only)

- Where: hython (command line) · project file ของ Entagma ที่โหลดเอง
- Tested: Houdini 21.0.671 · Endless_Blossom_2025_Part-1.hiplc (sha256 7dd1a271…)

อ่าน /obj/geo1/curve1 (ทรงกลีบ) curve2 (barb guide) curve3 (ก้าน) จาก project file แล้ว save เป็น ASSET_entagma_curve1/2/3.bgeo สำหรับ INPUT_CURVES = "asset" ไม่แก้ไฟล์ต้นฉบับ

ดาวน์โหลด project file จากโพสต์ Endless Blossom บน entagma.com เอง — เส้นเหล่านี้เป็นของ Entagma ไม่ได้แนบมาใน shelf

### verify_endless_blossom.py — Headless check: builder vs reviewed scene (hython)

- Where: hython (command line)
- Tested: Houdini 21.0.671 · PASS 2026-11-05

โหลด scene ที่ review (cpio) บันทึก type/wire/parm ทุก node + geometry ที่เฟรมสำคัญ แล้ว clear scene รัน builder แล้วเทียบ: ต้องต่างเฉพาะ path ที่ย้ายมา CONFIG, dP 0, จำนวน point/constraint เท่ากัน, 0 error ทั้งแบบมีและไม่มีไฟล์ Entagma

hython verify_endless_blossom.py build_endless_blossom.py EB_full_v052bL3_layout.cpio WORK_DIR · save scene ใหม่ 1 ไฟล์ใน WORK_DIR ไว้ให้ eb_cook_textures.py ตรวจ map ต่อ ไม่ sim ไม่ render

### petal_state_groups.vfl — Petal state groups (anim / volume_source)

- Where: Attribute Wrangle · Points · spare parm end_frame = 96
- Tested: Houdini 21.0.671

ก่อน loop: กลีบที่ @Frame < end_frame อยู่ group anim, ตรงเฟรม end_frame พอดีอยู่ group volume_source ซึ่ง Vellum จะดูดไปปล่อย — เพราะ Time Shift ของ loop อยู่หลัง node นี้ แต่ละกลีบจึงถึง end_frame คนละเวลา (ห่างกัน 4 เฟรม)

ชื่อ group ของครูคือ vellumsrc — เป็นแค่ชื่อ · ค่าสำคัญ: end_frame ต้องเท่ากับเฟรมที่ pose_blend ถึงปลาย (96)

### upper_shaft_group.vfl — Upper-shaft joint group (stand-in for a hand selection)

- Where: Attribute Wrangle · Points · หลัง rig_doctor
- Tested: Houdini 21.0.671

ครูเลือกข้อต่อครึ่งบนของก้านกลีบด้วยมือที่ 6:48 เราใช้ -P.z > 0.55 บน group shaft แทน เพื่อให้ rigpose ท่า B หมุนปลายกลีบ (r3x 7.5°)

กลีบวางตามแกน -Z (โคน 0 → ปลาย -1) ถ้าเส้นกลีบยาวไม่เท่านี้ต้องปรับ 0.55

### stem_curve_ai.vfl — AI-drawn stem guide curve

- Where: Attribute Wrangle · Detail (ไม่ต่อ input)
- Tested: Houdini 21.0.671

polyline 7 จุดจาก (0,0,0) ขึ้นไป (0,3,0) แทนเส้นก้านที่ครูวาดมือ (15:34) ใช้เมื่อ INPUT_CURVES = "ai"; โหมด asset ใช้ curve3 ของ Entagma แทน (กลีบจะตกสั้นกว่าของครู ~10% ถ้าใช้เส้นนี้)

ก้านวิ่งโคน→หัว ส่วนเส้นของครูวิ่งหัว→โคน จึงมี reverse ให้ และ carve ตัด 3.4% ที่ปลายหัวแทน

### petal_look_color_two_sided.vfl — Two-sided petal colour (inner warm / outer violet)

- Where: Attribute Wrangle · Points · หลัง merge ของ shell 2 ชั้น (i@inner)
- Tested: Houdini 21.0.671

look ของ AI ก่อนใช้ material ของ Entagma (PETAL_SHELL_src = 0): ไล่สีจาก uv.y (0 โคน → 1 ปลาย) แยกหน้าใน/หน้านอก แล้ว pow 2.2 ให้เป็น linear — วัดแล้วว่า ~95% ของหน้ากลีบหันเข้าแกนดอก

สีที่เขียนเป็น sRGB แล้ว pow(2.2) — ถ้าไม่ทำ กลีบจะซีด (เคยวินิจฉัยผิดเป็นเรื่องไฟ) · เส้นใบย้ายไป shader (st.x*90 → 1-|sin| ^4 ×0.35) เพราะ point Cd ~775 จุด/กลีบ ละเอียดไม่พอสำหรับ 65 เส้น

### backdrop_gradient.vfl — Navy backdrop sphere gradient

- Where: Attribute Wrangle · Points · บน sphere ที่ reverse แล้ว
- Tested: Houdini 21.0.671

ไล่สี navy เข้มลงมาด้านซ้ายล่าง ใช้กับ rig ไฟของเรา (LOOK_RIG_src = 0) · rig ของ Entagma ไม่มี backdrop (prune ออก, dome 0)

Karma PNG เก็บ dome เป็น alpha 0 → viewer เห็นพื้นขาว ถ้าอยากเห็นพื้นในภาพต้องมี backdrop emissive หรือ composite ทับดำ
