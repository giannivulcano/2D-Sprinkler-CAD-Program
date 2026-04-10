# Grid System Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate gridlines into a single canonical `GridlineItem` with lock, pull-tab grips, perpendicular reposition, on-selection spacing dimensions, edit-existing dialog, and proper elevation projection.

**Architecture:** Modify `gridline.py` as the single canonical class, absorbing lock/grips/perpendicular-move from the legacy `grid_line.py` (then remove it). Update `grid_lines_dialog.py` for edit-existing with identity-tracked diff reconciliation. Update `elevation_scene.py` for cardinal-only filtering and per-view Z-extent overrides. Add spacing dimension rendering to `model_view.py` and spacing interaction to `model_space.py`.

**Tech Stack:** Python 3.x, PyQt6, pytest

**Spec:** `docs/specs/grid-system.md`

---

### Task 1: Remove Legacy `grid_line.py` and Clean Imports

**Files:**
- Delete: `firepro3d/grid_line.py`
- Modify: any files importing `GridLine` from `grid_line`

- [ ] **Step 1: Find all imports of GridLine**

Run: `grep -rn "grid_line\|GridLine" firepro3d/ --include="*.py" | grep -v "__pycache__"`

Note every file that imports from `grid_line` or references `GridLine`.

- [ ] **Step 2: Remove imports and references**

In each file found in Step 1, remove the import line and any usage of `GridLine`. If there is fallback logic that creates `GridLine` instances (e.g., in serialization loaders), replace with `GridlineItem` usage or remove the branch.

- [ ] **Step 3: Delete `grid_line.py`**

```bash
git rm firepro3d/grid_line.py
```

- [ ] **Step 4: Run the application to verify no import errors**

Run: `cd "D:\Custom Code\FirePro3D" && python -c "from firepro3d.gridline import GridlineItem; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add -A firepro3d/grid_line.py firepro3d/
git commit -m "refactor(grid): remove legacy GridLine class (grid_line.py)"
```

---

### Task 2: Add Lock, Perpendicular Move, and Level Independence to `GridlineItem`

**Files:**
- Modify: `firepro3d/gridline.py`
- Test: `tests/test_gridline_core.py`

- [ ] **Step 1: Write failing tests for lock, perpendicular move, and level removal**

Create `tests/test_gridline_core.py`:

```python
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
        # Y unchanged
        assert vertical_gl.line().p1().y() == pytest.approx(0.0)
        assert vertical_gl.line().p2().y() == pytest.approx(5000.0)

    def test_move_perpendicular_horizontal_gl(self, horizontal_gl):
        """Horizontal gridline (dy=0): perpendicular is Y direction."""
        horizontal_gl.move_perpendicular(-300.0)
        assert horizontal_gl.line().p1().y() == pytest.approx(1700.0)
        assert horizontal_gl.line().p2().y() == pytest.approx(1700.0)
        # X unchanged
        assert horizontal_gl.line().p1().x() == pytest.approx(0.0)
        assert horizontal_gl.line().p2().x() == pytest.approx(5000.0)

    def test_set_perpendicular_position_vertical(self, vertical_gl):
        """set_perpendicular_position sets the X coordinate of a vertical gridline."""
        vertical_gl.set_perpendicular_position(2500.0)
        assert vertical_gl.line().p1().x() == pytest.approx(2500.0)
        assert vertical_gl.line().p2().x() == pytest.approx(2500.0)

    def test_set_perpendicular_position_horizontal(self, horizontal_gl):
        """set_perpendicular_position sets the Y coordinate of a horizontal gridline."""
        horizontal_gl.set_perpendicular_position(500.0)
        assert horizontal_gl.line().p1().y() == pytest.approx(500.0)
        assert horizontal_gl.line().p2().y() == pytest.approx(500.0)


class TestGripConstraint:
    def test_grip_constrained_along_direction(self, vertical_gl):
        """Grip drag on vertical gridline only moves along Y (line direction)."""
        vertical_gl.apply_grip(0, QPointF(1500, -300))
        # X should stay at 1000 (constrained), Y should move
        assert vertical_gl.line().p1().x() == pytest.approx(1000.0)
        assert vertical_gl.line().p1().y() == pytest.approx(-300.0, abs=1.0)


class TestLevelIndependence:
    def test_no_level_attribute(self, vertical_gl):
        """GridlineItem should not have a level field."""
        assert not hasattr(vertical_gl, 'level')

    def test_serialization_no_level(self, vertical_gl):
        """to_dict should not include a level key."""
        d = vertical_gl.to_dict()
        assert 'level' not in d

    def test_from_dict_ignores_level(self, scene):
        """from_dict should silently ignore a level field."""
        d = {
            "p1": [0, 0], "p2": [0, 5000],
            "label": "A", "level": "Level 2"
        }
        gl = GridlineItem.from_dict(d)
        assert not hasattr(gl, 'level')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py -v`
Expected: Multiple FAILs — `locked` property doesn't exist, `move_perpendicular` doesn't exist, `level` attribute still present.

- [ ] **Step 3: Implement lock property on GridlineItem**

In `firepro3d/gridline.py`, add to `GridlineItem.__init__`:

```python
self._locked = False
```

Add property:

```python
@property
def locked(self) -> bool:
    return self._locked

@locked.setter
def locked(self, value: bool):
    self._locked = value
```

Add lock guard to `apply_grip()` — at the top of the method, before any logic:

```python
if self._locked:
    return
```

- [ ] **Step 4: Implement perpendicular move methods**

In `firepro3d/gridline.py`, add to `GridlineItem`:

```python
def _perpendicular_vector(self) -> tuple[float, float]:
    """Return the unit perpendicular vector to this gridline's direction."""
    line = self.line()
    dx = line.p2().x() - line.p1().x()
    dy = line.p2().y() - line.p1().y()
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return (1.0, 0.0)
    # Perpendicular: rotate direction 90° CCW
    return (-dy / length, dx / length)

def move_perpendicular(self, offset: float):
    """Shift the entire gridline perpendicular to its direction by offset mm."""
    if self._locked:
        return
    px, py = self._perpendicular_vector()
    line = self.line()
    p1 = line.p1()
    p2 = line.p2()
    new_p1 = QPointF(p1.x() + offset * px, p1.y() + offset * py)
    new_p2 = QPointF(p2.x() + offset * px, p2.y() + offset * py)
    self.setLine(new_p1.x(), new_p1.y(), new_p2.x(), new_p2.y())
    self._update_bubble_positions()
    self.update()

def set_perpendicular_position(self, value: float):
    """Set the perpendicular coordinate to an absolute value."""
    if self._locked:
        return
    px, py = self._perpendicular_vector()
    line = self.line()
    p1 = line.p1()
    # Current perpendicular position = dot(p1, perp_vector)
    current = p1.x() * px + p1.y() * py
    self.move_perpendicular(value - current)
```

