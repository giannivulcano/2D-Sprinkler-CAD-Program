"""Unit tests for geometry utilities: CAD_Math and geometry_intersect."""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.cad_math import CAD_Math
from firepro3d.geometry_intersect import (
    line_line_intersection,
    line_line_intersection_unbounded,
    line_circle_intersections,
    line_circle_intersections_unbounded,
    line_arc_intersections,
    circle_circle_intersections,
    point_on_segment_param,
    nearest_intersection,
    is_parallel,
    perpendicular_translation,
    _normalize_angle,
    _angle_in_arc,
)

TOL = 1e-6


def _pt_eq(a: QPointF, b: QPointF, tol: float = TOL) -> bool:
    """Check if two QPointF are approximately equal."""
    return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


# ------------------------------------------------------------------ #
#  CAD_Math tests                                                      #
# ------------------------------------------------------------------ #

class TestGetVector:
    def test_basic(self):
        v = CAD_Math.get_vector(QPointF(1, 2), QPointF(4, 6))
        assert abs(v.x() - 3.0) < TOL
        assert abs(v.y() - 4.0) < TOL

    def test_zero_vector(self):
        v = CAD_Math.get_vector(QPointF(5, 5), QPointF(5, 5))
        assert abs(v.x()) < TOL
        assert abs(v.y()) < TOL

    def test_negative_components(self):
        v = CAD_Math.get_vector(QPointF(3, 7), QPointF(1, 2))
        assert abs(v.x() - (-2.0)) < TOL
        assert abs(v.y() - (-5.0)) < TOL


class TestGetUnitVector:
    def test_horizontal(self):
        u = CAD_Math.get_unit_vector(QPointF(0, 0), QPointF(10, 0))
        assert abs(u.x() - 1.0) < TOL
        assert abs(u.y()) < TOL

    def test_vertical(self):
        u = CAD_Math.get_unit_vector(QPointF(0, 0), QPointF(0, -5))
        assert abs(u.x()) < TOL
        assert abs(u.y() - (-1.0)) < TOL

    def test_diagonal(self):
        u = CAD_Math.get_unit_vector(QPointF(0, 0), QPointF(3, 4))
        length = math.hypot(u.x(), u.y())
        assert abs(length - 1.0) < TOL
        assert abs(u.x() - 0.6) < TOL
        assert abs(u.y() - 0.8) < TOL

    def test_coincident_points(self):
        u = CAD_Math.get_unit_vector(QPointF(7, 7), QPointF(7, 7))
        assert abs(u.x()) < TOL
        assert abs(u.y()) < TOL


class TestGetVectorLength:
    def test_horizontal(self):
        d = CAD_Math.get_vector_length(QPointF(0, 0), QPointF(5, 0))
        assert abs(d - 5.0) < TOL

    def test_diagonal(self):
        d = CAD_Math.get_vector_length(QPointF(0, 0), QPointF(3, 4))
        assert abs(d - 5.0) < TOL

    def test_zero_length(self):
        d = CAD_Math.get_vector_length(QPointF(3, 3), QPointF(3, 3))
        assert abs(d) < TOL

    def test_negative_direction(self):
        d = CAD_Math.get_vector_length(QPointF(5, 5), QPointF(2, 1))
        assert abs(d - 5.0) < TOL


class TestGetVectorLength3D:
    def test_basic(self):
        d = CAD_Math.get_vector_length_3d(QPointF(0, 0), QPointF(3, 4), 0.0, 0.0)
        assert abs(d - 5.0) < TOL

    def test_pure_z(self):
        d = CAD_Math.get_vector_length_3d(QPointF(0, 0), QPointF(0, 0), 0.0, 10.0)
        assert abs(d - 10.0) < TOL

    def test_full_3d(self):
        d = CAD_Math.get_vector_length_3d(QPointF(1, 2), QPointF(4, 6), 0.0, 12.0)
        expected = math.sqrt(9 + 16 + 144)  # 3^2 + 4^2 + 12^2 = 169 -> 13
        assert abs(d - expected) < TOL

    def test_zero_distance(self):
        d = CAD_Math.get_vector_length_3d(QPointF(5, 5), QPointF(5, 5), 3.0, 3.0)
        assert abs(d) < TOL


