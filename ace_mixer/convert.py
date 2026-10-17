"""Find the project/audio pair in a folder and turn the project into .ufdata."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import yaml

PROJECT_EXTS = {
    ".ace",
    ".acep",
    ".acet",
    ".aisp",
    ".ccs",
    ".ds",
    ".dspx",
    ".dv",
    ".sk",
    ".mtp",
    ".musicxml",
    ".mxl",
    ".nn",
    ".ppsf",
    ".ps_project",
    ".s5p",
    ".svip",
    ".svip3",
    ".svp",
    ".tlp",
    ".tlpx",
    ".tsmsln",
    ".tssln",
    ".ust",
    ".ustx",
    ".vfp",
    ".vog",
    ".vpr",
    ".vshp",
    ".vspx",
    ".vsq",
    ".vsqx",
    ".vvproj",
    ".vxf",
    ".xvsq",
    ".y77",
    ".xml",
}
AUDIO_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".aif", ".aiff", ".ogg"}

DEFAULT_LIBRESVIP = r"C:\Program Files\libresvip-cli\libresvip-cli.exe"


class ConvertError(RuntimeError):
    pass


def resolve_libresvip(explicit: str | None = None) -> str:
    for candidate in (explicit, os.environ.get("LIBRESVIP_CLI"), DEFAULT_LIBRESVIP):
        if candidate and os.path.exists(candidate):
            return candidate
    raise ConvertError("libresvip-cli not found. Pass --libresvip or set LIBRESVIP_CLI.")


def discover(directory: str) -> tuple[Path, Path]:
    """Return the project/audio pair inside ``directory``.

    Prefers a pair whose file stems match; otherwise requires exactly one
    project and one audio file so the choice is never ambiguous.
    """
    root = Path(directory)
    if not root.is_dir():
        raise ConvertError("not a directory: %s" % directory)
    files = [p for p in root.iterdir() if p.is_file()]
    projects = [p for p in files if p.suffix.lower() in PROJECT_EXTS]
    audios = [p for p in files if p.suffix.lower() in AUDIO_EXTS]
    if not projects:
        raise ConvertError("no project file found in %s" % directory)
    if not audios:
        raise ConvertError("no audio file found in %s" % directory)

    pairs = [
        (project, audio) for project in projects for audio in audios if project.stem == audio.stem
    ]
    if len(pairs) == 1:
        return pairs[0]
    if len(pairs) > 1:
        raise ConvertError(
            "ambiguous folder: %d project/audio pairs share a stem (%s). "
            "Keep one pair per folder, or pass one project explicitly."
            % (len(pairs), ", ".join(p.name for p, _ in pairs))
        )
    if len(projects) == 1 and len(audios) == 1:
        return projects[0], audios[0]

    raise ConvertError(
        "ambiguous folder: %d projects and %d audio files. Name the pair with "
        "matching stems (%s / %s)."
        % (
            len(projects),
            len(audios),
            ", ".join(p.name for p in projects[:3]),
            ", ".join(p.name for p in audios[:3]),
        )
    )


def strip_masked_curves(src: Path, dst: Path) -> list[str]:
    """Drop MaskedCurve expression declarations so older LibreSVIP loads the file."""
    with open(src, encoding="utf-8-sig") as f:
        doc = yaml.safe_load(f)
    expressions = doc.get("expressions") or {}
    removed = [
        key
        for key, value in expressions.items()
        if isinstance(value, dict) and value.get("type") == "MaskedCurve"
    ]
    for key in removed:
        del expressions[key]
    with open(dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
    return removed


def _run_libresvip(cli: str, src: Path, dst: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [cli, "proj", "convert", str(src), str(dst)],
        input=("\n" * 40).encode("utf-8"),
        capture_output=True,
    )
    text = (proc.stdout + proc.stderr).decode("utf-8-sig", "replace")
    ok = dst.exists() and dst.stat().st_size > 1024
    return ok, text


def to_ufdata(project: Path, workdir: Path | None = None, libresvip: str | None = None) -> Path:
    """Convert any supported project to .ufdata, retrying without masked curves."""
    cli = resolve_libresvip(libresvip)
    work = Path(workdir or tempfile.mkdtemp(prefix="ace-mixer-"))
    work.mkdir(parents=True, exist_ok=True)
    dst = work / (project.stem + ".ufdata")

    ok, text = _run_libresvip(cli, project, dst)
    if ok:
        return dst

    if "MaskedCurve" in text and project.suffix.lower() == ".ustx":
        fixed = work / (project.stem + ".nomask.ustx")
        removed = strip_masked_curves(project, fixed)
        ok, text2 = _run_libresvip(cli, fixed, dst)
        if ok:
            return dst
        text = text2 + "\n(also failed after removing: %s)" % ", ".join(removed)

    tail = "\n".join(line for line in text.splitlines() if line.strip())[-1500:]
    raise ConvertError("libresvip-cli could not convert %s\n%s" % (project.name, tail))
