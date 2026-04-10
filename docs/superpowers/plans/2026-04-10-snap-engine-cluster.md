# Snap Engine Cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close four snap-engine spec roadmap items — add `QGraphicsPathItem` (DXF) to phase 4 with underlay group descent, add `ArcItem` tangent support, and build the Layer 2 matrix fixture test harness.

**Architecture:** All changes are in `firepro3d/snap_engine.py` (two new code branches) and one new test file `tests/test_snap_engine_matrix.py`. The phase-4 change adds a `QGraphicsPathItem` elif branch and wraps the `scene.items()` loop to descend into DXF underlay groups. The tangent change extends the existing `ArcItem` block in `_geometric_snaps`. The test harness covers every ✓-cell in the spec §5 matrix.

**Tech Stack:** Python 3.x, PyQt6, pytest, pytest-qt

**Spec:** `docs/specs/snapping-engine.md` — roadmap items 2, 6, 7, 9

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `firepro3d/snap_engine.py` | Modify (lines 315–410, 720–735) | Phase-4 `QGraphicsPathItem` branch + DXF group descent; ArcItem tangent in `_geometric_snaps` |
| `tests/test_snap_engine_matrix.py` | Create | Layer 2 matrix fixture tests — one class per item type, one method per ✓-cell |

---

## Task 1: QGraphicsPathItem Phase-4 Extraction + DXF Underlay Group Descent

**Files:**
- Modify: `firepro3d/snap_engine.py:315-410` (`_check_geometry_intersections`)
- Test: `tests/test_snap_engine_matrix.py` (DXF path intersection tests — Task 3)

**Context:** Phase 4 (`_check_geometry_intersections`) iterates `scene.items(search_rect)` and extracts segments from specific item types for intersection detection. Generic `QGraphicsPathItem` (DXF imports) has no branch, so DXF geometry never participates in intersection snaps (spec §5 note 7, bug⁷). Additionally, DXF underlay children live inside a `QGraphicsItemGroup` tagged `"DXF Underlay"` — phase 1 descends into these groups (line 272), but phase 4 doesn't.

- [ ] **Step 1: Add DXF underlay group descent to the phase-4 item loop**

In `_check_geometry_intersections`, the `for item in scene.items(search_rect)` loop (line 330) skips DXF underlay groups because they match no isinstance branch. Add group descent logic matching the phase-1 pattern, replacing the flat loop with one that yields children of DXF underlay groups.

In `firepro3d/snap_engine.py`, replace:

```python
        for item in scene.items(search_rect):
            if exclude is not None and item is exclude:
                continue
            if item.parentItem() is not None:
                continue
            if isinstance(item, ConstructionLine):
```

with:

```python
        def _phase4_items():
            """Yield items for segment extraction, descending into DXF groups."""
            for item in scene.items(search_rect):
                if exclude is not None and item is exclude:
                    continue
                if item.parentItem() is not None:
                    continue
                if (isinstance(item, QGraphicsItemGroup)
                        and item.data(0) == "DXF Underlay"):
                    for child in item.childItems():
                        yield child
                    continue
                yield item

        for item in _phase4_items():
            if isinstance(item, ConstructionLine):
```

- [ ] **Step 2: Add `QGraphicsPathItem` segment extraction branch**

After the `CircleItem` elif branch (line 366), add a new elif for generic `QGraphicsPathItem`. This must exclude `HatchItem` (all-N/A per spec), and `WallSegment`/`PolylineItem` are already handled by earlier elif branches so they won't reach this point.

Add after the `elif isinstance(item, CircleItem):` block:

```python
            elif isinstance(item, QGraphicsPathItem):
                # Generic path items (DXF imports). Skip HatchItem —
                # intentionally all-N/A per snap spec §5.
                if not isinstance(item, _hatch_type):
                    path = item.path()
                    n = path.elementCount()
                    for j in range(min(n - 1, 511)):
                        e1 = path.elementAt(j)
                        e2 = path.elementAt(j + 1)
                        _segments.append((
                            item.mapToScene(QPointF(e1.x, e1.y)),
                            item.mapToScene(QPointF(e2.x, e2.y)),
                            item,
                        ))
```

Also add the `HatchItem` import at the top of the method (matching the phase-1 pattern):

```python
    def _check_geometry_intersections(self, ctx: "_SnapCtx",
                                       scene: QGraphicsScene,
                                       search_rect: QRectF,
                                       exclude: QGraphicsItem | None,
                                       gl_items: list):
        """Phase 4: Line-line and line-circle intersection snaps."""
        from .annotations import HatchItem as _hatch_type
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_case_studies.py tests/test_snap_nearest_perpendicular_decoupling.py tests/test_snap_engine_primitives.py -v`

Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "feat(snap): add QGraphicsPathItem to phase-4 intersections + DXF group descent