Add `import math` at the top if not already present.

- [ ] **Step 5: Remove level field**

In `firepro3d/gridline.py`:

Remove `self.level = "Level 1"` from `__init__` (or equivalent).

In `to_dict()`: remove the `"level"` key from the returned dict.

In `from_dict()`: do NOT read `"level"` from the dict (or read and discard it silently — do not assign it to the instance).

In `get_properties()` and `set_property()`: remove the "Level" property entry if present.

- [ ] **Step 6: Update serialization for lock and paper_height_mm**

In `GridlineItem.__init__`, add:

```python
self.paper_height_mm = 3.0
```

In `to_dict()`, add:

```python
"locked": self._locked,
"paper_height_mm": self.paper_height_mm,
```

In `from_dict()`, add:

```python
gl._locked = d.get("locked", False)
gl.paper_height_mm = d.get("paper_height_mm", 3.0)
```

Also handle old-format key renames in `from_dict()`:

```python
# Migration: old GridLine format compatibility
if "bubble_start" in d and "bubble1_vis" not in d:
    d["bubble1_vis"] = d["bubble_start"]
if "bubble_end" in d and "bubble2_vis" not in d:
    d["bubble2_vis"] = d["bubble_end"]
```

- [ ] **Step 7: Run tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py -v`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add firepro3d/gridline.py tests/test_gridline_core.py
git commit -m "feat(grid): add lock, perpendicular move, level independence to GridlineItem"
```

---

### Task 3: `ItemIgnoresTransformations` on Bubbles and Pull-Tab Grips

**Files:**
- Modify: `firepro3d/gridline.py`

- [ ] **Step 1: Refactor GridBubble to use ItemIgnoresTransformations**

In `firepro3d/gridline.py`, modify the `GridBubble` class:

```python
class GridBubble(QGraphicsEllipseItem):
    """Zoom-independent circle bubble with centered label."""

    RADIUS_PX = 14.0  # Screen pixels (constant size)
```

In `GridBubble.__init__`, add:

```python
self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
```

Update the ellipse rect to use the screen-pixel radius instead of the scene-scaled `BUBBLE_RADIUS_MM`:

```python
r = self.RADIUS_PX
self.setRect(-r, -r, 2 * r, 2 * r)
```

Update `_center_label()` to use the pixel-based radius for text positioning.

Remove the old `BUBBLE_RADIUS_MM` constant if it's no longer used.

- [ ] **Step 2: Add pull-tab grip children**

In `firepro3d/gridline.py`, add a `_PullTabGrip` class:

```python
_GRIP_HALF = 5.0  # Half-width of pull-tab square (screen pixels)


class _PullTabGrip(QGraphicsRectItem):
    """Small square grip handle at a gridline endpoint.

    Uses ItemIgnoresTransformations for constant screen size.
    Visible only when parent gridline is selected or hovered.
    """

    def __init__(self, parent: GridlineItem):
        super().__init__(-_GRIP_HALF, -_GRIP_HALF, 2 * _GRIP_HALF, 2 * _GRIP_HALF, parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(QColor(68, 136, 204, 60)))  # Semi-transparent blue
        self.setZValue(1)
        self.setVisible(False)
```

In `GridlineItem.__init__`, after creating bubbles, create grips:

```python
self._grip1 = _PullTabGrip(self)
self._grip2 = _PullTabGrip(self)
self._update_grip_positions()
```

Add `_update_grip_positions()`:

```python
def _update_grip_positions(self):
    """Position grips at endpoints, offset outward along line direction."""
    line = self.line()
    p1, p2 = line.p1(), line.p2()
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if length < 1e-12:
        self._grip1.setPos(p1)
        self._grip2.setPos(p2)
        return
    # Offset outward by a small amount (10 scene units)
    ux, uy = dx / length, dy / length
    self._grip1.setPos(p1.x() - ux * 10, p1.y() - uy * 10)
    self._grip2.setPos(p2.x() + ux * 10, p2.y() + uy * 10)
```

Call `_update_grip_positions()` at the end of `_update_bubble_positions()`.

- [ ] **Step 3: Show/hide grips on selection and hover**

In `GridlineItem.itemChange()`, when selection state changes:

```python
def itemChange(self, change, value):
    if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
        selected = bool(value)
        self._grip1.setVisible(selected)
        self._grip2.setVisible(selected)
    return super().itemChange(change, value)
```

Add hover events:

```python
def hoverEnterEvent(self, event):
    if not self.isSelected():
        self._grip1.setVisible(True)
        self._grip2.setVisible(True)
    super().hoverEnterEvent(event)

def hoverLeaveEvent(self, event):
    if not self.isSelected():
        self._grip1.setVisible(False)
        self._grip2.setVisible(False)
    super().hoverLeaveEvent(event)
```

Enable hover events in `__init__`:

```python
self.setAcceptHoverEvents(True)
```

- [ ] **Step 4: Smoke-test visually**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
Place a gridline. Verify:
- Bubbles stay constant screen size when zooming in/out
- Pull-tab grips appear on hover and selection
- Grips disappear when deselected and not hovered

- [ ] **Step 5: Commit**

```bash
git add firepro3d/gridline.py
git commit -m "feat(grid): add ItemIgnoresTransformations bubbles and pull-tab grips"
```

---

### Task 4: Auto-Numbering Counter Sync and Duplicate Detection

**Files:**
- Modify: `firepro3d/gridline.py`
- Test: `tests/test_gridline_core.py` (append)

- [ ] **Step 1: Write failing tests for counter sync and duplicate detection**

Append to `tests/test_gridline_core.py`:

