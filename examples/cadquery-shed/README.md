# Detailed shed framing

All dimensions are native inches: a 120 × 96 inch platform, actual 1.5 × 3.5 inch wall stock, 16-inch framing stations, 1/8-inch sheet gaps and a 1/2-inch service bore.

This example includes a rimmed floor, a door opening, a window opening, four wall frames, actual sheathing sheets and cutouts, paired sloped rafters, ties, housed eave blocking, gable infill and roof panels. A through-bore is a deliberate exception on one front-wall stud. Changing the opening widths preserves that independent detail.

`shed.py` is the project-owned definition; `design.py` selects its parameters. Both are copied into each new project and saved with its history.

Create it with `stud init ./my-shed --example shed`, then `stud serve ./my-shed`. Begin an editing request before changing parameters; edit the returned workspace, evaluate it, and finish the request to save a checkpoint. Generate its packet with `stud plans ./my-shed --checkpoint CHECKPOINT --wait`.

The packet reports site-dependent foundation, anchorage, load sizing and weatherproofing details as unfinished. It is a framing study, and its geometric checks do not constitute structural analysis. Dimensions, blanks, cuts, stock purchases, panel layouts and assembly references come from the same saved model.
