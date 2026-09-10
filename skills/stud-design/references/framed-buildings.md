# Framed buildings

Use this branch for sheds, clubhouses and similar framed structures. Design physical construction assemblies and their load-path interfaces. Interior use informs clearances; decorating and furnishing need an explicit request.

Apply these construction criteria to the project's format. The `WallFrame`, `wall_enclosure`, `select_rafter_size`, `asphalt_roof` and boxed-overhang APIs referenced below belong to the retained legacy model. For current CadQuery projects, read `docs/cadquery.md` and `stud.buildings`; use a project-owned CadQuery function for details those native helpers do not implement. Do not mix inch-based legacy parts with a millimeter manifest.

## Decisions before geometry

Reuse the user's existing choices. Otherwise ask for wall stock and roof form together using the host's question tool. Offer gable, hip, shed or another requested style; a gable is a useful starting recommendation for a simple conventional clubhouse. Ask about pitch and overhang where they materially affect form. Confirm the site/support assumptions and whether interior walls will be finished. An unfinished interior does not need an invented drywall package.

Resolve ceiling intent before choosing roof ties. Reuse an explicit ceiling choice; otherwise infer from the intended use and state the assumption briefly. A basic unconditioned storage shed or a request to store tall objects usually suggests an open roof with no ceiling lining. A specified flat finished ceiling suggests ceiling framing and lining. “Clubhouse,” “workshop,” insulation, or finished walls alone can leave flat versus open/vaulted overhead space unclear; ask one focused question through the host's question tool when that distinction affects the design. Record the choice and any required clear height for large objects. A no-ceiling choice omits ceiling finishes and framing used solely to carry them; required roof ties still follow the selected roof system.

Explain the proposed bottom-up stages, then open the viewer and build coherent stages. Each stage owns expected parts and named requirements so deleting a required part or check leaves an actionable finding. Keep structural sizing and fastening evidence separate from geometry checks.

## Site inputs for a construction project

When location affects foundation, loading or enclosure decisions, the agent using Stud must first check the project's saved specification and conversation for a usable location. If it is missing, ask the end user where the structure will be built, starting with city/region and country. Request a more precise site only when needed to resolve jurisdiction, elevation, exposure or another relevant criterion. A cosmetic edit or a location-independent assembly check does not require a new site interview.

Use that location to research applicable criteria from the local authority and other primary sources. Record jurisdiction, source/date and the relevant snow, wind, seismic, frost and climate inputs in the project specification. Distinguish ground snow from the roof snow load required by a selected table. Treat soil bearing and site exposure as separate evidence; location alone does not establish them. If a source leaves a required criterion unresolved, ask a focused follow-up or identify the evidence needed.

Ask the end user for consequential preferences such as roof covering, conditioned use and ceiling intent when they are absent. Research suitable lumber/product options rather than expecting the user to supply engineering values. Carry the resulting inputs into the applicable sizing tables, support details and enclosure decisions, and preserve their sources with the design. Reuse saved answers; a changed site or specification requires reviewing affected selections and interfaces.

The intake is complete when each site-dependent decision has a sourced input or a specific unresolved item. Continue independent geometry while awaiting required answers, and keep dependent selections provisional. When developing Stud, exercise this workflow with labeled fixture scenarios and missing-input cases; a developer's personal building location is not a prerequisite for implementing the capability.

## Member sizing from span tables

Select load-bearing lumber from an applicable published span/load table or manufacturer design tool before treating its size as resolved. Use the smallest available listed section that satisfies the actual span, spacing, loads, deflection and construction-detail constraints; record the reason for a larger choice. Size floor joists, rafters, ceiling joists, headers and beams for their own member function and load path. Reusing floor stock for rafters does not establish the roof size.

Establish site/jurisdiction load criteria, roof covering and ceiling loads, species, grade, moisture/service condition, support geometry and spacing. Reuse sourced project inputs; ask focused questions for missing inputs that prevent choosing the applicable table. Ground snow and adjusted roof snow are distinct inputs. Calculate the span using the table's measurement convention: rafter tables commonly use the horizontal clear distance between bearing faces, excluding the overhang, rather than building length or sloping cut length.

