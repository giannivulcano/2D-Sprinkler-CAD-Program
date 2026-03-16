"""
view_3d.py
==========
Interactive 3D visualization of the sprinkler / piping model using vispy.

Renders nodes, pipes, sprinklers, construction geometry, level floors,
and architectural entities (walls, floor slabs) in a 3D scene.
Supports click-to-select with bidirectional sync to the 2D Model Space.
"""

from __future__ import annotations

import math
import numpy as np

import vispy
vispy.use("pyqt6")

from vispy import scene
from vispy.scene import visuals
from vispy.geometry import create_cylinder

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

from constants import DEFAULT_LEVEL
from node import Node
from pipe import Pipe
from sprinkler import Sprinkler
from construction_geometry import (
    ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from gridline import GridlineItem
from water_supply import WaterSupply
from Annotations import DimensionAnnotation, NoteAnnotation
from wall import WallSegment
from floor_slab import FloorSlab
from view_cube import ViewCube


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

FT_TO_MM = 304.8
CIRCLE_SEGMENTS = 64
PICK_TOLERANCE_PX = 15
MAX_CYLINDER_PIPES = 200   # above this count, fall back to line rendering

# Pipe nominal diameter → approximate OD in inches (for cylinder radius)
_NOMINAL_OD_IN = {
    '1"Ø': 1.315, '1-½"Ø': 1.900, '2"Ø': 2.375, '3"Ø': 3.500,
    '4"Ø': 4.500, '5"Ø': 5.563, '6"Ø': 6.625, '8"Ø': 8.625,
    # Legacy keys without Ø
    '1"': 1.315, '1-½"': 1.900, '2"': 2.375, '3"': 3.500,
    '4"': 4.500, '5"': 5.563, '6"': 6.625, '8"': 8.625,
}

# Colors
COL_NODE        = (0.55, 0.55, 0.55, 1.0)
COL_SPRINKLER   = (1.0, 0.2, 0.2, 1.0)
COL_WATER_SUPPLY = (0.0, 0.7, 0.86, 1.0)
COL_HIGHLIGHT   = (1.0, 1.0, 0.0, 0.85)
COL_CONSTR      = (0.4, 0.4, 0.4, 0.6)
COL_SEL_MESH    = (0.3, 0.6, 1.0, 1.0)      # selected wall/slab tint
COL_SEL_EDGE    = (0.2, 0.5, 1.0, 1.0)      # bright edge for selected mesh
DESELECT_ALPHA  = 0.3                         # fade non-selected meshes

# Pipe color name → RGBA
_PIPE_COLORS = {
    "Red":   (0.9, 0.15, 0.15, 1.0),
    "Blue":  (0.2, 0.4, 0.9, 1.0),
    "Black": (0.1, 0.1, 0.1, 1.0),
    "White": (0.95, 0.95, 0.95, 1.0),
    "Grey":  (0.55, 0.55, 0.55, 1.0),
}

# Level floor hues (cycled)
_FLOOR_COLORS = [
    (0.2, 0.4, 0.8, 0.35),
    (0.2, 0.8, 0.4, 0.35),
    (0.8, 0.4, 0.2, 0.35),
    (0.8, 0.2, 0.8, 0.35),
    (0.2, 0.8, 0.8, 0.35),
]


# ─────────────────────────────────────────────────────────────────────────────
# View3D widget
# ─────────────────────────────────────────────────────────────────────────────

class View3D(QWidget):
    """Interactive 3D visualization tab."""

    entitySelected = pyqtSignal(object)  # emits QGraphicsItem or None

    def __init__(self, model_space, level_manager, scale_manager, parent=None):
        super().__init__(parent)
        self._scene = model_space
        self._lm = level_manager
        self._sm = scale_manager

        # Dirty flag for lazy rebuild
        self._dirty = True
        self._first_build = True

        # Entity pick map: list index → QGraphicsItem
        self._node_refs: list[Node] = []
        self._pipe_refs: list[Pipe] = []
        self._node_positions_3d: np.ndarray | None = None
        self._pipe_midpoints_3d: np.ndarray | None = None

        # Wall / slab / roof pick maps
        self._wall_refs: list[WallSegment] = []
        self._slab_refs: list[FloorSlab] = []
        self._roof_refs: list = []
        self._wall_centroids_3d: np.ndarray | None = None
        self._slab_centroids_3d: np.ndarray | None = None
        self._roof_centroids_3d: np.ndarray | None = None
        # Per-entity mesh geometry for triangle-based picking
        self._wall_mesh_data: list[tuple[np.ndarray, np.ndarray]] = []  # (verts, faces)
        self._slab_mesh_data: list[tuple[np.ndarray, np.ndarray]] = []
        self._roof_mesh_data: list[tuple[np.ndarray, np.ndarray]] = []
        self._original_wall_colors: list[tuple] = []
        self._original_slab_colors: list[tuple] = []
        self._original_roof_colors: list[tuple] = []

        # Ortho / perspective state
        self._perspective = True

        self._build_ui()
        self._connect_signals()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar — compact wrapper widget with fixed height
        tb_widget = QWidget()
        tb_widget.setFixedHeight(28)
        tb_widget.setStyleSheet("background: #1e1e1e;")
        tb = QHBoxLayout(tb_widget)
        tb.setContentsMargins(4, 2, 4, 2)
        tb.setSpacing(4)

        _btn_style = "QPushButton { height: 20px; padding: 0 6px; font-size: 11px; }"

        self._fit_btn = QPushButton("Fit All")
        self._fit_btn.setStyleSheet(_btn_style)
        self._fit_btn.clicked.connect(self._fit_camera)
        tb.addWidget(self._fit_btn)

        self._proj_btn = QPushButton("Ortho")
        self._proj_btn.setStyleSheet(_btn_style)
        self._proj_btn.clicked.connect(self._toggle_projection)
        tb.addWidget(self._proj_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setStyleSheet(_btn_style)
        self._refresh_btn.clicked.connect(self.rebuild)
        tb.addWidget(self._refresh_btn)

        self._section_h_btn = QPushButton("H-Cut")
        self._section_h_btn.setStyleSheet(_btn_style)
        self._section_h_btn.setCheckable(True)
        self._section_h_btn.setToolTip("Horizontal section cut — hides geometry above cut height")
        self._section_h_btn.clicked.connect(self._toggle_horizontal_cut)
        tb.addWidget(self._section_h_btn)

        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setStyleSheet(_btn_style)
        self._grid_btn.setCheckable(True)
        self._grid_btn.setChecked(False)
        self._grid_btn.setToolTip("Toggle ground grid")
        self._grid_btn.clicked.connect(self._toggle_3d_grid)
        tb.addWidget(self._grid_btn)

        self._floors_btn = QPushButton("Floors")
        self._floors_btn.setStyleSheet(_btn_style)
        self._floors_btn.setCheckable(True)
        self._floors_btn.setChecked(False)
        self._floors_btn.setToolTip("Toggle level floor planes")
        self._floors_btn.clicked.connect(self._toggle_level_floors)
        tb.addWidget(self._floors_btn)

        tb.addStretch()
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #aaa; font-size: 11px;")
        tb.addWidget(self._info_label)
        layout.addWidget(tb_widget)

        # vispy canvas
        self._canvas = scene.SceneCanvas(keys="interactive", show=False)
        self._canvas.bgcolor = (0.12, 0.12, 0.14, 1.0)
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = scene.TurntableCamera(
            fov=45, distance=10000, elevation=30, azimuth=45,
        )

        layout.addWidget(self._canvas.native)

        # ViewCube overlay (top-right corner of the canvas)
        self._view_cube = ViewCube(self._canvas.native)
        self._view_cube.viewRequested.connect(self._on_viewcube_request)
        self._view_cube.raise_()
        self._position_viewcube()

        # Visuals (created once, data updated on rebuild)
        self._node_markers = visuals.Markers(parent=self._view.scene)
        self._sprinkler_markers = visuals.Markers(parent=self._view.scene)
        self._pipe_lines = visuals.Line(parent=self._view.scene, antialias=True)
        self._pipe_cylinder_meshes: list[visuals.Mesh] = []
        self._constr_lines = visuals.Line(
            parent=self._view.scene, antialias=True, color=COL_CONSTR,
        )
        self._ws_marker = visuals.Markers(parent=self._view.scene)
        self._highlight_markers = visuals.Markers(parent=self._view.scene)
        self._highlight_markers.visible = False

        # Level floor meshes, edge outlines, and labels (dynamic, recreated on rebuild)
        self._floor_meshes: list[visuals.Mesh] = []
        self._floor_edge_lines: list[visuals.Line] = []
        self._floor_labels: list[visuals.Text] = []
        # Wall and slab meshes (dynamic, recreated on rebuild)
        self._wall_meshes: list[visuals.Mesh] = []
        self._slab_meshes: list[visuals.Mesh] = []
        # Edge wireframe lines for walls and slabs
        self._wall_edge_lines: list[visuals.Line] = []
        self._slab_edge_lines: list[visuals.Line] = []
        # Roof meshes
        self._roof_meshes: list[visuals.Mesh] = []
        self._roof_edge_lines: list[visuals.Line] = []
        # Thermal radiation heatmap overlay
        self._radiation_meshes: list[visuals.Mesh] = []
        self._radiation_entity_map: dict = {}       # entity → vispy Mesh
        self._radiation_orig_colors: dict = {}      # entity → face_colors array

        # XYZ axis lines at world origin
        axis_len = 500.0  # mm
        axis_data = np.array([
            [0, 0, 0], [axis_len, 0, 0],    # X
            [0, 0, 0], [0, axis_len, 0],    # Y
            [0, 0, 0], [0, 0, axis_len],    # Z
        ], dtype=np.float32)
        axis_colors = np.array([
            [1, 0, 0, 1], [1, 0, 0, 1],     # X red
            [0, 1, 0, 1], [0, 1, 0, 1],     # Y green
            [0, 0, 1, 1], [0, 0, 1, 1],     # Z blue
        ], dtype=np.float32)
        self._axis_lines = visuals.Line(
            pos=axis_data, color=axis_colors, width=2.5,
            connect='segments', parent=self._view.scene,
        )
        self._axis_labels: list[visuals.Text] = []
        for lbl, pos, col in [
            ("X", [axis_len + 60, 0, 0], (1, 0.2, 0.2, 1)),
            ("Y", [0, axis_len + 60, 0], (0.2, 1, 0.2, 1)),
            ("Z", [0, 0, axis_len + 60], (0.4, 0.4, 1.0, 1)),
        ]:
            t = visuals.Text(
                text=lbl, pos=np.array([pos], dtype=np.float32),
                color=col, font_size=14, bold=True,
                parent=self._view.scene,
            )
            self._axis_labels.append(t)

        # Ground grid in XY plane at Z=0
        self._ground_grid = self._create_ground_grid(5000, 1000)
        self._ground_grid.visible = False
        self._3d_grid_visible = False
        self._level_floors_visible = False

        # Pan state for middle-mouse-button pan
        self._pan_active = False
        self._pan_last_pos = None

        # Section cut state
        self._h_cut_enabled: bool = False
        self._h_cut_height_mm: float = 3000.0     # default ~10 ft

        # Debounce timer
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(100)
        self._rebuild_timer.timeout.connect(self._do_rebuild)

        # Camera sync → ViewCube (track interactive rotation)
        self._canvas.events.mouse_release.connect(self._on_canvas_mouse_release)
        self._canvas.events.mouse_move.connect(self._on_canvas_mouse_move)

        # Mouse picking
        self._canvas.events.mouse_press.connect(self._on_mouse_press)

        # Keyboard events (forward Enter/Escape during radiation selection)
        self._canvas.events.key_press.connect(self._on_key_press)

        # Scroll-to-cursor zoom
        self._canvas.events.mouse_wheel.connect(self._on_mouse_wheel)

        # Middle-button pan
        self._canvas.events.mouse_press.connect(self._on_pan_press)
        self._canvas.events.mouse_move.connect(self._on_pan_move)
        self._canvas.events.mouse_release.connect(self._on_pan_release)

    def _connect_signals(self):
        self._scene.sceneModified.connect(self._schedule_rebuild)
        self._scene.selectionChanged.connect(self._on_2d_selection_changed)

    # ── Coordinate mapping ─────────────────────────────────────────────────

    def _scene_to_3d(self, sx: float, sy: float, z_mm: float = 0.0):
        """Convert 2D scene coords + elevation (mm) to 3D world (mm)."""
        ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
        return np.array([sx / ppm, -sy / ppm, z_mm])

    def _node_to_3d(self, node: Node):
        if node is None:
            return np.array([0.0, 0.0, 0.0])
        return self._scene_to_3d(
            node.scenePos().x(), node.scenePos().y(), node.z_pos,
        )

    def _level_z_mm(self, level_name: str) -> float:
        lvl = self._lm.get(level_name)
        return lvl.elevation if lvl else 0.0

    # ── Rebuild ────────────────────────────────────────────────────────────

    def _schedule_rebuild(self):
        self._dirty = True
        if self.isVisible():
            if not self._rebuild_timer.isActive():
                self._rebuild_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._rebuild_timer.start()

    def _do_rebuild(self):
        if not self._dirty:
            return
        self.rebuild()

    def rebuild(self):
        """Rebuild all 3D visuals from Model_Space data."""
        self._dirty = False

        self._extract_nodes()
        self._extract_pipes()
        self._extract_sprinklers()
        self._extract_water_supply()
        self._extract_construction_geometry()
        self._extract_level_floors()
        self._extract_walls()
        self._extract_floor_slabs()
        self._extract_roofs()
        self._on_2d_selection_changed()

        # Always keep rotation center at the geometry bounding box centre
        bounds = self._compute_scene_bounds()
        if bounds is not None:
            center, _ = bounds
            self._view.camera.center = tuple(center)

        if self._first_build:
            self._fit_camera()
            self._first_build = False

        counts = (
            f"Nodes: {len(self._node_refs)}  "
            f"Pipes: {len(self._pipe_refs)}"
        )
        self._info_label.setText(counts)
        self._canvas.update()

    # ── Extract: Nodes ─────────────────────────────────────────────────────

    def _extract_nodes(self):
        nodes = list(self._scene.sprinkler_system.nodes)
        self._node_refs = nodes
        if not nodes:
            self._node_markers.visible = False
            self._node_positions_3d = None
            return

        positions = np.array([self._node_to_3d(n) for n in nodes])
        self._node_positions_3d = positions

        colors = np.array([
            COL_NODE if not n.has_sprinkler() else (0.3, 0.3, 0.3, 0.5)
            for n in nodes
        ])
        self._node_markers.set_data(
            pos=positions, face_color=colors, size=6, edge_width=0,
        )
        self._node_markers.visible = True

    # ── Extract: Sprinklers ────────────────────────────────────────────────

    def _extract_sprinklers(self):
        nodes_with_spr = [n for n in self._scene.sprinkler_system.nodes
                          if n.has_sprinkler()]
        if not nodes_with_spr:
            self._sprinkler_markers.visible = False
            return

        positions = np.array([self._node_to_3d(n) for n in nodes_with_spr])
        colors = []
        for n in nodes_with_spr:
            orient = n.sprinkler._properties.get("Orientation", {}).get("value", "Upright")
            if orient == "Pendent":
                colors.append((1.0, 0.2, 0.2, 1.0))
            elif orient == "Sidewall":
                colors.append((0.2, 0.8, 0.2, 1.0))
            else:
                colors.append((0.2, 0.4, 1.0, 1.0))
        colors = np.array(colors)

        self._sprinkler_markers.set_data(
            pos=positions, face_color=colors, size=10,
            edge_width=1, edge_color=(1, 1, 1, 0.8),
            symbol="disc",
        )
        self._sprinkler_markers.visible = True

    # ── Extract: Pipes ─────────────────────────────────────────────────────

    def _extract_pipes(self):
        # Remove old cylinder meshes
        for m in self._pipe_cylinder_meshes:
            m.parent = None
        self._pipe_cylinder_meshes.clear()

        pipes = list(self._scene.sprinkler_system.pipes)
        self._pipe_refs = pipes
        if not pipes:
            self._pipe_lines.visible = False
            self._pipe_midpoints_3d = None
            return

        # Build line segment pairs (always needed for midpoints + fallback)
        positions = []
        colors = []
        mids = []
        pipe_data = []  # (p1, p2, color, radius_mm) for cylinder rendering
        for p in pipes:
            if p.node1 is None or p.node2 is None:
                continue
            p1 = self._node_to_3d(p.node1)
            p2 = self._node_to_3d(p.node2)
            positions.append(p1)
            positions.append(p2)
            mids.append((p1 + p2) / 2.0)

            col_name = p._properties.get("Colour", {}).get("value", "Red")
            c = _PIPE_COLORS.get(col_name, (0.9, 0.15, 0.15, 1.0))
            colors.append(c)
            colors.append(c)

            nom = p._properties.get("Diameter", {}).get("value", '2"Ø')
            od_in = _NOMINAL_OD_IN.get(nom, 2.375)
            radius_mm = od_in * 25.4 / 2.0
            pipe_data.append((p1, p2, c, radius_mm))

        if not mids:
            self._pipe_lines.visible = False
            self._pipe_midpoints_3d = None
            return

        self._pipe_midpoints_3d = np.array(mids)

        use_cylinders = len(pipe_data) <= MAX_CYLINDER_PIPES

        if use_cylinders:
            # Render pipes as 3D cylinders
            self._pipe_lines.visible = False
            for p1, p2, color, radius in pipe_data:
                length = float(np.linalg.norm(p2 - p1))
                if length < 1e-6:
                    continue
                try:
                    md = create_cylinder(
                        rows=2, cols=16,
                        radius=[radius, radius],
                        length=length,
                    )
                    verts = md.get_vertices()
                    faces = md.get_faces()
                    # Align cylinder: create_cylinder makes Z-axis cylinder
                    # centered at origin. We need to rotate to p1→p2 direction.
                    verts = self._align_cylinder(verts, p1, p2, length)
                    mesh = visuals.Mesh(
                        vertices=verts, faces=faces,
                        color=color,
                        shading='smooth',
                        parent=self._view.scene,
                    )
                    self._pipe_cylinder_meshes.append(mesh)
                except Exception:
                    pass  # skip problematic pipes
        else:
            # Fallback: line rendering for large pipe counts
            nom = pipes[0]._properties.get("Diameter", {}).get("value", '2"Ø')
            od = _NOMINAL_OD_IN.get(nom, 2.375)
            width = max(2.0, od * 1.5)
            self._pipe_lines.set_data(
                pos=np.array(positions),
                color=np.array(colors),
                width=width,
                connect="segments",
            )
            self._pipe_lines.visible = True

    @staticmethod
    def _align_cylinder(verts: np.ndarray, p1: np.ndarray, p2: np.ndarray,
                        length: float) -> np.ndarray:
        """Rotate + translate cylinder vertices from Z-axis to p1→p2 direction.

        create_cylinder produces a cylinder along Z, centered at origin,
        spanning z ∈ [-length/2, +length/2].
        """
        direction = (p2 - p1) / length  # unit vector
        midpoint = (p1 + p2) / 2.0

        # Build rotation matrix from Z-axis to 'direction'
        z_axis = np.array([0.0, 0.0, 1.0])
        v = np.cross(z_axis, direction)
        c = float(np.dot(z_axis, direction))

        if abs(c + 1.0) < 1e-6:
            # Anti-parallel: 180° rotation around X
            rot = np.diag([-1.0, -1.0, 1.0]).astype(np.float32)
            rot[2, 2] = -1.0
            rot[0, 0] = 1.0
        elif abs(c - 1.0) < 1e-6:
            # Already aligned
            rot = np.eye(3, dtype=np.float32)
        else:
            # Rodrigues' rotation formula
            vx = np.array([
                [0, -v[2], v[1]],
                [v[2], 0, -v[0]],
                [-v[1], v[0], 0],
            ])
            rot = np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))
            rot = rot.astype(np.float32)

        # Apply rotation and translation
        result = (rot @ verts.T).T + midpoint.astype(np.float32)
        return result

    # ── Extract: Water Supply ──────────────────────────────────────────────

    def _extract_water_supply(self):
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is None:
            self._ws_marker.visible = False
            return
        pos = self._scene_to_3d(ws.scenePos().x(), ws.scenePos().y(), 0)
        self._ws_marker.set_data(
            pos=np.array([pos]), face_color=[COL_WATER_SUPPLY],
            size=14, edge_width=2, edge_color=(1, 1, 1, 1),
            symbol="diamond",
        )
        self._ws_marker.visible = True

    # ── Extract: Construction Geometry ─────────────────────────────────────

    def _extract_construction_geometry(self):
        lines_data = []  # pairs of 3D points

        def _pen_rgba(item):
            c = item.pen().color()
            return (c.redF(), c.greenF(), c.blueF(), c.alphaF())

        # Lines
        for item in getattr(self._scene, "_draw_lines", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            p1 = item._pt1
            p2 = item._pt2
            lines_data.append(np.array([p1.x() / ppm, -p1.y() / ppm, z]))
            lines_data.append(np.array([p2.x() / ppm, -p2.y() / ppm, z]))

        # Construction lines
        for item in getattr(self._scene, "_construction_lines", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            p1 = item._pt1
            p2 = item._pt2
            lines_data.append(np.array([p1.x() / ppm, -p1.y() / ppm, z]))
            lines_data.append(np.array([p2.x() / ppm, -p2.y() / ppm, z]))

        # Rectangles (4 edges)
        for item in getattr(self._scene, "_draw_rects", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            r = item.rect()
            corners = [
                np.array([r.left() / ppm, -r.top() / ppm, z]),
                np.array([r.right() / ppm, -r.top() / ppm, z]),
                np.array([r.right() / ppm, -r.bottom() / ppm, z]),
                np.array([r.left() / ppm, -r.bottom() / ppm, z]),
            ]
            for i in range(4):
                lines_data.append(corners[i])
                lines_data.append(corners[(i + 1) % 4])

        # Circles (polygon approximation)
        for item in getattr(self._scene, "_draw_circles", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            cx = item._center.x() / ppm
            cy = -item._center.y() / ppm
            r = item._radius / ppm
            for i in range(CIRCLE_SEGMENTS):
                a1 = 2 * math.pi * i / CIRCLE_SEGMENTS
                a2 = 2 * math.pi * (i + 1) / CIRCLE_SEGMENTS
                lines_data.append(np.array([cx + r * math.cos(a1), cy + r * math.sin(a1), z]))
                lines_data.append(np.array([cx + r * math.cos(a2), cy + r * math.sin(a2), z]))

        # Arcs
        for item in getattr(self._scene, "_draw_arcs", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            cx = item._center.x() / ppm
            cy = -item._center.y() / ppm
            r = item._radius / ppm
            start = math.radians(item._start_deg)
            span = math.radians(item._span_deg)
            n_seg = max(8, int(abs(span) / (2 * math.pi) * CIRCLE_SEGMENTS))
            for i in range(n_seg):
                a1 = start + span * i / n_seg
                a2 = start + span * (i + 1) / n_seg
                lines_data.append(np.array([cx + r * math.cos(a1), cy + r * math.sin(a1), z]))
                lines_data.append(np.array([cx + r * math.cos(a2), cy + r * math.sin(a2), z]))

        # Polylines
        for item in getattr(self._scene, "_polylines", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            pts = item._points
            for i in range(len(pts) - 1):
                lines_data.append(np.array([pts[i].x() / ppm, -pts[i].y() / ppm, z]))
                lines_data.append(np.array([pts[i + 1].x() / ppm, -pts[i + 1].y() / ppm, z]))

        if lines_data:
            self._constr_lines.set_data(
                pos=np.array(lines_data), connect="segments",
            )
            self._constr_lines.visible = True
        else:
            self._constr_lines.visible = False

    # ── Extract: Level Floors ──────────────────────────────────────────────

    def _extract_level_floors(self):
        # Remove old floor meshes, edge lines, and labels
        for m in self._floor_meshes:
            m.parent = None
        self._floor_meshes.clear()
        for ln in self._floor_edge_lines:
            ln.parent = None
        self._floor_edge_lines.clear()
        for lbl in self._floor_labels:
            lbl.parent = None
        self._floor_labels.clear()

        # Compute overall XY bounds from all nodes
        nodes = list(self._scene.sprinkler_system.nodes)
        if not nodes:
            return

        positions = self._node_positions_3d
        if positions is None or len(positions) == 0:
            return

        x_min, y_min = positions[:, 0].min(), positions[:, 1].min()
        x_max, y_max = positions[:, 0].max(), positions[:, 1].max()
        pad = max(abs(x_max - x_min), abs(y_max - y_min)) * 0.15 + 500
        x_min -= pad
        x_max += pad
        y_min -= pad
        y_max += pad

        for i, lvl in enumerate(self._lm.levels):
            z = lvl.elevation
            col = _FLOOR_COLORS[i % len(_FLOOR_COLORS)]

            verts = np.array([
                [x_min, y_min, z],
                [x_max, y_min, z],
                [x_max, y_max, z],
                [x_min, y_max, z],
            ], dtype=np.float32)
            faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)

            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                parent=self._view.scene,
            )
            self._floor_meshes.append(mesh)

            # Edge outline (closed loop around the floor boundary)
            border_pts = np.array([
                [x_min, y_min, z],
                [x_max, y_min, z],
                [x_max, y_max, z],
                [x_min, y_max, z],
                [x_min, y_min, z],  # close loop
            ], dtype=np.float32)
            edge_line = visuals.Line(
                pos=border_pts,
                color=(col[0], col[1], col[2], 0.6),
                width=1.5,
                connect='strip',
                parent=self._view.scene,
            )
            self._floor_edge_lines.append(edge_line)

            # Level name label
            label = visuals.Text(
                text=lvl.name,
                pos=np.array([[x_min + 200, y_min + 200, z + 50]]),
                color=(1.0, 1.0, 1.0, 0.7),
                font_size=12,
                bold=True,
                parent=self._view.scene,
            )
            self._floor_labels.append(label)

    # ── Edge extraction helper ──────────────────────────────────────────────

    @staticmethod
    def _edges_from_faces(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
        """Extract visible edge segments from a triangulated mesh.

        Filters out internal diagonal edges created when quads are split
        into two triangles.  An edge shared by two coplanar faces (normals
        within ~0.06° of each other) is considered a triangulation artefact
        and is skipped.

        Returns Nx3 array of line-segment endpoints (pairs of 3D points),
        suitable for ``visuals.Line(connect='segments')``.
        """
        # Build edge → face-index mapping and compute face normals
        edge_faces: dict[tuple[int, int], list[int]] = {}
        face_normals: list[np.ndarray] = []

        for fi, f in enumerate(faces):
            v0, v1, v2 = verts[int(f[0])], verts[int(f[1])], verts[int(f[2])]
            normal = np.cross(v1 - v0, v2 - v0)
            norm_len = np.linalg.norm(normal)
            if norm_len > 1e-10:
                normal = normal / norm_len
            face_normals.append(normal)

            for i in range(3):
                e = tuple(sorted([int(f[i]), int(f[(i + 1) % 3])]))
                edge_faces.setdefault(e, []).append(fi)

        if not edge_faces:
            return np.zeros((0, 3), dtype=np.float32)

        segments: list[np.ndarray] = []
        for (a, b), fi_list in edge_faces.items():
            if len(fi_list) == 1:
                # Boundary edge — always visible
                segments.append(verts[a])
                segments.append(verts[b])
            elif len(fi_list) == 2:
                # Shared edge — draw only if the two faces are NOT coplanar
                dot = abs(float(np.dot(face_normals[fi_list[0]],
                                       face_normals[fi_list[1]])))
                if dot < 0.999:
                    segments.append(verts[a])
                    segments.append(verts[b])
            else:
                # Non-manifold edge — always visible
                segments.append(verts[a])
                segments.append(verts[b])

        if not segments:
            return np.zeros((0, 3), dtype=np.float32)
        return np.array(segments, dtype=np.float32)

    # ── Extract: Walls ────────────────────────────────────────────────────

    def _extract_walls(self):
        """Render wall entities as extruded 3D meshes with edge lines."""
        # Remove old meshes and edge lines
        for m in self._wall_meshes:
            m.parent = None
        self._wall_meshes.clear()
        for ln in self._wall_edge_lines:
            if ln is not None:
                ln.parent = None
        self._wall_edge_lines.clear()
        self._wall_refs.clear()
        self._wall_mesh_data.clear()
        self._original_wall_colors.clear()

        scene_obj = self._scene
        if scene_obj is None:
            self._wall_centroids_3d = None
            return
        lm = self._lm
        centroids = []
        for wall in getattr(scene_obj, "_walls", []):
            mesh_data = wall.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.8, 0.8, 0.8, 0.9))
            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                shading='smooth',
                parent=self._view.scene,
            )
            self._wall_meshes.append(mesh)
            self._wall_refs.append(wall)
            self._wall_mesh_data.append((verts, faces))
            self._original_wall_colors.append((col, (0.1, 0.1, 0.1, 0.8)))
            centroids.append(verts.mean(axis=0))
            # Edge wireframe
            edge_segs = self._edges_from_faces(verts, faces)
            if len(edge_segs) > 0:
                edge_line = visuals.Line(
                    pos=edge_segs,
                    color=(0.1, 0.1, 0.1, 0.8),
                    width=1.5,
                    connect='segments',
                    parent=self._view.scene,
                )
                self._wall_edge_lines.append(edge_line)
            else:
                self._wall_edge_lines.append(None)
        self._wall_centroids_3d = np.array(centroids) if centroids else None

    # ── Extract: Floor Slabs ──────────────────────────────────────────────

    def _extract_floor_slabs(self):
        """Render floor slab entities as solid 3D meshes with edge lines."""
        # Remove old meshes and edge lines
        for m in self._slab_meshes:
            m.parent = None
        self._slab_meshes.clear()
        for ln in self._slab_edge_lines:
            if ln is not None:
                ln.parent = None
        self._slab_edge_lines.clear()
        self._slab_refs.clear()
        self._slab_mesh_data.clear()
        self._original_slab_colors.clear()

        scene_obj = self._scene
        if scene_obj is None:
            self._slab_centroids_3d = None
            return
        lm = self._lm
        centroids = []
        for slab in getattr(scene_obj, "_floor_slabs", []):
            mesh_data = slab.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.5, 0.5, 0.8, 0.5))
            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                parent=self._view.scene,
            )
            self._slab_meshes.append(mesh)
            self._slab_refs.append(slab)
            self._slab_mesh_data.append((verts, faces))
            self._original_slab_colors.append((col, (0.15, 0.15, 0.15, 0.7)))
            centroids.append(verts.mean(axis=0))
            # Edge wireframe
            edge_segs = self._edges_from_faces(verts, faces)
            if len(edge_segs) > 0:
                edge_line = visuals.Line(
                    pos=edge_segs,
                    color=(0.15, 0.15, 0.15, 0.7),
                    width=1.0,
                    connect='segments',
                    parent=self._view.scene,
                )
                self._slab_edge_lines.append(edge_line)
            else:
                self._slab_edge_lines.append(None)
        self._slab_centroids_3d = np.array(centroids) if centroids else None

    def _extract_roofs(self):
        """Render roof entities as solid 3D meshes with edge lines."""
        for m in self._roof_meshes:
            m.parent = None
        self._roof_meshes.clear()
        for ln in self._roof_edge_lines:
            if ln is not None:
                ln.parent = None
        self._roof_edge_lines.clear()
        self._roof_refs.clear()
        self._roof_mesh_data.clear()
        self._original_roof_colors.clear()

        scene_obj = self._scene
        if scene_obj is None:
            self._roof_centroids_3d = None
            return
        lm = self._lm
        centroids = []
        for roof in getattr(scene_obj, "_roofs", []):
            mesh_data = roof.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.8, 0.7, 0.5, 0.5))
            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                parent=self._view.scene,
            )
            self._roof_meshes.append(mesh)
            self._roof_refs.append(roof)
            self._roof_mesh_data.append((verts, faces))
            self._original_roof_colors.append((col, (0.15, 0.15, 0.15, 0.7)))
            centroids.append(verts.mean(axis=0))
            edge_segs = self._edges_from_faces(verts, faces)
            if len(edge_segs) > 0:
                edge_line = visuals.Line(
                    pos=edge_segs,
                    color=(0.15, 0.15, 0.15, 0.7),
                    width=1.0,
                    connect='segments',
                    parent=self._view.scene,
                )
                self._roof_edge_lines.append(edge_line)
            else:
                self._roof_edge_lines.append(None)
        self._roof_centroids_3d = np.array(centroids) if centroids else None

    # ── Camera ─────────────────────────────────────────────────────────────

    def _compute_scene_bounds(self):
        """Compute bounding box center and span across ALL 3D geometry.

        Returns (center, span) as numpy arrays, or None if no geometry.
        """
        all_pts: list[np.ndarray] = []
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            all_pts.append(self._node_positions_3d)
        if self._pipe_midpoints_3d is not None and len(self._pipe_midpoints_3d) > 0:
            all_pts.append(self._pipe_midpoints_3d)
        if self._wall_centroids_3d is not None and len(self._wall_centroids_3d) > 0:
            all_pts.append(self._wall_centroids_3d)
        if self._slab_centroids_3d is not None and len(self._slab_centroids_3d) > 0:
            all_pts.append(self._slab_centroids_3d)
        if self._roof_centroids_3d is not None and len(self._roof_centroids_3d) > 0:
            all_pts.append(self._roof_centroids_3d)
        if not all_pts:
            return None
        combined = np.vstack(all_pts)
        return combined.mean(axis=0), combined.max(axis=0) - combined.min(axis=0)

    def _fit_camera(self):
        """Auto-fit camera to encompass all geometry."""
        bounds = self._compute_scene_bounds()
        if bounds is not None:
            center, span = bounds
            dist = max(span) * 1.8
            self._view.camera.center = tuple(center)
            self._view.camera.distance = max(dist, 1000)

    def _toggle_projection(self):
        """Toggle between perspective and orthographic projection."""
        self._perspective = not self._perspective
        cam = self._view.camera
        if self._perspective:
            cam.fov = 45
            self._proj_btn.setText("Ortho")
        else:
            # Transfer perspective zoom level to ortho scale_factor so
            # mouse-wheel zoom continues to work in orthographic mode.
            half_h = cam.distance * math.tan(math.radians(cam.fov / 2))
            cam.fov = 0
            cam.scale_factor = half_h * 2
            self._proj_btn.setText("Perspective")

    def _create_ground_grid(self, extent: float, step: float):
        """Create a ground grid in the XY plane at Z=0."""
        pts = []
        val = -extent
        while val <= extent:
            pts.append([val, -extent, 0])
            pts.append([val,  extent, 0])
            pts.append([-extent, val, 0])
            pts.append([ extent, val, 0])
            val += step
        return visuals.Line(
            pos=np.array(pts, dtype=np.float32),
            color=(0.3, 0.3, 0.3, 0.2),
            width=1.0,
            connect='segments',
            parent=self._view.scene,
        )

    def _toggle_3d_grid(self):
        """Toggle ground grid visibility (origin axis always remains visible)."""
        self._3d_grid_visible = not self._3d_grid_visible
        self._ground_grid.visible = self._3d_grid_visible

    def _toggle_level_floors(self):
        """Toggle level floor planes, edge lines, and labels visibility."""
        self._level_floors_visible = not self._level_floors_visible
        vis = self._level_floors_visible
        for m in self._floor_meshes:
            m.visible = vis
        for ln in self._floor_edge_lines:
            ln.visible = vis
        for lbl in self._floor_labels:
            lbl.visible = vis
        self._canvas.update()

    def _set_view_preset(self, elevation: float, azimuth: float):
        """Set camera to a standard engineering view preset."""
        self._view.camera.elevation = elevation
        self._view.camera.azimuth = azimuth
        # Top view → switch to orthographic for true plan view
        if elevation == 90:
            self._view.camera.fov = 0
            self._proj_btn.setText("Perspective")
            self._perspective = False
        self._fit_camera()
        self._sync_viewcube()
        self._canvas.update()

    # ── ViewCube ──────────────────────────────────────────────────────────

    def _position_viewcube(self):
        """Place the ViewCube in the top-right corner of the canvas."""
        cw = self._canvas.native.width()
        vc = self._view_cube
        margin = 4
        vc.move(cw - vc.width() - margin, margin)

    def _on_viewcube_request(self, elevation: float, azimuth: float):
        """Handle a ViewCube click → snap camera to the requested angle."""
        self._set_view_preset(elevation, azimuth)

    def _sync_viewcube(self):
        """Push current camera angles to the ViewCube so it rotates."""
        elev = self._view.camera.elevation
        azim = self._view.camera.azimuth
        self._view_cube.set_camera_angles(elev, azim)

    def _on_canvas_mouse_release(self, event):
        """Sync ViewCube after the user finishes rotating the camera."""
        self._sync_viewcube()

    def _on_canvas_mouse_move(self, event):
        """Sync ViewCube during interactive camera rotation."""
        if event.is_dragging:
            self._sync_viewcube()

    # ── Scroll-to-cursor zoom ────────────────────────────────────────────

    def _on_mouse_wheel(self, event):
        """Zoom toward/away from the cursor position instead of screen center."""
        cam = self._view.camera
        screen_pos = np.array(event.pos[:2], dtype=float)

        # Scroll delta: positive = zoom in, negative = zoom out
        delta = event.delta[1] if len(event.delta) > 1 else event.delta[0]
        zoom_factor = 0.9 if delta > 0 else 1.0 / 0.9  # ~1.111

        # Unproject cursor position to 3D world coordinates
        try:
            tr = self._node_markers.transforms.get_transform(
                map_from='canvas', map_to='visual',
            )
            # Use depth=0.5 (mid-clip) as a reasonable depth estimate
            mapped = tr.map(list(screen_pos) + [0.5])
            if len(mapped) >= 4 and mapped[3] != 0:
                mapped = mapped / mapped[3]
            target_3d = np.array(mapped[:3], dtype=float)
            if not np.all(np.isfinite(target_3d)):
                return  # fallback to default zoom
        except Exception:
            return  # let default camera zoom handle it

        # Shift camera center toward cursor's 3D point
        center = np.array(cam.center, dtype=float)
        shift = (target_3d - center) * (1.0 - zoom_factor)
        cam.center = tuple(center + shift)

        # Apply zoom
        if cam.fov > 0:  # perspective
            cam.distance = max(cam.distance * zoom_factor, 10)
        else:  # orthographic
            cam.scale_factor = max(cam.scale_factor * zoom_factor, 1)

        self._canvas.update()
        self._sync_viewcube()
        event.handled = True

    # ── Middle-button pan ─────────────────────────────────────────────────

    def _on_pan_press(self, event):
        """Start pan on middle mouse button press (vispy button 3)."""
        if event.button == 3:  # middle button in vispy
            self._pan_active = True
            self._pan_last_pos = np.array(event.pos[:2], dtype=float)
            # Block camera from processing this event (prevent default orbit)
            event.handled = True

    def _on_pan_move(self, event):
        """Pan the 3D camera by adjusting camera.center."""
        if not self._pan_active or self._pan_last_pos is None:
            return
        cur = np.array(event.pos[:2], dtype=float)
        dx = cur[0] - self._pan_last_pos[0]
        dy = cur[1] - self._pan_last_pos[1]
        self._pan_last_pos = cur

        cam = self._view.camera
        # Compute right and up vectors from camera azimuth/elevation
        az = math.radians(cam.azimuth)
        el = math.radians(cam.elevation)

        # Right vector (perpendicular to look direction in XY plane)
        right = np.array([-math.sin(az), math.cos(az), 0.0])
        # Up vector (perpendicular to both look direction and right)
        up = np.array([
            -math.cos(az) * math.sin(el),
            -math.sin(az) * math.sin(el),
            math.cos(el),
        ])

        # Scale movement by camera distance for reasonable speed
        scale = cam.distance * 0.001
        shift = (dx * right - dy * up) * scale

        center = np.array(cam.center, dtype=float)
        cam.center = tuple(center + shift)
        self._canvas.update()
        event.handled = True

    def _on_pan_release(self, event):
        """End pan on middle mouse button release."""
        if event.button == 3 and self._pan_active:
            self._pan_active = False
            self._pan_last_pos = None
            self._sync_viewcube()
            event.handled = True

    def resizeEvent(self, event):
        """Reposition ViewCube when the widget is resized."""
        super().resizeEvent(event)
        self._position_viewcube()

    # ── Section Cuts ───────────────────────────────────────────────────────

    def _toggle_horizontal_cut(self):
        """Toggle horizontal section cut on/off."""
        self._h_cut_enabled = self._section_h_btn.isChecked()
        if self._h_cut_enabled:
            # Use mid-level height as default cut if levels exist
            if self._lm is not None:
                levels = self._lm.levels
                if len(levels) >= 2:
                    self._h_cut_height_mm = levels[1].elevation
            self._apply_horizontal_cut()
        else:
            self._remove_horizontal_cut()
        self._canvas.update()

    def _apply_horizontal_cut(self):
        """Hide all meshes whose geometry is entirely above the cut plane."""
        cut_z = self._h_cut_height_mm
        for mesh_list in (self._wall_meshes, self._slab_meshes, self._roof_meshes, self._floor_meshes):
            for m in mesh_list:
                md = getattr(m, '_meshdata', None)
                if md is not None:
                    verts = md.get_vertices()
                    if verts is not None and len(verts) > 0:
                        min_z = verts[:, 2].min()
                        m.visible = min_z < cut_z
                    else:
                        m.visible = True
                else:
                    m.visible = True

        # Sync edge line visibility with their corresponding meshes
        for i, ln in enumerate(self._wall_edge_lines):
            if ln is not None:
                ln.visible = self._wall_meshes[i].visible if i < len(self._wall_meshes) else True
        for i, ln in enumerate(self._slab_edge_lines):
            if ln is not None:
                ln.visible = self._slab_meshes[i].visible if i < len(self._slab_meshes) else True
        for i, ln in enumerate(self._roof_edge_lines):
            if ln is not None:
                ln.visible = self._roof_meshes[i].visible if i < len(self._roof_meshes) else True

        # Clip nodes/sprinklers above cut
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            below = self._node_positions_3d[:, 2] < cut_z
            pos_vis = self._node_positions_3d[below]
            if len(pos_vis) > 0:
                self._node_markers.set_data(
                    pos=pos_vis,
                    face_color=COL_NODE, edge_color=COL_NODE,
                    size=6,
                )
            else:
                self._node_markers.set_data(pos=np.zeros((0, 3), dtype=np.float32))

    def _remove_horizontal_cut(self):
        """Restore all meshes to visible (respecting floors toggle)."""
        for mesh_list in (self._wall_meshes, self._slab_meshes, self._roof_meshes):
            for m in mesh_list:
                m.visible = True
        # Restore floor meshes only if floors are toggled on
        floors_vis = self._level_floors_visible
        for m in self._floor_meshes:
            m.visible = floors_vis
        for ln in self._floor_edge_lines:
            if ln is not None:
                ln.visible = floors_vis
        for lbl in self._floor_labels:
            lbl.visible = floors_vis
        # Restore edge lines
        for ln in self._wall_edge_lines + self._slab_edge_lines + self._roof_edge_lines:
            if ln is not None:
                ln.visible = True
        # Restore node markers
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            self._node_markers.set_data(
                pos=self._node_positions_3d,
                face_color=COL_NODE, edge_color=COL_NODE,
                size=6,
            )

    # ── Selection / Picking ────────────────────────────────────────────────

    def _on_mouse_press(self, event):
        """Handle click in 3D view for entity selection.

        Plain click selects one item (clearing previous selection).
        Ctrl+click toggles the clicked item in/out of the current selection
        (for multi-select during radiation analysis, etc.).
        """
        if event.button != 1:  # left click only
            return

        screen_pos = np.array(event.pos[:2], dtype=float)
        hit = self._pick_nearest(screen_pos)
        print(f"[3D] click at {screen_pos}, hit={hit}")

        # Check for Ctrl modifier (vispy stores modifiers as a tuple of strings)
        modifiers = getattr(event, 'modifiers', None) or []
        ctrl_held = 'Control' in modifiers

        if hit is not None:
            if ctrl_held:
                # Toggle selection on this item
                hit.setSelected(not hit.isSelected())
            else:
                self._scene.clearSelection()
                hit.setSelected(True)
            selected = [it for it in self._scene.selectedItems()]
            self.entitySelected.emit(hit)
            self._highlight_mesh_selection(selected)
            # Block camera rotation when clicking an entity
            event.handled = True
        elif ctrl_held:
            # Ctrl+click on empty space: do nothing (preserve selection,
            # block camera so an accidental miss doesn't rotate the view)
            event.handled = True
        else:
            # Plain click on empty space: let the camera handle it
            # (allows orbit rotation without losing workflow).
            # Don't clear selection — user can rotate freely and keep
            # their current selection intact.
            pass

    def _on_key_press(self, event):
        """Forward Enter/Escape to Model_Space during radiation selection."""
        if getattr(self._scene, '_radiation_selecting', False):
            if event.key == 'Enter' or event.key == 'Return':
                self._scene.radiationConfirm.emit()
                return
            if event.key == 'Escape':
                self._scene._radiation_selecting = False
                self._scene.radiationCancel.emit()
                return

    @staticmethod
    def _point_in_triangle_2d(p, a, b, c):
        """Return True if 2D point *p* is inside triangle (a, b, c).

        Uses the sign-of-cross-product (barycentric) method.
        """
        def _cross(o, v1, v2):
            return (v1[0] - o[0]) * (v2[1] - o[1]) - (v1[1] - o[1]) * (v2[0] - o[0])
        d1 = _cross(p, a, b)
        d2 = _cross(p, b, c)
        d3 = _cross(p, c, a)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)

    def _pick_mesh_entities(self, screen_pos, mesh_data_list, ref_list):
        """Check if *screen_pos* falls inside any projected triangle of the
        meshes in *mesh_data_list*.  Returns the first matching entity from
        *ref_list*, or ``None``.
        """
        for idx, (verts, faces) in enumerate(mesh_data_list):
            # Project all vertices to screen space (cache per-entity)
            projected = []
            for v in verts:
                s = self._project_to_screen(v)
                projected.append(s)
            # Test each triangle
            for face in faces:
                tri = [projected[face[0]], projected[face[1]], projected[face[2]]]
                if any(t is None for t in tri):
                    continue
                if self._point_in_triangle_2d(screen_pos, tri[0], tri[1], tri[2]):
                    return ref_list[idx]
        return None

    def _pick_nearest(self, screen_pos: np.ndarray):
        """Find nearest entity to a screen-space click position."""
        best_item = None
        best_dist = float("inf")

        # Check nodes (point-distance)
        if self._node_positions_3d is not None:
            for i, pos3d in enumerate(self._node_positions_3d):
                screen = self._project_to_screen(pos3d)
                if screen is None:
                    continue
                dist = np.linalg.norm(screen - screen_pos)
                if dist < PICK_TOLERANCE_PX and dist < best_dist:
                    best_dist = dist
                    best_item = self._node_refs[i]

        # Check pipe midpoints (point-distance)
        if self._pipe_midpoints_3d is not None:
            for i, pos3d in enumerate(self._pipe_midpoints_3d):
                screen = self._project_to_screen(pos3d)
                if screen is None:
                    continue
                dist = np.linalg.norm(screen - screen_pos)
                if dist < PICK_TOLERANCE_PX and dist < best_dist:
                    best_dist = dist
                    best_item = self._pipe_refs[i]

        # If a node/pipe was hit at close range, prefer it over mesh hits
        if best_item is not None and best_dist < PICK_TOLERANCE_PX / 2:
            return best_item

        # Check walls (triangle hit-test on projected mesh)
        hit = self._pick_mesh_entities(screen_pos, self._wall_mesh_data, self._wall_refs)
        if hit is not None:
            return hit

        # Check slabs
        hit = self._pick_mesh_entities(screen_pos, self._slab_mesh_data, self._slab_refs)
        if hit is not None:
            return hit

        # Check roofs
        hit = self._pick_mesh_entities(screen_pos, self._roof_mesh_data, self._roof_refs)
        if hit is not None:
            return hit

        return best_item

    def _project_to_screen(self, world_pos: np.ndarray):
        """Project a 3D world position to 2D screen (canvas) coordinates.

        Uses the node_markers visual's transform chain so the full path
        scene → camera → canvas is traversed (including the perspective
        projection from the TurntableCamera).
        """
        try:
            # Use a concrete visual (node_markers) that lives inside the
            # view's scene.  Its transform chain includes:
            #   visual-local → scene → viewbox → document → canvas
            # which passes through the camera's projection matrix.
            tr = self._node_markers.transforms.get_transform(
                map_from='visual', map_to='canvas',
            )
            pos = np.array(world_pos[:3], dtype=np.float64)
            mapped = tr.map(pos)
            # Perspective divide: vispy returns homogeneous coords [x,y,z,w]
            if len(mapped) >= 4 and mapped[3] != 0:
                mapped = mapped / mapped[3]
            result = np.array(mapped[:2], dtype=float)
            # Reject if the result contains NaN/Inf or is behind the camera
            if not np.all(np.isfinite(result)):
                return None
            return result
        except Exception as exc:
            print(f"[3D] projection failed: {exc}")
            return None

    # ── Mesh Selection Highlight ─────────────────────────────────────────────

    def _highlight_mesh_selection(self, selected_items):
        """Highlight selected walls/slabs and fade non-selected ones.

        *selected_items* is a list of WallSegment / FloorSlab instances
        (may be empty or None).
        """
        if selected_items is None:
            selected_items = []

        # Reset all walls to original colors
        for i, mesh in enumerate(self._wall_meshes):
            if i < len(self._original_wall_colors):
                orig_col, orig_edge = self._original_wall_colors[i]
                mesh.color = orig_col
                if i < len(self._wall_edge_lines) and self._wall_edge_lines[i] is not None:
                    self._wall_edge_lines[i].set_data(color=orig_edge, width=1.5)

        for i, mesh in enumerate(self._slab_meshes):
            if i < len(self._original_slab_colors):
                orig_col, orig_edge = self._original_slab_colors[i]
                mesh.color = orig_col
                if i < len(self._slab_edge_lines) and self._slab_edge_lines[i] is not None:
                    self._slab_edge_lines[i].set_data(color=orig_edge, width=1.0)

        for i, mesh in enumerate(self._roof_meshes):
            if i < len(self._original_roof_colors):
                orig_col, orig_edge = self._original_roof_colors[i]
                mesh.color = orig_col
                if i < len(self._roof_edge_lines) and self._roof_edge_lines[i] is not None:
                    self._roof_edge_lines[i].set_data(color=orig_edge, width=1.0)

        # Reset all radiation overlay meshes to original colors
        for entity, orig_fc in self._radiation_orig_colors.items():
            rad_mesh = self._radiation_entity_map.get(entity)
            if rad_mesh is not None:
                try:
                    rad_mesh.set_data(face_colors=orig_fc)
                except Exception:
                    pass

        if not selected_items:
            self._canvas.update()
            return

        # Build sets of selected wall and slab indices
        sel_wall_idxs = set()
        sel_slab_idxs = set()
        sel_roof_idxs = set()
        for sel in selected_items:
            for i, ref in enumerate(self._wall_refs):
                if ref is sel:
                    sel_wall_idxs.add(i)
            for i, ref in enumerate(self._slab_refs):
                if ref is sel:
                    sel_slab_idxs.add(i)
            for i, ref in enumerate(self._roof_refs):
                if ref is sel:
                    sel_roof_idxs.add(i)

        if not sel_wall_idxs and not sel_slab_idxs and not sel_roof_idxs:
            self._canvas.update()
            return

        # Highlight selected, fade others
        for i, mesh in enumerate(self._wall_meshes):
            if i in sel_wall_idxs:
                mesh.color = COL_SEL_MESH
                if i < len(self._wall_edge_lines) and self._wall_edge_lines[i] is not None:
                    self._wall_edge_lines[i].set_data(color=COL_SEL_EDGE, width=3.0)
            else:
                if i < len(self._original_wall_colors):
                    r, g, b, _a = self._original_wall_colors[i][0]
                    mesh.color = (r, g, b, DESELECT_ALPHA)

        for i, mesh in enumerate(self._slab_meshes):
            if i in sel_slab_idxs:
                mesh.color = COL_SEL_MESH
                if i < len(self._slab_edge_lines) and self._slab_edge_lines[i] is not None:
                    self._slab_edge_lines[i].set_data(color=COL_SEL_EDGE, width=2.5)
            else:
                if i < len(self._original_slab_colors):
                    r, g, b, _a = self._original_slab_colors[i][0]
                    mesh.color = (r, g, b, DESELECT_ALPHA)

        for i, mesh in enumerate(self._roof_meshes):
            if i in sel_roof_idxs:
                mesh.color = COL_SEL_MESH
                if i < len(self._roof_edge_lines) and self._roof_edge_lines[i] is not None:
                    self._roof_edge_lines[i].set_data(color=COL_SEL_EDGE, width=2.5)
            else:
                if i < len(self._original_roof_colors):
                    r, g, b, _a = self._original_roof_colors[i][0]
                    mesh.color = (r, g, b, DESELECT_ALPHA)

        # Highlight radiation heatmap overlays for selected entities
        if self._radiation_meshes:
            for sel in selected_items:
                rad_mesh = self._radiation_entity_map.get(sel)
                orig_fc = self._radiation_orig_colors.get(sel)
                if rad_mesh is not None and orig_fc is not None:
                    # Brighten colors to indicate selection
                    tinted = orig_fc.copy()
                    tinted[:, :3] = np.clip(tinted[:, :3] * 0.5 + 0.5, 0.0, 1.0)
                    try:
                        rad_mesh.set_data(face_colors=tinted)
                    except Exception:
                        pass

        self._canvas.update()

    # ── 2D → 3D Selection Sync ─────────────────────────────────────────────

    def _on_2d_selection_changed(self):
        """Highlight selected items in 3D."""
        try:
            selected = self._scene.selectedItems()
        except RuntimeError:
            # Scene C++ object already deleted during shutdown
            return
        if not selected:
            self._highlight_markers.visible = False
            self._highlight_mesh_selection(None)
            return

        positions = []
        mesh_selected = []
        for item in selected:
            if isinstance(item, Node):
                positions.append(self._node_to_3d(item))
            elif isinstance(item, Pipe):
                if item.node1 is not None and item.node2 is not None:
                    mid = (self._node_to_3d(item.node1) + self._node_to_3d(item.node2)) / 2
                    positions.append(mid)
            elif isinstance(item, (WallSegment, FloorSlab)):
                mesh_selected.append(item)
            elif hasattr(item, '_roof_type'):  # RoofItem
                mesh_selected.append(item)

        if positions:
            self._highlight_markers.set_data(
                pos=np.array(positions),
                face_color=COL_HIGHLIGHT,
                size=16, edge_width=2, edge_color=(1, 1, 1, 1),
                symbol="ring",
            )
            self._highlight_markers.visible = True
        else:
            self._highlight_markers.visible = False

        self._highlight_mesh_selection(mesh_selected)

    # ------------------------------------------------------------------
    # Thermal radiation heatmap overlay
    # ------------------------------------------------------------------

    def show_radiation_heatmap(self, result):
        """Overlay colour-mapped meshes on receiver surfaces.

        Parameters
        ----------
        result : RadiationResult
            The solver result containing per-receiver mesh and flux data.
        """
        self.clear_radiation_heatmap()
        threshold = result.threshold

        for entity, flux in result.per_receiver_flux.items():
            sub = result.per_receiver_mesh.get(entity)
            if sub is None:
                continue
            verts = np.asarray(sub["vertices"], dtype=np.float64)
            faces = np.asarray(sub["faces"], dtype=np.int32)
            if len(faces) == 0:
                continue

            # Offset vertices slightly along per-face normals to avoid
            # z-fighting with the underlying wall/roof mesh.
            OFFSET_MM = 15.0
            v0 = verts[faces[:, 0]]
            v1 = verts[faces[:, 1]]
            v2 = verts[faces[:, 2]]
            normals = np.cross(v1 - v0, v2 - v0)
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            normals = normals / norms  # unit face normals (Nf, 3)

            # Compute per-vertex offset by averaging adjacent face normals
            vert_normals = np.zeros_like(verts)
            vert_counts = np.zeros(len(verts))
            for col in range(3):
                np.add.at(vert_normals, faces[:, col], normals)
                np.add.at(vert_counts, faces[:, col], 1.0)
            vert_counts = np.where(vert_counts > 0, vert_counts, 1.0)
            vert_normals /= vert_counts[:, np.newaxis]
            vn_len = np.linalg.norm(vert_normals, axis=1, keepdims=True)
            vn_len = np.where(vn_len > 1e-8, vn_len, 1.0)
            vert_normals /= vn_len

            offset_verts = (verts + vert_normals * OFFSET_MM).astype(np.float32)

            face_colors = self._flux_to_colors(flux, threshold)

            # Ensure face_colors length matches faces
            if len(face_colors) < len(faces):
                pad = np.tile([0.0, 0.2, 0.8, 1.0],
                              (len(faces) - len(face_colors), 1)).astype(np.float32)
                face_colors = np.vstack([face_colors, pad])
            elif len(face_colors) > len(faces):
                face_colors = face_colors[:len(faces)]

            mesh = visuals.Mesh(
                vertices=offset_verts,
                faces=faces,
                face_colors=face_colors,
                shading=None,
                parent=self._view.scene,
            )
            self._radiation_meshes.append(mesh)
            self._radiation_entity_map[entity] = mesh
            self._radiation_orig_colors[entity] = face_colors.copy()

        self._canvas.update()

    def clear_radiation_heatmap(self):
        """Remove all radiation overlay meshes."""
        for m in self._radiation_meshes:
            m.parent = None
        self._radiation_meshes.clear()
        self._radiation_entity_map.clear()
        self._radiation_orig_colors.clear()
        self._canvas.update()

    @staticmethod
    def _flux_to_colors(flux: np.ndarray, threshold: float) -> np.ndarray:
        """Map flux values to RGBA face colours using a 5-band scheme.

        Bands (relative to threshold):
          < 25%  — blue
          25-50% — green
          50-75% — yellow
          75-100% — orange
          >= 100% — red
        """
        if threshold <= 0:
            threshold = 1.0
        ratio = np.asarray(flux, dtype=np.float64) / threshold
        n = len(ratio)
        colors = np.zeros((n, 4), dtype=np.float32)
        colors[:, 3] = 1.0  # fully opaque

        # Blue: < 25%
        m = ratio < 0.25
        colors[m] = [0.0, 0.2, 0.8, 1.0]

        # Green: 25-50%
        m = (ratio >= 0.25) & (ratio < 0.50)
        colors[m] = [0.0, 0.7, 0.2, 1.0]

        # Yellow: 50-75%
        m = (ratio >= 0.50) & (ratio < 0.75)
        colors[m] = [0.9, 0.9, 0.0, 1.0]

        # Orange: 75-100%
        m = (ratio >= 0.75) & (ratio < 1.00)
        colors[m] = [1.0, 0.5, 0.0, 1.0]

        # Red: >= 100%
        m = ratio >= 1.00
        colors[m] = [1.0, 0.0, 0.0, 1.0]

        return colors
