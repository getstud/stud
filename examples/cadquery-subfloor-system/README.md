# Composed subfloor study

Start with `stud init PATH --example subfloor-system`. The copied design contains
project inputs and calls installed `stud.floors` operations for an L-shaped floor,
a shared stair opening, and a wing whose joists and panels rotate 90 degrees.

Change `OPENING` to regenerate framing and panel cuts together. Change the panel
edge system to `square` to generate local backing where T&G formerly supported
joints. Panel origin, stagger, product and connection selections are explicit.

The model uses nominal touching sheet modules. The fabrication report deliberately
retains a `nominal_sheet_layout` finding: final coverage, installation allowances
and cuts must be reconciled with actual purchased stock. Geometric checks do not
supply structural member sizing, fastening design or a complete installation order.