class TestGetVectorAngle:
    def test_pointing_up(self):
        # Vector (0, -1) => up in screen coords. Should give 0 degrees.
        angle = CAD_Math.get_vector_angle(QPointF(0, 0), QPointF(0, -10))
        assert abs(angle - 0.0) < 1.0  # within 1 degree

    def test_pointing_right(self):
        # Vector (1, 0) => right. atan2(0, 1) = 0 deg, +90 = 90.
        angle = CAD_Math.get_vector_angle(QPointF(0, 0), QPointF(10, 0))
        assert abs(angle - 90.0) < 1.0

    def test_pointing_down(self):
        # Vector (0, 1) => down in screen coords. atan2(1, 0) = 90, +90 = 180.
        angle = CAD_Math.get_vector_angle(QPointF(0, 0), QPointF(0, 10))
        assert abs(angle - 180.0) < 1.0

    def test_pointing_left(self):
        # Vector (-1, 0) => left. atan2(0, -1) = 180, +90 = 270.
        angle = CAD_Math.get_vector_angle(QPointF(0, 0), QPointF(-10, 0))
        assert abs(angle - 270.0) < 1.0


class TestGetAngleBetweenVectors:
    def test_parallel_same_direction(self):
        v1 = QPointF(1, 0)
        v2 = QPointF(5, 0)
        assert abs(CAD_Math.get_angle_between_vectors(v1, v2)) < TOL

    def test_perpendicular_signed(self):
        v1 = QPointF(1, 0)
        v2 = QPointF(0, 1)
        angle = CAD_Math.get_angle_between_vectors(v1, v2, signed=True)
        assert abs(angle - 90.0) < TOL

    def test_perpendicular_unsigned(self):
        v1 = QPointF(1, 0)
        v2 = QPointF(0, 1)
        angle = CAD_Math.get_angle_between_vectors(v1, v2, signed=False)
        assert abs(angle - 90.0) < TOL

    def test_opposite_direction(self):
        v1 = QPointF(1, 0)
        v2 = QPointF(-1, 0)
        angle = CAD_Math.get_angle_between_vectors(v1, v2, signed=False)
        assert abs(angle - 180.0) < TOL

    def test_negative_signed(self):
        v1 = QPointF(1, 0)
        v2 = QPointF(0, -1)
        angle = CAD_Math.get_angle_between_vectors(v1, v2, signed=True)
        assert abs(angle - (-90.0)) < TOL

    def test_zero_vector_returns_zero(self):
        v1 = QPointF(0, 0)
        v2 = QPointF(1, 0)
        assert abs(CAD_Math.get_angle_between_vectors(v1, v2)) < TOL

    def test_both_zero_vectors(self):
        assert abs(CAD_Math.get_angle_between_vectors(QPointF(0, 0), QPointF(0, 0))) < TOL


