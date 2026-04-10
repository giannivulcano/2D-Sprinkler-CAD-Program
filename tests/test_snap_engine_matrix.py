"""Layer-2 matrix fixture tests for SnapEngine.

One test class per item type in docs/specs/snapping-engine.md §5.
One test method per ✓-cell (snap type that should work for that item type).

Each test constructs a minimal QGraphicsScene, places one item, and asserts
that ``SnapEngine.find()`` returns the expected snap type at the expected
point.  Intersection tests add a plain ``QGraphicsLineItem`` as a crossing
partner.

Requires ``qapp`` (pytest-qt fixture) because QGraphicsScene and
QGraphicsItem are GUI classes.

Per spec §10.2 (roadmap item 9).
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QTransform
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
)

from firepro3d.construction_geometry import (
    ArcItem,
    CircleItem,
    LineItem,
    PolylineItem,
    RectangleItem,
)
from firepro3d.gridline import GridlineItem
from firepro3d.snap_engine import SnapEngine
from firepro3d.wall import WallSegment


# ── Helpers ──────────────────────────────────────────────────────────────────

OFFSET = 5.0        # cursor offset from expected point (within tolerance)
PERP_OFFSET = 30.0  # perpendicular / nearest cursor distance from segment

ABS_TOL = 2.0       # point comparison tolerance (scene units)


def _engine(**overrides) -> SnapEngine:
    """Create a SnapEngine with all snaps on, applying any overrides."""
    eng = SnapEngine()
    for k, v in overrides.items():
        setattr(eng, k, v)
    return eng


def _scene() -> QGraphicsScene:
    """Minimal scene."""
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


def _find(engine: SnapEngine, scene: QGraphicsScene,
          cursor: QPointF):
    """Run find() with identity transform (scale=1, tol=40 scene units)."""
    return engine.find(cursor, scene, QTransform())


def _crossing_line(scene: QGraphicsScene,
                   x: float = 100.0,
                   y_range: float = 100.0) -> QGraphicsLineItem:
    """Add a vertical crossing partner at x."""
    line = QGraphicsLineItem(QLineF(
        QPointF(x, -y_range), QPointF(x, y_range)))
    scene.addItem(line)
    return line


def _assert_snap(result, snap_type: str, expected_pt: QPointF,
                 tol: float = ABS_TOL):
    """Assert result matches expected snap type and point."""
    assert result is not None, f"expected {snap_type} snap, got None"
    assert result.snap_type == snap_type, (
        f"expected {snap_type}, got {result.snap_type}"
    )
    assert abs(result.point.x() - expected_pt.x()) < tol, (
        f"{snap_type} X: expected {expected_pt.x()}, got {result.point.x()}"
    )
    assert abs(result.point.y() - expected_pt.y()) < tol, (
        f"{snap_type} Y: expected {expected_pt.y()}, got {result.point.y()}"
    )


# ── LineItem ─────────────────────────────────────────────────────────────────

class TestLineItem:
    """LineItem: end ✓, mid ✓, int ✓ (phase 4), per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.item = LineItem(QPointF(0, 0), QPointF(200, 0))
        self.scene.addItem(self.item)

    def test_endpoint_p1(self):
        result = _find(_engine(), self.scene, QPointF(0, OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_p2(self):
        result = _find(_engine(), self.scene, QPointF(200, OFFSET))
        _assert_snap(result, "endpoint", QPointF(200, 0))

    def test_midpoint(self):
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "midpoint", QPointF(100, 0))

    def test_intersection(self):
        _crossing_line(self.scene, x=100)
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(80, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(80, 0))


# ── GridlineItem ─────────────────────────────────────────────────────────────

class TestGridlineItem:
    """GridlineItem: end ✓, mid ✓, int ✓ (phase 2+4), per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.item = GridlineItem(QPointF(0, 0), QPointF(200, 0))
        self.scene.addItem(self.item)
        self.scene._gridlines = [self.item]

    def test_endpoint_p1(self):
        result = _find(_engine(), self.scene, QPointF(0, OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_p2(self):
        result = _find(_engine(), self.scene, QPointF(200, OFFSET))
        _assert_snap(result, "endpoint", QPointF(200, 0))

    def test_midpoint(self):
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "midpoint", QPointF(100, 0))

    def test_intersection(self):
        gl2 = GridlineItem(QPointF(100, -100), QPointF(100, 100))
        self.scene.addItem(gl2)
        self.scene._gridlines.append(gl2)
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(80, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(80, 0))


# ── QGraphicsLineItem (Pipe proxy) ───────────────────────────────────────────

class TestQGraphicsLineItem:
    """Generic QGraphicsLineItem (Pipe): end ✓, mid ✓, int ✓ (phase 4), per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.item = QGraphicsLineItem(
            QLineF(QPointF(0, 0), QPointF(200, 0)))
        self.scene.addItem(self.item)

    def test_endpoint_p1(self):
        result = _find(_engine(), self.scene, QPointF(0, OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_p2(self):
        result = _find(_engine(), self.scene, QPointF(200, OFFSET))
        _assert_snap(result, "endpoint", QPointF(200, 0))

    def test_midpoint(self):
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "midpoint", QPointF(100, 0))

    def test_intersection(self):
        _crossing_line(self.scene, x=100)
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(80, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(80, 0))


# ── RectangleItem ────────────────────────────────────────────────────────────

class TestRectangleItem:
    """RectangleItem: end ✓ (corners), mid ✓ (edge centers), int ✓ (phase 4),
    cen ✓, per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        # Use a small rectangle (60x60) so the center at (30,30)
        # is within the search tolerance (40) of every edge,
        # ensuring scene.items() always finds the item even when
        # the cursor is near the interior center point.
        self.item = RectangleItem(QPointF(0, 0), QPointF(60, 60))
        self.scene.addItem(self.item)

    def test_endpoint_top_left(self):
        result = _find(_engine(), self.scene, QPointF(0, 0 + OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_bottom_right(self):
        result = _find(_engine(), self.scene, QPointF(60, 60 + OFFSET))
        _assert_snap(result, "endpoint", QPointF(60, 60))

    def test_midpoint_top_edge(self):
        result = _find(_engine(), self.scene,
                        QPointF(30, 0 - OFFSET))
        _assert_snap(result, "midpoint", QPointF(30, 0))

    def test_center(self):
        # Disable endpoint, midpoint, perpendicular, and nearest so
        # center (priority 3) isn't masked by closer edge-based snaps.
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False, snap_nearest=False),
            self.scene, QPointF(30, 30 + OFFSET))
        _assert_snap(result, "center", QPointF(30, 30))

    def test_intersection(self):
        _crossing_line(self.scene, x=30)
        result = _find(_engine(), self.scene, QPointF(30, 0 + OFFSET))
        _assert_snap(result, "intersection", QPointF(30, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False),
            self.scene, QPointF(20, 0 - PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(20, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_perpendicular=False),
            self.scene, QPointF(20, 0 - PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(20, 0))


# ── QGraphicsEllipseItem (full circle) ───────────────────────────────────────

class TestFullCircle:
    """CircleItem (full circle): int ✓ (phase 4 vs segments),
    cen ✓, qua ✓, per ✓, tan ✓, nea ✓.

    Uses CircleItem (a QGraphicsEllipseItem subclass) because phase-4
    intersection detection extracts circles from CircleItem._center /
    ._radius — a bare QGraphicsEllipseItem would miss intersection snaps.

    The engine reads quadrant/perpendicular/nearest positions from the
    item's boundingRect(), which includes pen-width padding.  Assertions
    use a relaxed tolerance (4 scene units) to accommodate the ≈3-unit
    BR expansion caused by the default cosmetic pen.
    """

    BR_TOL = 4.0  # allow for bounding-rect pen-width expansion

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        # CircleItem centered at (100, 100), radius 50
        self.item = CircleItem(QPointF(100, 100), 50.0)
        self.scene.addItem(self.item)

    def test_center(self):
        result = _find(_engine(), self.scene, QPointF(100, 100 + OFFSET))
        _assert_snap(result, "center", QPointF(100, 100))

    def test_quadrant_right(self):
        # Disable perpendicular/nearest so quadrant wins
        result = _find(
            _engine(snap_center=False, snap_perpendicular=False,
                    snap_nearest=False),
            self.scene, QPointF(155, 100))
        _assert_snap(result, "quadrant", QPointF(150, 100),
                     tol=self.BR_TOL)

    def test_quadrant_top(self):
        result = _find(
            _engine(snap_center=False, snap_perpendicular=False,
                    snap_nearest=False),
            self.scene, QPointF(100, 45))
        _assert_snap(result, "quadrant", QPointF(100, 50),
                     tol=self.BR_TOL)

    def test_intersection(self):
        _crossing_line(self.scene, x=100, y_range=200)
        result = _find(_engine(), self.scene,
                        QPointF(100, 50 - OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 50))

    def test_perpendicular(self):
        # Cursor outside circle, closest point on circumference
        result = _find(
            _engine(snap_center=False, snap_quadrant=False),
            self.scene, QPointF(100 + 80, 100))
        _assert_snap(result, "perpendicular", QPointF(150, 100),
                     tol=self.BR_TOL)

    def test_tangent(self):
        # Cursor must be outside the circle radius but close enough that
        # the tangent point falls within the snap tolerance (40 scene
        # units).  With BR-derived radius ~53 and tol=40, the cursor
        # must satisfy sqrt(d^2 - r^2) < 40 → d < ~66.
        cursor = QPointF(160, 100)  # d=60, tangent dist ≈ 28
        result = _find(
            _engine(snap_center=False, snap_quadrant=False,
                    snap_perpendicular=False, snap_nearest=False),
            self.scene, cursor)
        assert result is not None, "expected tangent snap"
        assert result.snap_type == "tangent"

    def test_nearest(self):
        result = _find(
            _engine(snap_center=False, snap_quadrant=False,
                    snap_perpendicular=False),
            self.scene, QPointF(100 + 80, 100))
        _assert_snap(result, "nearest", QPointF(150, 100),
                     tol=self.BR_TOL)


# ── QGraphicsEllipseItem (Node) ──────────────────────────────────────────────

class TestNodeCircle:
    """QGraphicsEllipseItem with .pipes attr (Node proxy): cen ✓ only."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.item = QGraphicsEllipseItem(90, 90, 20, 20)
        self.item.pipes = []  # Mark as Node
        self.scene.addItem(self.item)

    def test_center(self):
        result = _find(_engine(), self.scene, QPointF(100, 100 + OFFSET))
        _assert_snap(result, "center", QPointF(100, 100))

    def test_no_quadrant(self):
        """Nodes suppress quadrant snaps."""
        result = _find(
            _engine(snap_center=False),
            self.scene, QPointF(110 + OFFSET, 100))
        # Should not find quadrant (either None or a different type)
        if result is not None:
            assert result.snap_type != "quadrant"


# ── WallSegment ──────────────────────────────────────────────────────────────

def _add_wall(scene: QGraphicsScene,
              p1: QPointF, p2: QPointF,
              thickness_mm: float = 150.0) -> WallSegment:
    """Create and register a WallSegment in the given scene."""
    wall = WallSegment(p1, p2, thickness_mm=thickness_mm)
    scene.addItem(wall)
    scene._walls.append(wall)
    return wall


class TestWallSegment:
    """WallSegment: mid ✓ (centerline + face mids), per ✓ (5 segments), nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.wall = _add_wall(self.scene,
                              QPointF(0, 0), QPointF(1000, 0))

    def test_midpoint_centerline(self):
        result = _find(_engine(), self.scene, QPointF(500, OFFSET))
        _assert_snap(result, "midpoint", QPointF(500, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(300, PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(300, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False),
            self.scene, QPointF(300, PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(300, 0))


# ── PolylineItem ─────────────────────────────────────────────────────────────

class TestPolylineItem:
    """PolylineItem: end ✓ (vertices), mid ✓ (segment mids), int ✓ (phase 4),
    per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.item = PolylineItem(QPointF(0, 0))
        self.item.append_point(QPointF(200, 0))
        self.item.append_point(QPointF(200, 200))
        self.scene.addItem(self.item)

    def test_endpoint_first(self):
        result = _find(_engine(), self.scene, QPointF(0, OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_last(self):
        result = _find(_engine(), self.scene,
                        QPointF(200, 200 + OFFSET))
        _assert_snap(result, "endpoint", QPointF(200, 200))

    def test_midpoint_first_segment(self):
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "midpoint", QPointF(100, 0))

    def test_intersection(self):
        _crossing_line(self.scene, x=100)
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(80, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(80, 0))


# ── ArcItem ──────────────────────────────────────────────────────────────────

class TestArcItem:
    """ArcItem: end ✓ (start/end), mid ✓ (angular), int ✓ (phase 4 vs segments),
    cen ✓, qua ✓ (in-range), per ✓, tan ✓, nea ✓.

    Uses a small radius (30) so the center is within the snap tolerance
    (40 scene units) of the arc path.  ArcItem is a QGraphicsPathItem,
    so ``scene.items(search_rect)`` only finds it when the search rect
    overlaps the actual arc curve — the cursor must be near the path.
    """

    R = 30.0  # arc radius

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        # Arc: center (0,0), radius 30, start 0°, span 90° (CCW)
        # In Qt's Y-down system with atan2(-dy, dx):
        #   0°  → point (30, 0)
        #   90° → point (0, -30)
        #   45° → point (≈21.2, ≈-21.2)
        self.item = ArcItem(QPointF(0, 0), self.R, 0.0, 90.0)
        self.scene.addItem(self.item)

    def test_endpoint_start(self):
        """Start of arc at 0° → (30, 0)."""
        result = _find(_engine(), self.scene, QPointF(self.R, OFFSET))
        _assert_snap(result, "endpoint", QPointF(self.R, 0))

    def test_endpoint_end(self):
        """End of arc at 90° → (0, -30)."""
        result = _find(_engine(), self.scene, QPointF(OFFSET, -self.R))
        _assert_snap(result, "endpoint", QPointF(0, -self.R))

    def test_midpoint(self):
        """Angular midpoint at 45° → (≈21.2, ≈-21.2)."""
        mid_x = self.R * math.cos(math.radians(45))
        mid_y = -self.R * math.sin(math.radians(45))
        result = _find(_engine(), self.scene,
                        QPointF(mid_x + OFFSET, mid_y))
        _assert_snap(result, "midpoint", QPointF(mid_x, mid_y))

    def test_center(self):
        """Center at (0, 0) — cursor near start endpoint on the arc."""
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_quadrant=False, snap_perpendicular=False,
                    snap_nearest=False),
            self.scene, QPointF(self.R, OFFSET))
        _assert_snap(result, "center", QPointF(0, 0))

    def test_quadrant_0deg(self):
        """0° quadrant falls within 0°-90° arc → (30, 0)."""
        result = _find(
            _engine(snap_endpoint=False, snap_perpendicular=False,
                    snap_nearest=False),
            self.scene, QPointF(self.R, OFFSET))
        _assert_snap(result, "quadrant", QPointF(self.R, 0))

    def test_intersection(self):
        """Crossing line at x=15 intersects the arc.

        Phase 4 treats ArcItem as a QGraphicsPathItem and extracts line
        segments from the path approximation (cubic beziers decomposed
        into chords).  The intersection point is therefore approximate —
        use a relaxed tolerance of 5 scene units.
        """
        _crossing_line(self.scene, x=15, y_range=100)
        # Analytical: R*cos(θ)=15 → θ=60° → y = -R*sin(60°) ≈ -25.98
        expected_y = -self.R * math.sin(math.radians(60))
        result = _find(_engine(), self.scene,
                        QPointF(15, expected_y + OFFSET))
        _assert_snap(result, "intersection", QPointF(15, expected_y),
                     tol=5.0)

    def test_perpendicular(self):
        """Cursor outside arc along 0° direction — perp snaps to (30, 0)."""
        # Cursor at (30 + 8, 0) — still within tol=40 of the arc path
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_quadrant=False),
            self.scene, QPointF(self.R + 8, 0))
        _assert_snap(result, "perpendicular", QPointF(self.R, 0))

    def test_tangent(self):
        """Cursor outside the arc radius — tangent point on the visible arc."""
        # Cursor at (30+8, 0) — outside radius=30, within tol of arc path
        cursor = QPointF(self.R + 8, 0)
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_quadrant=False,
                    snap_perpendicular=False, snap_nearest=False),
            self.scene, cursor)
        assert result is not None, "expected tangent snap"
        assert result.snap_type == "tangent"

    def test_nearest(self):
        """Cursor outside arc along 0° — nearest snaps to (30, 0)."""
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_quadrant=False,
                    snap_perpendicular=False),
            self.scene, QPointF(self.R + 8, 0))
        _assert_snap(result, "nearest", QPointF(self.R, 0))


