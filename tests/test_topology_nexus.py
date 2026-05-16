import math

import pytest

from mempalace.topology.nexus import NEXUS_WORD, decimation, family, nexus_label, polarity, step_period


def test_nexus_label_canonical_table():
    for idx, value in enumerate(NEXUS_WORD):
        assert nexus_label(idx) == value
        assert nexus_label(idx + 18) == value


def test_family_partitions_labels():
    assert {label for label in range(1, 10) if family(label) == 1} == {1, 4, 7}
    assert {label for label in range(1, 10) if family(label) == 2} == {2, 5, 8}
    assert {label for label in range(1, 10) if family(label) == 3} == {3, 6, 9}


def test_family_rejects_invalid_label():
    with pytest.raises(ValueError):
        family(0)


def test_polarity_fold():
    assert [polarity(i) for i in range(18)] == ([1] * 9) + ([-1] * 9)


def test_step_period_matches_gcd():
    for step in range(1, 18):
        assert step_period(step) == 18 // math.gcd(18, step)


def test_decimation_canonical_cycles():
    assert decimation(0, 3, 6) == [1, 2, 4, 8, 7, 5]
    assert decimation(6, 2, 9) == [4, 8, 3, 7, 2, 6, 1, 5, 9]

