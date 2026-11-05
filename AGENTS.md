# Plug Houdini Lab — notes for Codex (and any agent that reads AGENTS.md)

This repo is Plug's personal Houdini Lab: paste-able techniques (`techniques/`), reviewed scenes
(`hip/`), FX AI — Claude inside Houdini (`mcp/`) — and the skills Plug wrote for working here.
Notes are Thai; code, node names and comments are English. Reply in Thai; refer to yourself as
"Brother" in Thai sentences. Never overwrite Plug's `.hipnc` files; never touch his running Houdini
outside the `houdini-live` MCP (`.mcp.json`).

## Skills — one catalog, the same skills in every client

- **Canonical:** `.claude/skills/<name>/SKILL.md` (+ `references/`). Claude Code loads these as project
  skills when this folder is the working directory — that covers Dremzo Code's Claude engine and the FX AI
  chat inside Houdini (its cwd is this repo, `$FXAI_HOME`).
- **Codex reads `.agents/skills/<name>/`** — a GENERATED mirror of the canonical skill (same text, links
  pointed at the canonical `references/`, a `.mirror-source` naming the source file and its sha256). Do not
  edit a mirror; edit the canonical file and regenerate.
- **`skills/CATALOG.json`** — the generated index: every skill's name, description, path, each file's
  sha256 and a `content_id` (first 12 hex of a sha256 over the file list). The same `content_id` in
  Codex, Dremzo Code and FX AI means the same skill version. Dremzo Code's `get_skill` tool reads this
  project's skills by name for its other engines (GPT, Gemini, Antigravity) and reports the `content_id`.
- **After editing or adding a skill:** `python tools/skills_catalog.py` (stdlib only; hython works too),
  then commit `skills/CATALOG.json` and `.agents/skills/` with it. `python tools/skills_catalog.py --check`
  exits 1 while they differ — `tests/test_skills_catalog.py` runs it.
- `python tools/skills_catalog.py --probe <folder>` shows what a client opening that folder sees;
  `--fxai` shows what the installed FX AI sees (reads Houdini's `packages/fx_ai.json`, nothing else).

Current skills: see `skills/CATALOG.json` (names and one-line descriptions). Open a skill only when the
request is about it; a skill is knowledge — it hosts, publishes, spends or grants nothing.
