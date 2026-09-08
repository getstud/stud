# Worked example: coordinated gable shed

This 12 × 16 example demonstrates the Python API, shared dimensions and geometric checks. Its architecture and provisional stock choices are editable. It is not an approved plan or the default result for every shed.

Copy this directory to a new project outside the app, then run `stud build /absolute/path/to/project` and `stud serve /absolute/path/to/project --no-open`. From a checkout, use `python3 /absolute/path/to/stud_cli.py` in place of `stud`. Installed copies are in `engine/examples/framed-shed/`. Keep generated output, comments and prices with the new project.

## Decisions to adapt

| Choice | This example | Alternatives and dependencies |
|---|---|---|
| Roof/walls | Gable, 6:12, 2×4 walls | Choose the requested roof form and wall system. This helper's scope is a sawn-rafter gable; other forms can use project-owned assemblies. |
| Ridge | Full-depth ridge board ending at gable walls | `ridge_termination='extended'` is supported, with enclosure evidence unresolved until that detail is supplied. Structural ridge systems require their own supports. |
| Overhang | Closed 12-inch eaves and rakes | Adjust dimensions, or omit soffit inputs for an open overhang. Recheck intersections and support geometry. |
| Fascia/return | Tail depth plus soffit overlap; triangular closure, 4 inches past trim | `eave_fascia_overlap=None` uses the registered fascia face depth for a deeper boxed closure. Select a blank deep enough for the rectangular soffit supports (13¼ inches works with these fixture sizes). `bird_box_return=0` ends at the framing corner; other inward lengths are supported. Shape follows these mating dimensions. |
| Sheet siding | `SIDING_LAYOUT='centered'` | `'start'` aligns full sheets to the finished edge; `SIDING_OFFSET` can place the first joint a specified distance from that edge. Cutouts stay in their parent sheet. |
| Grouping | Separate fascia toggle | `FASCIA_ASSEMBLY=None` keeps the boards in the roof group. |
| Trim | Board corners, 4-inch opening casing, door kickboard | Width, overlap, stock and optional kickboard are builder inputs. Derive return lengths from the selected corner trim, not this example's 3-inch inside edge. |

The constants at the top of `design.py` expose the highlighted choices. Other dimensions, products and finishes are explicit inputs at their owning stock registrations and builder calls. When changing pitch or section size, recalculate fascia overlap, ridge depth, notches and finish clearances together.

## What carries forward

The example composes supports → floor → walls/openings → roof/gables → enclosure/trim → products → roof finish. Builders own member presence, solid collisions, stock fit, bearing/contact, panel support and opening clearance. Alternative configurations retain those checks. Finish colors, proportions, sheet alignment and visible assembly groups remain design decisions.

Load-bearing stock, site loads, soil/footings, product selections, fastening and weather details remain provisional. The thin ends of the example's scribed soffit cleats have no verified fastening schedule. Establish those inputs for a construction project; passed geometry does not establish capacity or code compliance.
