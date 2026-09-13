# Framed buildings

Use this branch for houses, garages, workshops, additions, sheds, clubhouses and similar framed structures. Design physical construction assemblies and their load-path interfaces. Interior use informs clearances; decorating and furnishing need an explicit request.

Use `docs/cadquery.md` and the `stud.buildings` framing helpers for CadQuery projects. Compose specific buildings in project-owned Python. Verify helper signatures and documented scope before use; enclosure, roofing and overhang details outside that scope need project-owned geometry and evidence. The US framing helpers require an inch project.

## Decisions before geometry

Reuse the user's existing choices. Otherwise ask for wall stock and roof form together using the host's question tool. Offer gable, hip, shed or another requested style; a gable is a useful starting recommendation for a simple conventional clubhouse. Ask about pitch and overhang where they materially affect form. Confirm the site/support assumptions and whether interior walls will be finished. An unfinished interior does not need an invented drywall package.

Resolve ceiling intent before choosing roof ties. Reuse an explicit ceiling choice; otherwise infer from the intended use and state the assumption briefly. A basic unconditioned storage shed or a request to store tall objects usually suggests an open roof with no ceiling lining. A specified flat finished ceiling suggests ceiling framing and lining. “Clubhouse,” “workshop,” insulation, or finished walls alone can leave flat versus open/vaulted overhead space unclear; ask one focused question through the host's question tool when that distinction affects the design. Record the choice and any required clear height for large objects. A no-ceiling choice omits ceiling finishes and framing used solely to carry them; required roof ties still follow the selected roof system.

Build coherent support-to-covering assemblies within the user's requested scope. Use `model.expect` to preserve expected parts, requirements and connections independently of surviving outputs. Read `design_review` alongside native measurements; missing expected geometry invalidates verification, while unresolved sizing and fastening remain separate. Internal construction order can execute in one request; honor a user-requested stopping point when present.

## Site inputs for a construction project

When location affects foundation, loading or enclosure decisions, first check the project's saved specification and conversation for a region. If it is missing, ask for a state, province or region, plus country when unclear. Accept that answer as sufficient location intake; do not follow up for a specific city, town or address. Reuse a more precise location if the user volunteers one. A cosmetic edit or a location-independent assembly check does not require a new site interview.

Use the supplied region to research criteria from regional authorities and other primary sources. Record the geographic scope, source/date and relevant snow, wind, seismic, frost and climate inputs in the project specification. Where criteria vary within the region, record the variation and leave site-dependent selections provisional instead of inventing a municipality or requesting a more precise location. Distinguish ground snow from the roof snow load required by a selected table. Treat soil bearing and site exposure as separate evidence; location alone does not establish them. Identify unresolved jurisdiction and site evidence alongside the design.

Ask the end user for consequential preferences such as roof covering, conditioned use and ceiling intent when they are absent. Research suitable lumber/product options rather than expecting the user to supply engineering values. Carry the resulting inputs into the applicable sizing tables, support details and enclosure decisions, and preserve their sources with the design. Reuse saved answers; a changed site or specification requires reviewing affected selections and interfaces.

The intake is complete when each site-dependent decision has a sourced input or a specific unresolved item. Continue independent geometry while awaiting required answers, and keep dependent selections provisional. When developing Stud, exercise this workflow with labeled fixture scenarios and missing-input cases; a developer's personal building location is not a prerequisite for implementing the capability.

## Member sizing from span tables

Select load-bearing lumber from an applicable published span/load table or manufacturer design tool before treating its size as resolved. Use the smallest available listed section that satisfies the actual span, spacing, loads, deflection and construction-detail constraints; record the reason for a larger choice. Size floor joists, rafters, ceiling joists, headers and beams for their own member function and load path. Reusing floor stock for rafters does not establish the roof size.

Establish site/jurisdiction load criteria, roof covering and ceiling loads, species, grade, moisture/service condition, support geometry and spacing. Reuse sourced project inputs; ask focused questions for missing inputs that prevent choosing the applicable table. Ground snow and adjusted roof snow are distinct inputs. Calculate the span using the table's measurement convention: rafter tables commonly use the horizontal clear distance between bearing faces, excluding the overhang, rather than building length or sloping cut length.

Record source URL, publisher/edition, table and row, design inputs, allowable span and actual span with the selected stock. Check the table's bracing, bearing, load pattern and system assumptions. Select another sourced table or designed system when outside its scope; a guessed large member remains provisional. Preserve that sizing evidence in the project independently of the geometry helpers.

Recheck sizing when span, spacing, loads, ceiling intent, tie elevation, species or grade changes. Regenerate seats, remaining sections, ridge/fascia depths, gable notches and stock cuts after a size change. Span-table adequacy covers only its stated checks; bearing, birdsmouths, cantilevers, connections, uplift and raised ties need their corresponding details. Before moving on, every load-bearing member family has either a recorded sizing basis or an explicit unresolved input; geometric fit alone is not a sizing result.

## Foundation stage

