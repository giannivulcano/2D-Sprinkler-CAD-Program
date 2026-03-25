"""
view_range_dialog.py
====================
Dialog for editing the view-range (cut plane) settings of a plan view.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox, QPushButton,
    QLabel, QGroupBox,
)
from PyQt6.QtCore import Qt

from dimension_edit import DimensionEdit
from level_manager import PlanView, PlanViewManager, LevelManager


class ViewRangeDialog(QDialog):
    """Edit *view_height* (cut plane) and *view_depth* for a PlanView."""

    def __init__(self, plan_view: PlanView, level_manager: LevelManager,
                 plan_view_manager: PlanViewManager, scale_manager,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"View Range \u2014 {plan_view.name}")
        self.setMinimumWidth(340)
        self._pv = plan_view
        self._lm = level_manager
        self._pvm = plan_view_manager

        layout = QVBoxLayout(self)

        # Info label
        lvl = self._lm.get(plan_view.level_name)
        elev_str = f"{lvl.elevation:.1f} mm" if lvl else "?"
        info = QLabel(f"Level: <b>{plan_view.level_name}</b>  "
                      f"(elevation {elev_str})")
        layout.addWidget(info)

        # View range fields
        group = QGroupBox("View Range")
        form = QFormLayout(group)

        self._height_edit = DimensionEdit(scale_manager,
                                          initial_mm=plan_view.view_height)
        form.addRow("Cut Plane Height:", self._height_edit)

        self._depth_edit = DimensionEdit(scale_manager,
                                         initial_mm=plan_view.view_depth)
        form.addRow("View Depth:", self._depth_edit)

        layout.addWidget(group)

        # Reset button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(reset_btn)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_defaults(self):
        """Recompute smart defaults from level spacing."""
        lvl = self._lm.get(self._pv.level_name)
        if lvl is None:
            return
        elev = lvl.elevation

        levels_sorted = sorted(self._lm.levels, key=lambda l: l.elevation)
        next_lvl = None
        for l in levels_sorted:
            if l.elevation > elev:
                next_lvl = l
                break

        from level_manager import _DEFAULT_SLAB_THICKNESS_MM
        if next_lvl is not None:
            view_height = next_lvl.elevation - _DEFAULT_SLAB_THICKNESS_MM
        else:
            view_height = elev + lvl.view_top

        view_depth = elev + lvl.view_bottom

        self._height_edit.set_value_mm(view_height)
        self._depth_edit.set_value_mm(view_depth)

    def get_values(self) -> tuple[float, float]:
        """Return (view_height, view_depth) in mm."""
        return (self._height_edit.value_mm(), self._depth_edit.value_mm())