class TestRotatePoint:
    def test_90_degrees(self):
        pt = QPointF(1, 0)
        pivot = QPointF(0, 0)
        result = CAD_Math.rotate_point(pt, pivot, 90)
        assert abs(result.x() - 0.0) < TOL
        assert abs(result.y() - 1.0) < TOL

    def test_180_degrees(self):
        pt = QPointF(1, 0)
        pivot = QPointF(0, 0)
        result = CAD_Math.rotate_point(pt, pivot, 180)
        assert abs(result.x() - (-1.0)) < TOL
        assert abs(result.y() - 0.0) < TOL

    def test_360_degrees_identity(self):
        pt = QPointF(3, 4)
        pivot = QPointF(1, 1)
        result = CAD_Math.rotate_point(pt, pivot, 360)
        assert abs(result.x() - pt.x()) < TOL
        assert abs(result.y() - pt.y()) < TOL

    def test_zero_degrees_identity(self):
        pt = QPointF(3, 4)
        pivot = QPointF(1, 1)
        result = CAD_Math.rotate_point(pt, pivot, 0)
        assert abs(result.x() - pt.x()) < TOL
        assert abs(result.y() - pt.y()) < TOL

    def test_rotation_around_non_origin_pivot(self):
        pt = QPointF(3, 2)
        pivot = QPointF(2, 2)
        result = CAD_Math.rotate_point(pt, pivot, 90)
        assert abs(result.x() - 2.0) < TOL
        assert abs(result.y() - 3.0) < TOL

    def test_point_at_pivot(self):
        pt = QPointF(5, 5)
        result = CAD_Math.rotate_point(pt, pt, 45)
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 5.0) < TOL


class TestMirrorPoint:
    def test_mirror_across_x_axis(self):
        pt = QPointF(3, 5)
        result = CAD_Math.mirror_point(pt, QPointF(0, 0), QPointF(1, 0))
        assert abs(result.x() - 3.0) < TOL
        assert abs(result.y() - (-5.0)) < TOL

    def test_mirror_across_y_axis(self):
        pt = QPointF(3, 5)
        result = CAD_Math.mirror_point(pt, QPointF(0, 0), QPointF(0, 1))
        assert abs(result.x() - (-3.0)) < TOL
        assert abs(result.y() - 5.0) < TOL

    def test_point_on_axis(self):
        pt = QPointF(3, 0)
        result = CAD_Math.mirror_point(pt, QPointF(0, 0), QPointF(1, 0))
        assert abs(result.x() - 3.0) < TOL
        assert abs(result.y()) < TOL

    def test_mirror_across_diagonal(self):
        pt = QPointF(1, 0)
        result = CAD_Math.mirror_point(pt, QPointF(0, 0), QPointF(1, 1))
        assert abs(result.x() - 0.0) < TOL
        assert abs(result.y() - 1.0) < TOL

    def test_degenerate_axis(self):
        pt = QPointF(3, 4)
        result = CAD_Math.mirror_point(pt, QPointF(5, 5), QPointF(5, 5))
        assert abs(result.x() - 3.0) < TOL
        assert abs(result.y() - 4.0) < TOL


class TestScalePoint:
    def test_scale_up(self):
        result = CAD_Math.scale_point(QPointF(3, 4), QPointF(0, 0), 2.0)
        assert abs(result.x() - 6.0) < TOL
        assert abs(result.y() - 8.0) < TOL

    def test_scale_down(self):
        result = CAD_Math.scale_point(QPointF(6, 8), QPointF(0, 0), 0.5)
        assert abs(result.x() - 3.0) < TOL
        assert abs(result.y() - 4.0) < TOL

    def test_scale_factor_one(self):
        pt = QPointF(5, 7)
        result = CAD_Math.scale_point(pt, QPointF(1, 1), 1.0)
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 7.0) < TOL

    def test_scale_factor_zero(self):
        result = CAD_Math.scale_point(QPointF(5, 7), QPointF(1, 1), 0.0)
        assert abs(result.x() - 1.0) < TOL
        assert abs(result.y() - 1.0) < TOL

    def test_scale_with_non_origin_base(self):
        result = CAD_Math.scale_point(QPointF(5, 5), QPointF(3, 3), 3.0)
        assert abs(result.x() - 9.0) < TOL
        assert abs(result.y() - 9.0) < TOL

    def test_negative_scale(self):
        result = CAD_Math.scale_point(QPointF(4, 0), QPointF(2, 0), -1.0)
        assert abs(result.x() - 0.0) < TOL
        assert abs(result.y() - 0.0) < TOL