Record source URL, publisher/edition, table and row, design inputs, allowable span and actual span with the selected stock. Check the table's bracing, bearing, load pattern and system assumptions. Select another sourced table or designed system when outside its scope; a guessed large member remains provisional. In current Stud, `select_rafter_size` and `gable_roof(span_table=...)` support the explicitly bounded lookup documented in the installed construction-assembly documentation. For other conditions, consult a current applicable primary source and preserve the same evidence in the project.

Recheck sizing when span, spacing, loads, ceiling intent, tie elevation, species or grade changes. Regenerate seats, remaining sections, ridge/fascia depths, gable notches and stock cuts after a size change. Span-table adequacy covers only its stated checks; bearing, birdsmouths, cantilevers, connections, uplift and raised ties need their corresponding details. Before moving on, every load-bearing member family has either a recorded sizing basis or an explicit unresolved input; geometric fit alone is not a sizing result.

## Floor stage

Plan support lines, beams, joist direction and subfloor together. Prefer the shorter unsupported joist span when supports permit; an interior beam may change the best direction. Record any alternative's reason. Check bearing and lateral restraint before covering the frame.

Distinguish four blocking purposes: joist end restraint, intermediate lateral restraint/bridging, bearing/load transfer, and panel-edge backing. Select required locations using the actual joist system, panel edge detail and adopted rules. Do not infer a universal midspan interval from the word “blocking.”