Adds a QGraphicsPathItem elif branch to _check_geometry_intersections
so DXF path imports participate in phase-4 intersection detection.
HatchItem is explicitly excluded (all-N/A per spec §5).

Also adds DXF underlay group descent to phase 4, matching the phase-1
pattern — children of QGraphicsItemGroup tagged 'DXF Underlay' are
now yielded into the segment extraction loop.

Closes snap-spec roadmap items 2 and 7."
```

---

## Task 2: ArcItem Tangent Support

**Files:**
- Modify: `firepro3d/snap_engine.py:722-735` (`_geometric_snaps`, ArcItem block)
- Test: `tests/test_snap_engine_matrix.py` (ArcItem tangent tests — Task 3)

**Context:** The `_geometric_snaps` method handles ArcItem for perpendicular and nearest (line 722), but has no tangent logic. The full-circle tangent code for `QGraphicsEllipseItem` (line 757) computes two tangent points using `math.acos(r / d)`. The arc version must additionally filter each tangent point through `_angle_in_arc` to ensure it falls on the visible arc, and skip when the cursor is inside the radius.

- [ ] **Step 1: Add tangent emission to the ArcItem block**

In `_geometric_snaps`, the ArcItem block (line 722) currently ends after the nearest emission. Add tangent logic after the perpendicular/nearest block, inside the same `if isinstance(item, ArcItem):` check.

In `firepro3d/snap_engine.py`, replace:

```python
        # ── ArcItem — closest point on arc circumference ─────────────────
        if isinstance(item, ArcItem):
            cx, cy = item._center.x(), item._center.y()
            r = item._radius
            dx = cursor.x() - cx
            dy = cursor.y() - cy
            d = math.hypot(dx, dy)
            if d > 1e-6:
                foot_angle_deg = math.degrees(math.atan2(-dy, dx))
                if _angle_in_arc(foot_angle_deg, item._start_deg, item._span_deg):
                    foot = QPointF(cx + r * dx / d, cy + r * dy / d)
                    if self.snap_perpendicular:
                        pts.append(("perpendicular", foot))
                    if self.snap_nearest:
                        pts.append(("nearest", foot))
```

with:

```python
        # ── ArcItem — closest point on arc circumference + tangent ───────
        if isinstance(item, ArcItem):
            cx, cy = item._center.x(), item._center.y()
            r = item._radius
            dx = cursor.x() - cx
            dy = cursor.y() - cy
            d = math.hypot(dx, dy)
            if d > 1e-6:
                foot_angle_deg = math.degrees(math.atan2(-dy, dx))
                if _angle_in_arc(foot_angle_deg, item._start_deg, item._span_deg):
                    foot = QPointF(cx + r * dx / d, cy + r * dy / d)
                    if self.snap_perpendicular:
                        pts.append(("perpendicular", foot))
                    if self.snap_nearest:
                        pts.append(("nearest", foot))

                # Tangent — cursor must be outside the arc's radius
                if self.snap_tangent and d > r + 1e-6:
                    angle_to_cursor = math.atan2(
                        cursor.y() - cy, cursor.x() - cx,
                    )
                    half_angle = math.acos(r / d)
                    for sign in (+1, -1):
                        a = angle_to_cursor + sign * half_angle
                        tp = QPointF(cx + r * math.cos(a),
                                     cy + r * math.sin(a))
                        # Only emit if tangent point falls on the visible arc
                        tp_deg = math.degrees(math.atan2(-(tp.y() - cy),
                                                          tp.x() - cx))
                        if _angle_in_arc(tp_deg, item._start_deg,
                                         item._span_deg):
                            pts.append(("tangent", tp))
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_case_studies.py tests/test_snap_nearest_perpendicular_decoupling.py tests/test_snap_engine_primitives.py -v`

Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "feat(snap): add ArcItem tangent support in _geometric_snaps

The arc branch now emits tangent candidates when snap_tangent is on.
Uses the same math as the full-circle tangent (acos(r/d) half-angle),
filtered through _angle_in_arc so only tangent points on the visible
arc are emitted. Cursor-inside-radius guard prevents math domain errors.

Closes snap-spec roadmap item 6 — ArcItem×tangent flips to ✓."
```

---

## Task 3: Matrix Fixture Test Harness

**Files:**
- Create: `tests/test_snap_engine_matrix.py`

