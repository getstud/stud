# Ridge termination at a closed gable overhang

Research date: 8 September 2026. Prompted by area comment
`f56e0293-77e5-4545-8510-2c6be3f1d5c1` on the visible ridge end.

The projection is a model coordination defect. `gable_roof` extends a rectangular
2×10 ridge board through both rake overhangs, while the sloped soffit panels stop
at the ridge faces. The model does not provide a closed peak around that deeper
member. Geometric contact checks passing did not establish enclosure continuity.

## Published guidance

- [2021 IRC R802.3](https://codes.iccsafe.org/content/IRC2021P2/chapter-8-roof-ceiling-construction)
  requires ridge-board depth to cover the rafter cut end, and distinguishes a
  tied roof from one needing an engineered supported ridge. This is a reference
  provision, not a determination of a particular site's adopted code. For the
  fixture's 7.25-inch rafters at 6:12, the plumb end is 8.106 inches; a 7.25-inch
  ridge would not meet that depth criterion. The 9.25-inch board's depth is not
  evidence that its exterior termination is correct.
- [PNNL: Framing of Gable Roof Overhangs](https://basc.pnnl.gov/resource-guides/framing-gable-roof-overhangs)
  describes ladder and outrigger assemblies, supported fascia, roof decking,
  and rigid soffit closing the underside. Its wind-specific guidance requires
  selecting connections and framing appropriate to the overhang and exposure;
  it is not blanket approval of the fixture's 12-inch ladder.
- [Tim Uhler: Rake Wall Framing, JLC](https://www.jlconline.com/how-to/framing/rake-wall-framing_o/)
  documents closed gable soffits framed as assemblies. Fly rafters meet at plumb
  cuts at the peak, where a connector holds the joint together. The soffit and
  trim are fitted to that framing.

## Recommended model correction — inference from those details

For this closed, slim-rake design, terminate the full-depth ridge board at the
gable wall and frame the overhang peak as a connected ladder/fly-rafter assembly.
Retain full ridge depth where the main rafters meet it. Update fly-rafter peak
geometry and its connections; simply shortening the ridge would remove the
current peak contact without replacing it. Extend and support the soffit across
its existing ridge-width gap, close the corresponding gable cladding notch,
and preserve the accepted fascia depth. Check both ends and rotated/mirrored
frames. Add an enclosure requirement that detects an exposed ridge or open peak.

This is a proposed detail for the current model, not a universal requirement
that all ridge boards stop at the wall. A deliberately extended ridge can be
part of another designed overhang system, but its section, connections and
finish envelope must be coordinated. Do not arbitrarily notch or shave a
structural ridge beam to solve a cosmetic clash. The subsequent approved implementation uses the wall-terminated detail for
closed ridge-board roofs. The structural-ridge case is deliberately separate.
Peak face contacts and the ridge envelope are checked; connector capacity and
installation schedules remain unverified.
