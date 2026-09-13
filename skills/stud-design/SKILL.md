---
name: stud-design
description: Create, revise, check, and realistically visualize physical designs in stud using CadQuery, versioned requests, material purchases, and drawing packets. Use for furniture and construction projects, viewer navigation and guided presentations, estimates, saved versions, and plan delivery.
---

# Stud design

Use the installed Stud app for physical design projects. Keep the installation separate from the user's project. For development of Stud itself, implement reusable behavior and exercise it with labeled fixtures; missing site or product choices do not block tool development.

## Establish the project and its format

Locate `stud`, verify `stud --version` and `stud doctor`, and identify the target folder. Use `stud projects --json` when the location is unknown. Read [Stud integration](references/stud-integration.md) for the request commands and installed documentation.

A project requires `stud.json` with `engine: cadquery` and ordinary Python exporting `model = Model(...)`. Verify the manifest before serving or evaluating. A folder without it is an incomplete or unsupported project, not an invitation to select another authoring API. Recover initialization or use the valid project folder before continuing; keep its declared units fixed.

Read the existing source, saved assumptions, current status and prompts before revising it. Keep stable object IDs and deliberate local exceptions. Execute designs only from trusted sources.

## Open the viewer and begin the request

For a new design, initialize its project and open `stud serve` before writing geometry. For an existing design, reuse its viewer. With the Codex browser, use `--no-open` and open the printed URL in a visible tab. Keep that viewer available throughout the work.

For every design-changing request:

1. Inspect `stud status`. Read the active option ID and head; reuse an existing active request only when it belongs to this work.
2. Call `stud begin` with the expected head, intent, and a stable client key. Edit only the returned isolated workspace.
3. Complete a coherent set of Python edits across the needed files, then capture `source` and call `evaluate --source SOURCE_ID --wait`. Saving files does not start a build. Inspect that result before correcting the source or delivering the design; evaluate again after corrections. Builds still stream completed geometry to the viewer.
4. After the requested revision is ready, capture the final source ID and call `stud finish` with that ID, a summary, and any addressed prompt IDs. Wait for the job and report its checkpoint and outcome. Reuse the same request/key on retries.

`finish` requires a completed evaluation of the current source; if it reports `evaluation_required`, evaluate that source and inspect the result before retrying. A checkpoint may honestly record failed checks or generation. Cancellation retains the unfinished workspace; it does not discard source. Late writes belong to the canceled workspace and must not be copied over another option.

Let the existing addition animation and camera tracking present coherent stages. User camera interaction takes precedence. Reserve deliberate camera control for review after a build stage. Native CLI `show` takes the displayed build ID; browser WebMCP uses `expected_revision` from `viewer_context`. A waiting native focus job needs a real viewer acknowledgement before claiming the camera moved.

## Author the design and its evidence

Use ordinary CadQuery operations, then register completed shapes with `stud.cad.Model`. Read `stud.json` before authoring: native units are **inches (`in`) or millimeters (`mm`)**, with X/Y horizontal and Z up. Keep the project units fixed. In an inch project, model a 1½-inch board as `1.5` and an actual 2×4 section as `[1.5, 3.5]`; all stock, cuts, holes and offsets use those units. New projects default to inches; select `--units mm` at creation for metric work. Assembly locations are rigid local placements. Keep meaningful persistent IDs across parameter edits; shape hashes and face indices are not semantic identities.

Read the installed `docs/cadquery.md` before first use of registration, native requirements, estimating demands, or drawings. Use `stud.buildings` framing helpers, `stud.construction` stock-frame operations and `stud.stock` plane/member/panel cuts and grouped registration when their documented scope fits. Use `stud.roof_geometry` to project XY roof footprints into the generic panel frame. Specific models belong in project-owned Python: `stud init --example NAME` copies the example and its helpers into the project. Edit those copied files or compose focused functions from the shared operations; roof-form recipes and structural/finish choices belong to the design. CadQuery is the geometry language; Stud does not require every operation to use a custom primitive.

Keep one specification for outside/finished dimensions, actual stock, clear openings, datums, and accepted choices. Derive mating surfaces, dependent members and expected measurements from that specification; display bounds may include kernel padding and are unsuitable for exact bearing-area thresholds. Model each physical part once, including notches and bores. Record its original stock frame, blank size, operations, and material demand separately from its finished shape.

