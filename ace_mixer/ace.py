"""Thin wrapper around acestudio-cli.

Everything that talks to ACE Studio lives here so the rest of the package can
be tested without the app running.
"""

from __future__ import annotations

import json
import os
import subprocess

DEFAULT_CLI = r"C:\Program Files\ACE Studio\acestudio-cli.exe"
PARAMS = ("air", "tension", "falsetto", "energy")
V27_MODEL = "Verse 2.7"


class AceError(RuntimeError):
    pass


def resolve_cli(explicit: str | None = None) -> str:
    for candidate in (explicit, os.environ.get("ACESTUDIO_CLI"), DEFAULT_CLI):
        if candidate and os.path.exists(candidate):
            return candidate
    raise AceError("acestudio-cli not found. Pass --cli or set ACESTUDIO_CLI.")


def run(cli: str, args: list[str], stdin_text: str | None = None) -> str:
    payload = None if stdin_text is None else stdin_text.encode("utf-8")
    proc = subprocess.run([cli, *args], input=payload, capture_output=True)
    if proc.returncode != 0:
        raise AceError(
            "acestudio-cli %s failed:\n%s\n%s"
            % (
                " ".join(args[:2]),
                proc.stdout.decode("utf-8-sig", "replace").strip(),
                proc.stderr.decode("utf-8-sig", "replace").strip(),
            )
        )
    return proc.stdout.decode("utf-8-sig", "replace")


def run_json(cli: str, args: list[str]) -> dict:
    return json.loads(run(cli, [*args, "--json"]))


def list_tracks(cli: str) -> list[dict]:
    return run_json(cli, ["track", "list"]).get("tracks", [])


def list_clips(cli: str, track_uuid: str) -> list[dict]:
    return run_json(cli, ["clip", "list", "--track-uuid", track_uuid]).get("clips", [])


def sound_source(cli: str, track_uuid: str) -> dict:
    return run_json(cli, ["sound-source", "get", "--track-uuid", track_uuid])


def model_name(cli: str, track_uuid: str) -> str | None:
    try:
        return (sound_source(cli, track_uuid).get("model") or {}).get("name")
    except AceError:
        return None


def find_v27_clip(cli: str, track_uuid: str | None = None) -> tuple[dict, dict]:
    """Return (track, clip) for a Verse 2.7 track that holds a sung clip."""
    tracks = list_tracks(cli)
    if track_uuid:
        tracks = [t for t in tracks if t.get("trackUuid") == track_uuid]
        if not tracks:
            raise AceError("no track with uuid %s" % track_uuid)

    for track in tracks:
        if model_name(cli, track["trackUuid"]) != V27_MODEL:
            continue
        for clip in list_clips(cli, track["trackUuid"]):
            if clip.get("clipType") == "sing" and clip.get("noteCount", 0) > 0:
                return track, clip
    raise AceError(
        "no Verse 2.7 track with a non-empty sing clip was found. "
        "Load a Verse 2.7 voice on a track and import notes first."
    )


def import_ufdata(cli: str, path: str, track_uuid: str, pos: str = "0t") -> dict:
    return run_json(
        cli, ["import", "file", "--path", path, "--track-uuid", track_uuid, "--pos", pos]
    )


def read_param(cli: str, clip_uuid: str, param: str) -> tuple[list[float | None], float, float]:
    data = run_json(cli, ["vocalparam", "read", "--clip-uuid", clip_uuid, "--param", param])
    points = None
    for layer in data.get("layers", []):
        if layer.get("layer") == "baseline":
            points = layer.get("points")
            break
    if points is None:
        points = (data.get("effective") or {}).get("points")
    if points is None:
        raise AceError("no baseline/effective curve for %s" % param)
    rng = data.get("valueRange") or {}
    return points, float(rng.get("min", 0.0)), float(rng.get("max", 1.0))


def write_param(
    cli: str,
    clip_uuid: str,
    param: str,
    values: list[float | None],
    layer: str = "user",
    chunk: int = 38400,
) -> None:
    total = len(values)
    start = 0
    while start < total:
        end = min(start + chunk, total)
        payload = json.dumps([None if v is None else round(float(v), 5) for v in values[start:end]])
        run(
            cli,
            [
                "vocalparam",
                "write",
                "--clip-uuid",
                clip_uuid,
                "--param",
                param,
                "--layer",
                layer,
                "--pos-begin",
                str(start),
                "--points",
                "@-",
            ],
            payload,
        )
        start = end


def export_audio(cli: str, path: str, start_tick: int, end_tick: int) -> None:
    run(
        cli,
        [
            "export",
            "audio",
            "--path",
            path,
            "--from",
            "%dt" % start_tick,
            "--to",
            "%dt" % end_tick,
            "--sample-rate",
            "44100",
            "--bit-depth",
            "32",
            "--channels",
            "1",
            "--without-effects",
            "true",
            "--wait",
        ],
    )
