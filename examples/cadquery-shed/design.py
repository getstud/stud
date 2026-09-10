"""A detailed 8 x 10 foot framing study; all coordinates are millimeters."""
from stud.cad import Model
from stud.buildings import shed

model = Model('8 x 10 foot shed framing')
components = shed(model, length=3048, depth=2438.4, door_width=914.4, window_width=650,
    wall_exceptions={'front': {'stud.at_406_4': {'bore': {'x': 19, 'z': 500, 'diameter': 12}}}})