For floor framing, anchored sills or separate decking, read installed `docs/floor-systems.md`. Prefer `stud.framing` and `stud.floors` operations with compact project-owned inputs; move an opening or change stock by editing its owning specification and re-executing Python. Use `PanelSpec` and `deck_floor` for subfloor panels; use `FloorSurface` and `DeckRegion` for irregular outlines and rotated regions. T&G joints use native edge-system evidence; do not add blanket backing to satisfy a square-edge check. Keep nominal layout modules separate from actual stock dimensions and installation allowances. Drawings are optional evidence. Compose and check as much of the building as the user requested; internal construction order does not require pauses for approval.

For a new building or a change affecting site, member sizing, foundations, roof form, enclosure, exterior finishes or ties, read [Framed buildings](references/framed-buildings.md). Apply its intake to the requested construction scope and preserve existing answers. For foundations, ground slabs, piers/piles or frost protection, read [Foundations by composition](references/foundations.md). For roof work, also read [Roof types and detailing](references/roof-types.md) for the chosen form and its completion criteria. Examples are fabrication studies; their native geometry checks do not supply site loads or structural approval.

Build support assemblies before covering them. Use `model.batch()` for coherent groups and explicit `replace=True` for a replacement. Regenerate named references after replacement; unresolved references must remain visible. Use one opening definition for displaced framing and sheet cuts. Preserve deliberate per-instance exceptions in the owning parameters.

Before repeating a new or uncertain joint, author and check one representative instance with its mating parts, covering clearance, edge backing and original stock. Inspect its native findings and fabrication evidence, correct the shared definition, then repeat it. Reuse established details where applicable; this is a focused probe of an uncertain interface, not an extra gate for every part.

Declare measurable intent: lengths, clearance, collisions, stock fit, bearing direction and area, and continuous support behind actual panel edges. When adding a requirement kind, consult the target/units table and runnable bearing example in installed `docs/cadquery.md`. A contact is not a fastening specification. Declare connections, hardware, and unresolved evidence. A pass count alone does not establish complete coverage.

Record actual stock lengths/kerf and explicit sheet layouts. Give every physical part a purchasing basis; distinguish purchased packs from installed quantities. Preserve quote supplier, source, date, currency and purchase unit. Missing prices remain missing. Price-only changes use the records interface and do not rebuild geometry.

## Review, compare and deliver

For realistic images or finished-appearance requests, read [HD rendering](references/hd-rendering.md). Combined requests such as “Show me how this would look with cedar siding” require a design material change through the request workflow, followed by an untextured reference capture and actual image generation in the conversation. A visualization-only request uses the displayed design and leaves the editing target unchanged.

For viewer navigation, part inspection, cost questions, saved-version review, plan delivery, or a guided presentation, read [WebMCP viewer control](references/stud-integration.md#webmcp-viewer-control). Discover the tools in the existing viewer tab and use their current schemas. Start from `viewer_context` to resolve the displayed revision and exact part IDs. Use individual controls for immediate requests and `sequence` for a prepared walkthrough; let the user start playback when ready. User navigation or camera takeover interrupts the presentation.

Inspect affected geometry and native findings in the same build. Partial current geometry and a previous complete model have different identities; do not claim a previous result proves the current edit. Match measurements and review prompts to source/build/checkpoint context. Retain original captures and unresolved/deleted targets; resolve a prompt only after addressing its request.

Start with a compact result summary: source/build identity, job status, check counts and coverage, fabrication findings, and artifact paths. Inspect specific non-passing requirements and affected parts next, paging large lists until the relevant findings are accounted for. Use documented fields and explicit field selection when reading JSON; retrieve full projections or inventories only when needed for the current review. Keep unresolved evidence visible in the final summary.

Use Versions to inspect original saved estimates, compare geometry under historical or common prices, create alternatives, and restore an older design as a new request. Inspection and comparison do not retarget the active editing workspace. Finish or cancel an active writer before activating another option.

Generate plans for an explicit checkpoint. Check dimensions, stock frames/cuts, sheet arrangements, step prerequisites and part/connection references together. For deliverable PDFs, render and inspect every page for clipping, scale, legibility and usable details. A revision creates another immutable packet; retain the old one.

Close the scope when the final request has a classified outcome and checkpoint, the viewer identifies that revision, and the required quantities, findings and deliverables agree. Report specific unresolved construction or pricing evidence alongside what was verified. Keep a concept's remaining work distinguishable from a packet ready for fabrication.
