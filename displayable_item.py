"""
displayable_item.py
===================
Mixin class providing shared display-manager attributes for all scene items
that participate in the Display Manager's category/instance system.

Usage — add to the MRO alongside the Qt graphics item base class::

    class WallSegment(DisplayableItemMixin, QGraphicsPathItem):
        def __init__(self, ...):
            QGraphicsPathItem.__init__(self)
            self.init_displayable()   # sets level, user_layer, display overrides
            ...

The mixin deliberately does **not** call ``super().__init__()`` to avoid
interfering with the Qt graphics item constructor chain.  Call
``init_displayable()`` explicitly in your ``__init__``.
"""

from __future__ import annotations

from PyQt6.QtGui import QTransform
from constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER


def centre_svg_on_origin(item, target_mm: float, fallback_scale: float = 1.0,
                          display_scale: float = 1.0, *, reset_pos: bool = False):
    """Scale and centre an SVG item so its visual centre maps to local (0, 0).

    Parameters
    ----------
    item :          QGraphicsSvgItem (or any item with boundingRect)
    target_mm :     Desired size in scene units (mm).
    fallback_scale: Scale to use if the SVG has zero natural size.
    display_scale:  Extra multiplier from Display Manager.
    reset_pos :     If True, also call ``item.setPos(0, 0)`` (for child items).
    """
    bounds = item.boundingRect()
    center = bounds.center()
    svg_natural = max(bounds.width(), bounds.height())
    s = target_mm / svg_natural if svg_natural > 0 else fallback_scale
    s *= display_scale
    t = QTransform(s, 0, 0, s, -s * center.x(), -s * center.y())
    item.setTransform(t)
    if reset_pos:
        item.setPos(0, 0)


class DisplayableItemMixin:
    """Mixin providing standard display-manager attributes.

    Attributes set by ``init_displayable()``:

    * ``level``              — floor level name (str)
    * ``user_layer``         — user-defined layer name (str)
    * ``_display_color``     — pen/stroke colour override (str | None)
    * ``_display_fill_color``— fill/brush colour override (str | None)
    * ``_display_overrides`` — per-instance overrides from Display Manager (dict)
    * ``_scale_manager_ref`` — fallback ScaleManager for items not in a scene
    """

    def init_displayable(self, level: str = DEFAULT_LEVEL,
                         user_layer: str = DEFAULT_USER_LAYER):
        """Initialise the shared display attributes.

        Call this early in ``__init__`` after the Qt base class constructor.
        """
        self.level: str = level
        self.user_layer: str = user_layer
        self._display_color: str | None = None
        self._display_fill_color: str | None = None
        self._display_overrides: dict = {}
        self._scale_manager_ref = None

    def _fmt(self, mm: float) -> str:
        """Format *mm* as a display string using the scene's ScaleManager."""
        from format_utils import fmt_length
        return fmt_length(self, mm)

    def _get_scale_manager(self):
        """Return the ScaleManager from the scene, or a stored fallback."""
        from format_utils import get_scale_manager
        return get_scale_manager(self)
