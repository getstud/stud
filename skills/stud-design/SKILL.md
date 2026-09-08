---
name: stud-design
description: Create, revise, and check physical designs in Stud, the Python-based 3D workshop. Use for furniture, storage, workbenches, enclosures, and structures modeled as named parts with material takeoffs. Covers assembly generation, geometric validation, and viewer review.
---

# Stud design

Use the installed Stud app to create and revise design projects. Keep edits in the project’s design files and annotations; changes to Stud itself belong to a separate software-development task. Build parametric assemblies whose geometry, connection requirements, and material quantities come from the same dimensions. Use this workflow for the scope requested: a finish edit needs a targeted rebuild and review; a new design needs its interfaces established before detailed geometry.

## Establish the working context

Locate the installed `stud` command and the target design project. Verify the installation with `stud --version` and `stud --help`. A project has `design.py` exporting `project`; the installation supplies the CLI, model API, viewer, and validation engine. If Stud is unavailable, identify the missing dependency instead of constructing a substitute viewer.

For project setup, commands, modeling documentation, or unfamiliar validation behavior, read [Stud integration](references/stud-integration.md). Consult the installed modeling documentation as needed; a Stud source checkout is not required.

For an existing project, inspect its generators, assumptions, comments, validation report, and model revision before editing. Preserve unrelated model choices, stable IDs, annotations, and quotes. Treat executable designs as trusted local code only when their source is established.

## Open the viewer before building

For a new design, initialize its project, start `stud serve`, and confirm the viewer is open before writing the design geometry. For an existing design, open or reuse its viewer before making changes. When using Codex's in-app browser, start the server with `--no-open` and open its printed URL in a visible browser tab. Keep that tab and server running throughout the work.

Build the design in coherent assembly stages, saving a valid model and checking that the viewer receives each revision before adding the next stage. The viewer animates new parts in model order after each successful rebuild. Add supports and framing before panels and finishes so the user can watch the design develop. Preserve stable part IDs across revisions; failed builds retain the last good preview. Keep validation requirements accurate at every stage and label incomplete relationships as provisional.

## Turn intent into parameters and interfaces

Keep a single authoritative specification in the project: requested dimensions, datum definitions, material sizes, openings, finishes, and provisional choices. State whether a dimension is outside framing, finished size, clear space, nominal stock, or actual stock. Normalize geometric calculations to inches; world X/Y/Z means width/depth/elevation.

Carry forward accepted decisions. Use stated assumptions for reversible aesthetic or layout choices; request missing information when it materially determines fit, function, or required design evidence. Ask only for information relevant to the current scope.

For walls in a framed structure, ask whether the walls will use 2×4 or 2×6 lumber before generating wall geometry unless the user or existing project already specifies the framing. Carry that choice into wall depth, openings, and material quantities. Honor an explicitly chosen alternative wall system.

Define dependent surfaces before placing parts. Examples:

- Cabinet: outside envelope → carcass thickness → clear opening → drawer/door allowance.
- Workbench: finished height → top thickness → support height → foot adjustment.
- Framed structure: foundation → floor datum → wall top → roof plane → edge/soffit finish.

Give every shared surface one calculation. Derive mating members from that surface rather than copying coordinates. Finish thickness and clearances participate in the same calculations; make the measurement reference explicit when finishes change the outside size.

**Ready to generate:** the requested form and its critical mating surfaces are defined, with material unknowns labeled rather than silently fixed.

## Generate assemblies with their requirements

Build in dependency order for the object: supports and primary frame, openings and moving parts, secondary supports, panels, then finishes and hardware. A shell preview is appropriate for exploring proportions; label its thicknesses and quantities as provisional until detailed.

Model wood-framed walls as individual studs, plates, and opening framing, with sheathing and finishes as separate parts. A single solid wall is only a provisional envelope for an explicitly requested massing or shell preview; replace it with individual framing members when developing the wall design.

Use documented Stud assembly helpers where they fit the design. `WallFrame` and `framed_opening`, when available, handle wall transforms and generate opening requirements. For recurring assemblies specific to this design, keep helper functions in the project and give their parts stable IDs and explicit requirements.

Use semantic IDs such as `cabinet.left.side` or `bench.top.panel.01`; preserve them when the same physical part changes. Orient repeated assemblies in local coordinates, then transform consistently into world coordinates. Stud boxes rotate about their centers.

