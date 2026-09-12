"""Four roof planes composed with reusable stock cuts and panel operations."""
from stud.cad import Model
from hip_roof import hip_roof

model=Model('Hip roof | composable framing study',units='in')
roof=hip_roof(model)
