from math import floor
import math
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsItem, QGraphicsTextItem, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPointF
from CAD_Math import CAD_Math


class Pipe(QGraphicsLineItem):
    SNAP_TOLERANCE_DEG = 7.5  # snap if within this angle

    def __init__(self, node1, node2):

        super().__init__()
        # Properties
        self._properties = {
            "Diameter": {"type": "enum", "value": "Ø 2\"", "options": ["1\"Ø", "1-½\"Ø", "2\"Ø","3\"Ø","4\"Ø","5\"Ø","6\"Ø","8\"Ø"]},
            "Material" : {"type": "enum", "value": "Galvanized Steel", "options": ["Galvanized Steel", "Stainless Steel", "Black Steel","PVC"]},
            "Colour" : {"type": "enum", "value": "Red", "options": ["Black", "White", "Red", "Blue","Grey"]},
            "Line Weight" : {"type": "enum", "value": "1", "options": ["1", "2","3","4"]},
            "Phase" : {"type": "enum", "value": "New", "options": ["New", "Existing","Demo"]},
            "Show Label" : {"type": "enum", "value": "True", "options": ["True", "False"]},

        }

        self.node1 = node1
        self.node2 = node2
        self.colour = None
        self.length = 0.0


        self.label = QGraphicsTextItem("", self)  # Child of pipe

        #self.set_pipe_display()
        
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-100)
        
        # track node movement
        if node1 and node2:
            self.node1.pipes.append(self)
            self.node2.pipes.append(self)
            self.update_geometry()

    def set_pipe_display(self):
        colour = QColor(self._properties["Colour"]["value"]) #If you're storing names ("red") or hex codes, QColor handles both.
        line_weight = float(self._properties["Line Weight"]["value"])+4
        pen = QPen(colour, line_weight)
        self.setPen(pen)

    # --------------------------------------------
    # PIPE LABEL HELPERS
    def update_label(self, visible=None):
        if not self.node1 or not self.node2:
            return  # cannot position label yet
        
        if not hasattr(self, "label") or self.label is None:
            self.label = QGraphicsTextItem(parent=self)
            self.label.setDefaultTextColor(Qt.GlobalColor.black)
            self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        
        visible = True if self._properties["Show Label"]["value"] == "True" else False
        self.label.setVisible(visible)
        if not visible:
            return  # skip extra work if hidden

        # Format text
        diameter = self._properties.get('Diameter', {}).get('value', 'N/A')
        length = self.set_units(getattr(self, "length", 0.0), "Imperial")

        html = f"<div style='text-align:center'>{diameter}<br>{length}</div>"
        self.label.setHtml(html)

        # Adjust width to match content for proper centering
        self.label.setTextWidth(self.label.boundingRect().width())

        self.set_label_position()


    def set_label_position(self):
        line = self.line()  # QLineF
    
        v1 = CAD_Math.get_unit_vector(line.p1(),line.p2())
        # If pointing left, flip direction
        if v1.x() < 0:
            v1 = QPointF(-v1.x(), -v1.y())
        v2 = QPointF(1, 0)
        angle = -CAD_Math.get_angle_between_vectors(v1, v2, signed=True)
        if angle == 90:
            angle = -90
        
        mid_point = QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
        bounds = self.label.boundingRect()
        center = bounds.center()

        # set transform origin so future rotations work around the center
        self.label.setTransformOriginPoint(center)

        # move label so its center sits on line midpoint
        self.label.setPos(mid_point - center)
        self.label.setRotation(angle)

    # --------------------------------------------------------------
    # PIPE HELPERS

    def update_geometry(self):
        start = self.node1.scenePos()
        end = self.node2.scenePos()

        # Snap visually for the pipe line
        snapped_end = self.snap_point_45_if_close(start, end)
        self.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())

        # Store the length
        self.length = CAD_Math.get_vector_length(self.node1.scenePos(),self.node2.scenePos())

        self.update_label()  # <- move here

    def set_units(self, length, units):
        if units == "Imperial":
            return self.format_feet_inches(float(length))
    
    def format_feet_inches(self, total_inches):
        """
        Format total inches into feet-inches-fractions with denominators 2, 4, 8, 16 only.
        Example: 1' 3 1/2", 7/8", 2' 0"
        """
        # break into feet and inches
        feet = int(total_inches // 12)
        inches_decimal = total_inches % 12
        inches_whole = int(floor(inches_decimal))
        frac_decimal = inches_decimal - inches_whole
        
        # possible denominators: 2, 4, 8, 16
        denominators = [2, 4, 8, 16]
        best_num, best_den = 0, 1
        min_error = 1.0
        
        for d in denominators:
            n = round(frac_decimal * d)
            error = abs(frac_decimal - n / d)
            if error < min_error:
                min_error = error
                best_num, best_den = n, d
        
        # normalize (if fraction rounds to whole inch)
        if best_num == best_den:
            inches_whole += 1
            best_num, best_den = 0, 1
        
        # carry over 12 inches → 1 foot
        if inches_whole == 12:
            feet += 1
            inches_whole = 0
        
        # build string
        parts = []
        if feet > 0:
            parts.append(f"{feet}'")
        
        inch_part = ""
        if inches_whole > 0:
            inch_part += str(inches_whole)
        if best_num > 0:
            if inch_part:
                inch_part += f" {best_num}/{best_den}"
            else:
                inch_part = f"{best_num}/{best_den}"
        if inch_part:
            parts.append(f'{inch_part}"')
        
        if not parts:  # handle case 0"
            parts.append('0"')
        
        return " ".join(parts)

    @classmethod
    def snap_point_45_if_close(cls, start: QPointF, end: QPointF) -> QPointF:
        dx = end.x() - start.x()
        dy = end.y() - start.y()

        angle = math.degrees(math.atan2(dy, dx))
        snap_angle = round(angle / 45) * 45

        # only snap if within tolerance
        if abs(angle - snap_angle) <= cls.SNAP_TOLERANCE_DEG:
            length = math.hypot(dx, dy)
            rad = math.radians(snap_angle)
            return QPointF(start.x() + length * math.cos(rad),
                           start.y() + length * math.sin(rad))
        else:
            return end
        
    def get_properties(self):
        return self._properties.copy()

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value

            if key in ("Diameter","Show Label"):
                self.update_label()
            if key in ("Colour", "Line Weight"):
                self.set_pipe_display()
    
    def set_properties(self, template: "Pipe"):
        """Copy property values from a template sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])

    def paint(self, painter, option, widget=None):
        # get base style from your properties
        colour = QColor(self._properties["Colour"]["value"])
        line_weight = 4 + float(self._properties["Line Weight"]["value"])
        base_pen = QPen(colour, line_weight)

        # normal draw
        painter.setPen(base_pen)
        painter.drawLine(self.line())

        # highlight if selected
        if self.isSelected():
            highlight_pen = QPen(colour, line_weight + 4)
            painter.setPen(highlight_pen)
            painter.drawLine(self.line())
            
            # also show node endpoints
            radius = 6  # adjust radius as you like
            brush = QBrush(QColor("white"))
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)

            for node in (self.node1, self.node2):
                if node is not None:
                    pos = node.scenePos()
                    painter.drawEllipse(QPointF(pos.x(), pos.y()), radius, radius)


        # prevent the default dotted selection rect
        option.state &= ~QStyle.StateFlag.State_Selected