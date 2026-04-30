"""tests/test_hydraulic_solver.py — Hydraulic solver unit tests."""

import pytest
from firepro3d.equivalent_length import equivalent_length_ft, FITTING_TYPE_MAP


class TestEquivalentLength:
    """NFPA 13 Table 22.4.3.1.1 lookup tests."""

    def test_90_elbow_2_inch(self):
        assert equivalent_length_ft("90elbow", '2"Ø') == 5

    def test_90_elbow_1_inch(self):
        assert equivalent_length_ft("90elbow", '1"Ø') == 2.5

    def test_45_elbow_3_inch(self):
        assert equivalent_length_ft("45elbow", '3"Ø') == 4

    def test_tee_4_inch(self):
        assert equivalent_length_ft("tee", '4"Ø') == 20

    def test_tee_up_is_tee(self):
        assert equivalent_length_ft("tee_up", '2"Ø') == 10

    def test_tee_down_is_tee(self):
        assert equivalent_length_ft("tee_down", '2"Ø') == 10

    def test_elbow_up_is_90(self):
        assert equivalent_length_ft("elbow_up", '2"Ø') == 5

    def test_elbow_down_is_90(self):
        assert equivalent_length_ft("elbow_down", '2"Ø') == 5

    def test_wye_is_45(self):
        assert equivalent_length_ft("wye", '2"Ø') == 3

    def test_cross_4_inch(self):
        assert equivalent_length_ft("cross", '4"Ø') == 20

    def test_cap_is_zero(self):
        assert equivalent_length_ft("cap", '2"Ø') == 0

    def test_no_fitting_is_zero(self):
        assert equivalent_length_ft("no fitting", '2"Ø') == 0

    def test_unknown_fitting_returns_zero(self):
        assert equivalent_length_ft("unknown_type", '2"Ø') == 0

    def test_unknown_diameter_returns_zero(self):
        assert equivalent_length_ft("90elbow", '99"Ø') == 0

    def test_three_quarter_inch(self):
        """Verify future pipe size is in the table."""
        assert equivalent_length_ft("90elbow", '¾"Ø') == 2

    def test_all_fitting_types_mapped(self):
        """Every Fitting.type value must appear in FITTING_TYPE_MAP."""
        expected_types = [
            "no fitting", "cap", "45elbow", "90elbow", "tee", "wye",
            "cross", "tee_up", "tee_down", "elbow_up", "elbow_down",
        ]
        for ft in expected_types:
            assert ft in FITTING_TYPE_MAP, f"{ft} not in FITTING_TYPE_MAP"
