"""
elevation_scene.py
==================
QGraphicsScene that projects 3D model entities onto a vertical elevation plane.

Each elevation direction (North/South/East/West) projects onto a different axis:
  North (looking from +Y → -Y): H = world X, V = world Z
  South (looking from -Y → +Y): H = -world X, V = world Z
  East  (looking from +X → -X): H = -world Y, V = world Z
  West  (looking from -X → +X): H = world Y, V = world Z

Scene coordinates: H increases rightward, V (= -Z) increases downward (Qt convention).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QGraphicsSimpleTextItem, QGraphicsPathItem,
)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF, QLineF, QTimer
from PyQt6.QtGui import QPen, QColor, QBrush, QFont, QPainterPath

from PyQt6.QtCore import QSettings

from constants import DEFAULT_LEVEL
import theme as th

if TYPE_CHECKING:
    from Model_Space import Model_Space
    from level_manager import LevelManager
    from scale_manager import ScaleManager

# Data role for storing source entity reference on projected items
_ROLE_SOURCE = Qt.ItemDataRole.UserRole


class ElevationScene(QGraphicsScene):
    """Projects model entities onto a vertical plane for elevation display."""

    entitySelected = pyqtSignal(object)   # picked legacy entity
    cursorMoved = pyqtSignal(str)         # formatted "H: … Z: …"

    def __init__(self, direction: str, model_space: "Model_Space",
                 level_manager: "LevelManager", scale_manager: "ScaleManager",
                 parent=None):
        super().__init__(parent)
        self._direction = direction.lower()
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._show_datums = True

        # Theme
        _t = th.detect()
        bg = QColor(_t.canvas_bg)
        self.setBackgroundBrush(QBrush(bg))

        # Edge/line color based on background brightness
        br = bg.redF() * 0.299 + bg.greenF() * 0.587 + bg.blueF() * 0.114
        self._edge_color = QColor("#d0d0d0") if br < 0.5 else QColor("#000000")
        self._datum_color = QColor("#4488cc")

        # Large scene rect (in mm)
        self.setSceneRect(-500000, -500000, 1000000, 1000000)

        # Debounce rebuild
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(100)
        self._rebuild_timer.timeout.connect(self.rebuild)
        self._ms.sceneModified.connect(self._schedule_rebuild)
        self.selectionChanged.connect(self._on_selection_changed)

    # ── Selection sync ───────────────────────────────────────────────────

    def _on_selection_changed(self):
        """When items are selected (click or rubber-band), emit source entity."""
        selected = self.selectedItems()
        if selected:
            # Emit the last selected item's source entity
            for item in reversed(selected):
                source = item.data(_ROLE_SOURCE)
                if source is not None:
                    self.entitySelected.emit(source)
                    return
        self.entitySelected.emit(None)

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def direction(self) -> str:
        return self._direction

    @property
    def show_datums(self) -> bool:
        return self._show_datums

    @show_datums.setter
    def show_datums(self, val: bool):
        self._show_datums = val
        self.rebuild()

    # ── Coordinate projection ────────────────────────────────────────────

    def _ppm(self) -> float:
        """Pixels-per-mm (calibration factor), default 1.0."""
        return self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0

    def _scene_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert legacy scene coords (pixels) to world mm with Y flip."""
        ppm = self._ppm()
        return sx / ppm, -sy / ppm

    def _world_to_elev(self, wx: float, wy: float, wz: float) -> tuple[float, float]:
        """Project world (mm) coords onto elevation 2D plane.

        Returns (h, v) where h is horizontal scene coord and v = -wz
        (Qt Y increases downward, Z increases upward).
        """
        d = self._direction
        if d == "north":
            h = -wx       # looking south: East (+X) on left, West (-X) on right
        elif d == "south":
            h = wx        # looking north: West (-X) on left, East (+X) on right
        elif d == "east":
            h = wy        # looking west: South (-Y) on left, North (+Y) on right
        elif d == "west":
            h = -wy       # looking east: North (+Y) on left, South (-Y) on right
        else:
            h = -wx
        return h, -wz

    def _level_z(self, level_name: str) -> float:
        lvl = self._lm.get(level_name)
        return lvl.elevation if lvl else 0.0

    # ── Rebuild ──────────────────────────────────────────────────────────

    def _schedule_rebuild(self):
        if not self._rebuild_timer.isActive():
            self._rebuild_timer.start()

    def rebuild(self):
        """Clear and re-project all entities from the model."""
        self.clear()
        self._project_level_datums()
        self._project_walls()
        self._project_pipes()
        self._project_sprinklers()
        self._project_floor_slabs()
        self._project_roofs()
        self._project_gridlines()
        self._project_construction_geometry()

    # ── Walls ────────────────────────────────────────────────────────────

    def _project_walls(self):
        ppm = self._ppm()
        for wall in getattr(self._ms, "_walls", []):
            # Get Z extents
            base_z = 0.0
            top_z = wall._height_mm
            base_lvl = self._lm.get(wall._base_level)
            if base_lvl:
                base_z = base_lvl.elevation + wall._base_offset_mm
            top_lvl = self._lm.get(wall._top_level)
            if top_lvl:
                top_z = top_lvl.elevation + wall._top_offset_mm
            else:
                top_z = base_z + wall._height_mm
            if abs(top_z - base_z) < 1.0:
                continue

            # Get mitered 2D quad corners, convert to world mm
            try:
                p1l, p1r, p2r, p2l = wall.mitered_quad()
            except Exception:
                p1l, p1r, p2r, p2l = wall.quad_points()

            corners_world = []
            for pt in (p1l, p1r, p2r, p2l):
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                corners_world.append((wx, wy))

            # Project to elevation H axis
            h_values = [self._world_to_elev(wx, wy, 0)[0]
                        for wx, wy in corners_world]
            h_min = min(h_values)
            h_max = max(h_values)
            width = h_max - h_min
            if width < 0.5:
                continue

            # Elevation scene rect: (h_min, -top_z) to (h_max, -base_z)
            v_top = -top_z      # Qt Y for top of wall
            v_bottom = -base_z  # Qt Y for bottom of wall
            height = v_bottom - v_top

            rect = QGraphicsRectItem(h_min, v_top, width, height)

            # Apply wall color and fill
            pen = QPen(self._edge_color, 1)
            pen.setCosmetic(True)
            rect.setPen(pen)

            fill_mode = getattr(wall, "_fill_mode", "Solid")
            color = QColor(wall._color) if hasattr(wall, "_color") else QColor("#cccccc")
            if fill_mode == "Solid":
                rect.setBrush(QBrush(color))
            elif fill_mode == "Hatch":
                color.setAlpha(80)
                rect.setBrush(QBrush(color, Qt.BrushStyle.BDiagPattern))
            else:
                rect.setBrush(QBrush())

            rect.setData(_ROLE_SOURCE, wall)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setZValue(-50)
            self.addItem(rect)

    # ── Pipes ────────────────────────────────────────────────────────────

    def _project_pipes(self):
        _PIPE_COLORS = {
            "Red":   "#e62828", "Blue":  "#3366e6", "Black": "#1a1a1a",
            "White": "#f2f2f2", "Grey":  "#8c8c8c",
        }
        for pipe in self._ms.sprinkler_system.pipes:
            n1, n2 = pipe.node1, pipe.node2
            if n1 is None or n2 is None:
                continue
            # Get world positions
            wx1, wy1 = self._scene_to_world(n1.scenePos().x(), n1.scenePos().y())
            wx2, wy2 = self._scene_to_world(n2.scenePos().x(), n2.scenePos().y())
            z1 = getattr(n1, "z_pos", 0.0)
            z2 = getattr(n2, "z_pos", 0.0)

            h1, v1 = self._world_to_elev(wx1, wy1, z1)
            h2, v2 = self._world_to_elev(wx2, wy2, z2)

            col_name = pipe._properties.get("Colour", {}).get("value", "Red")
            color = QColor(_PIPE_COLORS.get(col_name, "#e62828"))

            line = QGraphicsLineItem(h1, v1, h2, v2)
            pen = QPen(color, 2)
            pen.setCosmetic(True)
            line.setPen(pen)
            line.setData(_ROLE_SOURCE, pipe)
            line.setFlag(QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable, True)
            line.setZValue(5)
            self.addItem(line)

    # ── Sprinklers ───────────────────────────────────────────────────────

    def _project_sprinklers(self):
        for node in self._ms.sprinkler_system.nodes:
            if not node.has_sprinkler():
                continue
            wx, wy = self._scene_to_world(node.scenePos().x(), node.scenePos().y())
            z = getattr(node, "z_pos", 0.0)
            h, v = self._world_to_elev(wx, wy, z)

            orient = node.sprinkler._properties.get(
                "Orientation", {}).get("value", "Upright")
            if orient == "Pendent":
                color = QColor("#ff3232")
            elif orient == "Sidewall":
                color = QColor("#32c832")
            else:
                color = QColor("#3264ff")

            r = 30.0  # mm radius
            ellipse = QGraphicsEllipseItem(h - r, v - r, r * 2, r * 2)
            pen = QPen(color, 1.5)
            pen.setCosmetic(True)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush())
            ellipse.setData(_ROLE_SOURCE, node)
            ellipse.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
            ellipse.setZValue(10)
            self.addItem(ellipse)

    # ── Floor slabs ──────────────────────────────────────────────────────

    def _project_floor_slabs(self):
        for slab in getattr(self._ms, "_floor_slabs", []):
            z = self._level_z(getattr(slab, "level", DEFAULT_LEVEL))
            thickness = getattr(slab, "_thickness_mm", 150.0)

            # Get slab boundary extents in world mm
            pts = getattr(slab, "_points", [])
            if not pts:
                continue
            h_vals = []
            for pt in pts:
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                h, _ = self._world_to_elev(wx, wy, 0)
                h_vals.append(h)
            h_min, h_max = min(h_vals), max(h_vals)

            v_top = -(z)
            v_bottom = -(z - thickness)
            rect = QGraphicsRectItem(h_min, v_top, h_max - h_min, v_bottom - v_top)
            pen = QPen(self._edge_color, 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            col = QColor("#8080cc")
            col.setAlpha(80)
            rect.setBrush(QBrush(col))
            rect.setData(_ROLE_SOURCE, slab)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setZValue(-80)
            self.addItem(rect)

    # ── Roofs ────────────────────────────────────────────────────────────

    def _project_roofs(self):
        for roof in getattr(self._ms, "_roofs", []):
            mesh_data = None
            try:
                mesh_data = roof.get_3d_mesh(level_manager=self._lm)
            except Exception:
                pass
            if mesh_data is None:
                continue

            verts = mesh_data.get("vertices", [])
            if not verts:
                continue
            col = mesh_data.get("color", (0.8, 0.7, 0.5, 0.5))

            # Project all vertices and draw outline polygon
            elev_pts = []
            for vx, vy, vz in verts:
                h, v = self._world_to_elev(vx, vy, vz)
                elev_pts.append(QPointF(h, v))

            if not elev_pts:
                continue

            # Draw convex hull outline (simplified)
            h_vals = [p.x() for p in elev_pts]
            v_vals = [p.y() for p in elev_pts]
            rect = QGraphicsRectItem(
                min(h_vals), min(v_vals),
                max(h_vals) - min(h_vals), max(v_vals) - min(v_vals),
            )
            pen = QPen(self._edge_color, 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            rc = QColor.fromRgbF(col[0], col[1], col[2])
            rc.setAlpha(int(col[3] * 255) if len(col) > 3 else 128)
            rect.setBrush(QBrush(rc))
            rect.setData(_ROLE_SOURCE, roof)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setZValue(-70)
            self.addItem(rect)

    # ── Display manager helpers ──────────────────────────────────────────

    def _gridline_display_props(self) -> dict:
        """Read Grid Line display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Grid Line/color",   "#4488cc"),
            "fill":    s.value("display/Grid Line/fill",    "#1a1a2e"),
            "opacity": int(s.value("display/Grid Line/opacity", 100)),
            "visible": str(s.value("display/Grid Line/visible", "true")).lower() not in ("false", "0"),
            "scale":   float(s.value("display/Grid Line/scale", 1.0)),
        }

    # ── Gridlines ────────────────────────────────────────────────────────

    @staticmethod
    def _gridline_is_vertical(line_geom) -> bool:
        """True if the gridline is more vertical than horizontal in scene."""
        dx = abs(line_geom.x2() - line_geom.x1())
        dy = abs(line_geom.y2() - line_geom.y1())
        return dy >= dx

    def _should_show_gridline(self, line_geom) -> bool:
        """Filter gridlines by elevation direction.

        North/South elevations look along Y — show only vertical gridlines
        (which run along Y and project to distinct H positions on the X axis).
        East/West elevations look along X — show only horizontal gridlines
        (which run along X and project to distinct H positions on the Y axis).
        """
        is_vert = self._gridline_is_vertical(line_geom)
        if self._direction in ("north", "south"):
            return is_vert       # vertical gridlines → visible as vertical lines in N/S
        else:  # east, west
            return not is_vert   # horizontal gridlines → visible as vertical lines in E/W

    def _project_gridlines(self):
        props = self._gridline_display_props()
        if not props["visible"]:
            return

        grid_color = QColor(props["color"])
        fill_color = QColor(props["fill"])
        opacity = props["opacity"] / 100.0
        bubble_scale = props["scale"]
        BUBBLE_R = 203.2 * bubble_scale  # 8" in mm, scaled

        for gl in getattr(self._ms, "_gridlines", []):
            line_geom = gl.line()

            # Filter: only show gridlines perpendicular to the view direction
            if not self._should_show_gridline(line_geom):
                continue

            # Get both endpoints in world mm
            wx1, wy1 = self._scene_to_world(line_geom.x1(), line_geom.y1())
            wx2, wy2 = self._scene_to_world(line_geom.x2(), line_geom.y2())
            h1, _ = self._world_to_elev(wx1, wy1, 0)
            h2, _ = self._world_to_elev(wx2, wy2, 0)

            h_avg = (h1 + h2) / 2.0

            # Vertical dashed line spanning all levels
            levels = self._lm.levels
            if not levels:
                continue
            z_min = min(l.elevation for l in levels) - 1000
            z_max = max(l.elevation for l in levels) + 4000

            line = QGraphicsLineItem(h_avg, -z_max, h_avg, -z_min)
            pen = QPen(grid_color, 1, Qt.PenStyle.DashDotLine)
            pen.setCosmetic(True)
            line.setPen(pen)
            line.setOpacity(opacity)
            line.setZValue(-95)
            self.addItem(line)

            # Bubble at top and bottom
            label_text = getattr(gl, "_label_text", "")
            for v_pos in (-z_max - BUBBLE_R - 50, -z_min + BUBBLE_R + 50):
                bubble = QGraphicsEllipseItem(
                    h_avg - BUBBLE_R, v_pos - BUBBLE_R,
                    BUBBLE_R * 2, BUBBLE_R * 2,
                )
                b_pen = QPen(grid_color, max(1, BUBBLE_R * 0.04))
                bubble.setPen(b_pen)
                bubble.setBrush(QBrush(fill_color))
                bubble.setOpacity(opacity)
                bubble.setZValue(-90)
                self.addItem(bubble)

                if label_text:
                    label = QGraphicsSimpleTextItem(label_text)
                    font = QFont("Arial")
                    font.setPixelSize(max(8, int(BUBBLE_R * 0.9)))
                    font.setBold(True)
                    label.setFont(font)
                    label.setBrush(QBrush(grid_color.lighter(150)))
                    br = label.boundingRect()
                    label.setPos(
                        h_avg - br.width() / 2,
                        v_pos - br.height() / 2,
                    )
                    label.setOpacity(opacity)
                    label.setZValue(-89)
                    self.addItem(label)

    # ── Construction geometry ────────────────────────────────────────────

    def _project_construction_geometry(self):
        ppm = self._ppm()
        constr_color = QColor("#666666")
        pen = QPen(constr_color, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)

        for item in getattr(self._ms, "_draw_lines", []):
            z = self._level_z(getattr(item, "level", DEFAULT_LEVEL))
            wx1, wy1 = self._scene_to_world(item._pt1.x(), item._pt1.y())
            wx2, wy2 = self._scene_to_world(item._pt2.x(), item._pt2.y())
            h1, v1 = self._world_to_elev(wx1, wy1, z)
            h2, v2 = self._world_to_elev(wx2, wy2, z)
            line = QGraphicsLineItem(h1, v1, h2, v2)
            line.setPen(pen)
            line.setZValue(-90)
            self.addItem(line)

        for item in getattr(self._ms, "_construction_lines", []):
            z = self._level_z(getattr(item, "level", DEFAULT_LEVEL))
            wx1, wy1 = self._scene_to_world(item._pt1.x(), item._pt1.y())
            wx2, wy2 = self._scene_to_world(item._pt2.x(), item._pt2.y())
            h1, v1 = self._world_to_elev(wx1, wy1, z)
            h2, v2 = self._world_to_elev(wx2, wy2, z)
            line = QGraphicsLineItem(h1, v1, h2, v2)
            line.setPen(pen)
            line.setZValue(-90)
            self.addItem(line)

    # ── Level datums ─────────────────────────────────────────────────────

    def _datum_extent(self) -> tuple[float, float]:
        """Compute H range for datum lines to match gridline extents.

        Returns (h_min, h_max) in world mm based on the actual gridline
        positions.  Falls back to DEFAULT_GRIDLINE_LENGTH_IN if no gridlines.
        """
        from constants import DEFAULT_GRIDLINE_LENGTH_IN
        ppm = self._ppm()

        gridlines = getattr(self._ms, "_gridlines", [])
        if not gridlines:
            # Fallback: 1000" offset, 864" length (default gridline dims)
            half = DEFAULT_GRIDLINE_LENGTH_IN / ppm / 2.0
            return -half, half

        # Gather all gridline H positions to find the full extent
        h_vals = []
        for gl in gridlines:
            lg = gl.line()
            wx1, wy1 = self._scene_to_world(lg.x1(), lg.y1())
            wx2, wy2 = self._scene_to_world(lg.x2(), lg.y2())
            h1, _ = self._world_to_elev(wx1, wy1, 0)
            h2, _ = self._world_to_elev(wx2, wy2, 0)
            h_vals.extend([h1, h2])

        if not h_vals:
            half = DEFAULT_GRIDLINE_LENGTH_IN / ppm / 2.0
            return -half, half

        margin = abs(max(h_vals) - min(h_vals)) * 0.2 + 500
        return min(h_vals) - margin, max(h_vals) + margin

    def _project_level_datums(self):
        if not self._show_datums:
            return

        # Use same display properties as gridlines
        props = self._gridline_display_props()
        datum_color = QColor(props["color"])
        fill_color = QColor(props.get("fill", "#1a1a2e"))
        opacity = props["opacity"] / 100.0
        scale = props.get("scale", 1.0)

        h_min, h_max = self._datum_extent()

        # Datum line pen — dash-dot-dash (same as gridlines)
        from gridline import BUBBLE_RADIUS_MM
        pen_w = max(1.0, BUBBLE_RADIUS_MM * 0.04 * scale)
        pen = QPen(datum_color, pen_w, Qt.PenStyle.DashDotLine)
        pen.setCosmetic(False)  # world-space width (scales with zoom)

        # Text size: 175mm (scales with display manager scale factor)
        text_height = 175.0 * scale
        name_font = QFont("Consolas")
        name_font.setPixelSize(max(1, int(text_height)))
        name_font.setBold(True)

        elev_font = QFont("Consolas")
        elev_font.setPixelSize(max(1, int(text_height * 0.8)))

        # Bubble radius matches gridline bubbles
        bubble_r = BUBBLE_RADIUS_MM * scale

        for lvl in self._lm.levels:
            z = lvl.elevation
            v = -z  # Qt Y

            # ── Datum line ───────────────────────────────────────────
            line = QGraphicsLineItem(h_min, v, h_max, v)
            line.setPen(pen)
            line.setOpacity(opacity)
            line.setZValue(-100)
            self.addItem(line)

            # ── Classic elevation bubble at left end (4-quadrant) ────
            bx = h_min - bubble_r * 0.5
            by = v

            circle_pen = QPen(datum_color, pen_w)
            circle_pen.setCosmetic(False)

            # Full circle outline
            circle = QGraphicsEllipseItem(
                bx - bubble_r, by - bubble_r,
                bubble_r * 2, bubble_r * 2,
            )
            circle.setPen(circle_pen)
            circle.setBrush(QBrush(fill_color))
            circle.setOpacity(opacity)
            circle.setZValue(-98)
            self.addItem(circle)

            # Cross lines (horizontal + vertical through center)
            h_line = QGraphicsLineItem(bx - bubble_r, by, bx + bubble_r, by)
            h_line.setPen(circle_pen)
            h_line.setOpacity(opacity)
            h_line.setZValue(-97)
            self.addItem(h_line)

            v_line = QGraphicsLineItem(bx, by - bubble_r, bx, by + bubble_r)
            v_line.setPen(circle_pen)
            v_line.setOpacity(opacity)
            v_line.setZValue(-97)
            self.addItem(v_line)

            # Fill two opposite quadrants (top-right + bottom-left)
            q_path = QPainterPath()
            q_path.moveTo(bx, by)
            q_path.arcTo(bx - bubble_r, by - bubble_r,
                         bubble_r * 2, bubble_r * 2,
                         0, 90)
            q_path.closeSubpath()
            q_path.moveTo(bx, by)
            q_path.arcTo(bx - bubble_r, by - bubble_r,
                         bubble_r * 2, bubble_r * 2,
                         180, 90)
            q_path.closeSubpath()

            filled_quads = QGraphicsPathItem(q_path)
            filled_quads.setPen(QPen(Qt.PenStyle.NoPen))
            filled_quads.setBrush(QBrush(datum_color))
            filled_quads.setOpacity(opacity * 0.6)
            filled_quads.setZValue(-96)
            self.addItem(filled_quads)

            # ── Tag to the right of bubble: Level name above, elevation below
            tag_x = bx + bubble_r + 50  # gap right of bubble

            # Level name (capitalized, above line)
            display_name = lvl.name.upper() if lvl.name else "LEVEL"
            name_text = QGraphicsSimpleTextItem(display_name)
            name_text.setFont(name_font)
            name_text.setBrush(QBrush(datum_color))
            name_text.setOpacity(opacity)
            name_br = name_text.boundingRect()
            name_text.setPos(tag_x, v - name_br.height() - 20)
            name_text.setZValue(-99)
            self.addItem(name_text)

            # Elevation value (below line)
            elev_str = self._sm.format_length(z) if self._sm else f"{z:.0f} mm"
            elev_text = QGraphicsSimpleTextItem(elev_str)
            elev_text.setFont(elev_font)
            elev_text.setBrush(QBrush(datum_color.lighter(130)))
            elev_text.setOpacity(opacity)
            elev_text.setPos(tag_x, v + 20)
            elev_text.setZValue(-99)
            self.addItem(elev_text)

    # ── Selection ────────────────────────────────────────────────────────
    # Selection is handled by Qt's built-in rubber-band + ItemIsSelectable
    # flags, routed through _on_selection_changed() which emits entitySelected.
