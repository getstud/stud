from stud.cad import Model
from stud.construction import roof_joint

model = Model('Sloped rafter with a flat bearing seat')
roof_joint(model, slope=0.5, run=500, seat=89)