**Context:** Layer 2 tests per spec §10.2. One test class per item type in the §5 matrix, one test method per ✓-cell. Each test constructs a minimal `QGraphicsScene`, places one item of the row's type, and asserts that `SnapEngine.find()` returns the expected snap type at the expected point. Intersection tests use a plain `QGraphicsLineItem` as the canonical crossing partner. All tests require `qapp` (pytest-qt fixture).

### Geometry conventions used across all fixtures

All items are placed at coordinates that make expected snap points easy to compute:
- Lines: horizontal from `(0, 0)` to `(200, 0)` → endpoint at `(0,0)` and `(200,0)`, midpoint at `(100,0)`.
- Rectangles: `(0, 0, 200, 100)` → corners at the four rect corners, edge midpoints at edge centers, center at `(100, 50)`.
- Circles: center `(100, 100)`, radius `50` → quadrants at `(150,100)`, `(50,100)`, `(100,50)`, `(100,150)`.
- Arcs: center `(0, 0)`, radius `100`, start 0°, span 90° (first quadrant) → endpoints at `(100, 0)` and `(0, -100)`, midpoint at 45°, center at origin, quadrant at 0° `(100, 0)`.
- Polylines: vertices at `(0,0)`, `(100,0)`, `(100,100)` → endpoints at all three, midpoints at `(50,0)` and `(100,50)`.
- Walls: from `(0,0)` to `(1000,0)`, thickness 150mm → centerline midpoint at `(500,0)`, face midpoints offset by half-thickness.
- DXF paths: a `QGraphicsPathItem` with path from `(0,0)` to `(200,0)` to `(200,200)` → endpoints at vertices, midpoints at segment centers.
- Crossing partner for intersection tests: a `QGraphicsLineItem` from `(100, -100)` to `(100, 100)` crossing the test item at `(100, 0)`.

### Cursor placement strategy

For each snap type, the cursor is placed near the expected snap point but offset slightly so the snap engine has to resolve:
- **endpoint/midpoint/center/quadrant:** cursor offset 5 units in Y from the expected point.
- **intersection:** cursor offset 5 units in Y from the crossing point.
- **perpendicular:** cursor placed 30 units perpendicular to the nearest segment (creates a clear foot-of-perpendicular).
- **nearest:** cursor placed 30 units perpendicular (same as perpendicular — both should emit independently; we assert the nearest one).
- **tangent:** cursor placed outside the circle/arc radius, offset to produce a tangent on the visible portion.

- [ ] **Step 1: Create test file with helpers and LineItem tests**

Create `tests/test_snap_engine_matrix.py`:

```python
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
          cursor: QPointF) -> "OsnapResult | None":
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
```

- [ ] **Step 2: Run LineItem tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestLineItem -v`

Expected: All 6 tests PASS.

- [ ] **Step 3: Add GridlineItem tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

This requires an import for `GridlineItem`. Add to the imports section:

```python
from firepro3d.gridline import GridlineItem
```

- [ ] **Step 4: Run GridlineItem tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestGridlineItem -v`

Expected: All 6 tests PASS.

- [ ] **Step 5: Add QGraphicsLineItem (Pipe proxy) tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

- [ ] **Step 6: Run QGraphicsLineItem tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestQGraphicsLineItem -v`

Expected: All 6 tests PASS.

- [ ] **Step 7: Add RectangleItem tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
# ── RectangleItem ────────────────────────────────────────────────────────────

class TestRectangleItem:
    """RectangleItem: end ✓ (corners), mid ✓ (edge centers), int ✓ (phase 4),
    cen ✓, per ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        self.item = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        self.scene.addItem(self.item)

    def test_endpoint_top_left(self):
        result = _find(_engine(), self.scene, QPointF(0, 0 + OFFSET))
        _assert_snap(result, "endpoint", QPointF(0, 0))

    def test_endpoint_bottom_right(self):
        result = _find(_engine(), self.scene, QPointF(200, 100 + OFFSET))
        _assert_snap(result, "endpoint", QPointF(200, 100))

    def test_midpoint_top_edge(self):
        result = _find(_engine(), self.scene,
                        QPointF(100, 0 - OFFSET))
        _assert_snap(result, "midpoint", QPointF(100, 0))

    def test_center(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False),
            self.scene, QPointF(100, 50 + OFFSET))
        _assert_snap(result, "center", QPointF(100, 50))

    def test_intersection(self):
        _crossing_line(self.scene, x=100)
        result = _find(_engine(), self.scene, QPointF(100, 0 + OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 0))

    def test_perpendicular(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False),
            self.scene, QPointF(80, 0 - PERP_OFFSET))
        _assert_snap(result, "perpendicular", QPointF(80, 0))

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_perpendicular=False),
            self.scene, QPointF(80, 0 - PERP_OFFSET))
        _assert_snap(result, "nearest", QPointF(80, 0))
```

