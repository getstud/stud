"""A six-foot bench; direct CadQuery and ordinary Python remain available here."""
from stud.cad import Model
from workbench import workbench

model = Model('Garage workbench', units='in')
bench = workbench(model, width=72, depth=24, height=36,
                  dog_hole=(8, 4))
