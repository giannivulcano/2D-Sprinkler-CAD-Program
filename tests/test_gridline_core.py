"""Unit tests for GridlineItem core features: lock, perpendicular move, level independence."""
import sys
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.gridline import GridlineItem


@pytest.fixture
def scene(qapp):
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


@pytest.fixture
def vertical_gl(scene):
    """Vertical gridline at x=1000, from y=0 to y=5000."""
    gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000))
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


@pytest.fixture
def horizontal_gl(scene):
    """Horizontal gridline at y=2000, from x=0 to x=5000."""
    gl = GridlineItem(QPointF(0, 2000), QPointF(5000, 2000))
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


class TestLock:
    def test_default_unlocked(self, vertical_gl):
        assert vertical_gl.locked is False

    def test_lock_prevents_grip_drag(self, vertical_gl):
        vertical_gl.locked = True
        original_p1 = QPointF(vertical_gl.line().p1())
        vertical_gl.apply_grip(0, QPointF(1000, -500))
        assert vertical_gl.line().p1().y() == pytest.approx(original_p1.y())

    def test_lock_prevents_perpendicular_move(self, vertical_gl):
        vertical_gl.locked = True
        original_x = vertical_gl.line().p1().x()
        vertical_gl.move_perpendicular(200.0)
        assert vertical_gl.line().p1().x() == pytest.approx(original_x)

    def test_unlock_allows_grip_drag(self, vertical_gl):
        vertical_gl.locked = True
        vertical_gl.locked = False
        vertical_gl.apply_grip(0, QPointF(1000, -500))
        assert vertical_gl.line().p1().y() != 0.0


class TestPerpendicularMove:
    def test_move_perpendicular_vertical_gl(self, vertical_gl):
        """Vertical gridline (dx=0): perpendicular is X direction."""
        vertical_gl.move_perpendicular(200.0)
        assert vertical_gl.line().p1().x() == pytest.approx(1200.0)
        assert vertical_gl.line().p2().x() == pytest.approx(1200.0)
        assert vertical_gl.line().p1().y() == pytest.approx(0.0)
        assert vertical_gl.line().p2().y() == pytest.approx(5000.0)

    def test_move_perpendicular_horizontal_gl(self, horizontal_gl):
        """Horizontal gridline (dy=0): perpendicular is Y direction."""
        horizontal_gl.move_perpendicular(-300.0)
        assert horizontal_gl.line().p1().y() == pytest.approx(1700.0)
        assert horizontal_gl.line().p2().y() == pytest.approx(1700.0)
        assert horizontal_gl.line().p1().x() == pytest.approx(0.0)
        assert horizontal_gl.line().p2().x() == pytest.approx(5000.0)

    def test_set_perpendicular_position_vertical(self, vertical_gl):
        vertical_gl.set_perpendicular_position(2500.0)
        assert vertical_gl.line().p1().x() == pytest.approx(2500.0)
        assert vertical_gl.line().p2().x() == pytest.approx(2500.0)

    def test_set_perpendicular_position_horizontal(self, horizontal_gl):
        horizontal_gl.set_perpendicular_position(500.0)
        assert horizontal_gl.line().p1().y() == pytest.approx(500.0)
        assert horizontal_gl.line().p2().y() == pytest.approx(500.0)


class TestGripConstraint:
    def test_grip_constrained_along_direction(self, vertical_gl):
        vertical_gl.apply_grip(0, QPointF(1500, -300))
        assert vertical_gl.line().p1().x() == pytest.approx(1000.0)
        assert vertical_gl.line().p1().y() == pytest.approx(-300.0, abs=1.0)


class TestLevelIndependence:
    def test_no_level_attribute(self, vertical_gl):
        assert not hasattr(vertical_gl, 'level')

    def test_serialization_no_level(self, vertical_gl):
        d = vertical_gl.to_dict()
        assert 'level' not in d

    def test_from_dict_ignores_level(self, scene):
        d = {
            "p1": [0, 0], "p2": [0, 5000],
            "label": "A", "level": "Level 2"
        }
        gl = GridlineItem.from_dict(d)
        assert not hasattr(gl, 'level')
