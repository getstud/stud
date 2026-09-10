"""A detailed 8 x 10 foot framing study; all coordinates are inches."""
from stud.cad import Model
from shed import shed

model = Model('8 x 10 foot shed framing', units='in')
components = shed(model, length=120, depth=96, door_width=36, window_width=26,
    wall_exceptions={'front': {'stud.at_16': {'bore': {'x': .75, 'z': 20, 'diameter': .5}}}})
