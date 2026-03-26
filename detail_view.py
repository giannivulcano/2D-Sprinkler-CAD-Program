"""
detail_view.py
==============
Detail view marker and manager.

A detail view is a plan view with a rectangular crop boundary.  The marker
appears on the source plan as a dashed rectangle with a circular callout tag.
Opening the detail view creates a tab that shows only the content inside
the crop boundary.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsRectItem, QGraphicsItem, QGraphicsEllipseItem,
    QGraphicsSimpleTextItem, QTabWidget,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import QPen, QBrush, QColor, QFont, QPainterPath

from gridline import BUBBLE_RADIUS_MM
from constants import DEFAULT_LEVEL

if TYPE_CHECKING:
    from Model_Space import Model_Space
    from level_manager import LevelManager
    from scale_manager import ScaleManager


# ─────────────────────────────────────────────────────────────────────────────
# Detail Marker
# ─────────────────────────────────────────────────────────────────────────────

_MARKER_COLOR = "#4488cc"
_TAG_RADIUS = BUBBLE_RADIUS_MM * 2.0


class DetailMarker(QGraphicsRectItem):
    """Dashed rectangle on a plan view marking a detail crop boundary.

    Has a circular tag at the bottom-center with the detail number.
    Selectable and resizable via 8 grip handles.
    Double-click opens the detail view tab.
    """

    def __init__(self, name: str, rect: QRectF, level_name: str = DEFAULT_LEVEL,
                 parent: QGraphicsItem | None = None):
        super().__init__(rect, parent)
        self._name = name
        self._level_name = level_name
        self._manager: DetailViewManager | None = None

        # Visual style
        color = QColor(_MARKER_COLOR)
        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        fill = QColor(_MARKER_COLOR)
        fill.setAlpha(12)
        self.setBrush(QBrush(fill))
        self.setZValue(45)  # above walls (-50..0) but below datum lines (50)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._exclude_from_bulk_select = True

        # For display manager categorization
        self.level = level_name
        self.user_layer: str = "Default"
        self._display_overrides: dict = {}

        # Build tag
        self._tag_color = color
        self._build_tag()

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value
        self._update_tag_label()

    @property
    def level_name(self) -> str:
        return self._level_name

    @property
    def crop_rect(self) -> QRectF:
        return self.rect()

    # ── Tag (circle + label at bottom-center) ────────────────────────────

    def _build_tag(self):
        """Create the circular callout tag with detail number."""
        r = _TAG_RADIUS
        self._tag_circle = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r, self)
        pen = QPen(self._tag_color, 2)
        pen.setCosmetic(True)
        self._tag_circle.setPen(pen)
        self._tag_circle.setBrush(QBrush(QColor("#1a1a2e")))
        self._tag_circle.setZValue(46)

        # Number inside circle
        self._tag_text = QGraphicsSimpleTextItem("", self._tag_circle)
        font = QFont("Consolas", 10)
        font.setBold(True)
        self._tag_text.setFont(font)
        self._tag_text.setBrush(QBrush(self._tag_color))
        self._tag_text.setZValue(47)

        # Label below circle
        self._label_text = QGraphicsSimpleTextItem("", self)
        label_font = QFont("Consolas", 8)
        self._label_text.setFont(label_font)
        self._label_text.setBrush(QBrush(self._tag_color))
        self._label_text.setZValue(46)

        self._update_tag_label()
        self._reposition_tag()

    def _update_tag_label(self):
        """Update the number and label text."""
        # Extract number from name like "Detail 1" → "1"
        parts = self._name.split()
        number = parts[-1] if parts else "1"
        self._tag_text.setText(number)
        # Center text in circle
        br = self._tag_text.boundingRect()
        self._tag_text.setPos(-br.width() / 2, -br.height() / 2)

        self._label_text.setText(self._name.upper())

    def _reposition_tag(self):
        """Place tag at bottom-center of the crop rectangle."""
        r = self.rect()
        cx = r.center().x()
        tag_y = r.bottom() + _TAG_RADIUS + 20
        self._tag_circle.setPos(cx, tag_y)

        # Label centered below the tag circle
        lbr = self._label_text.boundingRect()
        self._label_text.setPos(cx - lbr.width() / 2,
                                tag_y + _TAG_RADIUS + 10)

    # ── Grip protocol ────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """8 grips: 4 corners + 4 edge midpoints."""
        r = self.rect()
        return [
            r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft(),
            QPointF(r.center().x(), r.top()),
            QPointF(r.right(), r.center().y()),
            QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()),
        ]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Resize the crop rect from a grip drag."""
        r = self.rect()

        if index == 0:
            r.setTopLeft(new_pos)
        elif index == 1:
            r.setTopRight(new_pos)
        elif index == 2:
            r.setBottomRight(new_pos)
        elif index == 3:
            r.setBottomLeft(new_pos)
        elif index == 4:
            r.setTop(new_pos.y())
        elif index == 5:
            r.setRight(new_pos.x())
        elif index == 6:
            r.setBottom(new_pos.y())
        elif index == 7:
            r.setLeft(new_pos.x())

        r = r.normalized()
        self.setRect(r)
        self._reposition_tag()

        # Update open detail tab's clip rect
        if self._manager is not None:
            self._manager._on_marker_resized(self._name, r)

    # ── Interaction ──────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        """Double-click opens the detail view tab."""
        sc = self.scene()
        if sc is not None and hasattr(sc, "openViewRequested"):
            sc.openViewRequested.emit("detail", self._name)
        event.accept()

    def boundingRect(self):
        br = super().boundingRect()
        # Extend to include tag below
        tag_bottom = self.rect().bottom() + _TAG_RADIUS * 2 + 80
        if tag_bottom > br.bottom():
            br.setBottom(tag_bottom)
        return br

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect())
        # Add tag circle to hit-test area
        r = _TAG_RADIUS
        tag_center = self._tag_circle.pos()
        path.addEllipse(tag_center, r, r)
        return path

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        r = self.rect()
        return {
            "name": self._name,
            "level_name": self._level_name,
            "crop_rect": {
                "x": r.x(), "y": r.y(),
                "w": r.width(), "h": r.height(),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DetailMarker":
        cr = data["crop_rect"]
        rect = QRectF(cr["x"], cr["y"], cr["w"], cr["h"])
        return cls(
            name=data["name"],
            rect=rect,
            level_name=data.get("level_name", DEFAULT_LEVEL),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Detail View Manager
# ─────────────────────────────────────────────────────────────────────────────

class DetailViewManager:
    """Manages detail view markers and tabs.

    Parameters
    ----------
    model_space : Model_Space
        The 2D scene containing the model.
    level_manager : LevelManager
        Level elevation lookup.
    scale_manager : ScaleManager
        Coordinate conversion.
    tab_widget : QTabWidget
        Central tab widget for detail view tabs.
    """

    def __init__(self, model_space: "Model_Space",
                 level_manager: "LevelManager",
                 scale_manager: "ScaleManager",
                 tab_widget: QTabWidget):
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._tabs = tab_widget

        # name → DetailMarker
        self._markers: dict[str, DetailMarker] = {}
        # name → Model_View (open tabs only)
        self._open_views: dict[str, object] = {}
        self._counter = 0

    @property
    def detail_names(self) -> list[str]:
        return list(self._markers.keys())

    def next_name(self) -> str:
        """Generate the next auto-incremented detail name."""
        self._counter += 1
        return f"Detail {self._counter}"

    def create_detail(self, name: str, crop_rect: QRectF,
                      level_name: str = DEFAULT_LEVEL) -> DetailMarker:
        """Create a detail marker and add it to the scene."""
        marker = DetailMarker(name, crop_rect, level_name)
        marker._manager = self
        self._markers[name] = marker
        self._ms.addItem(marker)
        return marker

    def open_detail(self, name: str):
        """Open or switch to a detail view tab."""
        tab_name = f"Detail: {name}"

        # If already open, switch to it
        if name in self._open_views:
            view = self._open_views[name]
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.setCurrentIndex(i)
                    return view
            # Tab was removed externally
            del self._open_views[name]

        marker = self._markers.get(name)
        if marker is None:
            return None

        # Create a new plan view with clip rect
        from Model_View import Model_View
        view = Model_View(self._ms)
        view.setObjectName(f"detail_view_{name}")
        view._clip_rect = marker.crop_rect
        view._detail_name = name

        idx = self._tabs.addTab(view, tab_name)
        self._tabs.setCurrentIndex(idx)
        self._open_views[name] = view

        # Apply level and fit to clip rect
        QTimer.singleShot(50, lambda: self._fit_detail_view(view, marker))

        return view

    def _fit_detail_view(self, view, marker):
        """Fit the detail view to its crop rect."""
        rect = QRectF(marker.crop_rect)
        margin = max(rect.width(), rect.height()) * 0.05
        rect.adjust(-margin, -margin, margin, margin)
        view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def close_detail(self, name: str):
        """Close a detail view tab and remove its marker."""
        # Close tab
        view = self._open_views.pop(name, None)
        if view is not None:
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.removeTab(i)
                    break

        # Remove marker from scene
        marker = self._markers.pop(name, None)
        if marker is not None and marker.scene() is self._ms:
            self._ms.removeItem(marker)

    def delete_detail(self, name: str):
        """Delete a detail (marker + tab). Used from project browser."""
        self.close_detail(name)

    def _on_marker_resized(self, name: str, new_rect: QRectF):
        """Called when a marker's crop rect changes via grip drag."""
        view = self._open_views.get(name)
        if view is not None:
            view._clip_rect = new_rect

    def get_marker(self, name: str) -> DetailMarker | None:
        return self._markers.get(name)

    # ── Serialization ────────────────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [m.to_dict() for m in self._markers.values()]

    def from_list(self, data: list[dict]):
        """Restore detail markers from saved data."""
        for d in data:
            name = d["name"]
            cr = d["crop_rect"]
            rect = QRectF(cr["x"], cr["y"], cr["w"], cr["h"])
            level = d.get("level_name", DEFAULT_LEVEL)
            marker = self.create_detail(name, rect, level)
            # Update counter to avoid name collisions
            parts = name.split()
            if len(parts) >= 2:
                try:
                    num = int(parts[-1])
                    self._counter = max(self._counter, num)
                except ValueError:
                    pass