```python
from firepro3d.gridline import (
    GridlineItem, reset_grid_counters, sync_grid_counters,
    _next_number, _next_letter_idx, auto_label,
)


class TestCounterSync:
    def test_sync_numbers(self, scene):
        """After loading gridlines labeled 1,2,5, counter should be 6."""
        reset_grid_counters()
        for label in ["1", "2", "5"]:
            gl = GridlineItem(QPointF(0, 0), QPointF(5000, 0), label=label)
            scene.addItem(gl)
            scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        # Next auto-label for horizontal should be "6"
        lbl = auto_label(QPointF(0, 0), QPointF(100, 0))
        assert lbl == "6"

    def test_sync_letters(self, scene):
        """After loading gridlines labeled A, C, counter should produce D."""
        reset_grid_counters()
        for label in ["A", "C"]:
            gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label=label)
            scene.addItem(gl)
            scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        # Next auto-label for vertical should be "D"
        lbl = auto_label(QPointF(0, 0), QPointF(0, 100))
        assert lbl == "D"

    def test_sync_multi_letter(self, scene):
        """After loading gridlines up to AA, counter should produce AB."""
        reset_grid_counters()
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="AA")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        lbl = auto_label(QPointF(0, 0), QPointF(0, 100))
        assert lbl == "AB"

    def test_sync_ignores_custom_labels(self, scene):
        """Custom labels like 'X-1' are ignored by sync."""
        reset_grid_counters()
        gl = GridlineItem(QPointF(0, 0), QPointF(5000, 0), label="X-1")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        lbl = auto_label(QPointF(0, 0), QPointF(100, 0))
        assert lbl == "1"


class TestDuplicateDetection:
    def test_duplicate_detected(self, scene):
        gl_a = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        gl_a2 = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl_a)
        scene.addItem(gl_a2)
        scene._gridlines = [gl_a, gl_a2]
        from firepro3d.gridline import check_duplicate_labels
        dupes = check_duplicate_labels(scene._gridlines)
        assert gl_a in dupes
        assert gl_a2 in dupes

    def test_no_duplicate(self, scene):
        gl_a = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        gl_b = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="B")
        scene.addItem(gl_a)
        scene.addItem(gl_b)
        scene._gridlines = [gl_a, gl_b]
        from firepro3d.gridline import check_duplicate_labels
        dupes = check_duplicate_labels(scene._gridlines)
        assert len(dupes) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py::TestCounterSync -v`
Expected: ImportError — `sync_grid_counters` not defined.

- [ ] **Step 3: Implement `sync_grid_counters()`**

In `firepro3d/gridline.py`, add:

```python
def _label_to_letter_idx(label: str) -> int | None:
    """Convert a letter label (A-Z, AA, AB, ...) to its counter index.

    Returns None if label is not a valid letter sequence.
    """
    if not label.isalpha():
        return None
    label = label.upper()
    if len(label) == 1:
        return ord(label) - ord('A')
    elif len(label) == 2:
        return 26 + (ord(label[0]) - ord('A')) * 26 + (ord(label[1]) - ord('A'))
    return None


def sync_grid_counters(gridlines: list[GridlineItem]):
    """Reset global counters to max+1 based on existing gridline labels.

    Call after file load, undo/redo, or dialog accept.
    """
    global _next_number, _next_letter_idx
    max_num = 0
    max_letter = -1
    for gl in gridlines:
        label = gl.grid_label
        # Try as number
        try:
            n = int(label)
            max_num = max(max_num, n)
            continue
        except ValueError:
            pass
        # Try as letter
        idx = _label_to_letter_idx(label)
        if idx is not None:
            max_letter = max(max_letter, idx)
    _next_number = max_num + 1
    _next_letter_idx = max_letter + 1
```

- [ ] **Step 4: Implement `check_duplicate_labels()`**

In `firepro3d/gridline.py`, add:

```python
def check_duplicate_labels(gridlines: list[GridlineItem]) -> set[GridlineItem]:
    """Return the set of gridlines that share a label with another gridline."""
    from collections import Counter
    label_counts = Counter(gl.grid_label for gl in gridlines)
    return {gl for gl in gridlines if label_counts[gl.grid_label] > 1}
```

- [ ] **Step 5: Wire duplicate warning to bubble rendering**

In `GridlineItem`, add a method to update bubble border color based on duplicate state:

```python
def update_duplicate_warning(self, is_duplicate: bool):
    """Set bubble border to orange warning if duplicate, else restore normal color."""
    color = QColor("#ff8800") if is_duplicate else self._grid_color
    pen = QPen(color, 2)
    self.bubble1.setPen(pen)
    self.bubble2.setPen(pen)
```

Add a module-level function to apply duplicate warnings across all gridlines:

```python
def apply_duplicate_warnings(gridlines: list[GridlineItem]):
    """Scan for duplicate labels and update bubble border colors."""
    dupes = check_duplicate_labels(gridlines)
    for gl in gridlines:
        gl.update_duplicate_warning(gl in dupes)
```

Call `apply_duplicate_warnings(scene._gridlines)` after any label change: in `set_property()` when key is "Label", in `sync_grid_counters()`, and in `apply_grid_dialog()`.

- [ ] **Step 6: Run tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add firepro3d/gridline.py tests/test_gridline_core.py
git commit -m "feat(grid): add counter sync, duplicate detection, and warning visuals"
```

---

### Task 5: Serialization Round-Trip and Migration Tests

**Files:**
- Test: `tests/test_gridline_core.py` (append)

- [ ] **Step 1: Write serialization tests**

Append to `tests/test_gridline_core.py`:

```python
class TestSerialization:
    def test_round_trip(self, scene):
        """to_dict → from_dict preserves all fields."""
        gl = GridlineItem(QPointF(100, 200), QPointF(100, 5200), label="C")
        gl.locked = True
        gl.set_bubble_visible(1, False)
        gl.paper_height_mm = 4.5
        gl.user_layer = "Gridlines"

        d = gl.to_dict()
        gl2 = GridlineItem.from_dict(d)

        assert gl2.grid_label == "C"
        assert gl2.locked is True
        assert gl2.paper_height_mm == pytest.approx(4.5)
        assert gl2.user_layer == "Gridlines"
        assert gl2.line().p1().x() == pytest.approx(100.0)
        assert gl2.line().p1().y() == pytest.approx(200.0)
        assert gl2.line().p2().x() == pytest.approx(100.0)
        assert gl2.line().p2().y() == pytest.approx(5200.0)

    def test_migration_old_format(self, scene):
        """Old GridLine format loads correctly into GridlineItem."""
        old = {
            "type": "grid_line",
            "label": "B",
            "axis": "x",
            "start": [500, 0],
            "end": [500, 3000],
            "locked": True,
            "bubble_start": True,
            "bubble_end": False,
        }
        gl = GridlineItem.from_dict(old)
        assert gl.grid_label == "B"
        assert gl.locked is True
        assert gl.line().p1().x() == pytest.approx(500.0)
        assert gl.line().p2().y() == pytest.approx(3000.0)
        # Defaults for missing fields
        assert gl.paper_height_mm == pytest.approx(3.0)
        assert gl.user_layer == "Default"

    def test_missing_fields_get_defaults(self, scene):
        """Minimal dict gets sensible defaults."""
        d = {"p1": [0, 0], "p2": [0, 1000], "label": "Z"}
        gl = GridlineItem.from_dict(d)
        assert gl.locked is False
        assert gl.paper_height_mm == pytest.approx(3.0)
        assert gl.user_layer == "Default"
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py::TestSerialization -v`
Expected: Failures where old-format migration doesn't work yet.

- [ ] **Step 3: Update `from_dict()` for full migration support**

In `firepro3d/gridline.py`, replace `from_dict()` with a version that handles both formats:

```python
@classmethod
def from_dict(cls, d: dict) -> GridlineItem:
    # Handle old GridLine format
    if "type" in d and d["type"] == "grid_line":
        p1 = d.get("start", [0, 0])
        p2 = d.get("end", [0, 0])
    else:
        p1 = d.get("p1", [0, 0])
        p2 = d.get("p2", [0, 0])

    label = d.get("label", "")

    gl = cls(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]), label=label)
    gl._locked = d.get("locked", False)
    gl.paper_height_mm = d.get("paper_height_mm", 3.0)
    gl.user_layer = d.get("user_layer", "Default")

    # Bubble visibility — handle both old and new key names
    if "bubble1_vis" in d:
        gl.set_bubble_visible(1, d["bubble1_vis"])
    elif "bubble_start" in d:
        gl.set_bubble_visible(1, d["bubble_start"])

    if "bubble2_vis" in d:
        gl.set_bubble_visible(2, d["bubble2_vis"])
    elif "bubble_end" in d:
        gl.set_bubble_visible(2, d["bubble_end"])

    # Display overrides
    gl._display_overrides = d.get("display_overrides", {})

    # Silently ignore "level" and "axis" fields
    return gl
