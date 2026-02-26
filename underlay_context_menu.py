"""
Underlay Context Menu
=====================
Right-click context menu for underlay items (PDF / DXF) in the scene.
Provides: Scale, Rotate, Opacity, Lock/Unlock, Refresh from disk, Remove.
"""

from PyQt6.QtWidgets import (
    QMenu, QInputDialog, QGraphicsItem, QGraphicsItemGroup
)
from PyQt6.QtGui import QAction
from underlay import Underlay


class UnderlayContextMenu:
    """
    Creates and shows a context menu for a given underlay (data, item) pair.
    `scene` must be the Model_Space that owns the underlay list.
    """

    @staticmethod
    def show(scene, underlay_data: Underlay, underlay_item: QGraphicsItem, screen_pos):
        """Build and exec the context menu at *screen_pos* (global coords)."""
        menu = QMenu()

        # ── Scale ────────────────────────────────────────────────────
        scale_action = QAction(f"Scale… (current: {underlay_data.scale:.3f})", menu)
        scale_action.triggered.connect(
            lambda: UnderlayContextMenu._set_scale(scene, underlay_data, underlay_item)
        )
        menu.addAction(scale_action)

        # ── Rotate ───────────────────────────────────────────────────
        rotate_action = QAction(f"Rotate… (current: {underlay_data.rotation:.1f}°)", menu)
        rotate_action.triggered.connect(
            lambda: UnderlayContextMenu._set_rotation(scene, underlay_data, underlay_item)
        )
        menu.addAction(rotate_action)

        # ── Opacity ──────────────────────────────────────────────────
        opacity_pct = int(underlay_data.opacity * 100)
        opacity_action = QAction(f"Opacity… (current: {opacity_pct}%)", menu)
        opacity_action.triggered.connect(
            lambda: UnderlayContextMenu._set_opacity(scene, underlay_data, underlay_item)
        )
        menu.addAction(opacity_action)

        menu.addSeparator()

        # ── Lock / Unlock ────────────────────────────────────────────
        if underlay_data.locked:
            lock_action = QAction("🔓 Unlock", menu)
        else:
            lock_action = QAction("🔒 Lock", menu)
        lock_action.triggered.connect(
            lambda: UnderlayContextMenu._toggle_lock(scene, underlay_data, underlay_item)
        )
        menu.addAction(lock_action)

        # ── Refresh from disk ────────────────────────────────────────
        refresh_action = QAction("🔄 Refresh from Disk", menu)
        refresh_action.triggered.connect(
            lambda: scene.refresh_underlay(underlay_data, underlay_item)
        )
        menu.addAction(refresh_action)

        menu.addSeparator()

        # ── Remove ───────────────────────────────────────────────────
        remove_action = QAction("❌ Remove Underlay", menu)
        remove_action.triggered.connect(
            lambda: scene.remove_underlay(underlay_data, underlay_item)
        )
        menu.addAction(remove_action)

        menu.exec(screen_pos)

    # ─── action handlers ─────────────────────────────────────────────

    @staticmethod
    def _set_scale(scene, data: Underlay, item: QGraphicsItem):
        val, ok = QInputDialog.getDouble(
            scene.views()[0] if scene.views() else None,
            "Set Underlay Scale",
            "Scale factor:",
            data.scale, 0.001, 1000.0, 4
        )
        if ok:
            data.scale = val
            item.setScale(val)

    @staticmethod
    def _set_rotation(scene, data: Underlay, item: QGraphicsItem):
        val, ok = QInputDialog.getDouble(
            scene.views()[0] if scene.views() else None,
            "Set Underlay Rotation",
            "Rotation (degrees):",
            data.rotation, -360.0, 360.0, 1
        )
        if ok:
            data.rotation = val
            item.setRotation(val)

    @staticmethod
    def _set_opacity(scene, data: Underlay, item: QGraphicsItem):
        val, ok = QInputDialog.getInt(
            scene.views()[0] if scene.views() else None,
            "Set Underlay Opacity",
            "Opacity (0–100%):",
            int(data.opacity * 100), 0, 100
        )
        if ok:
            data.opacity = val / 100.0
            item.setOpacity(data.opacity)

    @staticmethod
    def _toggle_lock(scene, data: Underlay, item: QGraphicsItem):
        data.locked = not data.locked
        if data.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        else:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)