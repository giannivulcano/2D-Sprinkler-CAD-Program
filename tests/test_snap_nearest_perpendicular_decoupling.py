"""Regression test for snap-engine roadmap item 5 (docs/specs/snapping-engine.md §12).

When both ``snap_perpendicular`` and ``snap_nearest`` are enabled,
``_geometric_snaps`` must emit BOTH a ``perpendicular`` and a ``nearest``
candidate at the foot-of-perpendicular point. Prior to the fix the
``nearest`` branch was nested under ``elif``, silencing it whenever
``snap_perpendicular`` was on.
"""

from __future__ import annotations

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtWidgets import QGraphicsLineItem

from firepro3d.snap_engine import SnapEngine


def _make_engine(perp: bool, nearest: bool) -> SnapEngine:
    engine = SnapEngine()
    engine.snap_perpendicular = perp
    engine.snap_nearest = nearest
    return engine


def test_both_emitted_when_both_toggles_on(qapp):
    """Both candidates must appear at the same foot point."""
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=True, nearest=True)

    results = engine._geometric_snaps(QPointF(50, 20), line)

    types = [t for t, _ in results]
    assert "perpendicular" in types
    assert "nearest" in types

    perp_pt = next(p for t, p in results if t == "perpendicular")
    near_pt = next(p for t, p in results if t == "nearest")
    assert abs(perp_pt.x() - near_pt.x()) < 1e-9
    assert abs(perp_pt.y() - near_pt.y()) < 1e-9


def test_only_perpendicular_when_nearest_off(qapp):
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=True, nearest=False)
    types = [t for t, _ in engine._geometric_snaps(QPointF(50, 20), line)]
    assert "perpendicular" in types
    assert "nearest" not in types


def test_only_nearest_when_perpendicular_off(qapp):
    """Previously broken: nearest was unreachable under the elif."""
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=False, nearest=True)
    types = [t for t, _ in engine._geometric_snaps(QPointF(50, 20), line)]
    assert "nearest" in types
    assert "perpendicular" not in types