The accessible [2018 IRC R502.7.1](https://codes.iccsafe.org/content/IRC2018P7/chapter-5-floors) applies its 8-foot intermediate-restraint interval to joists exceeding nominal 2×12. [Local amendments can differ](https://wheaton.il.us/1203/2024-International-Residential-Code-Amen). [Weyerhaeuser TJI guidance](https://www.weyerhaeuser.com/woodproducts/engineered-lumber/tji-joists/) says midspan blocking is not required for that product but bearing restraint is. These examples are not a substitute for the selected product and adopted jurisdiction. Record the source of any interval supplied to a builder.

Declare a supported panel-edge system: blocking, an applicable tongue-and-groove product, or another specified detail. Rectangular panel geometry alone proves neither T&G engagement nor edge support. Review the panel layout and stock cuts; area takeoff is not nesting.

## Wall stage

Use individual plates, studs and opening members. Resolve host framing before inserting opening builders. At corners and bearing-wall intersections, provide the selected top-plate lap/connection detail and offset in-line plate splices. For conventional double plates, [2024 IRC R602.3.2](https://codes.iccsafe.org/content/IRC2024P2/chapter-6-wall-construction) specifies overlapping corners/intersections and 24-inch minimum joint offsets; alternatives have their own conditions.

Finished interior corners need attachment support on both wall faces. Use a suitable stud/nailer corner, blocking or specified drywall clips; model the chosen arrangement and preserve insulation access where relevant. [PNNL corner details](https://basc.pnnl.gov/resource-guides/advanced-framing-insulated-corners) illustrate alternatives to simply adding studs.

## Roof stage

Keep the chosen form explicit. Use a supported builder or project-owned generator for that form; identify a missing capability instead of replacing a hip or gable with a flat roof. Distinguish structural ridge beams and their supports from ridge boards with the required tie system. A ridge board alone does not establish a stable roof.

For an open roof, seek useful overhead clearance and economical member lengths when selecting the tie arrangement. Distinguish each member's function: [American Wood Council guidance](https://awc.org/faq/what-is-the-difference-between-a-collar-tie-and-a-rafter-tie/) places collar ties in the upper third to resist separation near the ridge under uplift, and rafter ties in the lower third to resist outward gravity thrust. High collar ties do not replace required lower rafter ties. Ceiling joists can also serve as rafter ties only with suitable continuity and connections.

Where more clearance is needed, consider a supported structural ridge system or a specifically designed raised-rafter-tie arrangement, together with the applicable collar-tie/ridge-connection detail. Establish tie elevation, spacing, section, connection basis and clear height from the selected system before generating it. Compare total material quantities, including ridge supports and connections, before claiming savings. The current `gable_roof` ridge-board builder generates plate-level rafter ties; use a supported alternative or project-owned generator for raised ties, and keep unresolved structural evidence explicit. Moving those existing ties upward or relabeling them as collar ties is not a complete system change.

For sawn rafters with birdsmouths, derive seat and heel cuts from plate position, pitch and required bearing. Keep each cut rafter one physical part with its original stock blank. Check actual seat contact and the sourced notch/remaining-section limits. Engineered rafters/trusses follow their manufacturer's permitted cuts and connections.

Derive eaves, rakes, tails/lookouts, fascia, soffits and roof skins from shared roof planes and finish thicknesses. Choose open or closed overhangs, the rake support arrangement, fascia proportions and corner-return treatment for this design. The current `gable_roof` helper supplies one ladder-and-boxed-return construction detail; it is a configurable option. Use project-owned assemblies and named interface checks for another construction method.

When using that ladder detail, its single outer fly rafter and inner attachment rail meet the selected fascia, soffit and main framing. Check the connections, panel edges and peak closure. A triangular bird-box face follows from matching eave fascia depth to the plumb rafter tail plus rake-soffit overlap; deeper fascia produces a different closure. Return length and separate fascia grouping are project choices. An extended ridge needs a coordinated enclosure; a structural ridge beam also needs its support/connection design.

For a new gable shed or changes to these details, consult the installed `engine/examples/framed-shed/README.md` and `design.py` (checkout `examples/framed-shed/`). They show one complete API composition and identify the editable choices. Copy useful patterns into the user's project, then recheck the changed interfaces; select a different form when it better fits the request. See `docs/construction.md` for argument meanings and supported alternatives.

For asphalt roofing, use `asphalt_roof` when its standard-slope gable scope fits.
Read the installed construction documentation for required stock yields and
representation limits. Include deck, membrane/ice protection, eave/rake drip
edges, starters, field shingles and ridge closure; account for roofing dead load.
Check deck-to-rafter bearing, required panel edge support and finish substrate
contact before covering. Bevel fascia tops to the roof plane. Retrieve the
selected manufacturers' current slope, exposure, overlap, fastening and edge
instructions. Establish ventilation and condensation control with the end user
when designing a real building. For tool-development fixtures, record those
inputs as provisional rather than requesting a development user's site.
Exposed-coverage graphics do not model concealed laps or prove weather sealing;
keep those limits explicit. Count shingles by installed coverage and ridge/edge
accessories by length, including package yields and cutting/lap allowances.

## Enclosure and openings

Resolve corner trim before siding ends. For board-trim corners, model the vertical corner boards and the mating siding extents. Close unintended gaps while preserving product-specific movement, sealant and drainage joints; [manufacturer guidance](https://www.jameshardie.ca/product-support/resource-center/technical-documents/caulking-tips) may require a deliberate joint.

For sheet siding, compare edge widths before placing panels. Centered sheets often avoid slivers; an edge-aligned or offset layout may better suit openings, product joints or the desired appearance. Set `siding_layout` and `siding_offset` explicitly when that choice matters. Keep a connected sheet with its window/door notches as one physical part; split disconnected remnants. Coordinate gable joints with the wall below.

Carry exterior cladding through gable ends to the roof/soffit profile and cover any exposed floor rim included in the enclosure. For a boxed return with continuous corner trim, coordinate the trim’s scribed cuts, soffit clearances and backing. Choose another trim termination when the design calls for it. Use shared roof/trim dimensions; verify the newly cut panel edges rather than hiding overlaps. Consult `wall_enclosure(roof=...)` and `gable_roof(corner_trim_clearance=...)` in the installed construction documentation for the supported detail.

Keep rough-opening framing separate from door/window products. Model frames, leaf/sash/glazing, sills/thresholds, wall-depth interfaces and installation allowances. Check handedness and selected open states; one closed pose is not a motion check. Distinguish rough-opening size from usable clear opening. Count a purchased unit once even when represented by several solids.

## Stage review

Before covering each stage, inspect an isolated bearing/corner/edge and read its requirements. Missing framing, unsupported panel edges, untied plate junctions and unmodeled roof edges remain specific findings. Do not replace feasible detail with a broad “construction unverified” note. Final handoff identifies the completed geometry, sourced assumptions, and remaining structural/product/site evidence.
