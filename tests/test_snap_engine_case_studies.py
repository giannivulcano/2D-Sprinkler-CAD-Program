"""Case-study regression tests from docs/specs/snapping-engine.md §7.

Test 1 covers §7.1: snapping near the outer corner of an L-joint must
return the wall's face-corner endpoint, not a phase-4 intersection.
Test 2 covers §7.2: a single wall alone must not emit any intersection
candidate from wall-internal face crossings.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.snap_engine import SnapEngine
from firepro3d.wall import WallSegment


def _make_scene() -> QGraphicsScene:
    """Create a minimal scene that WallSegment will accept."""
    scene = QGraphicsScene()
    # WallSegment's mitered logic looks up scene._walls; seed it.
    scene._walls = []
    return scene


def _add_wall(scene: QGraphicsScene,
              p1: QPointF, p2: QPointF,
              thickness_mm: float = 150.0) -> WallSegment:
    """Create and register a WallSegment in the given scene."""
    wall = WallSegment(p1, p2, thickness_mm=thickness_mm)
    scene.addItem(wall)
    scene._walls.append(wall)
    return wall


def test_l_joint_corner_resolves_to_face_endpoint(qapp):
    """§7.1: Cursor at an L-joint outer corner must snap to a face
    endpoint, not an intersection."""
    scene = _make_scene()

    # L-joint: horizontal wall from (0,0) to (1000,0); vertical wall
    # from (1000,0) to (1000,1000). Walls meet at (1000, 0).
    wall_a = _add_wall(scene, QPointF(0, 0),    QPointF(1000, 0))
    wall_b = _add_wall(scene, QPointF(1000, 0), QPointF(1000, 1000))

    # Outer corner of the L (opposite the interior angle). For a
    # 150 mm centered wall with no scene scale_manager, the outer
    # corner is roughly at (1075, -75) — half-thickness outward on
    # each wall's outer face. Use the wall's own snap_quad_points
    # to find the real point rather than guessing.
    ql_a = wall_a.snap_quad_points()
    ql_b = wall_b.snap_quad_points()
    # Outer corner of wall_a's far-side cap closest to wall_b.
    # Cursor placed exactly on wall_a's face-right-corner-B, which is
    # the mitered corner at the joint.
    cursor = ql_a[2]  # p2r — right face, endpoint 2

    engine = SnapEngine()
    # Use identity transform → scale=1, tol in scene units = 40.
    result = engine.find(cursor, scene, QTransform())

    assert result is not None, "expected a snap result at the L-joint"
    assert result.snap_type == "endpoint", (
        f"expected endpoint, got {result.snap_type!r} "
        f"(name={result.name!r})"
    )
    assert result.name is not None and result.name.startswith("face-"), (
        f"expected a face-* named target, got name={result.name!r}"
    )


def test_isolated_wall_emits_no_internal_intersection(qapp):
    """§7.2: A lone wall must not produce an ``intersection`` snap
    from its own face×face crossings. With the same-parent filter
    already in place (Change A) this passes today; the test pins it
    against regressions."""
    scene = _make_scene()
    wall = _add_wall(scene, QPointF(0, 0), QPointF(1000, 0))

    # Cursor placed on the wall centerline well away from either cap.
    cursor = QPointF(500, 0)

    engine = SnapEngine()
    result = engine.find(cursor, scene, QTransform())

    # The closest valid candidate here is the centerline midpoint.
    assert result is not None
    assert result.snap_type != "intersection", (
        f"wall-internal face crossings leaked as intersection at "
        f"{result.point.x()},{result.point.y()}"
    )
