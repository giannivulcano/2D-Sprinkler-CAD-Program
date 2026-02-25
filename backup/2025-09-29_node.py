import math
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF, QLineF
from PyQt6.QtGui import QBrush, QTransform
from PyQt6.QtSvgWidgets import QGraphicsSvgItem

class Node(QGraphicsEllipseItem):
    RADIUS = 5

    # Central place for symbol definitions
    SYMBOLS = {
        "no fitting": {
            "path": "fitting_symbols/no_fitting.svg"
        },
        "cap": {
            "path": "fitting_symbols/cap.svg",
            "through": QPointF(0, 1)  # entry/exit
        },
        "45elbow": {
            "path": "fitting_symbols/45_elbow.svg",
            "through": (QPointF(1,0), QPointF(-(math.sqrt(2) / 2), -(math.sqrt(2) / 2)))
        },
        "90elbow": {
            "path": "fitting_symbols/90_elbow.svg",
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "tee": {
            "path": "fitting_symbols/tee.svg",
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "wye": {
            "path": "fitting_symbols/wye.svg",
            "through": (QPointF(1, 0), QPointF(-(math.sqrt(2) / 2), -(math.sqrt(2) / 2)))
        },
        "cross": {
            "path": "fitting_symbols/double_tee.svg",
            "through": QPointF(0, -1)
        }
    }


    def __init__(self, x, y, svg_path=None):
        super().__init__(-self.RADIUS, -self.RADIUS,
                         self.RADIUS*2, self.RADIUS*2)
        self.setPos(x, y)

        # Base ellipse (can hide later if you only want SVGs)
        #self.setBrush(QBrush(Qt.GlobalColor.blue))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.x_pos = x
        self.y_pos = y
        self.icon_scale = 4
        self.sprinkler = None
        self.fitting = None
        self.pipes = []
        self.graphics = None
        self.symbol = None

        #self.update_fitting()   # <-- auto-update here

    # -------------------------------------------------------------------------
    # Sprinkler helpers
    def add_sprinkler(self, sprinkler):
        if self.sprinkler is None:
            self.sprinkler = sprinkler

    def delete_sprinkler(self):
        self.sprinkler = None

    def has_sprinkler(self):
        return self.sprinkler is not None

    # -------------------------------------------------------------------------
    # Pipe helpers
    def add_pipe(self, pipe):
        
        if pipe not in self.pipes:
            if len(self.pipes) < 4:
                self.pipes.append(pipe)

                self.update_fitting()   # <-- auto-update here
                pipe.update_geometry()
            else:
                print("only 4 connections permitted")
            
            print(self)
            print("i have ", len(self.pipes), " connetions")

    def remove_pipe(self, pipe):
        if pipe in self.pipes:
            self.pipes.remove(pipe)
            self.update_fitting()   # <-- auto-update here

        if pipe.node1 is self:
            pipe.node1 = None
        elif pipe.node2 is self:
            pipe.node2 = None
    # -------------------------------------------------------------------------
    # Graphics handling    
    def determine_fitting(self) -> str:
        print(self, " => determine_fitting")
        
        count = len(self.pipes)
        print("\tnode at ", self.scenePos(), " has ", count, " pipes")

        if count == 0:
            return "no fitting"
        elif count == 1:
            return "cap"
        elif count == 2:
            # Get unit vectors for both pipes
            v1 = self.get_pipe_unit_vector(self.pipes[0])
            v2 = self.get_pipe_unit_vector(self.pipes[1])

            # Angle between vectors in degrees (unsigned)
            angle = abs(self.get_angle_between_vector(v1, v2, signed=False))
            print("\tangle between pipes: ", angle)
            if math.isclose(angle, 180, abs_tol=10):
                return "no fitting"  # straight-through
            elif math.isclose(angle, 90, abs_tol=10):
                return "90elbow"
            elif math.isclose(angle, 45, abs_tol=5) or math.isclose(angle, 135, abs_tol=5):
                return "45elbow"
            else:
                return "no fitting"  # fallback for odd angles

        elif count == 3:
            V1 = self.get_pipe_unit_vector(self.pipes[0])
            V2 = self.get_pipe_unit_vector(self.pipes[1])
            V3 = self.get_pipe_unit_vector(self.pipes[2])
            
            angle1 = round(self.get_angle_between_vector(V1, V2, signed=False))
            angle2 = round(self.get_angle_between_vector(V1, V3, signed=False))
            angle3 = round(self.get_angle_between_vector(V2, V3, signed=False))

            print(angle1, ", ", angle2, ", ", angle3)

            if 90 in (angle1, angle2, angle3):
                return "tee"
            else:
                return "wye"

        elif count == 4:
            return "cross"
        else:
            return "no fitting"

        
    def update_fitting(self):
        print(self, " => update_fitting")
        new_fitting = self.determine_fitting()
        


        self.fitting = new_fitting
        print("\tfitting type: ", self.fitting)
        symbol_def = self.SYMBOLS[self.fitting]

        if self.symbol:
            self.scene().removeItem(self.symbol)

        self.symbol = QGraphicsSvgItem(symbol_def["path"], self)

        # --- compute scale ---
        self.symbol_scale = .5

        self.align_fitting()

            
    # -------------------------------------------------------------------------
    # Geometry helpers
    def distance_to(self, x, y):
        return QLineF(self.scenePos(), QPointF(x, y)).length()

    def snap_point_if_close(self, start: QPointF, end: QPointF, reference_pipe=None, tolerance_deg=7.5) -> QPointF:
        """
        Snaps 'end' to 45° increments relative to a reference pipe if provided,
        otherwise relative to the horizontal axis.
        
        :param start: The start point (node position)
        :param end: The end point (mouse position)
        :param reference_pipe: Optional Pipe object to snap relative to its direction
        :param tolerance_deg: Maximum allowed deviation for snapping
        """
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)

        if length == 0:
            return end

        # Determine base angle
        if reference_pipe:
            base_angle = self.get_pipe_angle(reference_pipe)
        else:
            base_angle = 0  # horizontal axis

        # Angle from start to end
        angle = math.degrees(math.atan2(dy, dx))

        # Relative angle to base
        rel_angle = angle - base_angle

        # Snap relative angle to nearest 45°
        snap_rel = round(rel_angle / 45) * 45

        if abs(rel_angle - snap_rel) <= tolerance_deg:
            rad = math.radians(base_angle + snap_rel)
            return QPointF(start.x() + length * math.cos(rad),
                        start.y() + length * math.sin(rad))
        else:
            return end
        
    def snap_point_45(self, start: QPointF, end: QPointF, reference_pipe=None) -> QPointF:
        """
        Snap 'end' to 45° increments relative to reference_pipe if provided,
        otherwise relative to horizontal axis.
        """
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return end

        # Base angle in degrees
        base_angle = self.get_pipe_angle(reference_pipe) if reference_pipe else 0

        # Angle from start to end
        angle = math.degrees(math.atan2(dy, dx))

        # Relative angle to base
        rel_angle = angle - base_angle

        # Snap to nearest 45° increment
        snap_rel = round(rel_angle / 45) * 45

        # Final snapped position
        rad = math.radians(base_angle + snap_rel)
        return QPointF(start.x() + length * math.cos(rad),
                    start.y() + length * math.sin(rad))

    
    def get_pipe_vector(self, pipe) -> QPointF:
        """
        Returns a vector from this node to the other end of the pipe.
        """
        if pipe.node1 is self:
            other = pipe.node2
        elif pipe.node2 is self:
            other = pipe.node1
        else:
            raise ValueError("This pipe is not connected to this node")

        return other.scenePos() - self.scenePos()


    def get_pipe_unit_vector(self, pipe) -> QPointF:
        # Keep full float precision; do not round here
        vec = self.get_pipe_vector(pipe)
        length = math.hypot(vec.x(), vec.y())
        if length == 0:
            return QPointF(0.0, 0.0)
        return QPointF(vec.x() / length, vec.y() / length)

    def rotate_unit_vector(self, v_from: QPointF, v_to: QPointF) -> QTransform:
        """
        Returns a QTransform that rotates v_from to align with v_to.
        Both inputs must be QPointF.
        """
        if not isinstance(v_from, QPointF) or not isinstance(v_to, QPointF):
            raise TypeError("v_from and v_to must be QPointF")

        # Compute angle in radians
        angle_from = math.atan2(v_from.y(), v_from.x())
        angle_to   = math.atan2(v_to.y(), v_to.x())

        # Convert to degrees
        angle_deg = math.degrees(angle_to - angle_from)

        # Create rotation transform
        transform = QTransform()
        transform.rotate(angle_deg)

        return transform
    
    def get_pipe_angle(self, pipe) -> float:
        u = self.get_pipe_unit_vector(pipe)
        angle = math.degrees(math.atan2(u.y(), u.x()))
        return (angle + 90) % 360   # 0° = up, 90° = right, etc.


    def get_angle_between_vector(self, v1: QPointF, v2: QPointF, signed: bool = True) -> float:
        """
        Returns the angle between v1 and v2 in degrees.
        
        Args:
            v1, v2: QPointF vectors
            signed: If True, returns signed angle (-180, 180],
                    If False, returns smallest positive angle [0, 180].
        """
        mag1 = math.hypot(v1.x(), v1.y())
        mag2 = math.hypot(v2.x(), v2.y())
        if mag1 == 0 or mag2 == 0:
            return 0.0

        # Normalize
        x1, y1 = v1.x() / mag1, v1.y() / mag1
        x2, y2 = v2.x() / mag2, v2.y() / mag2

        # Dot product (clamp for safety)
        dot = max(-1.0, min(1.0, x1 * x2 + y1 * y2))
        angle = math.degrees(math.acos(dot))

        if signed:
            # Cross product (determinant) to get sign
            cross = x1 * y2 - y1 * x2
            if cross < 0:
                angle = -angle

        return angle
    


    def make_qtransform_from_qpoints(self, M1, M2):
        """
        M1 and M2: lists of two QPointF columns each
        Returns: QTransform that maps M2 -> M1
        """
        a1, a2 = M2
        b1, b2 = M1

        ax1, ay1 = a1.x(), a1.y()
        ax2, ay2 = a2.x(), a2.y()
        bx1, by1 = b1.x(), b1.y()
        bx2, by2 = b2.x(), b2.y()

        det = ax1*ay2 - ay1*ax2
        if abs(det) < 1e-12:
            raise ValueError("M2 columns are collinear; cannot invert")

        # inverse of M2
        inv00 = ay2 / det
        inv01 = -ax2 / det
        inv10 = -ay1 / det
        inv11 = ax1 / det

        # linear map Q = M1 @ inv(M2)
        m11 = bx1*inv00 + bx2*inv10
        m12 = bx1*inv01 + bx2*inv11
        m21 = by1*inv00 + by2*inv10
        m22 = by1*inv01 + by2*inv11

        transform = QTransform(m11, m12, 0.0,
                            m21, m22, 0.0,
                            0.0, 0.0, 1.0)

        return transform

    def align_fitting(self):

        print("\n\tnode => align_fitting")
        
        pipe_vectors = []
        for pipe in self.pipes:
            pipe_vectors.append(self.get_pipe_unit_vector(pipe))
            transform = None

        if self.fitting in ("no fitting"):
            transform = self.rotate_unit_vector(QPointF(1,0), QPointF(1,0))

        if self.fitting in ("cap", "cross"):
            V1 = pipe_vectors[0]
            V2 = self.SYMBOLS[self.fitting].get("through")
            transform = self.rotate_unit_vector(V2, V1) #aligns V2 with V1

        elif self.fitting in ("90elbow", "45elbow"):
            M1 = pipe_vectors
            M2 = self.SYMBOLS[self.fitting].get("through")
            transform = self.make_qtransform_from_qpoints(M2, M1)

        elif self.fitting in ("tee", "wye"):
            
            M1 = pipe_vectors
            #find the pipe vectors angle that is 135 or 90 and assign these to M1
            if self.get_angle_between_vector(M1[0],M1[1],signed=False) == 180:
                M2 = [M1[0],M1[2]]
            elif self.get_angle_between_vector(M1[0],M1[2],signed=False) == 180:
                M2 = [M1[0],M1[1]]
            elif self.get_angle_between_vector(M1[1],M1[2],signed=False) == 180:
                M2 = [M1[1],M1[0]]
            else:
                M2 = self.SYMBOLS[self.fitting].get("through")
                print("error")

            M3 = self.SYMBOLS[self.fitting].get("through")

            print(M3)
            print(M2)
            transform = self.make_qtransform_from_qpoints(M3, M2)
            


        bounds = self.symbol.boundingRect()
        center = bounds.center()
        # Set transform origin to center
        self.symbol.setTransformOriginPoint(center)

        transform.scale(self.symbol_scale, self.symbol_scale)
        self.symbol.setTransform(transform)


        # After transform, move the item so its **center aligns with node position**
        # Use the transformed bounding rect
        transformed_bounds = self.symbol.mapRectToParent(bounds)
        self.symbol.setPos(-transformed_bounds.center())


            
    # -------------------------------------------------------------------------
    #item change handling

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # when the node is being dragged, snap to allowed directions if near
            for pipe in self.pipes:
                other = pipe.node1 if pipe.node2 is self else pipe.node2
                # call instance method, not the class — keeps 'self' semantics right
                snapped = self.snap_point_if_close(other.scenePos(), value)
                value = snapped
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for pipe in self.pipes:
                pipe.update_geometry()
            # After moving, update fitting so SVGs rotate live
            self.update_fitting()
        return super().itemChange(change, value)
