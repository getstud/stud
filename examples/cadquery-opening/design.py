from stud.cad import Model
from stud.construction import rotated_opening

model = Model('Rotated opening and mirrored corner detail')
rotated_opening(model, width=900, angle=30, mirrored_detail=True)
