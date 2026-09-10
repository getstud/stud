# Courtyard residence workload

This project is a representative building workload for CadQuery, live display, quantities, history and drawings. It is an architectural framing study with 14 room bays on each of two storeys, three connected wings and 5,488 sq ft of floor platforms. Each bay is 168 inches square. All dimensions are native inches, including actual 1.5 × 3.5 inch wall stock and the 1/2-inch service bore.

Create it with `stud init PATH --example mansion`. Ordinary Python in `mansion.py` composes the same wall, floor and roof helpers used by the smaller examples. The model includes nested rotated wings, window and passage openings, an upper stair void, sloped/birdsmouth rafters, cut sheets with supported seams, and an intentional service bore in a persistent kitchen stud. Each completed assembly can appear before the whole model finishes.

`residence()` accepts `local_window_width`, shared `window_width`, `slope`, `bore_diameter`, whole-building `rotation`, and `include_guest`. The benchmark widens one window, changes shared windows, rotates all wings, removes a module while changing roof/bore details, and restores the defaults. Each cached result is compared against a fresh execution with all native queries repeated.

The paired module frames and their floor platforms are deliberate workload geometry. Inter-module connections, foundation, load sizing, inter-storey load paths, egress/fire separation, roof junctions/drainage and weatherproofing need project-specific design. The study is not a permit or construction-ready house design. The ordinary authored notes and connection findings carry those omissions; no separate building ontology is introduced.

Run `python scripts/benchmark-native.py mansion --plans --edits` from the stud source checkout to capture real worker, memory, drawing, estimate, history and comparison timings. The house drawing benchmark selects its upper-floor overview, kitchen wall and rafter-seat detail; it does not generate thousands of repeated workshop instructions. Use the small shed/workbench examples for complete DIY packet acceptance.
