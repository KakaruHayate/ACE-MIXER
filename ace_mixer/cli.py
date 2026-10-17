"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, ace, convert, curves, mix


def _doctor(args: argparse.Namespace) -> int:
    rows: list[tuple[str, str, bool]] = []

    try:
        cli = ace.resolve_cli(args.cli)
        rows.append(("acestudio-cli", cli, True))
    except ace.AceError as exc:
        cli = ""
        rows.append(("acestudio-cli", str(exc), False))

    try:
        lv = convert.resolve_libresvip(args.libresvip)
        rows.append(("libresvip-cli", lv, True))
    except convert.ConvertError as exc:
        rows.append(("libresvip-cli", str(exc), False))

    if cli:
        try:
            tracks = ace.list_tracks(cli)
            v27 = [
                t["trackName"]
                for t in tracks
                if ace.model_name(cli, t["trackUuid"]) == ace.V27_MODEL
            ]
            rows.append(("Verse 2.7 tracks", ", ".join(v27) or "(none)", bool(v27)))
        except ace.AceError as exc:
            rows.append(("ACE connection", str(exc), False))

    ok = all(flag for _, _, flag in rows)
    for name, detail, flag in rows:
        print("%s %-18s %s" % ("OK  " if flag else "FAIL", name, detail))
    return 0 if ok else 1


def _resolve_clip(args: argparse.Namespace, cli: str) -> tuple[dict, dict]:
    if args.clip_uuid:
        for track in ace.list_tracks(cli):
            for clip in ace.list_clips(cli, track["trackUuid"]):
                if clip.get("clipUuid") == args.clip_uuid:
                    return track, clip
        raise ace.AceError("no clip with uuid %s" % args.clip_uuid)
    return ace.find_v27_clip(cli, args.track_uuid)


def _run(args: argparse.Namespace) -> int:
    cli = ace.resolve_cli(args.cli)
    project, audio = convert.discover(args.dir)
    print("project : %s" % project.name)
    print("audio   : %s" % audio.name)

    workdir = Path(args.workdir) if args.workdir else None
    ufdata = convert.to_ufdata(project, workdir, args.libresvip)
    print("ufdata  : %s" % ufdata)

    track, clip = _resolve_clip(args, cli)
    tick_len = int(clip["clipEnd"]) - int(clip["clipBegin"])
    print(
        "target  : %s / %s (%d notes, %d ticks)"
        % (track["trackName"], clip["clipName"], clip.get("noteCount", 0), tick_len)
    )

    if args.import_notes:
        ace.import_ufdata(cli, str(ufdata), track["trackUuid"], "%dt" % clip["clipBegin"])
        track, clip = _resolve_clip(args, cli)
        tick_len = int(clip["clipEnd"]) - int(clip["clipBegin"])
        print("imported notes; clip is now %d ticks" % tick_len)

    if tick_len <= 0:
        raise ace.AceError("clip has no length")

    params = [p.strip() for p in args.params.split(",") if p.strip()]
    unknown = [p for p in params if p not in ace.PARAMS]
    if unknown:
        raise SystemExit("unknown parameter(s): %s" % ", ".join(unknown))

    print("extracting %s from the dry render ..." % ", ".join(params))
    extracted = curves.extract(str(audio), tick_len, f0_ufdata=str(ufdata), raw=args.raw)

    report: dict[str, dict] = {}
    for param in params:
        base, lo, hi = ace.read_param(cli, clip["clipUuid"], param)
        mixed, stats = mix.blend(base, extracted[param], args.ratio, args.mode, (lo, hi))
        report[param] = stats
        print(
            "  %-9s voiced %6d/%6d  result %.3f..%.3f mean %.3f%s"
            % (
                param,
                stats["voiced"],
                stats["ticks"],
                stats.get("min", float("nan")),
                stats.get("max", float("nan")),
                stats.get("mean", float("nan")),
                "" if stats.get("baseline") else "  (no baseline: wrote external)",
            )
        )
        if not args.dry_run:
            ace.write_param(cli, clip["clipUuid"], param, mixed, args.layer, args.chunk)

    if args.json:
        print(
            json.dumps(
                {
                    "clip": clip["clipUuid"],
                    "ratio": args.ratio,
                    "mode": args.mode,
                    "params": report,
                },
                indent=2,
            )
        )
    if args.dry_run:
        print("dry run: nothing written")
    else:
        print("done. Render in ACE Studio to hear it; further edits are yours in the UI.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ace-mixer", description=__doc__)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cli", help="acestudio-cli path (or ACESTUDIO_CLI)")
    common.add_argument("--libresvip", help="libresvip-cli path (or LIBRESVIP_CLI)")

    doc = sub.add_parser("doctor", parents=[common], help="check the tool chain")
    doc.set_defaults(func=_doctor)

    run = sub.add_parser("run", parents=[common], help="mix a folder's style into a V2.7 clip")
    run.add_argument("--dir", required=True, help="folder holding the project and its dry render")
    run.add_argument("--ratio", type=float, default=0.5, help="external weight, 0..1 (default 0.5)")
    run.add_argument("--mode", choices=["match", "direct"], default="match")
    run.add_argument("--params", default="air,tension,falsetto,energy")
    run.add_argument("--layer", default="user")
    run.add_argument("--chunk", type=int, default=38400)
    run.add_argument("--track-uuid", help="target track (default: first Verse 2.7 track)")
    run.add_argument("--clip-uuid", help="target clip (default: first sung clip on that track)")
    run.add_argument(
        "--import-notes",
        action="store_true",
        help="also replace the clip's notes with the project's",
    )
    run.add_argument(
        "--raw", action="store_true", help="skip percentile normalisation of the extracted curves"
    )
    run.add_argument("--workdir", help="where intermediate .ufdata files go")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=_run)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ace.AceError, convert.ConvertError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