# ── QGraphicsPathItem (DXF) ─────────────────────────────────────────────────

class TestDXFPathItem:
    """Generic QGraphicsPathItem (DXF import proxy): end ✓, mid ✓, int ✓ (phase 4),
    per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(200, 0)
        path.lineTo(200, 200)
        self.item = QGraphicsPathItem(path)
        self.scene.addItem(self.item)

    def test_endpoint_first(self):
        result = _find(_engine(), self.scene, QPointF(0, OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_last(self):
        result = _find(_engine(), self.scene,
                        QPointF(200, 200 + OFFSET))
        _assert_snap(result, "endpoint", QPointF(200, 200))

    def test_midpoint(self):
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "midpoint", QPointF(100, 0))

    def test_intersection(self):
        _crossing_line(self.scene, x=100)
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(80, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_perpendicular=False),
            self.scene, QPointF(80, PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(80, 0))


# ── HatchItem (negative test) ───────────────────────────────────────────────

class TestHatchItem:
    """HatchItem: all N/A — must contribute zero snap candidates."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from firepro3d.annotations import HatchItem
        self.scene = _scene()
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(200, 0)
        path.lineTo(200, 200)
        path.closeSubpath()
        self.item = HatchItem(path, QPointF(0, 0))
        self.scene.addItem(self.item)

    def test_no_snap(self):
        """HatchItem must produce no snap of any type."""
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        assert result is None, (
            f"HatchItem leaked a {result.snap_type} snap"
        )
