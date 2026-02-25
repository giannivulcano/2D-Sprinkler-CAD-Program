from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QGraphicsItem, QStyle
from PyQt6.QtGui import QPen, QColor

class Sprinkler(QGraphicsSvgItem):
    GRAPHICS ={
        "Sprinkler0": r"graphics/sprinkler_graphics/sprinkler0.svg",
        "Sprinkler1": r"graphics/sprinkler_graphics/sprinkler1.svg",
        "Sprinkler2": r"graphics/sprinkler_graphics/sprinkler2.svg"
    }

    def __init__(self, node):
        super().__init__()   # <-- critical
        self.node = node
        self._properties = {
            "K-Factor": {"type": "enum", "value": "5.6", "options": ["5.6", "8.0", "12.0"]},
            "Type" : {"type": "enum", "value": "Wet", "options": ["Wet", "Dry", "Preaction","Deluge"]},
            "Orientation": {"type": "enum", "value": "Upright", "options": ["Upright", "Pendent", "Sidewall"]},
            "Temperature": {"type": "string", "value": "68°C"},
            "Manufacturer": {"type": "enum", "value": "Tyco", "options": ["Victaulic", "Tyco"]},
            "Graphic" : {"type": "enum", "value": "Sprinkler0", "options": ["Sprinkler0", "Sprinkler1", "Sprinkler2"]},
            "Elevation": {"type": "enum", "value": "0", "options": ["Sprinkler1", "Sprinkler2"]}
        }
        self.scale = 10/30


        # Create the SVG graphics
        self.set_graphic(self.GRAPHICS[self._properties["Graphic"]["value"]])
    

    def set_graphic(self, svg_path):
        self.graphics = QGraphicsSvgItem(svg_path)
        self.graphics.setScale(self.scale)
        # Set the node as parent so it moves automatically
        self.graphics.setParentItem(self.node)

        # Center the SVG on the node
        bounds = self.graphics.boundingRect()
        self.graphics.setTransformOriginPoint(bounds.center())
        self.graphics.setPos(-bounds.width() / 2, -bounds.height() / 2)

        self.graphics.setZValue(100)
    
    def get_properties(self):
        return self._properties.copy()

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value

            if key == "Graphic":
                svg_path = self.GRAPHICS.get(value)
                if svg_path:
                    self.set_graphic(svg_path)

    
    def set_properties(self, template: "Sprinkler"):
        """Copy property values from a template sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])