```

- [ ] **Step 4: Run tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py::TestSerialization -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/gridline.py tests/test_gridline_core.py
git commit -m "test(grid): add serialization round-trip and migration tests"
```

---

### Task 6: Elevation Filtering — Cardinal Only

**Files:**
- Modify: `firepro3d/elevation_scene.py`
- Test: `tests/test_gridline_core.py` (append)

- [ ] **Step 1: Write failing tests for elevation filtering**

Append to `tests/test_gridline_core.py`:

```python
class TestElevationFiltering:
    """Test the cardinal-only rule for elevation gridline visibility."""

    def test_vertical_in_north(self):
        """Exactly vertical gridline (dx=0) should appear in North elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        # Vertical: p1=(1000,0), p2=(1000,5000), dx=0
        assert _is_cardinal_for_elevation(QPointF(1000, 0), QPointF(1000, 5000), "north") is True

    def test_vertical_not_in_east(self):
        """Vertical gridline should NOT appear in East elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        assert _is_cardinal_for_elevation(QPointF(1000, 0), QPointF(1000, 5000), "east") is False

    def test_horizontal_in_east(self):
        """Exactly horizontal gridline (dy=0) should appear in East elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        assert _is_cardinal_for_elevation(QPointF(0, 2000), QPointF(5000, 2000), "east") is True

    def test_horizontal_not_in_north(self):
        """Horizontal gridline should NOT appear in North elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        assert _is_cardinal_for_elevation(QPointF(0, 2000), QPointF(5000, 2000), "north") is False

    def test_angled_in_no_elevation(self):
        """Angled gridline should not appear in any elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        p1, p2 = QPointF(0, 0), QPointF(3000, 4000)
        for direction in ("north", "south", "east", "west"):
            assert _is_cardinal_for_elevation(p1, p2, direction) is False

    def test_nearly_vertical_excluded(self):
        """Gridline at 89.999° (dx=0.001) should NOT pass cardinal test."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        p1 = QPointF(1000, 0)
        p2 = QPointF(1000.1, 5000)  # dx=0.1, well above 1e-6 epsilon
        assert _is_cardinal_for_elevation(p1, p2, "north") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py::TestElevationFiltering -v`
Expected: ImportError — `_is_cardinal_for_elevation` not defined.

- [ ] **Step 3: Implement `_is_cardinal_for_elevation()`**

In `firepro3d/elevation_scene.py`, add a module-level helper function:

```python
_CARDINAL_EPSILON = 1e-6


def _is_cardinal_for_elevation(p1: QPointF, p2: QPointF, direction: str) -> bool:
    """Return True if the gridline defined by p1,p2 should appear in the given elevation.

    Only exactly-cardinal gridlines appear:
    - North/South: show gridlines where dx == 0 (vertical)
    - East/West: show gridlines where dy == 0 (horizontal)
    """
    dx = abs(p2.x() - p1.x())
    dy = abs(p2.y() - p1.y())
    if direction in ("north", "south"):
        return dx < _CARDINAL_EPSILON
    elif direction in ("east", "west"):
        return dy < _CARDINAL_EPSILON
    return False
```

- [ ] **Step 4: Wire into `_project_gridlines()`**

In `firepro3d/elevation_scene.py`, find the `_project_gridlines()` method. Replace the existing `_should_show_gridline()` / `_gridline_is_vertical()` filtering logic with a call to `_is_cardinal_for_elevation()`:

```python
for gl in self._ms._gridlines:
    if not gl.isVisible():
        continue
    line = gl.line()
    p1 = gl.mapToScene(line.p1())
    p2 = gl.mapToScene(line.p2())
    if not _is_cardinal_for_elevation(p1, p2, self._direction):
        continue
    # ... rest of projection logic unchanged
```

Remove the old `_gridline_is_vertical()` and `_should_show_gridline()` methods if they are now unused.

- [ ] **Step 5: Run tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_core.py::TestElevationFiltering -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add firepro3d/elevation_scene.py tests/test_gridline_core.py
git commit -m "feat(grid): cardinal-only elevation filtering with epsilon test"
```

---

### Task 7: Per-View Z-Extent Overrides in Elevation

**Files:**
- Modify: `firepro3d/elevation_scene.py`

- [ ] **Step 1: Add `_gridline_z_overrides` storage**

In `ElevationScene.__init__()`, add:

```python
self._gridline_z_overrides: dict[str, dict] = {}
# Keyed by gridline label → {"v_top": float, "v_bot": float}
```

- [ ] **Step 2: Apply overrides in `_project_gridlines()`**

After computing the default `v_top` and `v_bot` from the full building height (level extents), check for overrides:

```python
label = gl.grid_label
if label in self._gridline_z_overrides:
    ov = self._gridline_z_overrides[label]
    v_top = ov.get("v_top", v_top)
    v_bot = ov.get("v_bot", v_bot)
```

- [ ] **Step 3: Store overrides on grip drag**

In the `ElevGridlineItem` grip drag handler (mouseReleaseEvent or similar), after a grip is moved, write the override back to the parent scene:

```python
def _commit_grip_override(self):
    """Write current Z-extent back to the scene's override dict."""
    scene = self.scene()
    if scene and hasattr(scene, '_gridline_z_overrides'):
        line = self.line()
        scene._gridline_z_overrides[self._label] = {
            "v_top": line.p1().y(),
            "v_bot": line.p2().y(),
        }
