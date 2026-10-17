# Agent install prompt

Copy everything between the markers into an agent that can run local commands
on this machine.

---8<--- copy from here ---8<---

Set up **ACE Mixer** on this machine and then run one mix.

1. Check what already exists before installing anything:
   - `acestudio-cli.exe` (search `C:\Program Files\ACE Studio\`, or wherever
     ACE Studio is installed)
   - a `libresvip-cli.exe` build (the GUI build has no usable CLI)
   - Python 3.10+ with `uv`, or a prebuilt `ace-mixer.exe`

2. Install the tool. Prefer the prebuilt exe; otherwise clone and install:

   ```bash
   # prebuilt, no Python needed
   # https://github.com/KakaruHayate/ACE-MIXER/releases/latest

   git clone https://github.com/KakaruHayate/ACE-MIXER
   # mainland-China mirror (a first 502 means "still caching", retry):
   # git clone https://gitclone.com/github.com/KakaruHayate/ACE-MIXER.git
   cd ACE-MIXER
   uv venv && uv pip install -e .
   ```

3. Verify the chain **before** touching any project:

   ```bash
   ace-mixer doctor --cli "<path to acestudio-cli.exe>"
   ```

   `doctor` must report a reachable ACE Studio, a `libresvip-cli`, and at
   least one Verse 2.7 track. Do not continue if any line says FAIL — report
   the failing line instead.

4. Ask me for the folder holding the project and its dry render, and for the
   mix ratio (0 = keep the ACE voice's own expression, 1 = only the source's
   shape). If I do not give a ratio, use 0.5.

5. Run a dry pass first, show me the per-parameter summary, and only then
   write:

   ```bash
   ace-mixer run --dir "<folder>" --ratio <w> --dry-run
   ace-mixer run --dir "<folder>" --ratio <w>
   ```

Rules:

- Never modify the voice library, never create or delete blends. The tool only
  writes the clip's `user` layer.
- If the folder contains more than one project or more than one audio file,
  stop and ask me which pair to use rather than guessing.
- If ACE is not running, ask me to start it; do not try to launch the GUI.
- If `doctor` reports no Verse 2.7 track, ask me to load a Verse 2.7 voice and
  import notes first. Do not substitute another model generation.
- After writing, tell me to render in ACE Studio; further curve edits are mine
  to make in the UI.

---8<--- copy to here ---8<---
