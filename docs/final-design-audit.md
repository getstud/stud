# Final design audit — 8 September 2026

Audited the current **Structural regression | 12 × 16 | assembly review** design, revision `50f411929e29`, displayed at localhost:8767. This is the assembly fixture in `projects/framing-validation/design.py`; it is not an approved construction package or a replacement for the separately named AFTER HOURS project. The audit made no model or generator changes.

Fresh validation reproduced **343 parts, 1,145 PASS, zero FAIL/WARNING and 20 UNVERIFIED**. The saved report declares 695/695 generated requirements passed. These counts describe existing checks, not design completeness. Visual inspection and additional in-memory probes found important omissions that the green checks do not catch.

## Approved correction status

The first implementation pass following this audit now adds door and window sill packers, named wall-to-floor bearing requirements, and separate 3/8-inch soffit versus 3/4-inch bird-box closure stocks. Stock thickness is declared and checked. The current model has 345 parts and 1,162 passing checks, no failures/warnings and 22 unverified items. The two added unverified notes explicitly retain manufacturer-specific sill installation details.

Verification: five focused audit regressions passed, including the review correction. Full 126-test discovery had only a sandboxed local-server startup failure; all six tests in that module passed with socket access. Both desktop-resource parity tests passed.

The original findings below remain as audit evidence. The threshold's host-wall bearing gap is filled and measured; support of projecting product noses, flashing and material suitability still need the selected unit. Wall-floor separation is now caught for each wall. The mixed soffit purchasing row is split. This is a Stud development fixture. Site and product inputs are test parameters; gathering real project inputs belongs to the agent using the shipped skill. The skill now directs that agent to request missing location/preferences, research applicable criteria, and persist the resulting sizing/enclosure basis. Remaining builder and validation capabilities can be developed without a personal construction site. No capacity or weather-enclosure completion is claimed for this fixture.

### Fascia, gable cladding and corner-trim correction

The next approved pass cuts the rake fascia to 7-5/8 inches (7-1/4-inch rafter plus 3/8-inch soffit), using a separate 1×10 purchase blank. The bird-box face closes beneath it. Front/back sheathing and siding now cover the upper wall and both gables, including the ridge underside cut. Exterior finishes extend down over the floor rim. All eight corner boards extend into the gable-soffit region, with scribed cuts, notched soffit panels and added edge backing. Each trim board remains one stock blank.

Current fixture: 375 parts, revision `01d5414547ab`, 1,253 PASS, zero FAIL/WARNING and 21 UNVERIFIED. New checks cover the actual rake depth, polygon soffit edges, gable siding footprint and upper trim backing. All 131 Python and 25 JavaScript tests pass, including rotated/mirrored regression cases and renderer-volume/boundary checks. The original gable, exposed-rim and fascia-depth observations below are superseded by this correction; remaining weather-system and structural evidence is still unresolved.

### Asphalt roof finish correction

The roof now has a reusable `asphalt_roof` finish assembly: 5/8-inch deck panels,
membrane, drip-edge aprons, eave/rake starters, staggered charcoal shingle courses
and a closed ridge cap. Eave fascia tops are beveled to the roof plane. The
current revision is `850763ab0533`: 773 parts, 1,658 passing checks, no failures or
warnings, and 28 unverified findings. New requirements include deck bearing,
membrane coverage contact, starter bearing, field substrate contact and cap
bearing. Missing or collectively displaced finish layers are regression cases.

Shingle counts use exposed area and installed package yield. Accessories use
linear coverage, including when stock is shared between roles. The geometry
represents net coverage; hidden headlaps and folded metal roof flanges remain
installation details. Deck span rating, panel edge clips/blocking, installation
gaps, fastening, ice protection and ventilation/condensation design are still
explicitly unverified. This corrects the absent-roof finding below without
claiming a construction-ready weather enclosure. See `docs/cadquery.md` and `skills/stud-design/references/framed-buildings.md`.
Verification covers 137 Python cases across full/focused runs (the server module
was rerun successfully with localhost access) and all 25 JavaScript tests.

## Confirmed model and validation gaps

| Priority | Finding and evidence | Required resolution |
|---|---|---|
| High | **Roof enclosure is absent.** The roof has rafters, ties, overhang framing, fascia and soffits, but no roof sheathing, underlayment, covering, ridge cap or drip-edge system. | Select the roof assembly, derive its layers and edge interfaces, add panel support/attachment details and account for its weight in sizing. |
| High | **The upper gable enclosure is open.** Front/back sheathing, siding and corner trim stop at Z=109.981 in; wall tops are Z=123.25 in. This leaves a 13.269-inch upper-wall band before the triangular gable area, which also has no skin. Gable studs alone do not close it. | Continue the front/back enclosure to the roof slope, with supported edges and the chosen weather-control layers. Coordinate the bird-box/wall junctions. The eave walls have a different termination condition and should not simply receive the same rectangular height change. |
| High | **Door threshold has no modeled bearing.** `entry.unit.threshold` underside is Z=27.75 in; subfloor top is Z=27.25 in. The resulting half-inch gap has no modeled sill support/shims. A downward contact scan against every other solid returned zero contact. Door/window support coverage is also zero. | Add the selected product's threshold support and sill/pan detail, plus explicit support and attachment requirements. Preserve any intentional installation clearance while filling the required bearing locations. |
| High | **Wall-to-floor bearing is missing from validation.** No explicit rule links a wall/roof/enclosure part to a floor, beam or pad. In an in-memory copy, lowering all `floor.*`, `beam.*` and `pad.*` parts by 0.25 in created a wall-floor gap but still produced 1,145 PASS, zero FAIL and 20 UNVERIFIED. The actual saved walls currently sit on the subfloor; the defect is that this relationship is not checked. | Add bearing and assembly-connection requirements across this interface, and a regression that fails when the lower assembly separates. Contact alone will still not verify fastening capacity. |
| Medium | **One sheet-stock item mixes two thicknesses.** Stock `soffit` contains 12 parts at 3/8 in and eight bird-box closure parts at 3/4 in. It is presented as one three-sheet area allowance and one pricing row. These are distinct purchasing products even if their material and sheet dimensions match. | Split sheet stocks by thickness/product, regenerate quantities and price them separately. Check nesting and waste before using the quantities for purchasing. |