class TestPointOnLineNearest:
    def test_projection_onto_horizontal_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(5, 3), QPointF(0, 0), QPointF(10, 0))
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y()) < TOL

    def test_projection_onto_vertical_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(3, 5), QPointF(0, 0), QPointF(0, 10))
        assert abs(result.x()) < TOL
        assert abs(result.y() - 5.0) < TOL

    def test_point_already_on_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(3, 3), QPointF(0, 0), QPointF(6, 6))
        assert abs(result.x() - 3.0) < TOL
        assert abs(result.y() - 3.0) < TOL

    def test_projection_beyond_segment(self):
        # Infinite line projection extends beyond the segment endpoints.
        result = CAD_Math.point_on_line_nearest(
            QPointF(20, 5), QPointF(0, 0), QPointF(10, 0))
        assert abs(result.x() - 20.0) < TOL
        assert abs(result.y()) < TOL

    def test_degenerate_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(5, 5), QPointF(3, 3), QPointF(3, 3))
        assert abs(result.x() - 3.0) < TOL
        assert abs(result.y() - 3.0) < TOL


class TestRotateUnitVector:
    def test_x_to_y(self):
        """Rotating (1,0) to align with (0,1) should be ~90 degrees."""
        t = CAD_Math.rotate_unit_vector(QPointF(1, 0), QPointF(0, 1))
        # Apply transform to (1, 0) and check
        mapped = t.map(QPointF(1, 0))
        assert abs(mapped.x() - 0.0) < TOL
        assert abs(mapped.y() - 1.0) < TOL

    def test_identity(self):
        t = CAD_Math.rotate_unit_vector(QPointF(1, 0), QPointF(1, 0))
        mapped = t.map(QPointF(5, 3))
        assert abs(mapped.x() - 5.0) < TOL
        assert abs(mapped.y() - 3.0) < TOL

    def test_type_error(self):
        with pytest.raises(TypeError):
            CAD_Math.rotate_unit_vector((1, 0), QPointF(0, 1))


class TestMakeQTransformFromQPoints:
    def test_identity_mapping(self):
        # M1 == M2 => identity transform
        a = [QPointF(1, 0), QPointF(0, 1)]
        t = CAD_Math.make_qtransform_from_qpoints(a, a)
        mapped = t.map(QPointF(3, 4))
        assert abs(mapped.x() - 3.0) < TOL
        assert abs(mapped.y() - 4.0) < TOL

    def test_scale_transform(self):
        M1 = [QPointF(2, 0), QPointF(0, 2)]
        M2 = [QPointF(1, 0), QPointF(0, 1)]
        t = CAD_Math.make_qtransform_from_qpoints(M1, M2)
        mapped = t.map(QPointF(1, 1))
        assert abs(mapped.x() - 2.0) < TOL
        assert abs(mapped.y() - 2.0) < TOL

    def test_collinear_raises(self):
        M2 = [QPointF(1, 2), QPointF(2, 4)]  # collinear
        M1 = [QPointF(1, 0), QPointF(0, 1)]
        with pytest.raises(ValueError, match="collinear"):
            CAD_Math.make_qtransform_from_qpoints(M1, M2)


# ------------------------------------------------------------------ #
#  geometry_intersect tests                                            #
# ------------------------------------------------------------------ #

class TestLineLineIntersection:
    def test_perpendicular_cross(self):
        # Horizontal (0,0)-(10,0) vs vertical (5,-5)-(5,5)
        result = line_line_intersection(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, -5), QPointF(5, 5))
        assert result is not None
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 0.0) < TOL

    def test_at_endpoint(self):
        result = line_line_intersection(
            QPointF(0, 0), QPointF(5, 0),
            QPointF(5, 0), QPointF(5, 5))
        assert result is not None
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 0.0) < TOL

    def test_no_intersection_parallel(self):
        result = line_line_intersection(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 1), QPointF(10, 1))
        assert result is None

    def test_no_intersection_segments_miss(self):
        # Lines would intersect if extended, but segments do not.
        result = line_line_intersection(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(5, -5), QPointF(5, -1))
        assert result is None

    def test_diagonal_cross(self):
        result = line_line_intersection(
            QPointF(0, 0), QPointF(10, 10),
            QPointF(10, 0), QPointF(0, 10))
        assert result is not None
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 5.0) < TOL

    def test_coincident_segments(self):
        # Coincident (parallel with zero distance) returns None.
        result = line_line_intersection(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(2, 0), QPointF(8, 0))
        assert result is None


