from stud.cad import Model
from roof_joint import roof_joint

model = Model('Sloped rafter with a flat bearing seat', units='in')
roof_joint(model, slope=0.5, run=20, seat=3.5)
