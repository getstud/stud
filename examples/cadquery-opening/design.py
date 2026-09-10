from stud.cad import Model
from opening import rotated_opening

model = Model('Rotated opening and mirrored corner detail', units='in')
rotated_opening(model, width=36, angle=30, mirrored_detail=True)