class TestLineLineIntersectionUnbounded:
    def test_basic(self):
        result = line_line_intersection_unbounded(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(5, -5), QPointF(5, 5))
        assert result is not None
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 0.0) < TOL

    def test_segments_miss_but_lines_hit(self):
        # Segments do not overlap, but infinite lines cross.
        result = line_line_intersection_unbounded(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(5, -5), QPointF(5, -1))
        assert result is not None
        assert abs(result.x() - 5.0) < TOL
        assert abs(result.y() - 0.0) < TOL

    def test_parallel_returns_none(self):
        result = line_line_intersection_unbounded(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 5), QPointF(10, 5))
        assert result is None


class TestLineCircleIntersections:
    def test_two_intersections(self):
        # Horizontal segment through circle centered at origin, radius 5
        pts = line_circle_intersections(
            QPointF(-10, 0), QPointF(10, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 2
        xs = sorted(p.x() for p in pts)
        assert abs(xs[0] - (-5.0)) < TOL
        assert abs(xs[1] - 5.0) < TOL

    def test_tangent(self):
        # Segment tangent to circle at (0, 5)
        pts = line_circle_intersections(
            QPointF(-10, 5), QPointF(10, 5),
            QPointF(0, 0), 5.0)
        assert len(pts) == 1
        assert abs(pts[0].x() - 0.0) < TOL
        assert abs(pts[0].y() - 5.0) < TOL

    def test_no_intersection(self):
        pts = line_circle_intersections(
            QPointF(-10, 10), QPointF(10, 10),
            QPointF(0, 0), 5.0)
        assert len(pts) == 0

    def test_segment_inside_circle(self):
        # Segment entirely inside circle -- no crossing.
        pts = line_circle_intersections(
            QPointF(-1, 0), QPointF(1, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 0

    def test_segment_starts_inside(self):
        # Segment starts inside, exits circle.
        pts = line_circle_intersections(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 1
        assert abs(pts[0].x() - 5.0) < TOL

    def test_degenerate_segment_on_circle(self):
        pts = line_circle_intersections(
            QPointF(5, 0), QPointF(5, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 1

    def test_degenerate_segment_off_circle(self):
        pts = line_circle_intersections(
            QPointF(3, 0), QPointF(3, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 0


class TestLineCircleIntersectionsUnbounded:
    def test_two_intersections(self):
        pts = line_circle_intersections_unbounded(
            QPointF(-1, 0), QPointF(1, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 2
        xs = sorted(p.x() for p in pts)
        assert abs(xs[0] - (-5.0)) < TOL
        assert abs(xs[1] - 5.0) < TOL

    def test_no_intersection(self):
        pts = line_circle_intersections_unbounded(
            QPointF(-1, 10), QPointF(1, 10),
            QPointF(0, 0), 5.0)
        assert len(pts) == 0

    def test_tangent(self):
        pts = line_circle_intersections_unbounded(
            QPointF(-1, 5), QPointF(1, 5),
            QPointF(0, 0), 5.0)
        assert len(pts) == 1

    def test_degenerate_segment(self):
        pts = line_circle_intersections_unbounded(
            QPointF(0, 0), QPointF(0, 0),
            QPointF(0, 0), 5.0)
        assert len(pts) == 0


class TestNormalizeAngle:
    def test_positive(self):
        assert abs(_normalize_angle(45.0) - 45.0) < TOL

    def test_negative(self):
        assert abs(_normalize_angle(-90.0) - 270.0) < TOL

    def test_wrap(self):
        assert abs(_normalize_angle(370.0) - 10.0) < TOL

    def test_zero(self):
        assert abs(_normalize_angle(0.0)) < TOL

    def test_360(self):
        assert abs(_normalize_angle(360.0)) < TOL


class TestAngleInArc:
    def test_in_positive_arc(self):
        assert _angle_in_arc(45.0, 0.0, 90.0) is True

    def test_out_positive_arc(self):
        assert _angle_in_arc(100.0, 0.0, 90.0) is False

    def test_wrapping_arc(self):
        # Arc from 350 degrees spanning 40 degrees (wraps through 0)
        assert _angle_in_arc(10.0, 350.0, 40.0) is True
        assert _angle_in_arc(200.0, 350.0, 40.0) is False

    def test_negative_span(self):
        # Clockwise arc
        assert _angle_in_arc(350.0, 10.0, -40.0) is True
        assert _angle_in_arc(180.0, 10.0, -40.0) is False

    def test_full_circle(self):
        assert _angle_in_arc(123.0, 0.0, 360.0) is True
        assert _angle_in_arc(0.0, 90.0, -360.0) is True


class TestLineArcIntersections:
    def test_hit_within_arc(self):
        # Arc on right half of circle (start=315, span=90 covering 0 deg)
        pts = line_arc_intersections(
            QPointF(-10, 0), QPointF(10, 0),
            QPointF(0, 0), 5.0,
            start_deg=315.0, span_deg=90.0)
        # Should find the intersection on the right side (5, 0) at angle 0
        assert len(pts) >= 1
        found = any(abs(p.x() - 5.0) < TOL and abs(p.y()) < TOL for p in pts)
        assert found

    def test_miss_outside_arc(self):
        # Arc on right side only (330..30 deg), vertical line at x=0
        # hits circle at (0, 5) angle=90 and (0, -5) angle=-90/270,
        # both outside [330, 30].
        pts = line_arc_intersections(
            QPointF(0, -10), QPointF(0, 10),
            QPointF(0, 0), 5.0,
            start_deg=330.0, span_deg=60.0)
        assert len(pts) == 0

    def test_full_circle_arc(self):
        pts = line_arc_intersections(
            QPointF(-10, 0), QPointF(10, 0),
            QPointF(0, 0), 5.0,
            start_deg=0.0, span_deg=360.0)
        assert len(pts) == 2


class TestCircleCircleIntersections:
    def test_two_intersections(self):
        pts = circle_circle_intersections(
            QPointF(0, 0), 5.0,
            QPointF(6, 0), 5.0)
        assert len(pts) == 2
        # Both points should be equidistant from each center (radius 5)
        for p in pts:
            assert abs(_dist(p, QPointF(0, 0)) - 5.0) < TOL
            assert abs(_dist(p, QPointF(6, 0)) - 5.0) < TOL

    def test_tangent_externally(self):
        pts = circle_circle_intersections(
            QPointF(0, 0), 5.0,
            QPointF(10, 0), 5.0)
        assert len(pts) == 1
        assert abs(pts[0].x() - 5.0) < TOL
        assert abs(pts[0].y()) < TOL

    def test_no_intersection_far_apart(self):
        pts = circle_circle_intersections(
            QPointF(0, 0), 1.0,
            QPointF(100, 0), 1.0)
        assert len(pts) == 0

    def test_one_inside_other(self):
        pts = circle_circle_intersections(
            QPointF(0, 0), 10.0,
            QPointF(1, 0), 2.0)
        assert len(pts) == 0

    def test_concentric(self):
        pts = circle_circle_intersections(
            QPointF(0, 0), 5.0,
            QPointF(0, 0), 5.0)
        assert len(pts) == 0

    def test_identical_position_different_radius(self):
        pts = circle_circle_intersections(
            QPointF(0, 0), 5.0,
            QPointF(0, 0), 3.0)
        assert len(pts) == 0


class TestPointOnSegmentParam:
    def test_start(self):
        t = point_on_segment_param(QPointF(0, 0), QPointF(0, 0), QPointF(10, 0))
        assert abs(t - 0.0) < TOL

    def test_end(self):
        t = point_on_segment_param(QPointF(10, 0), QPointF(0, 0), QPointF(10, 0))
        assert abs(t - 1.0) < TOL

    def test_midpoint(self):
        t = point_on_segment_param(QPointF(5, 0), QPointF(0, 0), QPointF(10, 0))
        assert abs(t - 0.5) < TOL

    def test_beyond_end(self):
        t = point_on_segment_param(QPointF(20, 0), QPointF(0, 0), QPointF(10, 0))
        assert abs(t - 2.0) < TOL

    def test_before_start(self):
        t = point_on_segment_param(QPointF(-5, 0), QPointF(0, 0), QPointF(10, 0))
        assert abs(t - (-0.5)) < TOL

    def test_degenerate_segment(self):
        t = point_on_segment_param(QPointF(5, 5), QPointF(3, 3), QPointF(3, 3))
        assert abs(t - 0.0) < TOL


class TestNearestIntersection:
    def test_picks_closest(self):
        click = QPointF(0, 0)
        pts = [QPointF(10, 0), QPointF(3, 0), QPointF(7, 0)]
        result = nearest_intersection(click, pts)
        assert result is not None
        assert abs(result.x() - 3.0) < TOL

    def test_empty_list(self):
        assert nearest_intersection(QPointF(0, 0), []) is None

    def test_single_point(self):
        result = nearest_intersection(QPointF(0, 0), [QPointF(5, 5)])
        assert result is not None
        assert abs(result.x() - 5.0) < TOL


class TestIsParallel:
    def test_parallel_horizontal(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 5), QPointF(10, 5)) is True

    def test_antiparallel(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(10, 5), QPointF(0, 5)) is True

    def test_perpendicular(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, 0), QPointF(5, 10)) is False

    def test_nearly_parallel_within_tolerance(self):
        # 3-degree deviation on a 10-unit segment
        assert is_parallel(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 0), QPointF(10, math.tan(math.radians(3)) * 10)) is True

    def test_degenerate_segment(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(0, 0),
            QPointF(0, 5), QPointF(10, 5)) is False

    def test_custom_tolerance(self):
        # 10-degree deviation should fail at 5-degree tolerance
        dx = 10
        dy = math.tan(math.radians(10)) * dx
        assert is_parallel(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 0), QPointF(dx, dy),
            tolerance_deg=5.0) is False
        # But pass at 15-degree tolerance
        assert is_parallel(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 0), QPointF(dx, dy),
            tolerance_deg=15.0) is True


class TestPerpendicularTranslation:
    def test_onto_horizontal_line(self):
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, 3))
        assert abs(delta.x()) < TOL
        assert abs(delta.y() - (-3.0)) < TOL

    def test_onto_vertical_line(self):
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(0, 10),
            QPointF(4, 5))
        assert abs(delta.x() - (-4.0)) < TOL
        assert abs(delta.y()) < TOL

    def test_point_already_on_line(self):
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, 0))
        assert abs(delta.x()) < TOL
        assert abs(delta.y()) < TOL

    def test_degenerate_ref_line(self):
        delta = perpendicular_translation(
            QPointF(5, 5), QPointF(5, 5),
            QPointF(3, 4))
        assert abs(delta.x()) < TOL
        assert abs(delta.y()) < TOL

    def test_diagonal_line(self):
        # Line y = x; point (3, 0) should project to (1.5, 1.5)
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(10, 10),
            QPointF(3, 0))
        foot = QPointF(3 + delta.x(), 0 + delta.y())
        assert abs(foot.x() - 1.5) < TOL
        assert abs(foot.y() - 1.5) < TOL
