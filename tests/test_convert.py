from pathlib import Path

import yaml

from ace_mixer.convert import strip_masked_curves

SOURCE = {
    "name": "t",
    "ustx_version": "0.10",
    "expressions": {
        "dyn": {
            "name": "dynamics",
            "abbr": "dyn",
            "type": "Curve",
            "min": -240,
            "max": 120,
            "default_value": 0,
            "is_flag": False,
        },
        "rpit": {
            "name": "rendered pitch",
            "abbr": "rpit",
            "type": "MaskedCurve",
            "min": 2400,
            "max": 10800,
            "default_value": 6000,
            "is_flag": False,
        },
        "pito": {
            "name": "pitch override",
            "abbr": "pito",
            "type": "MaskedCurve",
            "min": 2400,
            "max": 10800,
            "default_value": 6000,
            "is_flag": False,
        },
    },
}


def test_strips_only_masked_curves(tmp_path: Path) -> None:
    src = tmp_path / "in.ustx"
    dst = tmp_path / "out.ustx"
    src.write_text(yaml.safe_dump(SOURCE, allow_unicode=True), encoding="utf-8")

    removed = strip_masked_curves(src, dst)

    assert sorted(removed) == ["pito", "rpit"]
    out = yaml.safe_load(dst.read_text(encoding="utf-8"))
    assert list(out["expressions"]) == ["dyn"]
    assert out["name"] == "t"


def test_is_a_no_op_without_masked_curves(tmp_path: Path) -> None:
    src = tmp_path / "in.ustx"
    dst = tmp_path / "out.ustx"
    doc = {"name": "t", "expressions": {"dyn": {"type": "Curve"}}}
    src.write_text(yaml.safe_dump(doc), encoding="utf-8")

    assert strip_masked_curves(src, dst) == []
    assert yaml.safe_load(dst.read_text(encoding="utf-8"))["expressions"] == {
        "dyn": {"type": "Curve"}
    }