```

Call this at the end of the grip drag release.

- [ ] **Step 4: Serialize/deserialize overrides**

In `ElevationScene.to_dict()`, add:

```python
"gridline_z_overrides": self._gridline_z_overrides,
```

In `ElevationScene.from_dict()` (or the equivalent loader), add:

```python
self._gridline_z_overrides = d.get("gridline_z_overrides", {})
```

- [ ] **Step 5: Smoke-test**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
Open an elevation view. Verify gridlines span full building height. Drag a grip to shorten. Close and reopen the elevation — verify the override persists.

- [ ] **Step 6: Commit**

```bash
git add firepro3d/elevation_scene.py
git commit -m "feat(grid): per-view Z-extent overrides in elevation projections"
```

---

### Task 8: Body Drag (Perpendicular Constraint) in Model Space

**Files:**
- Modify: `firepro3d/model_space.py`

- [ ] **Step 1: Identify the drag handling code path**

In `model_space.py`, find the mouse event handlers that handle item dragging. Look for `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent` in the select/drag mode. The pattern is:
- On press: identify which item is hit, store drag start state
- On move: compute delta, move items
- On release: push undo state

- [ ] **Step 2: Add gridline body drag detection**

In the mouse press handler for select mode, after existing grip-hit detection, add gridline body detection:

```python
# Check if clicking on a gridline body (not bubble, not grip)
if isinstance(hit_item, GridlineItem) or (
    hasattr(hit_item, 'parentItem') and isinstance(hit_item.parentItem(), GridlineItem)
):
    gl = hit_item if isinstance(hit_item, GridlineItem) else hit_item.parentItem()
    if not gl.locked:
        self._dragging_gridline = gl
        self._gridline_drag_start = snapped_pos
        self._gridline_drag_original_pos = gl.line().p1()
```

- [ ] **Step 3: Implement constrained perpendicular movement on mouse move**

In the mouse move handler, when `self._dragging_gridline` is set:

```python
if self._dragging_gridline:
    gl = self._dragging_gridline
    delta_x = current_pos.x() - self._gridline_drag_start.x()
    delta_y = current_pos.y() - self._gridline_drag_start.y()
    px, py = gl._perpendicular_vector()
    # Project delta onto perpendicular direction
    perp_offset = delta_x * px + delta_y * py
    # Restore to original position + projected offset
    orig = self._gridline_drag_original_pos
    gl.set_perpendicular_position(orig.x() * px + orig.y() * py + perp_offset)
```

- [ ] **Step 4: Finalize on mouse release**

In the mouse release handler:

```python
if self._dragging_gridline:
    self.push_undo_state()
    self._dragging_gridline = None
```

- [ ] **Step 5: Initialize drag state variables**

In `__init__` (or the appropriate initialization section):

```python
self._dragging_gridline = None
self._gridline_drag_start = None
self._gridline_drag_original_pos = None
```

- [ ] **Step 6: Smoke-test**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
Place a vertical gridline. Click its body (the dashed line) and drag. Verify:
- Gridline moves only horizontally (perpendicular to its vertical direction)
- Bubbles and grips follow
- Undo reverts the move
- Locked gridline does not move

- [ ] **Step 7: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "feat(grid): constrained perpendicular body drag for gridlines"
```

---

### Task 9: On-Selection Spacing Dimensions

**Files:**
- Modify: `firepro3d/model_space.py` (selection change handler)
- Modify: `firepro3d/model_view.py` (dimension rendering)

- [ ] **Step 1: Compute spacing data on selection change**

In `model_space.py`, find the selection change handler (connected to `selectionChanged` signal or called from it). Add logic to compute spacing dimensions when gridlines are selected:

```python
def _compute_gridline_spacing(self) -> list[dict]:
    """Compute spacing dimensions for selected gridlines.

    Returns list of dicts: {
        "from_gl": GridlineItem, "to_gl": GridlineItem,
        "distance": float, "midpoint": QPointF,
        "perp_vector": (float, float)
    }
    """
    selected = [item for item in self.selectedItems()
                if isinstance(item, GridlineItem)]
    if not selected:
        return []

    all_gls = self._gridlines
    results = []

    for gl in selected:
        px, py = gl._perpendicular_vector()
        gl_perp_pos = gl.line().p1().x() * px + gl.line().p1().y() * py

        # Find parallel neighbors (same orientation classification)
        gl_dx = abs(gl.line().p2().x() - gl.line().p1().x())
        gl_dy = abs(gl.line().p2().y() - gl.line().p1().y())
        gl_is_vertical = gl_dy >= gl_dx

        neighbors = []
        for other in all_gls:
            if other is gl or other in selected:
                continue
            o_dx = abs(other.line().p2().x() - other.line().p1().x())
            o_dy = abs(other.line().p2().y() - other.line().p1().y())
            o_is_vertical = o_dy >= o_dx
            if o_is_vertical != gl_is_vertical:
                continue
            o_perp_pos = other.line().p1().x() * px + other.line().p1().y() * py
            neighbors.append((other, o_perp_pos))

        # Find nearest on each side
        before = [(o, p) for o, p in neighbors if p < gl_perp_pos]
        after = [(o, p) for o, p in neighbors if p > gl_perp_pos]

        if before:
            nearest_before = max(before, key=lambda x: x[1])
            dist = gl_perp_pos - nearest_before[1]
            mid_perp = (gl_perp_pos + nearest_before[1]) / 2
            # Compute midpoint in scene coords
            gl_mid_along = QPointF(
                (gl.line().p1().x() + gl.line().p2().x()) / 2,
                (gl.line().p1().y() + gl.line().p2().y()) / 2,
            )
            midpoint = QPointF(
                mid_perp * px + gl_mid_along.x() * (1 - abs(px)),
                mid_perp * py + gl_mid_along.y() * (1 - abs(py)),
            )
            results.append({
                "from_gl": nearest_before[0], "to_gl": gl,
                "distance": abs(dist), "midpoint": midpoint,
                "perp_vector": (px, py),
            })

        if after:
            nearest_after = min(after, key=lambda x: x[1])
            dist = nearest_after[1] - gl_perp_pos
            mid_perp = (gl_perp_pos + nearest_after[1]) / 2
            gl_mid_along = QPointF(
                (gl.line().p1().x() + gl.line().p2().x()) / 2,
                (gl.line().p1().y() + gl.line().p2().y()) / 2,
            )
            midpoint = QPointF(
                mid_perp * px + gl_mid_along.x() * (1 - abs(px)),
                mid_perp * py + gl_mid_along.y() * (1 - abs(py)),
            )
            results.append({
                "from_gl": gl, "to_gl": nearest_after[0],
                "distance": abs(dist), "midpoint": midpoint,
                "perp_vector": (px, py),
            })

    # Deduplicate (same pair may appear from both directions)
    seen = set()
    deduped = []
    for r in results:
        key = (id(r["from_gl"]), id(r["to_gl"]))
        rev_key = (id(r["to_gl"]), id(r["from_gl"]))
        if key not in seen and rev_key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
```

