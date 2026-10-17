from pathlib import Path

import pytest

from ace_mixer.convert import ConvertError, discover


def touch(path: Path) -> None:
    path.write_bytes(b"x")


def test_prefers_matching_stems(tmp_path: Path) -> None:
    touch(tmp_path / "song.ustx")
    touch(tmp_path / "song.wav")
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "backup.svp")
    project, audio = discover(str(tmp_path))
    assert project.name == "song.ustx"
    assert audio.name == "song.wav"


def test_single_pair_without_matching_stems(tmp_path: Path) -> None:
    touch(tmp_path / "take 1.svp")
    touch(tmp_path / "render.wav")
    project, audio = discover(str(tmp_path))
    assert project.suffix == ".svp"
    assert audio.suffix == ".wav"


def test_ambiguous_folder_is_rejected(tmp_path: Path) -> None:
    touch(tmp_path / "a.ustx")
    touch(tmp_path / "b.ustx")
    touch(tmp_path / "render.wav")
    with pytest.raises(ConvertError, match="ambiguous"):
        discover(str(tmp_path))


def test_two_matching_pairs_are_rejected(tmp_path: Path) -> None:
    touch(tmp_path / "one.ustx")
    touch(tmp_path / "one.wav")
    touch(tmp_path / "two.svp")
    touch(tmp_path / "two.wav")
    with pytest.raises(ConvertError, match="ambiguous"):
        discover(str(tmp_path))


def test_missing_audio_is_rejected(tmp_path: Path) -> None:
    touch(tmp_path / "a.ustx")
    with pytest.raises(ConvertError, match="no audio"):
        discover(str(tmp_path))