Register real stock cross-sections and available lengths. Keep a notched or tapered member as one physical part with its original blank dimensions and cut length. Choose only geometry supported by both the renderer and validator; report unsupported geometry explicitly. When the installed app cannot represent a needed shape, report the limitation and any approximation used in the design.

Generate openings once and share their volumes with framing, panels, trim, and hardware. Resolve host framing before adding an opening builder, and include subsequently created host finishes in its clearance scope. Exclude intentional occupants, such as a door leaf, from that scope; check their fit separately.

## Add environment context

For trees, terrain, or decorative objects outside the construction design, read the installed `engine/docs/environment.md` (or checkout `docs/environment.md`). Use `project.context_asset` with a project-local Three.js factory under `assets/`. Keep requested dimensions in its parameters and use inches with Z up. Environment assets are visual context; declare any necessary construction clearance separately. Verify the asset loads in the viewer's Environment section and inspect its placement with Fit scene.

## Validate relationships while building

Enable the installed version's automatic solid-collision and stock-fit checks for new designs. When revising a legacy project, inspect its coverage before opting in; expose newly discovered gaps without discarding existing rules.

Each assembly declares the relationships its function requires:

| Requirement | Check to use when supported |
|---|---|
| Interference between actual solids | `solid_collision` |
| Mating faces with measurable support/contact | `minimum_contact` |
| Faces at a shared elevation or offset | `face_alignment` |
| Usable opening volume | `opening_clearance` |
| Panel edges supported by members | `panel_support` |
| Obtainable lumber or sheet blanks | `stock_fit` |

Derive geometric thresholds from the intended interface. Alignment does not establish contact, and contact does not establish fastening or strength. Review coverage by relevant category; a part checked for stock can still have no support check. For moving parts, evaluate necessary clearance states rather than treating one closed pose as a motion check.

Keep intentional joint exceptions specific to a part pair with a reason. A known incomplete draft requirement remains visible as a warning with its reason; unavailable evidence remains unverified. Never weaken a check merely to obtain a successful build.

**Ready to cover an assembly:** critical relationships pass, or the requested concept explicitly identifies what is provisional. Surfaces and finishes must not conceal unresolved geometry from the review.

## Keep the revision loop short

Edit the project’s owning parameter or assembly helper → build → read findings → correct the cause → inspect the affected assembly in the viewer.

Batch related part changes into one coherent edit. Use numerical validation for dimensions, clearances, and support; use the browser for form, orientation, accessibility of parts, and visual interpretation of connections. Reuse one running viewer. Inspect isolated critical joints before reviewing the complete exterior. Match the displayed revision to the successful build: a failed edit can leave the last good preview visible.

Use the viewer’s WebMCP `show` site tool when available to present the design and focus review on changed parts or critical joints. Open the project’s viewer in the connected browser, discover its site tools, and follow [WebMCP viewer review](references/stud-integration.md#webmcp-viewer-review) for targeting and revision checks. If the browser does not expose WebMCP, use the viewer controls.

Make corrections in the project’s owning parameters and assembly helpers so a clean build directly produces the intended model. If an app or viewer limitation blocks review, describe the limitation and the affected design evidence.

For a small edit, run checks affected by its dependencies plus existing automatic checks. Broaden investigation when a failure or an interface change warrants it. For an audit, review requirement coverage and omissions as well as failures; a pass count alone cannot establish completeness.

## Close the requested scope

Confirm the final revision builds, affected interfaces have meaningful checks, and the viewer shows that revision. Preserve warning and unverified findings in the handoff.

Before presenting quantities for purchasing, examine lumber blanks/kerf, sheet fit and layout, finish coverage and waste, hardware allowances, and unpriced items. Stud's sheet area estimates do not establish a cutting layout; a zero unpriced subtotal is not an estimate. Keep a physical part's purchase quantity separate from its decorative representation.

Report what changed, what was verified, and the material unresolved choices. Distinguish concept, checked geometry, and fabrication/construction readiness. Geometry checks do not certify loads, material capacity, connections, or compliance; obtain applicable evidence when that is within the task's scope. Supply a detailed review artifact only when the scope or findings justify one.