Store the computed spacing on selection change:

```python
self._gridline_spacing_dims = self._compute_gridline_spacing()
self.update()  # Trigger view repaint
```

- [ ] **Step 2: Render spacing dimensions in model_view.py**

In `model_view.py`, find the `paintEvent` or overlay drawing method (likely where `DimensionalConstraint` visuals are drawn, around line 349). Add gridline spacing rendering after the existing constraint rendering:

```python
# Gridline spacing dimensions
if hasattr(scene, '_gridline_spacing_dims'):
    for dim in scene._gridline_spacing_dims:
        from_gl = dim["from_gl"]
        to_gl = dim["to_gl"]
        distance = dim["distance"]

        # Get perpendicular positions on the gridlines
        px, py = dim["perp_vector"]
        from_perp = from_gl.line().p1().x() * px + from_gl.line().p1().y() * py
        to_perp = to_gl.line().p1().x() * px + to_gl.line().p1().y() * py

        # Compute screen points at the midpoint of each gridline
        from_mid = QPointF(
            (from_gl.line().p1().x() + from_gl.line().p2().x()) / 2,
            (from_gl.line().p1().y() + from_gl.line().p2().y()) / 2,
        )
        to_mid = QPointF(
            (to_gl.line().p1().x() + to_gl.line().p2().x()) / 2,
            (to_gl.line().p1().y() + to_gl.line().p2().y()) / 2,
        )

        vp_from = self.mapFromScene(from_mid)
        vp_to = self.mapFromScene(to_mid)

        color = QColor("#0066cc")

        # Dimension line (dashed)
        painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(vp_from, vp_to)

        # Witness ticks at each end
        dx = vp_to.x() - vp_from.x()
        dy = vp_to.y() - vp_from.y()
        length = math.hypot(dx, dy)
        if length > 1:
            nx = -dy / length * 6
            ny = dx / length * 6
            painter.setPen(QPen(color, 1.5))
            painter.drawLine(vp_from.x() - nx, vp_from.y() - ny,
                           vp_from.x() + nx, vp_from.y() + ny)
            painter.drawLine(vp_to.x() - nx, vp_to.y() - ny,
                           vp_to.x() + nx, vp_to.y() + ny)

        # Distance label
        midpoint = QPointF((vp_from.x() + vp_to.x()) / 2,
                          (vp_from.y() + vp_to.y()) / 2)
        sm = scene.scale_manager if hasattr(scene, 'scale_manager') else None
        if sm:
            text = sm.format_distance(distance)
        else:
            text = f"{distance:.1f}"
        painter.setPen(QPen(color))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(midpoint.x() + 4, midpoint.y() - 4, text)
```

- [ ] **Step 3: Smoke-test**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
Place 3 vertical gridlines at different X positions. Select one:
- Verify dashed blue dimension lines appear to nearest neighbors on each side
- Verify distance labels show in display units
- Deselect: dimensions disappear

- [ ] **Step 4: Commit**

```bash
git add firepro3d/model_space.py firepro3d/model_view.py
git commit -m "feat(grid): on-selection spacing dimensions between parallel gridlines"
```

---

### Task 10: Double-Click Spacing Edit

**Files:**
- Modify: `firepro3d/model_view.py` (double-click detection)
- Modify: `firepro3d/model_space.py` (apply spacing edit)

- [ ] **Step 1: Detect double-click on spacing dimension**

In `model_view.py`, add or modify `mouseDoubleClickEvent`:

```python
def mouseDoubleClickEvent(self, event):
    scene = self.scene()
    if not hasattr(scene, '_gridline_spacing_dims'):
        return super().mouseDoubleClickEvent(event)

    click_pos = self.mapToScene(event.pos())
    HIT_TOLERANCE = 20  # pixels

    for dim in scene._gridline_spacing_dims:
        midpoint = dim["midpoint"]
        vp_mid = self.mapFromScene(midpoint)
        dist = math.hypot(event.pos().x() - vp_mid.x(),
                         event.pos().y() - vp_mid.y())
        if dist < HIT_TOLERANCE:
            self._start_spacing_edit(dim, event.pos())
            return

    super().mouseDoubleClickEvent(event)
```

- [ ] **Step 2: Implement inline text edit for spacing**

```python
def _start_spacing_edit(self, dim: dict, screen_pos):
    """Show an inline QLineEdit for editing gridline spacing."""
    from PyQt6.QtWidgets import QLineEdit

    scene = self.scene()
    sm = scene.scale_manager if hasattr(scene, 'scale_manager') else None
    current_display = sm.scene_to_display(dim["distance"]) if sm else dim["distance"]

    editor = QLineEdit(self)
    editor.setText(f"{current_display:.2f}")
    editor.setFixedWidth(80)
    editor.move(int(screen_pos.x()) - 40, int(screen_pos.y()) - 12)
    editor.selectAll()
    editor.show()
    editor.setFocus()

    def _accept():
        try:
            new_display_val = float(editor.text())
            new_scene_val = sm.display_to_scene(new_display_val) if sm else new_display_val
            scene._apply_spacing_edit(dim, new_scene_val)
        except ValueError:
            pass
        editor.deleteLater()

    editor.returnPressed.connect(_accept)
    editor.editingFinished.connect(lambda: editor.deleteLater())
```

- [ ] **Step 3: Implement `_apply_spacing_edit()` on model_space**

In `model_space.py`:

```python
def _apply_spacing_edit(self, dim: dict, new_distance: float):
    """Move selected gridline(s) to satisfy the new spacing value."""
    self.push_undo_state()

    from_gl = dim["from_gl"]
    to_gl = dim["to_gl"]
    old_distance = dim["distance"]
    delta = new_distance - old_distance

    # Determine which gridline(s) to move
    selected = [item for item in self.selectedItems()
                if isinstance(item, GridlineItem)]

    # The selected gridline moves; the unselected neighbor stays fixed
    if to_gl in selected and from_gl not in selected:
        # to_gl moves away from from_gl
        for gl in selected:
            if gl.locked:
                continue
            gl.move_perpendicular(delta)
    elif from_gl in selected and to_gl not in selected:
        # from_gl moves away from to_gl
        for gl in selected:
            if gl.locked:
                continue
            gl.move_perpendicular(-delta)
    else:
        # Both selected or neither — move to_gl by default
        if not to_gl.locked:
            to_gl.move_perpendicular(delta)

    self._gridline_spacing_dims = self._compute_gridline_spacing()
    self.update()
```

