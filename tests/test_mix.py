import pytest

from ace_mixer.mix import blend, summarize

BASE = [0.2, 0.4, 0.6, 0.8, None]
EXT = [0.9, 0.1, 0.5, 0.3, 0.7]


def test_ratio_zero_keeps_baseline() -> None:
    mixed, stats = blend(BASE, EXT, 0.0)
    assert stats["baseline"] == 1.0
    assert mixed[:4] == pytest.approx([0.2, 0.4, 0.6, 0.8])


def test_ratio_one_replaces_with_matched_shape() -> None:
    mixed, stats = blend(BASE, EXT, 1.0, mode="match")
    assert stats["base_mean"] == pytest.approx(0.5)
    # Clipping to the ACE parameter range may move the mean, but the source
    # ordering must survive: high external values map to high output values.
    assert mixed[0] > mixed[1]
    assert mixed[2] > mixed[3]


def test_match_only_transfers_shape() -> None:
    mixed, _ = blend(BASE, EXT, 1.0, mode="match")
    b_sorted = sorted(BASE[:4])
    m_sorted = sorted(mixed[:4])
    assert m_sorted[0] < m_sorted[-1]
    assert m_sorted != b_sorted


def test_unvoiced_ticks_stay_empty() -> None:
    ext = [0.9, 0.1, 0.5, 0.3, None]
    mixed, _ = blend(BASE, ext, 0.5)
    assert mixed[4] is None
    assert all(v is not None for v in mixed[:4])


def test_missing_baseline_writes_external() -> None:
    mixed, stats = blend([None] * 5, EXT, 0.5)
    assert stats["baseline"] == 0.0
    assert mixed[:5] == pytest.approx(EXT)


def test_out_of_range_weight_is_rejected() -> None:
    with pytest.raises(ValueError):
        blend(BASE, EXT, 1.5)


def test_summarize() -> None:
    s = summarize(BASE)
    assert s["voiced"] == 4.0
    assert s["ticks"] == 5.0
