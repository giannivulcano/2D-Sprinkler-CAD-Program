import sys, json
import ezdxf
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsItem, QGraphicsPixmapItem, QGraphicsTextItem, QApplication
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSize
from PyQt6.QtGui import QPen, QBrush, QColor, QPixmap
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from node import Node
from pipe import Pipe
from sprinkler import Sprinkler
from sprinkler_system import SprinklerSystem
from CAD_Math import CAD_Math
from Annotations import Annotation, DimensionAnnotation

class Model_Space(QGraphicsScene):
    SNAP_RADIUS = 10
    requestPropertyUpdate = pyqtSignal(object)  # emits any object to show in PropertyManager

    def __init__(self):
        super().__init__()
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self.mode = None
        self.units_per_meter = 10000  # 1000 scene units = 1 m
        # placement variables
        self.dimension_start = None
        self.node_start_pos = None
        self.node_end_pos = None
        self._selected_items = None
        # Ghost/preview node
        self.init_preview_node()
        # Ghost/preview pipe
        self.init_preview_pipe()
        # setup scene 
        self.draw_origin()

    def init_preview_pipe(self):
        self.preview_pipe = QGraphicsLineItem()
        pen = QPen(Qt.GlobalColor.darkGray, 2, Qt.PenStyle.DashLine)
        self.preview_pipe.setPen(pen)
        self.preview_pipe.setZValue(5)
        self.addItem(self.preview_pipe)
        self.preview_pipe.hide()

    def init_preview_node(self):
        self.preview_node = QGraphicsEllipseItem(0, 0, 10, 10)
        self.preview_node.setBrush(QBrush(QColor(0, 0, 255, 100)))  # Semi-transparent blue
        self.preview_node.setPen(QPen(Qt.GlobalColor.blue))
        self.preview_node.setZValue(10)  # Draw on top
        self.addItem(self.preview_node)
        bounds = self.preview_node.boundingRect()
        self.preview_node.setTransformOriginPoint(bounds.center())
        self.preview_node.hide()
    
    # ----------------------------
    # SCENE MANAGEMENT
    # ----------------------------
    def save_to_file(self, filename: str):
        """Save scene items to JSON file"""
        data = []
        for item in self.items():
            if isinstance(item, QGraphicsEllipseItem):
                rect = item.rect()
                pos = item.pos()
                data.append({
                    "type": "ellipse",
                    "x": pos.x(),
                    "y": pos.y(),
                    "w": rect.width(),
                    "h": rect.height()
                })
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

    def load_from_file(self, filename: str):
        """Load scene items from JSON file"""
        with open(filename, "r") as f:
            data = json.load(f)

        self.clear()
        for obj in data:
            if obj["type"] == "ellipse":
                ellipse = QGraphicsEllipseItem(QRectF(0, 0, obj["w"], obj["h"]))
                ellipse.setPos(QPointF(obj["x"], obj["y"]))
                self.addItem(ellipse)
            
    def draw_origin(self):
            """Draw a simple crosshair at (0,0) and axis lines."""
            pen = QPen(Qt.GlobalColor.black)
            pen.setWidth(1)

            # Crosshair size
            size = 10
            h_line = QGraphicsLineItem(-size, 0, size, 0)
            v_line = QGraphicsLineItem(0, -size, 0, size)

            h_line.setPen(pen)
            v_line.setPen(pen)
            self.addItem(h_line)
            self.addItem(v_line)

            # Optional axis lines to make orientation easier
            axis_pen = QPen(Qt.GlobalColor.gray)
            axis_pen.setWidth(0)
            axis_pen.setStyle(Qt.PenStyle.DashLine)

            x_axis = QGraphicsLineItem(-1000, 0, 1000, 0)
            y_axis = QGraphicsLineItem(0, -1000, 0, 1000)

            x_axis.setPen(axis_pen)
            y_axis.setPen(axis_pen)

            self.addItem(x_axis)
            self.addItem(y_axis)
        


            
    # DELETE SELECTED ITEMS ***
    def delete_selected_items(self):
        """Delete all selected nodes, pipes, and sprinklers safely."""
        for item in self.selectedItems():
            if isinstance(item, Pipe):
                self.delete_pipe(item)

        for item in self.selectedItems():
            if isinstance(item, Node):
                # Remove attached sprinklers first
                if item.has_sprinkler():
                    self.remove_sprinkler(item)

                for pipe in item.pipes:
                    self.delete_pipe(pipe)
    
        
        for item in self.selectedItems():
            if isinstance(item, Node):
                self.remove_node(item)



    # -------------------------
    # MODE MANAGEMENT
    # -------------------------
    def set_mode(self, mode, template=None):
        """Switch the current placement mode and reset previews."""
        self.mode = mode
        print(f"Mode set to: {self.mode}")

        # Hide preview items
        self.preview_node.hide()
        self.preview_pipe.hide()

        # Cancel any ongoing pipe placement
        if self.node_start_pos is not None:
            # need to add logic to stitch pipe backtogether=>  self.join_pipe(self.node_start_pos)
            self.remove_node(self.node_start_pos)
        
        # Only emit the template if we have one
        if mode in ("sprinkler", "pipe"):  
            self.current_template = template  
            if template:  
                self.requestPropertyUpdate.emit(template)
        else:
            self.current_template = None

    # -------------------------
    # NODE/PIPE/SPRINKLER MANAGEMENT
    # -------------------------    
    def find_nearby_node(self, x, y):
        for node in self.sprinkler_system.nodes:
            if node.distance_to(x, y) <= self.SNAP_RADIUS:
                return node
        return None  

    def find_or_create_node(self, x, y):
        """
        Returns an existing node within SNAP_RADIUS of (x, y),
        or creates a new node at (x, y) if none exists.
        """
        existing = self.find_nearby_node(x, y)
        if existing:
            return existing
        return self.add_node(x, y)

    def add_node(self, x, y):
        node = self.find_nearby_node(x, y)
        if not node:
            node = Node(x, y)
            self.addItem(node)
            self.sprinkler_system.add_node(node)

        
        return node
    
    def remove_node(self, n):
        try:
            self.sprinkler_system.remove_node(n)
        except ValueError:
            pass
        if n.scene() is self:
            self.removeItem(n)
        n = None
        self.node_start_pos = None

    def add_pipe(self, n1, n2, template=None):
        print("cad_scene => add_pipe:")
        
        pipe = Pipe(n1, n2)
        if template:
            pipe.set_properties(template)

        self.sprinkler_system.add_pipe(pipe)
        self.addItem(pipe)
        return pipe
    
    def split_pipe(self, pipe, split_point: QPointF):
        """
        Split a pipe into two at the given point.
        Returns the new node created at the split point.
        """
        # 1. Create new node at the split point
        new_node = self.add_node(split_point.x(), split_point.y())
        template = pipe
        # need these temporary nodes and to remove pipe for proper updating of fittings
        node_a = pipe.node1
        node_b = pipe.node2

        # 2. Create two new pipes
        self.add_pipe(node_a, new_node, template)
        self.add_pipe(new_node, node_b, template)

        # 3. Remove old pipe
        self.delete_pipe(pipe)


        # 4. update fittings
        new_node.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        


        return new_node
    
    def delete_pipe(self, pipe):
        # Detach pipe from both nodes
        for node in (pipe.node1, pipe.node2):
            if node is not None:
                node.remove_pipe(pipe)
                if not node.has_sprinkler() and not node.pipes:
                    self.remove_node(node)
                    pass
        # Kill node references to avoid later NoneType errors
        pipe.node1 = None
        pipe.node2 = None

        # Remove the pipe from scene and scene list
        try:
            self.removeItem(pipe)
        except Exception:
            pass  # in case it's already removed

        if pipe in self.sprinkler_system.pipes:
            self.sprinkler_system.remove_pipe(pipe)

    def add_sprinkler(self, n, template=None):
        if n.has_sprinkler():
            return
        else:
            n.add_sprinkler()
            sprinkler = n.sprinkler
            self.sprinkler_system.add_sprinkler(sprinkler)
            if template:
                sprinkler.set_properties(template)
            if n.has_fitting():
                n.fitting.update()
        
        return sprinkler
    
    def remove_sprinkler(self, n):
        sprinkler = n.sprinkler
        self.removeItem(sprinkler)
        self.sprinkler_system.remove_sprinkler(sprinkler)
        n.delete_sprinkler()

    # --------------------------------------------------------------------------------------
    # Importing and hanling Underlays
    def import_dxf(self, file_path, color=QColor("white"), line_weight=0):
        """
        Import a DXF file and draw basic entities as QGraphicsItems.
        Supports LINE, CIRCLE, ARC, LWPOLYLINE, TEXT.
        """
        try:
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
        except Exception as e:
            print("❌ Failed to load DXF:", e)
            return

        pen = QPen(color, line_weight)
        imported_items = []
        
        for e in msp:
            try:
                if e.dxftype() == "LINE":
                    start = QPointF(e.dxf.start[0], -e.dxf.start[1])
                    end = QPointF(e.dxf.end[0], -e.dxf.end[1])
                    line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
                    line.setPen(pen)
                    line.setZValue(-100)
                    imported_items.append(line)                    

                elif e.dxftype() == "CIRCLE":
                    r = e.dxf.radius
                    x, y = e.dxf.center
                    circle = QGraphicsEllipseItem(x - r, -y - r, 2 * r, 2 * r)
                    circle.setPen(pen)
                    circle.setZValue(-100)
                    imported_items.append(circle)

                elif e.dxftype() == "ARC":
                    r = e.dxf.radius
                    x, y = e.dxf.center
                    start_angle = -e.dxf.start_angle * 16  # Qt expects 1/16° units
                    end_angle = -(e.dxf.end_angle - e.dxf.start_angle) * 16
                    arc = QGraphicsEllipseItem(x - r, -y - r, 2 * r, 2 * r)
                    arc.setStartAngle(start_angle)
                    arc.setSpanAngle(end_angle)
                    arc.setPen(pen)
                    arc.setZValue(-100)
                    imported_items.append(arc)

                elif e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                    points = [(p[0], -p[1]) for p in e.get_points()]
                    for i in range(len(points) - 1):
                        x1, y1 = points[i]
                        x2, y2 = points[i + 1]
                        pline = QGraphicsLineItem(x1, y1, x2, y2)
                        pline.setPen(pen)
                        pline.setZValue(-100)
                        imported_items.append(pline)

                elif e.dxftype() == "TEXT":
                    pos = e.dxf.insert
                    text_item = QGraphicsTextItem(e.dxf.text)
                    text_item.setPos(pos[0], -pos[1])
                    text_item.setDefaultTextColor(color)
                    text_item.setZValue(-100)
                    imported_items.append(text_item)

            except Exception as inner:
                print(f"⚠️ Skipped entity {e.dxftype()} due to:", inner)

        # --- ✅ GROUP EVERYTHING HERE ---
        if imported_items:
            for item in imported_items:
                self.addItem(item)
            group = self.createItemGroup(imported_items)
            group.setZValue(-100)
            group.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            group.setData(0, "DXF Underlay")  # optional tag

        print(f"✅ Imported DXF: {file_path}")

    def import_pdf(self, file_path, dpi=150, page=0):
        try:

            doc = QPdfDocument(self)
            page_count = doc.pageCount()
            print(f"PDF has {page_count} pages")

            if page < 0 or page >= page_count:
                raise IndexError(f"Page {page} out of range (valid range 0-{page_count-1})")

            page_size = doc.pagePointSize(page)
            if not page_size.isValid():
                raise RuntimeError(f"Page {page} returned invalid size")
            
            # Get page size in points (1 pt = 1/72 inch)
            page_size = doc.pagePointSize(page)
            if not page_size.isValid():
                raise RuntimeError("Invalid page size returned from PDF")

            # Convert to pixels at chosen DPI
            width_px = int(page_size.width() * dpi / 72.0)
            height_px = int(page_size.height() * dpi / 72.0)

            target_size = QSize(width_px, height_px)

            options = QPdfDocumentRenderOptions()
            image = doc.render(page, target_size, options)  # returns QImage

            if image.isNull():
                raise RuntimeError("Failed to render PDF page to image")

            pixmap = QPixmap.fromImage(image)
            item = QGraphicsPixmapItem(pixmap)
            item.setZValue(-100)  # keep PDF underlay below CAD items
            self.addItem(item)

            # center in scene
            item.setPos(-pixmap.width() / 2, -pixmap.height() / 2)

            print(f"✅ Imported PDF '{file_path}' page {page} at {dpi} DPI "
                f"({width_px}x{height_px} px)")

        except Exception as e:
            print("❌ Error importing PDF:", e)
    # --------------------------------------------------------------------------------------
    # GEOMETRY HELPERS
        
    def get_snapped_position(self, x, y):
        """Snap to grid."""
        grid = 10  # grid size
        snapped_x = round(x / grid) * grid
        snapped_y = round(y / grid) * grid
        return QPointF(snapped_x, snapped_y)
    
    def project_point_onto_line(self, p1: QPointF, p2: QPointF, p: QPointF) -> QPointF:
        
        """
        Project point p onto the line segment defined by p1 -> p2.
        Returns the closest point on the segment.
        """
        line_dx = p2.x() - p1.x()
        line_dy = p2.y() - p1.y()
        line_len2 = line_dx**2 + line_dy**2

        if line_len2 == 0:  # p1 == p2, degenerate line
            return p1

        # Parameter t along the segment
        t = ((p.x() - p1.x()) * line_dx + (p.y() - p1.y()) * line_dy) / line_len2
        t = max(0, min(1, t))  # clamp to [0,1] so it stays on the segment

        proj_x = p1.x() + t * line_dx
        proj_y = p1.y() + t * line_dy

        return QPointF(proj_x, proj_y)
    
    def project_click_onto_pipe_segment(self, snapped, selection):
        
        line = selection.line()
        p1 = QPointF(line.x1(), line.y1())
        p2 = QPointF(line.x2(), line.y2())

        # Project click onto pipe segment
        proj = self.project_point_onto_line(p1, p2, snapped)
        return proj

    # -------------------------
    # HELPER FOR PREVIEW NODE
    # -------------------------
    def update_preview_node(self, pos: QPointF):
        """Set preview node position, offset by radius for center alignment."""
        offset = self.preview_node.boundingRect().center()
        self.preview_node.setPos(pos-offset)
        self.preview_node.show()
    # -------------------------
    # MOUSE MOVE EVENT
    # -------------------------
    def mouseMoveEvent(self, event):
        scene_pos = event.scenePos()
        snapped = self.get_snapped_position(scene_pos.x(), scene_pos.y())

        if self.mode == "pipe":
            if self.node_start_pos:
                start_node = self.node_start_pos
                start = start_node.scenePos()

                # Determine if snapping should be relative to an existing pipe
                snapped_end = start_node.snap_point_45(start, snapped)

                self.update_preview_node(snapped_end)
                self.preview_pipe.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())
                self.preview_pipe.show()
            else:
                self.update_preview_node(snapped)
                self.preview_pipe.hide()

        elif self.mode == "sprinkler":
            self.update_preview_node(snapped)
            self.preview_pipe.hide()

        elif self.mode == "dimension":
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        
        elif self.mode == "paste" or self.mode == "move":
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        
        else:
            self.preview_node.hide()
            self.preview_pipe.hide()

        super().mouseMoveEvent(event)

    # -------------------------
    # MOUSE PRESS EVENT
    # -------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        scene_pos = event.scenePos()
        snapped = self.get_snapped_position(scene_pos.x(), scene_pos.y())

        # Find clicked item, preferentially selects nodes over pipes
        items = self.items(snapped)
        selection = next((item for item in items if isinstance(item, Node)), None)
        if selection is None:
            selection = next((item for item in items if isinstance(item, Pipe)), None)


        # ---------------------
        # SPRINKLER MODE
        # ---------------------
        if self.mode == "sprinkler":
            if selection is None:
                node = self.add_node(snapped.x(), snapped.y())
            elif isinstance(selection, Pipe):
                proj = self.project_click_onto_pipe_segment(snapped, selection)
                node = self.split_pipe(selection, proj)
            elif isinstance(selection, Node):
                node = selection
                if node.has_sprinkler():
                    print("Node already has a sprinkler")
                    return

            template = getattr(self, "current_template", None)
            self.add_sprinkler(node, template)
            node.fitting.update()
            

        # ---------------------
        # PIPE MODE
        # ---------------------
        elif self.mode == "pipe":
            if self.node_start_pos is None:
                # First click: start node
                if isinstance(selection, Pipe):
                    proj = self.project_click_onto_pipe_segment(snapped, selection)
                    self.node_start_pos = self.split_pipe(selection, proj) ### BUG if we cancel out here, we need to rejoin the pipe
                else:
                    self.node_start_pos = self.find_or_create_node(snapped.x(), snapped.y())             
            else:
                # Second click: end node
                start_pos = self.node_start_pos.scenePos()   
                snapped_end = self.node_start_pos.snap_point_45(start_pos, snapped)
                
                if isinstance(selection, Pipe):
                    proj = self.project_click_onto_pipe_segment(snapped_end, selection)
                    end_node = self.split_pipe(selection, proj)
                else:
                    end_node = self.find_or_create_node(snapped_end.x(), snapped_end.y())

                template = getattr(self, "current_template", None)
                self.add_pipe(self.node_start_pos, end_node, template)
                self.node_start_pos.fitting.update()
                end_node.fitting.update()
                self.node_start_pos = None
                self.preview_pipe.hide()
                self.preview_node.hide()

        
        elif self.mode == "dimension":
            if self.dimension_start is None:
                # First click: start point
                self.dimension_start = snapped
            else:
                # Second click: end point
                dim = DimensionAnnotation(self.dimension_start, snapped)
                self.addItem(dim)
                self.annotations.add_dimension(dim)
                self.requestPropertyUpdate.emit(dim)
                self.dimension_start = None

                # Handle paste offset measurement
        elif self.mode in ("paste","move"):
            if self.node_start_pos is None:
                self.node_start_pos = snapped
            else:
                start_pos = self.node_start_pos 
                end_pos = snapped
                offset_vector = CAD_Math.get_vector(start_pos, end_pos)

                if self.mode == "paste":
                    self.paste_items(offset_vector)
                elif self.mode == "move":
                    self.move_items(offset_vector)
                self.node_start_pos = None
                self.set_mode(None)

                return  # don’t pass event further while selecting offset

        elif self.mode is None:
            if isinstance(selection, Node):
                print(selection)
                print(f"node has: {len(selection.pipes)} pipes connected")
    

                if selection.has_sprinkler == True:
                    #show sprinkler data.
                    print("sprinkler data")
                    print(len(selection.pipes))
            elif isinstance(selection, Pipe):
                print(selection.node1)
                print(selection.node2)



            
        super().mousePressEvent(event)
    # -------------------------
    # KEY PRESS EVENT
    # -------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.set_mode(None)
            for item in self.selectedItems():
                item.setSelected(False)

        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected_items()

        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            for item in self.items():
                if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)
        
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected_items()

        elif event.key() == Qt.Key.Key_M and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.selectedItems():
                self._selected_items = self.selectedItems()
                self.set_mode("move")

        elif event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.clipboard_data():
                self.set_mode("paste")
        
        elif event.key() == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            #redo action
            pass

        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            #undo action
            pass
        
        else:
            super().keyPressEvent(event)
    
    def copy_selected_items(self):
        """Copy selected items (nodes, pipes, sprinklers) to clipboard."""
        data = []
        # copy all selected sprinkler system data to clip board.
        for item in self.selectedItems():
            if isinstance(item, Node):
                
                # record attached sprinkler (if any)
                if item.has_sprinkler():
                    sprinkler = item.sprinkler.get_properties()
                else:
                    sprinkler = None

                # record connected pipes by node positions
                pipes = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    pipes.append({
                        "x": other.pos().x(),
                        "y": other.pos().y()
                    })
                
                data.append({
                    "type": "node",
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "sprinkler": sprinkler,
                    "pipes": pipes
                })

        clipboard = QApplication.clipboard()
        clipboard.setText(json.dumps(data))

    def paste_items(self,offset):
        """Paste items from clipboard into the scene with slight offset."""
        data = self.clipboard_data()

        for obj in data:
            if obj["type"] == "node":
                # compute new position
                new_x = obj["x"] + offset.x()
                new_y = obj["y"] + offset.y()

                # check for existing node near that position
                existing = self.find_nearby_node(new_x, new_y)
                if existing:
                    node1 = existing
                else:
                    node1 = self.add_node(new_x, new_y)

                # restore sprinkler if applicable
                if obj.get("sprinkler"):
                    # UPGRADE: need to add sprinkler properties
                    properties = obj.get("sprinkler")
                    template = Sprinkler(None)
                    for key, meta in properties.items():
                        template.set_property(key, meta["value"])

                    self.add_sprinkler(node1, template)

                # reconnect pipes
                if obj.get("pipes"):
                    for p in obj["pipes"]:
                        px = p["x"] + offset.x()
                        py = p["y"] + offset.y()
                        existing_p = self.find_nearby_node(px, py)
                        if existing_p:
                            node2 = existing_p
                        else:
                            node2 = self.add_node(px, py)

                        # avoid duplicates
                        if not any(
                            (pipe.node1 == node1 and pipe.node2 == node2)
                            or (pipe.node1 == node2 and pipe.node2 == node1)
                            for pipe in self.sprinkler_system.pipes
                        ):
                            # UPGRADE: need to add pipe properties
                            self.add_pipe(node1, node2)

                node1.fitting.update()

    def move_items(self,offset):
        """Paste items from clipboard into the scene with slight offset."""
        for item in self._selected_items:
            if isinstance(item, Node):
                item.moveBy(offset.x(),offset.y())
                item.setSelected(True)
                item.fitting.update()
                    
    def clipboard_data(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text:
            return None
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError:
            print("Clipboard doesn’t contain valid CAD data")
            return None