- [ ] **Step 4: Smoke-test**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
Place 2 vertical gridlines. Select one. Double-click the spacing dimension:
- Verify inline text field appears
- Enter a new value, press Enter
- Verify the selected gridline moves to the new spacing
- Verify undo reverts

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_view.py firepro3d/model_space.py
git commit -m "feat(grid): double-click spacing edit with numerical input"
```

---

### Task 11: Grid Lines Dialog — Edit Existing with Identity Tracking

**Files:**
- Modify: `firepro3d/grid_lines_dialog.py`
- Modify: `firepro3d/model_space.py`

- [ ] **Step 1: Add hidden identity column to dialog tables**

In `grid_lines_dialog.py`, in the `_GridTab` class (or equivalent tab widget), modify table creation to add a hidden column for the `GridlineItem` reference:

```python
COLUMNS = ["Label", "Offset", "Spacing", "Length", "Angle°"]
_COL_IDENTITY = 5  # Hidden column index

def _build_table(self):
    self._table.setColumnCount(len(COLUMNS) + 1)
    self._table.setHorizontalHeaderLabels(COLUMNS + ["_ref"])
    self._table.setColumnHidden(_COL_IDENTITY, True)
```

When populating from scene, store the reference:

```python
def _populate_from_scene(self, gridlines: list):
    for gl in gridlines:
        row = self._table.rowCount()
        self._table.insertRow(row)
        # ... populate label, offset, spacing, length, angle cells ...
        # Store identity ref
        ref_item = QTableWidgetItem()
        ref_item.setData(Qt.ItemDataRole.UserRole, gl)
        self._table.setItem(row, _COL_IDENTITY, ref_item)
```

For new rows (from Quick Fill or manual add), store `None`:

```python
ref_item = QTableWidgetItem()
ref_item.setData(Qt.ItemDataRole.UserRole, None)
self._table.setItem(row, _COL_IDENTITY, ref_item)
```

- [ ] **Step 2: Update `get_gridlines()` to return identity refs**

Modify the return format to include the backing item:

```python
def get_gridlines(self) -> list[dict]:
    result = []
    for row in range(self._table.rowCount()):
        # ... parse label, offset, length, angle ...
        ref_item = self._table.item(row, _COL_IDENTITY)
        backing = ref_item.data(Qt.ItemDataRole.UserRole) if ref_item else None
        result.append({
            "label": label,
            "offset": self._to_scene(offset),
            "length": self._to_scene(length),
            "angle_deg": angle,
            "_backing": backing,  # GridlineItem or None
        })
    return result
```

- [ ] **Step 3: Convert numeric fields to use display-unit conversion**

Replace hardcoded unit handling in spinboxes and table cells with `ScaleManager` conversion:

```python
# In __init__ or setup, receive scale_manager
self._sm = scale_manager

# For spinbox values:
self._length_spin.setValue(self._sm.scene_to_display(default_length))

# For table cell display:
display_val = self._sm.scene_to_display(scene_val)
item = QTableWidgetItem(f"{display_val:.2f}")

# For reading table cells:
scene_val = self._sm.display_to_scene(float(cell_text))
```

Remove any hardcoded inches conversion logic.

- [ ] **Step 4: Update `place_grid_lines()` for diff-based reconciliation**

In `model_space.py`, replace or augment `place_grid_lines()`:

```python
def apply_grid_dialog(self, specs: list[dict]):
    """Apply grid dialog results with diff-based reconciliation.

    Each spec dict has keys: label, offset, length, angle_deg, _backing.
    _backing is the original GridlineItem (for edits) or None (for new).
    """
    self.push_undo_state()

    # Track which existing gridlines are still referenced
    referenced = set()
    for spec in specs:
        backing = spec.get("_backing")
        if backing is not None:
            referenced.add(id(backing))

    # Phase 1: Delete gridlines not in the dialog
    to_delete = [gl for gl in self._gridlines if id(gl) not in referenced]
    if to_delete:
        # Confirmation was already shown in the dialog
        for gl in to_delete:
            self.removeItem(gl)
            self._gridlines.remove(gl)

    # Phase 2: Update existing and create new
    for spec in specs:
        backing = spec.get("_backing")
        label = spec.get("label", "?")
        offset = spec.get("offset", 0.0)
        length = spec.get("length", 1000.0)
        angle = spec.get("angle_deg", 90.0)

        # Compute p1, p2 from offset/length/angle (same as existing placement logic)
        rad = math.radians(angle)
        dx = math.cos(rad)
        dy = -math.sin(rad)
        px = -dy
        py = dx
        ox = offset * px
        oy = -offset * py
        bubble_overshoot = length * 0.06
        p1 = QPointF(ox - bubble_overshoot * dx, oy - bubble_overshoot * dy)
        p2 = QPointF(ox + length * dx, oy + length * dy)

        if backing is not None:
            # Update existing gridline in-place
            backing.setLine(p1.x(), p1.y(), p2.x(), p2.y())
            backing.grid_label = label
            backing._update_bubble_positions()
        else:
            # Create new gridline
            gl = GridlineItem(p1, p2, label=label)
            gl.user_layer = self.active_user_layer
            self.addItem(gl)
            apply_category_defaults(gl)
            self._gridlines.append(gl)

    sync_grid_counters(self._gridlines)
    self.sceneModified.emit()
```

- [ ] **Step 5: Add deletion confirmation in dialog**

In `grid_lines_dialog.py`, modify `accept()` to check for deletions:

```python
def accept(self):
    # Count deletions
    current_refs = set()
    for tab in [self._v_tab, self._h_tab]:
        for row in range(tab._table.rowCount()):
            ref_item = tab._table.item(row, _COL_IDENTITY)
            backing = ref_item.data(Qt.ItemDataRole.UserRole) if ref_item else None
            if backing is not None:
                current_refs.add(id(backing))

    all_existing = set(id(gl) for gl in self._existing_gridlines)
    deletions = all_existing - current_refs

    if deletions:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"{len(deletions)} gridline(s) will be deleted. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

    super().accept()