- [ ] **Step 8: Run RectangleItem tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestRectangleItem -v`

Expected: All 7 tests PASS.

- [ ] **Step 9: Add QGraphicsEllipseItem (full circle) tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
# ── QGraphicsEllipseItem (full circle) ───────────────────────────────────────

class TestFullCircle:
    """QGraphicsEllipseItem (full circle): int ✓ (phase 4 vs segments),
    cen ✓, qua ✓, per ✓, tan ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        # Circle centered at (100, 100), radius 50
        self.item = QGraphicsEllipseItem(50, 50, 100, 100)
        self.scene.addItem(self.item)

    def test_center(self):
        result = _find(_engine(), self.scene, QPointF(100, 100 + OFFSET))
        _assert_snap(result, "center", QPointF(100, 100))

    def test_quadrant_right(self):
        result = _find(
            _engine(snap_center=False),
            self.scene, QPointF(150 + OFFSET, 100))
        _assert_snap(result, "quadrant", QPointF(150, 100))

    def test_quadrant_top(self):
        result = _find(
            _engine(snap_center=False),
            self.scene, QPointF(100, 50 - OFFSET))
        _assert_snap(result, "quadrant", QPointF(100, 50))

    def test_intersection(self):
        _crossing_line(self.scene, x=100)
        result = _find(_engine(), self.scene,
                        QPointF(100, 50 - OFFSET))
        _assert_snap(result, "intersection", QPointF(100, 50))

    def test_perpendicular(self):
        # Cursor outside circle, closest point on circumference
        result = _find(
            _engine(snap_center=False, snap_quadrant=False),
            self.scene, QPointF(100 + 80, 100))
        _assert_snap(result, "perpendicular", QPointF(150, 100))

    def test_tangent(self):
        # Cursor outside circle — tangent point on the top of the circle
        # Place cursor far above and to the right
        cursor = QPointF(100, 100 - 120)  # directly above, d=120 > r=50
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
        _assert_snap(result, "nearest", QPointF(150, 100))
```

- [ ] **Step 10: Run full circle tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestFullCircle -v`

Expected: All 7 tests PASS.

- [ ] **Step 11: Add QGraphicsEllipseItem (Node) tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

- [ ] **Step 12: Run Node tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestNodeCircle -v`

Expected: All 2 tests PASS.

- [ ] **Step 13: Add WallSegment tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

- [ ] **Step 14: Run WallSegment tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestWallSegment -v`

Expected: All 3 tests PASS.

- [ ] **Step 15: Add PolylineItem tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

- [ ] **Step 16: Run PolylineItem tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestPolylineItem -v`

Expected: All 6 tests PASS.

- [ ] **Step 17: Add ArcItem tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
# ── ArcItem ──────────────────────────────────────────────────────────────────

