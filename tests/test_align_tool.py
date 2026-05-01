"""Tests for the Align tool: geometric primitives, AlignmentConstraint, edge
extraction, and tool integration."""

from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_intersect import is_parallel, perpendicular_translation


class TestIsParallel:
    """is_parallel(p1, p2, p3, p4, tolerance_deg) → bool"""

    def test_exactly_parallel_horizontal(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 50), QPointF(100, 50),
        ) is True

    def test_exactly_parallel_vertical(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(0, 100),
            QPointF(50, 0), QPointF(50, 100),
        ) is True

    def test_antiparallel(self):
        """180° offset is still parallel."""
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(100, 50), QPointF(0, 50),
        ) is True

    def test_within_tolerance_4deg(self):
        """4° is within default 5° tolerance."""
        rad = math.radians(4)
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 0), QPointF(100 * math.cos(rad), 100 * math.sin(rad)),
        ) is True

    def test_outside_tolerance_6deg(self):
        """6° exceeds default 5° tolerance."""
        rad = math.radians(6)
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 0), QPointF(100 * math.cos(rad), 100 * math.sin(rad)),
        ) is False

    def test_perpendicular(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 0), QPointF(0, 100),
        ) is False

    def test_diagonal_parallel(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 100),
            QPointF(50, 0), QPointF(150, 100),
        ) is True

    def test_degenerate_zero_length_segment(self):
        """Zero-length segment → not parallel."""
        assert is_parallel(
            QPointF(0, 0), QPointF(0, 0),
            QPointF(0, 50), QPointF(100, 50),
        ) is False


class TestPerpendicularTranslation:
    """perpendicular_translation(ref_p1, ref_p2, target_point) → QPointF delta"""

    def test_horizontal_ref_point_above(self):
        """Point above horizontal line → delta moves it down to the line."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(50, 30),
        )
        assert abs(delta.x()) < 1e-6
        assert abs(delta.y() - (-30.0)) < 1e-6

    def test_vertical_ref_point_right(self):
        """Point right of vertical line → delta moves it left to the line."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(0, 100),
            QPointF(20, 50),
        )
        assert abs(delta.x() - (-20.0)) < 1e-6
        assert abs(delta.y()) < 1e-6

    def test_point_already_on_line(self):
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(50, 0),
        )
        assert abs(delta.x()) < 1e-6
        assert abs(delta.y()) < 1e-6

    def test_diagonal_ref(self):
        """45° line — perpendicular translation should be along (-1,1)/√2."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 100),
            QPointF(50, 60),
        )
        new_x = 50 + delta.x()
        new_y = 60 + delta.y()
        assert abs(new_x - new_y) < 1e-6
