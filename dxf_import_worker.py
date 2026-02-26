"""
DXF Import Worker
=================
Runs the heavy DXF parsing + QGraphicsItem creation on a background thread
so the UI stays responsive.  Emits progress signals for a progress dialog.
"""

import math
from PyQt6.QtCore import QThread, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QPainterPath
from PyQt6.QtWidgets import (
    QGraphicsLineItem, QGraphicsEllipseItem,
    QGraphicsPathItem, QGraphicsTextItem
)

try:
    import ezdxf
except ImportError:
    ezdxf = None

from dxf_import_dialog import _sanitize_dxf
import os


class DxfImportWorker(QThread):
    """
    Parses a DXF file and builds QGraphicsItems off the main thread.

    Signals
    -------
    progress(int, int)   — (current, total) entity counts
    status(str)          — status message for the dialog
    finished_items(list) — list of QGraphicsItems ready to add to scene
    error(str)           — error message if import fails
    """
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished_items = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path: str, color: QColor, line_weight: int,
                 layers: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.color = color
        self.line_weight = line_weight
        self.layers = layers
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if ezdxf is None:
            self.error.emit("ezdxf is not installed")
            return

        # ── Sanitize and open ────────────────────────────────────────
        self.status.emit("Cleaning DXF file…")
        clean_path = _sanitize_dxf(self.file_path)

        try:
            self.status.emit("Reading DXF…")
            doc = ezdxf.readfile(clean_path)
            msp = doc.modelspace()
        except Exception as e:
            self.error.emit(f"Failed to load DXF: {e}")
            return
        finally:
            if clean_path != self.file_path and os.path.exists(clean_path):
                os.remove(clean_path)

        # ── Collect entities to process ──────────────────────────────
        self.status.emit("Counting entities…")
        all_entities = list(msp)
        total = len(all_entities)
        self.status.emit(f"Processing {total} entities…")

        pen = QPen(self.color, self.line_weight)
        items = []
        skipped = 0

        for i, entity in enumerate(all_entities):
            if self._cancelled:
                self.status.emit("Cancelled")
                return

            # Layer filter
            if self.layers is not None:
                entity_layer = entity.dxf.get("layer", "0") if hasattr(entity.dxf, "get") else "0"
                if entity_layer not in self.layers:
                    continue

            try:
                new_items = self._convert_entity(entity, pen, self.color)
                items.extend(new_items)
            except Exception as e:
                skipped += 1

            # Emit progress every 500 entities (avoids signal spam)
            if i % 500 == 0 or i == total - 1:
                self.progress.emit(i + 1, total)

        if skipped > 0:
            self.status.emit(f"Done — {len(items)} items created, {skipped} skipped")
        else:
            self.status.emit(f"Done — {len(items)} items created")

        self.finished_items.emit(items)

    # ─────────────────────────────────────────────────────────────────
    # Entity conversion (same logic as before, but optimized)
    # ─────────────────────────────────────────────────────────────────

    def _convert_entity(self, entity, pen: QPen, color: QColor) -> list:
        etype = entity.dxftype()
        items = []

        if etype == "LINE":
            start = QPointF(entity.dxf.start[0], -entity.dxf.start[1])
            end = QPointF(entity.dxf.end[0], -entity.dxf.end[1])
            line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
            line.setPen(pen)
            line.setZValue(-100)
            items.append(line)

        elif etype == "CIRCLE":
            r = entity.dxf.radius
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            circle = QGraphicsEllipseItem(cx - r, -cy - r, 2 * r, 2 * r)
            circle.setPen(pen)
            circle.setZValue(-100)
            items.append(circle)

        elif etype == "ARC":
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            start_angle = entity.dxf.start_angle
            end_angle = entity.dxf.end_angle

            rect = QRectF(cx - r, -cy - r, 2 * r, 2 * r)
            qt_start = -start_angle
            qt_end = -end_angle
            span = qt_end - qt_start
            if span > 0:
                span -= 360

            path = QPainterPath()
            path.arcMoveTo(rect, qt_start)
            path.arcTo(rect, qt_start, span)
            path_item = QGraphicsPathItem(path)
            path_item.setPen(pen)
            path_item.setZValue(-100)
            items.append(path_item)

        elif etype == "ELLIPSE":
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            mx, my = entity.dxf.major_axis.x, entity.dxf.major_axis.y
            ratio = entity.dxf.ratio
            major_len = math.hypot(mx, my)
            minor_len = major_len * ratio
            rotation = math.degrees(math.atan2(my, mx))

            start_param = entity.dxf.get("start_param", 0.0)
            end_param = entity.dxf.get("end_param", math.tau)
            is_full = math.isclose(abs(end_param - start_param), math.tau, rel_tol=1e-3)

            if is_full:
                ellipse = QGraphicsEllipseItem(
                    -major_len, -minor_len, 2 * major_len, 2 * minor_len
                )
                ellipse.setPen(pen)
                ellipse.setZValue(-100)
                ellipse.setPos(cx, -cy)
                ellipse.setRotation(-rotation)
                items.append(ellipse)
            else:
                path = QPainterPath()
                steps = 64
                param_range = end_param - start_param
                if param_range < 0:
                    param_range += math.tau
                rad = math.radians(rotation)
                cos_r, sin_r = math.cos(rad), math.sin(rad)
                for i in range(steps + 1):
                    t = start_param + param_range * (i / steps)
                    px = major_len * math.cos(t)
                    py = minor_len * math.sin(t)
                    rx = px * cos_r - py * sin_r + cx
                    ry = -(px * sin_r + py * cos_r + cy)
                    if i == 0:
                        path.moveTo(rx, ry)
                    else:
                        path.lineTo(rx, ry)
                path_item = QGraphicsPathItem(path)
                path_item.setPen(pen)
                path_item.setZValue(-100)
                items.append(path_item)

        elif etype in ("LWPOLYLINE", "POLYLINE"):
            # Use a single QPainterPath instead of N separate line items
            points = list(entity.get_points())
            if len(points) >= 2:
                path = QPainterPath()
                path.moveTo(points[0][0], -points[0][1])
                for pt in points[1:]:
                    path.lineTo(pt[0], -pt[1])
                # Close if flagged
                if hasattr(entity.dxf, "flags") and entity.dxf.flags & 1:
                    path.closeSubpath()
                path_item = QGraphicsPathItem(path)
                path_item.setPen(pen)
                path_item.setZValue(-100)
                items.append(path_item)

        elif etype == "SPLINE":
            try:
                points = list(entity.flattening(0.5))
                if points:
                    path = QPainterPath()
                    path.moveTo(points[0].x, -points[0].y)
                    for pt in points[1:]:
                        path.lineTo(pt.x, -pt.y)
                    path_item = QGraphicsPathItem(path)
                    path_item.setPen(pen)
                    path_item.setZValue(-100)
                    items.append(path_item)
            except Exception:
                pass

        elif etype == "TEXT":
            pos = entity.dxf.insert
            text_item = QGraphicsTextItem(entity.dxf.text)
            text_item.setPos(pos[0], -pos[1])
            text_item.setDefaultTextColor(color)
            text_item.setZValue(-100)
            items.append(text_item)

        elif etype == "MTEXT":
            plain = entity.plain_text() if hasattr(entity, "plain_text") else entity.text
            insert = entity.dxf.insert
            text_item = QGraphicsTextItem(plain)
            text_item.setPos(insert.x, -insert.y)
            text_item.setDefaultTextColor(color)
            text_item.setZValue(-100)
            items.append(text_item)

        return items