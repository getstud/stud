"""A six-foot bench; direct CadQuery and ordinary Python remain available here."""
from stud.cad import Model, inches
from stud.construction import workbench

model = Model('Garage workbench')
bench = workbench(model, width=inches(72), depth=inches(24), height=inches(36),
                  dog_hole=(200, 100))