## Decisions and construction details still unresolved

| Area | Remaining gap |
|---|---|
| Member sizing | Rafters remain nominal 2×8 and do not carry a span-table receipt. The new selector exists but has not been applied to real site loads/species/grade. Floor joists, beams, headers, ridge and overhang members likewise lack a completed sizing basis. This does not establish that they are too small or too large. The rafter horizontal clear span in this geometry is 67.75 in; its stock length is not the span-table span. |
| Foundation and continuous connections | The six 12-inch support envelopes are not selected footing/pier products or a designed foundation. Soil/frost/drainage criteria, bearing capacity, anchorage, beam-to-support, floor-to-beam, wall-to-floor and roof-to-wall fastening/hold-down details remain unspecified. No continuous capacity check connects roof loads to the ground. |
| Roof ties and open overhead space | There are 13 full-width low rafter ties at wall-top level, with approximately 96 in from subfloor to tie underside. No high collar ties or ridge straps are modeled. Confirm the intended ceiling/clearance arrangement and specify the ridge/uplift connection detail. High collar ties do not replace lower thrust-resisting rafter ties; changing elevation requires an applicable system/design basis. |
| Cuts and bracing | Birdsmouth limits remain explicitly labeled regression inputs. Gable uprights have deep rafter notches and tie rebates; their retained section, fastening and bracing are not structurally checked. Contact and absence of collisions establish fit only. |
| Water, air and ventilation details | WRB/drainage plane, window/door sill pans and head/jamb flashing, sealants and roof-edge flashing are absent. Roof ventilation versus an unvented assembly has not been selected. The closed soffits have no specified vent openings, insect screening, airflow area or baffles. Insulation/air/vapor layers depend on the intended conditioned or unconditioned use. |
| Panels and cladding | Floor panel joints are nominal zero-gap meeting planes. Product-specific installation gaps, strength-axis/span rating, fastener schedules and exterior sheathing edge support remain unresolved. The wall finish begins at the subfloor top; exposed floor edges/rim framing need a deliberate exterior protection/termination detail. Corner trim geometry is checked, but product-specific joints and weather details are not finalized. |
| Doors, windows and access | Units are generic envelopes with no selected manufacturer, hinges, latches, locks, seals, fastening or installation schedule. Motion is checked only at sampled angles and with limited obstacle scopes. There is no entrance landing, step or ramp despite the model's elevated floor; actual grade and intended access must establish that design. |
| Fascia and bird-box finish | The new doubled rafters, rake backing, boxed returns and fascia butt joints pass their geometry checks. Fascia stock remains an assumed actual 3/4 × 13-1/4 in board, including 20-foot purchasing lengths; availability, material suitability, fastening, joint sealing and finish need selection. Its depth follows the current under-rafter soffit framing, so it should be reconsidered together with any rafter-size change. |
| Purchasing and budget | Lumber grades/species, sheet products, footing units and door/window products are unselected. Sheet quantities are area estimates, not verified cut layouts. Hardware, membranes, roofing and other missing assemblies are absent from a complete order. The displayed $0.00 is an unpriced subtotal, not a project cost. |

## What checked successfully

The fresh model has no detected positive-volume collisions. Existing checks pass for the floor framing and panel bearing, internal wall framing/opening relationships, rafter seats and ridge contacts, gable-stud fit, doubled fly rafters, inner rake backing, rake-soffit attachments, bird-box base support, eave ledger contact and fascia corner/peak/flush alignment. Product envelopes fit their declared openings and sampled motion checks pass. The preceding implementation test run passed 121 Python tests; this audit reran model validation and targeted contact/coverage probes rather than repeating that entire suite.

## Evidence and next work

Primary project evidence: `projects/framing-validation/design.py`, its exported parts, and `projects/framing-validation/output/model/validation.json`. Generator evidence: `stud/roofs.py`, `stud/walls.py`, `stud/openings.py`, `stud/floors.py`, and stock grouping in `stud/model.py::takeoff`. Temporary displacement probes were performed only in memory; no geometry changes were saved.

External references used to distinguish unresolved construction functions:

- [American Wood Council: collar ties versus rafter ties](https://awc.org/faq/what-is-the-difference-between-a-collar-tie-and-a-rafter-tie/) — explains their different locations and force-resisting functions.
- [PNNL: windows and doors are fully flashed](https://basc.pnnl.gov/resource-guides/windows-and-doors-are-fully-flashed) — outlines sill, jamb and head flashing integrated with the drainage plane.
- [PNNL: drainage plane behind exterior wall cladding](https://basc.pnnl.gov/resource-guides/drainage-plane-behind-exterior-wall-cladding) — describes continuity with flashing and the drainage path.

Fix the three newly confirmed implementation gaps first: threshold support, wall-floor validation and sheet-stock separation. Then resolve site/load/product and ceiling inputs, size the structural members, and complete roof/gable weather enclosure and connection details. A construction-ready claim should wait until those items have specific evidence rather than generic unverified notes.