For foundation selection, ground slabs, below-grade walls, piers/piles or frost
protection, read [Foundations by composition](foundations.md). Compose supports,
layers and building connections from shared datums; keep the garage floor's
support distinct from the foundation carrying its walls. Complete the requested
foundation geometry, quantities and interface checks before covering it with
floor or wall assemblies.

## Floor stage

Plan support lines, beams, joist direction and subfloor together. Prefer the shorter unsupported joist span when supports permit; an interior beam may change the best direction. Record any alternative's reason. Check bearing and lateral restraint before covering the frame.

Distinguish four blocking purposes: joist end restraint, intermediate lateral restraint/bridging, bearing/load transfer, and panel-edge backing. Select required locations using the actual joist system, panel edge detail and adopted rules. Do not infer a universal midspan interval from the word “blocking.”

The accessible [2018 IRC R502.7.1](https://codes.iccsafe.org/content/IRC2018P7/chapter-5-floors) applies its 8-foot intermediate-restraint interval to joists exceeding nominal 2×12. [Local amendments can differ](https://wheaton.il.us/1203/2024-International-Residential-Code-Amen). [Weyerhaeuser TJI guidance](https://www.weyerhaeuser.com/woodproducts/engineered-lumber/tji-joists/) says midspan blocking is not required for that product but bearing restraint is. These examples are not a substitute for the selected product and adopted jurisdiction. Record the source of any interval supplied to a builder.

Declare a supported panel-edge system: blocking, an applicable tongue-and-groove product, or another specified detail. Rectangular panel geometry alone proves neither T&G engagement nor edge support. Review the panel layout and stock cuts; area takeoff is not nesting.

## Wall stage

Use individual plates, studs and opening members. Resolve host framing before inserting opening builders. At corners and bearing-wall intersections, provide the selected top-plate lap/connection detail and offset in-line plate splices. For conventional double plates, [2024 IRC R602.3.2](https://codes.iccsafe.org/content/IRC2024P2/chapter-6-wall-construction) specifies overlapping corners/intersections and 24-inch minimum joint offsets; alternatives have their own conditions.

Finished interior corners need attachment support on both wall faces. Use a suitable stud/nailer corner, blocking or specified drywall clips; model the chosen arrangement and preserve insulation access where relevant. [PNNL corner details](https://basc.pnnl.gov/resource-guides/advanced-framing-insulated-corners) illustrate alternatives to simply adding studs.

## Roof stage

For roof selection, framing, pitch, ties, overhangs or roof finishes, read [Roof types and detailing](roof-types.md). Use its common roof specification and the selected form's section, then the applicable framing and finish details. Keep the member-sizing and site evidence above with that specification.

## Enclosure and openings

Treat exterior trim as part of the exterior finish stage. Inventory every exterior corner and door/window opening, then model the chosen corner boards, door side/head casing, and window side/head/sill or apron trim. Reuse the selected material, color and proportions; use a compatible trim detail for every present opening. Record an explicit design choice where an opening uses an integrated product finish. Derive trim and siding extents from shared opening and wall definitions, retaining installation clearances, usable openings, door/window operation, and product-specific movement and drainage joints.

Resolve corner trim before siding ends. Model the paired board joint and siding termination, or the selected applied-over-siding detail, with continuous backing and deliberate top/bottom terminations. Coordinate opening trim with head flashing, sill/threshold drainage and the weather barrier. Record stock sections, cuts, quantities, finish and fastening/product evidence for each trim family. Before completing exterior finishing, inspect all corners and opening perimeters for missing pieces, overlaps, exposed edges and obstructed clearances; add named checks for the affected interfaces. Product-specific joint requirements remain explicit; [manufacturer guidance](https://www.jameshardie.ca/product-support/resource-center/technical-documents/caulking-tips) may require a deliberate joint.

For sheet siding, compare edge widths before placing panels. Centered sheets often avoid slivers; an edge-aligned or offset layout may better suit openings, product joints or the desired appearance. Record the selected panel alignment and first-joint offset explicitly. Keep a connected sheet with its window/door notches as one physical part; split disconnected remnants. Coordinate gable joints with the wall below.

Carry exterior cladding through gable ends to the roof/soffit profile and cover any exposed floor rim included in the enclosure. For a boxed return with continuous corner trim, coordinate the trim’s scribed cuts, soffit clearances and backing. Choose another trim termination when the design calls for it. Use shared roof/trim dimensions; verify the newly cut panel edges rather than hiding overlaps.

Keep rough-opening framing separate from door/window products. Model frames, leaf/sash/glazing, sills/thresholds, wall-depth interfaces and installation allowances. Check handedness and selected open states; one closed pose is not a motion check. Distinguish rough-opening size from usable clear opening. Count a purchased unit once even when represented by several solids.

## Stage review

Before covering each stage, inspect an isolated bearing/corner/edge and read its requirements. Missing framing, unsupported panel edges, untied plate junctions and unmodeled roof edges remain specific findings. Do not replace feasible detail with a broad “construction unverified” note. Final handoff identifies the completed geometry, sourced assumptions, and remaining structural/product/site evidence.