```

- [ ] **Step 6: Wire dialog to new `apply_grid_dialog()`**

In the calling code (likely in `model_space.py` or a toolbar action), update the dialog invocation:

```python
# Old: self.place_grid_lines({"gridlines": dialog.get_gridlines()})
# New:
self.apply_grid_dialog(dialog.get_gridlines())
```

- [ ] **Step 7: Smoke-test**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
1. Place 3 gridlines via the dialog
2. Reopen the dialog — verify existing gridlines populate the tables
3. Modify one gridline's label and offset — verify it updates in-place (same visual item moves)
4. Delete a row — verify confirmation prompt, then gridline removed
5. Add a new row — verify new gridline created
6. Undo — verify entire dialog operation reverts as one step

- [ ] **Step 8: Commit**

```bash
git add firepro3d/grid_lines_dialog.py firepro3d/model_space.py
git commit -m "feat(grid): edit-existing dialog with identity-tracked diff reconciliation"
```

---

### Task 12: Integration Tests

**Files:**
- Create: `tests/test_gridline_integration.py`

- [ ] **Step 1: Write dialog CRUD integration test**

Create `tests/test_gridline_integration.py`:

```python
"""Integration tests for grid system: dialog CRUD, elevation, spacing."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.gridline import GridlineItem, sync_grid_counters


@pytest.fixture
def scene(qapp):
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


class TestDialogReconciliation:
    """Test the diff-based reconciliation logic."""

    def test_modify_in_place(self, scene):
        """Modifying a gridline via dialog updates the same object."""
        gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        original_id = id(gl)

        # Simulate dialog output: same backing, new offset
        gl.setLine(2000, 0, 2000, 5000)
        gl._update_bubble_positions()

        assert id(gl) == original_id
        assert gl.line().p1().x() == pytest.approx(2000.0)

    def test_create_new(self, scene):
        """New rows (backing=None) create new gridlines."""
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="X")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        assert len(scene._gridlines) == 1

    def test_delete_removes(self, scene):
        """Gridlines not referenced by dialog output are removed."""
        gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl)
        scene._gridlines.append(gl)

        scene.removeItem(gl)
        scene._gridlines.remove(gl)
        assert len(scene._gridlines) == 0


class TestElevationProjection:
    """Test gridline projection into elevation views."""

    def test_vertical_projects_to_north(self, scene):
        """Vertical gridline at x=1000 projects to H=1000 in north elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        p1, p2 = QPointF(1000, 0), QPointF(1000, 5000)
        assert _is_cardinal_for_elevation(p1, p2, "north") is True
        assert _is_cardinal_for_elevation(p1, p2, "south") is True
        assert _is_cardinal_for_elevation(p1, p2, "east") is False
        assert _is_cardinal_for_elevation(p1, p2, "west") is False

    def test_angled_projects_to_nothing(self, scene):
        """Angled gridline at 45° should not appear in any elevation."""
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        p1, p2 = QPointF(0, 0), QPointF(5000, 5000)
        for d in ("north", "south", "east", "west"):
            assert _is_cardinal_for_elevation(p1, p2, d) is False


class TestLockEnforcement:
    """Test that lock prevents all movement operations."""

    def test_lock_blocks_grip(self, scene):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        scene.addItem(gl)
        gl.locked = True
        original_y = gl.line().p1().y()
        gl.apply_grip(0, QPointF(0, -1000))
        assert gl.line().p1().y() == pytest.approx(original_y)

    def test_lock_blocks_perpendicular(self, scene):
        gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl)
        gl.locked = True
        gl.move_perpendicular(500)
        assert gl.line().p1().x() == pytest.approx(1000.0)

    def test_lock_serialization_round_trip(self, scene):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        gl.locked = True
        d = gl.to_dict()
        gl2 = GridlineItem.from_dict(d)
        assert gl2.locked is True
```

- [ ] **Step 2: Run tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/test_gridline_integration.py -v`
Expected: All PASS (these test the features we implemented in prior tasks).

- [ ] **Step 3: Commit**

```bash
git add tests/test_gridline_integration.py
git commit -m "test(grid): add integration tests for dialog, elevation, and lock"
```

---

### Task 13: Update `model_space.py` Level Handling and Counter Sync Call Sites

**Files:**
- Modify: `firepro3d/model_space.py`

- [ ] **Step 1: Remove level assignment on gridline creation**

In `model_space.py`, find all places where `gl.level = self.active_level` is set on a `GridlineItem`. Remove these assignments. There should be at least two sites:
- `_press_gridline()` (interactive 2-click placement)
- `place_grid_lines()` (batch placement from dialog)

- [ ] **Step 2: Add counter sync call sites**

Add `sync_grid_counters(self._gridlines)` calls at:

1. After file load (in the scene restoration / `from_dict` path)
2. After undo/redo (in the undo handler)
3. After `apply_grid_dialog()` (already added in Task 11)

Import at the top of `model_space.py`:

```python
from .gridline import GridlineItem, sync_grid_counters
```

- [ ] **Step 3: Remove level-based gridline filtering if present**

Search `model_space.py` for any code that filters gridlines by level (e.g., when switching active level). Remove or skip such filtering — gridlines should always be visible.

- [ ] **Step 4: Run existing tests**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "refactor(grid): remove level assignment, add counter sync call sites"
```

---

### Task 14: Lock Property in Property Panel and get_properties/set_property

**Files:**
- Modify: `firepro3d/gridline.py`

- [ ] **Step 1: Add Lock to get_properties()**

In `GridlineItem.get_properties()`, add:

```python
"Locked": {"type": "enum", "options": ["True", "False"], "value": str(self._locked)},
```

- [ ] **Step 2: Add Lock to set_property()**

In `GridlineItem.set_property()`, add:

```python
elif key == "Locked":
    self._locked = value in ("True", True)
```

- [ ] **Step 3: Verify property panel shows Lock**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`
Place a gridline, select it, check the property panel shows "Locked: False". Toggle to True. Verify dragging is blocked.

- [ ] **Step 4: Commit**

```bash
git add firepro3d/gridline.py
git commit -m "feat(grid): expose lock property in property panel"
```

---

### Task 15: Final Verification and Cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `cd "D:\Custom Code\FirePro3D" && python -m pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 2: Verify no dead imports**

Run: `grep -rn "grid_line\|GridLine" firepro3d/ --include="*.py" | grep -v "__pycache__" | grep -v gridline.py`
Expected: No results (all references to the old `GridLine` class are gone).

- [ ] **Step 3: Smoke-test full workflow**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`

Verify:
1. Place gridline via 2-click — auto-labeled, bubbles constant size on zoom
2. Place gridlines via dialog — batch create works
3. Reopen dialog — existing gridlines populate, edit in-place works, delete works
4. Lock a gridline — drag blocked, property panel shows Locked
5. Select gridline — spacing dimensions appear to neighbors
6. Double-click dimension — edit spacing, gridline moves
7. Open elevation — only cardinal gridlines appear
8. Undo/redo — all operations revert cleanly

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore(grid): final cleanup and verification"
```
