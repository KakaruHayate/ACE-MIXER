# Agent install prompt

Copy everything between the markers into an agent that can run local commands
on this machine.

---8<--- copy from here ---8<---

Set up **ACE Mixer** on this machine and then run one mix.

1. Detect the platform first (`uname -m` on macOS). ACE Studio runs on Windows
   and macOS only; on Linux, stop and say so. Intel Macs have no prebuilt
   binary (the bundled numpy is arm64-only) — use the source install.

2. Get the binary — no Python is needed for this path:

   - Windows: `ace-mixer.exe` from
     <https://github.com/KakaruHayate/ACE-MIXER/releases/latest>
   - macOS (Apple Silicon): `ace-mixer-macos` from the same release, then `chmod +x`
     (if a browser download makes macOS refuse to run it:
     `xattr -d com.apple.quarantine ./ace-mixer-macos`)

   Only if the release asset is unavailable, build from source:

   ```bash
   git clone https://github.com/KakaruHayate/ACE-MIXER
   # mainland-China mirror (a first 502 means "still caching", retry):
   # git clone https://gitclone.com/github.com/KakaruHayate/ACE-MIXER.git
   cd ACE-MIXER
   # needs Python 3.10+ and uv
   uv venv && uv pip install -e .
   ```

   Then every `ace-mixer` below becomes `uv run ace-mixer`.

3. Install the skill. The binary is only the tool; the workflow lives in
   `skill/ace-v27-style-transfer`. Either copy that folder out of the
   checkout, or download `ace-mixer-skill.zip` from the release and unzip it.
   Put the folder in your skills directory, keeping its name:
   - Codex: `$CODEX_HOME/skills` (default `~/.codex/skills`)
   - Claude Code: `~/.claude/skills`

   Confirm `<skills>/ace-v27-style-transfer/SKILL.md` exists. If your harness
   has no skills directory, keep the folder and read `SKILL.md` before running
   anything.

4. Get the LibreSVIP CLI. The GUI build has no usable CLI, so download the CLI
   asset from <https://github.com/SoulMelody/LibreSVIP/releases/latest> —
   `LibreSVIP-CLI-<version>.win-amd64.zip`, `.macos-arm64.tar.gz` or
   `.macos-x86_64.tar.gz` — and extract it. Remember the full path to
   `libresvip-cli.exe` / `libresvip-cli`.

5. Verify the chain **before** touching any project:

   ```bash
   ace-mixer doctor --libresvip "<path to libresvip-cli>"
   ```

   `doctor` reports three lines: `acestudio-cli`, `libresvip-cli`, and at
   least one Verse 2.7 track. Do not continue if any line says FAIL — report
   that line and stop.

6. Ask me for the folder holding the project and its dry render, and for the
   mix ratio (0 = keep the ACE voice's own expression, 1 = only the source's
   shape). If I do not give a ratio, use 0.5.

7. Run a dry pass first, show me the per-parameter summary, and only then
   write:

   ```bash
   ace-mixer run --dir "<folder>" --ratio <w> --dry-run
   ace-mixer run --dir "<folder>" --ratio <w>
   ```

Rules:

- Never modify the voice library, never create or delete blends. The tool only
  writes the clip's `user` layer.
- If the folder contains more than one project or more than one audio file,
  stop and ask me which pair to use rather than guessing. Naming the pair with
  the same stem (`song.ustx` + `song.wav`) is how the tool picks one.
- If ACE is not running, ask me to start it; do not try to launch the GUI.
- If `doctor` reports no Verse 2.7 track, ask me to load a Verse 2.7 voice and
  import notes first. Do not substitute another model generation.
- After writing, tell me to render in ACE Studio; further curve edits are mine
  to make in the UI.

---8<--- copy to here ---8<---
