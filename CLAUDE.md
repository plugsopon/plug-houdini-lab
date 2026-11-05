# Houdini Snippet Shelf — notes for Claude

Plug's personal Houdini techniques (not Dremzo). Plug is an FX TD; reply in Thai, refer to
yourself as "Brother" in Thai sentences. He pastes scripts at Framestore on Houdini 20.5; home
tests run on 21.0.671 Apprentice (hython path in the houdini-hython-verify skill).

Skills in `.claude/skills/` — use them:
- `houdini-builder-script` — writing any paste-able Python that creates nodes
- `houdini-hython-verify` — checking scripts / .hipnc files headlessly before handing them over
- `houdini-shelf-publish` — adding a technique or version to the shelf (artifact + folder + git)
- `houdini-flower-endless-blossom` — building a procedural flower (petal → rig → loop → Vellum → COP maps →
  Karma) from the Endless Blossom technique on the shelf: which builder to paste, which hython script runs
  what, and the measured traps

These skills are ONE catalog for every client: `skills/CATALOG.json` (name, description, files' sha256,
`content_id`) and the Codex mirror `.agents/skills/` are generated from `.claude/skills/` by
`python tools/skills_catalog.py` — run it after editing a skill and commit all three together
(`--check` fails while they differ; `tests/test_skills_catalog.py`). Never edit a mirror. Dremzo Code's
`get_skill` reads this project's skills by name for its other engines; FX AI sees them as project skills.

The Artifact tool IS available in the FX AI chat inside Houdini (brother_chat sets
`CLAUDE_CODE_ENTRYPOINT=claude-desktop`, 2026-10-03). Publishing the shelf page is part of every
shelf update — never stop at folder + git. If `Artifact` is genuinely missing, say so to Plug
plainly and remind him the artifact is behind; don't leave it for him to discover.

Live Houdini (`houdini-live` MCP, see mcp/README.md): only reaches a session where Plug ran
`brother_link.start()` himself. If several are open, ask which one (or match the hip name he
mentions) and `houdini_use_session` it. Debug by LOOKING first (scene → problems → node →
geometry/compare) and report findings. Change his scene only when he asks, with a
`Brother: <what>` label, one change per call, and say what to Ctrl+Z (or `houdini_undo`).
Never save his hip through the MCP.

Layout: see README.md. Never overwrite Plug's .hipnc files. Outside the MCP, never touch his
running Houdini (hython is a separate process).