class TestArcItem:
    """ArcItem: end ✓ (start/end), mid ✓ (angular), int ✓ (phase 4 vs segments),
    cen ✓, qua ✓ (in-range), per ✓, tan ✓, nea ✓."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.scene = _scene()
        # Arc: center (0,0), radius 100, start 0°, span 90° (CCW)
        # In Qt's Y-down coordinate system with atan2(-dy, dx):
        #   0°  → point (100, 0)
        #   90° → point (0, -100)
        #   45° → point (≈70.7, ≈-70.7)
        self.item = ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0)
        self.scene.addItem(self.item)

    def test_endpoint_start(self):
        """Start of arc at 0° → (100, 0)."""
        result = _find(_engine(), self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "endpoint", QPointF(100, 0))

    def test_endpoint_end(self):
        """End of arc at 90° → (0, -100)."""
        result = _find(_engine(), self.scene, QPointF(OFFSET, -100))
        _assert_snap(result, "endpoint", QPointF(0, -100))

    def test_midpoint(self):
        """Angular midpoint at 45° → (≈70.7, ≈-70.7)."""
        mid_x = 100 * math.cos(math.radians(45))
        mid_y = -100 * math.sin(math.radians(45))
        result = _find(_engine(), self.scene,
                        QPointF(mid_x + OFFSET, mid_y))
        _assert_snap(result, "midpoint", QPointF(mid_x, mid_y))

    def test_center(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_quadrant=False),
            self.scene, QPointF(0, OFFSET))
        _assert_snap(result, "center", QPointF(0, 0))

    def test_quadrant_0deg(self):
        """0° quadrant falls within 0°-90° arc → (100, 0)."""
        result = _find(
            _engine(snap_endpoint=False),
            self.scene, QPointF(100, OFFSET))
        _assert_snap(result, "quadrant", QPointF(100, 0))

    def test_intersection(self):
        _crossing_line(self.scene, x=50, y_range=200)
        # Arc at x=50: 100*cos(θ) = 50 → θ=60° → y = -100*sin(60°) ≈ -86.6
        expected_y = -100 * math.sin(math.radians(60))
        result = _find(_engine(), self.scene,
                        QPointF(50, expected_y + OFFSET))
        _assert_snap(result, "intersection", QPointF(50, expected_y))

    def test_perpendicular(self):
        # Cursor outside arc, nearest point on circumference in arc range
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_quadrant=False),
            self.scene, QPointF(150, 0))
        _assert_snap(result, "perpendicular", QPointF(100, 0))

    def test_tangent(self):
        """Cursor outside the arc radius, tangent point on the visible arc."""
        # Place cursor at (200, 0) — outside radius 100
        cursor = QPointF(200, 0)
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_quadrant=False,
                    snap_perpendicular=False, snap_nearest=False),
            self.scene, cursor)
        assert result is not None, "expected tangent snap"
        assert result.snap_type == "tangent"
        # Tangent point must lie on the visible arc (0°-90° range)
        tp = result.point
        tp_angle = math.degrees(math.atan2(-tp.y(), tp.x())) % 360
        assert 0 <= tp_angle <= 90 + 1, (
            f"tangent point at {tp_angle}° is outside the arc's 0°-90° range"
        )

    def test_nearest(self):
        result = _find(
            _engine(snap_endpoint=False, snap_midpoint=False,
                    snap_center=False, snap_quadrant=False,
                    snap_perpendicular=False),
            self.scene, QPointF(150, 0))
        _assert_snap(result, "nearest", QPointF(100, 0))
```

- [ ] **Step 18: Run ArcItem tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestArcItem -v`

Expected: All 9 tests PASS.

- [ ] **Step 19: Add QGraphicsPathItem (DXF) tests**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

- [ ] **Step 20: Run DXF path tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestDXFPathItem -v`

Expected: All 6 tests PASS.

- [ ] **Step 21: Add HatchItem negative test**

Append to `tests/test_snap_engine_matrix.py`:

```python
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
```

- [ ] **Step 22: Run HatchItem negative test**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py::TestHatchItem -v`

Expected: 1 test PASS.

- [ ] **Step 23: Run full test suite**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_snap_engine_matrix.py tests/test_snap_engine_case_studies.py tests/test_snap_nearest_perpendicular_decoupling.py tests/test_snap_engine_primitives.py -v`

Expected: All tests PASS (existing + new).

- [ ] **Step 24: Commit**

```bash
git add tests/test_snap_engine_matrix.py
git commit -m "test(snap): add Layer 2 matrix fixture test harness

One test class per item type in snap spec §5 matrix, one method per
✓-cell. Covers: LineItem, GridlineItem, QGraphicsLineItem, RectangleItem,
QGraphicsEllipseItem (full circle + Node), WallSegment, PolylineItem,
ArcItem, QGraphicsPathItem (DXF). Includes HatchItem negative test.

Closes snap-spec roadmap item 9."
```

---

## Self-Review Checklist

**1. Spec coverage:**
- Roadmap item 2 (phase-4 filter audit) → Task 1 ✓
- Roadmap item 7 (QGraphicsPathItem phase-4 segments) → Task 1 ✓
- Roadmap item 6 (ArcItem tangent) → Task 2 ✓
- Roadmap item 9 (matrix fixture tests) → Task 3 ✓
- DXF underlay group descent (spec §13 Q2) → Task 1 ✓
- HatchItem exclusion (spec §5 "all-N/A") → Task 1 + Task 3 negative test ✓

**2. Placeholder scan:** No TBD/TODO/placeholders found. All steps have code.

**3. Type consistency:** `_engine()`, `_scene()`, `_find()`, `_assert_snap()`, `_crossing_line()`, `_add_wall()` — used consistently throughout. `SnapEngine` API (`find()`, `_geometric_snaps`) matches the read source. `ArcItem` constructor signature matches `construction_geometry.py:806`. `HatchItem` constructor needs verification — see note below.

**Note:** The `HatchItem.__init__` signature should be checked during implementation. The test in Step 21 assumes `HatchItem(path, offset_point)` — if the constructor differs, adjust accordingly.
