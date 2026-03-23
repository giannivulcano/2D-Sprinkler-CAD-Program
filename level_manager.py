"""
level_manager.py
================
Floor-level system for multi-story building support.

Each drawing item carries a ``level`` string attribute naming the floor
level it belongs to.  Switching the active level hides entities on other
levels, with optional faded display for context.

Classes
-------
Level           — dataclass for one level's properties
LevelManager    — ordered list of levels + visibility application

The UI widget (LevelWidget) is in level_widget.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import Qt


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

FADE_OPACITY = 0.25  # opacity for faded levels

from constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM
# Display mode options (stored in Level.display_mode)
DISPLAY_MODES = ["Auto", "Hidden", "Faded", "Visible"]


@dataclass
class Level:
    name:         str
    elevation:    float = 0.0       # mm, relative to project datum
    view_top:     float = 2000.0    # mm above elevation (future use)
    view_bottom:  float = -1000.0   # mm below elevation (future use)
    display_mode: str   = "Auto"    # Auto | Hidden | Faded | Visible

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "elevation_mm": self.elevation,
            "view_top":     self.view_top,
            "view_bottom":  self.view_bottom,
            "display_mode": self.display_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Level":
        # Prefer new mm key; fall back to legacy ft key converted to mm
        if "elevation_mm" in d:
            elev = d["elevation_mm"]
        else:
            elev = d.get("elevation", 0.0) * 304.8
        return cls(
            name         = d["name"],
            elevation    = elev,
            view_top     = d.get("view_top",     2000.0),
            view_bottom  = d.get("view_bottom",  -1000.0),
            display_mode = d.get("display_mode", "Auto"),
        )


# Defaults shipped with every new document
DEFAULT_LEVELS: list[Level] = [
    Level(DEFAULT_LEVEL, elevation=0.0),
    Level("Level 2", elevation=3048.0),
    Level("Level 3", elevation=6096.0),
]


# ─────────────────────────────────────────────────────────────────────────────
# Manager (pure data, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class LevelManager:
    """Manages the ordered list of floor levels.

    The "active level" concept is now purely view-driven: whichever
    Plan tab is currently displayed defines the active level.  The
    manager no longer stores active-level state; callers pass the
    level name explicitly to ``apply_for_level()``.
    """

    def __init__(self):
        self._levels: list[Level] = [
            Level(**vars(l)) for l in DEFAULT_LEVELS
        ]

    # ── Level list API ────────────────────────────────────────────────────────

    @property
    def levels(self) -> list[Level]:
        return list(self._levels)

    def get(self, name: str) -> Level | None:
        for lvl in self._levels:
            if lvl.name == name:
                return lvl
        return None

    def add_level(self, name: str | None = None,
                  elevation: float = 0.0) -> Level:
        if name is None or self.get(name) is not None:
            i = 1
            while self.get(f"Level {i}") is not None:
                i += 1
            name = f"Level {i}"
        lvl = Level(name, elevation=elevation)
        self._levels.append(lvl)
        return lvl

    def remove_level(self, name: str):
        """Delete a level.  The last remaining level cannot be deleted."""
        if len(self._levels) <= 1:
            return
        self._levels = [l for l in self._levels if l.name != name]

    def rename_level(self, old_name: str, new_name: str, items) -> bool:
        """Rename a level and update all items that referenced the old name."""
        if not new_name or (self.get(new_name) is not None
                           and new_name != old_name):
            return False
        lvl = self.get(old_name)
        if lvl is None:
            return False
        lvl.name = new_name
        for item in items:
            if getattr(item, "level", None) == old_name:
                item.level = new_name
        return True

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [l.to_dict() for l in self._levels]

    def from_list(self, data: list[dict]):
        self._levels = [Level.from_dict(d) for d in data]
        # Ensure at least one level exists
        if not self._levels:
            self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]

    def reset(self):
        """Reset to default levels (used on new file)."""
        self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]

    # ── Elevation helpers ───────────────────────────────────────────────────

    def update_elevations(self, scene):
        """Recompute z_pos for all nodes using ceiling_level + ceiling_offset."""
        from node import Node
        lvl_map = {l.name: l for l in self._levels}
        for node in scene.sprinkler_system.nodes:
            # 3D elevation = ceiling level elevation (mm) + ceiling offset (mm)
            ceil_lvl = lvl_map.get(getattr(node, "ceiling_level", DEFAULT_LEVEL))
            ceil_elev = ceil_lvl.elevation if ceil_lvl else 0.0
            node.z_pos = ceil_elev + getattr(node, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM)

    # ── Apply to scene ────────────────────────────────────────────────────────

    def apply_to_scene(self, scene, active_level: str | None = None):
        """Show/hide/fade entities based on *active_level* and display_mode,
        then re-apply layer visibility so both level AND layer filtering
        are respected.

        *active_level* is the level of the current plan view.  If ``None``,
        falls back to ``scene.active_level``.
        """
        active = active_level or getattr(scene, "active_level", DEFAULT_LEVEL)
        lvl_map = {l.name: l for l in self._levels}

        def _set_level_vis(item):
            lvl_name = getattr(item, "level", DEFAULT_LEVEL)
            lvl_def = lvl_map.get(lvl_name)
            mode = lvl_def.display_mode if lvl_def else "Auto"

            # "Hidden" always hides, even if active
            if mode == "Hidden":
                item.setVisible(False)
                item.setOpacity(1.0)
                return

            if lvl_name == active:
                # Active level — fully visible and selectable
                item.setVisible(True)
                item.setOpacity(1.0)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True,
                )
                return

            # Non-active level — check display_mode
            if mode == "Faded":
                item.setVisible(True)
                item.setOpacity(FADE_OPACITY)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
            elif mode == "Visible":
                item.setVisible(True)
                item.setOpacity(1.0)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
            else:
                # "Auto" when not active — hidden
                item.setVisible(False)
                item.setOpacity(1.0)

        # ── Sprinkler system ──────────────────────────────────────────────
        for node in scene.sprinkler_system.nodes:
            _set_level_vis(node)

        for pipe in scene.sprinkler_system.pipes:
            _set_level_vis(pipe)

        # ── Construction / draw geometry ──────────────────────────────────
        for item in getattr(scene, "_construction_lines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_polylines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_lines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_rects", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_circles", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_arcs", []):
            _set_level_vis(item)

        # ── Gridlines (always visible on all levels) ─────────────────────
        for item in getattr(scene, "_gridlines", []):
            item.setVisible(True)
            item.setOpacity(1.0)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # ── Annotations ───────────────────────────────────────────────────
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                _set_level_vis(dim)
            for note in getattr(annotations, "notes", []):
                _set_level_vis(note)

        # ── Walls ─────────────────────────────────────────────────────────
        for item in getattr(scene, "_walls", []):
            _set_level_vis(item)
            # Also handle openings belonging to this wall
            for op in getattr(item, "openings", []):
                _set_level_vis(op)

        # ── Floor slabs ──────────────────────────────────────────────────
        for item in getattr(scene, "_floor_slabs", []):
            _set_level_vis(item)

        # ── Roofs ────────────────────────────────────────────────────────
        for item in getattr(scene, "_roofs", []):
            _set_level_vis(item)

        # ── Hatches ───────────────────────────────────────────────────────
        for item in getattr(scene, "_hatch_items", []):
            _set_level_vis(item)

        # ── Water supply ──────────────────────────────────────────────────
        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            _set_level_vis(ws)

        # ── Re-apply user-layer visibility on top ─────────────────────────
        ulm = getattr(scene, "_user_layer_manager", None)
        if ulm is not None:
            ulm.apply_to_scene(scene)

        # ── Fixup: restore faded opacity for items that survived layer
        #    filtering (ulm.apply_to_scene may have reset opacity) ─────────
        faded_levels = {l.name for l in self._levels
                        if l.display_mode == "Faded" and l.name != active}
        if faded_levels:
            self._reapply_fade(scene, faded_levels)

    def _reapply_fade(self, scene, faded_levels: set[str]):
        """Re-apply FADE_OPACITY to items on faded levels that are still
        visible after user-layer filtering."""
        def _fix(item):
            if not item.isVisible():
                return
            if getattr(item, "level", DEFAULT_LEVEL) in faded_levels:
                item.setOpacity(FADE_OPACITY)

        for node in scene.sprinkler_system.nodes:
            _fix(node)
        for pipe in scene.sprinkler_system.pipes:
            _fix(pipe)
        for item in getattr(scene, "_construction_lines", []):
            _fix(item)
        for item in getattr(scene, "_polylines", []):
            _fix(item)
        for item in getattr(scene, "_draw_lines", []):
            _fix(item)
        for item in getattr(scene, "_draw_rects", []):
            _fix(item)
        for item in getattr(scene, "_draw_circles", []):
            _fix(item)
        for item in getattr(scene, "_draw_arcs", []):
            _fix(item)
        for item in getattr(scene, "_gridlines", []):
            _fix(item)
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                _fix(dim)
            for note in getattr(annotations, "notes", []):
                _fix(note)
        for item in getattr(scene, "_hatch_items", []):
            _fix(item)
        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            _fix(ws)

