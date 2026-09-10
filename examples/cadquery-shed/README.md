# Detailed shed framing

This example includes a rimmed floor, a door opening, a window opening, four wall frames, actual sheathing sheets and cutouts, paired sloped rafters, ties, housed eave blocking, gable infill and roof panels. A through-bore is a deliberate exception on one front-wall stud. Changing the opening widths preserves that independent detail.

Create it with `stud init ./my-shed --example shed`, then `stud serve ./my-shed`. Begin an editing request before changing parameters; edit the returned workspace, evaluate it, and finish the request to save a checkpoint. Generate its packet with `stud plans ./my-shed --checkpoint CHECKPOINT --wait`.

The packet reports site-dependent foundation, anchorage, load sizing and weatherproofing details as unfinished. It is a framing study, and its geometric checks do not constitute structural analysis. Dimensions, blanks, cuts, stock purchases, panel layouts and assembly references come from the same saved model.
