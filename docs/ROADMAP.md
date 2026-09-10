# stud roadmap

September 9, 2026

**stud turns a conversation into a physical design people can inspect, revise, price, and build from printable plans.** The user describes the project and requests changes. The agent writes Python using CadQuery. stud runs the design, shows it taking shape, supports feedback and comparison, and produces consistent drawings, quantities, and estimates.

stud has no product-imposed size ceiling: a workbench, a shed, and a mansion all belong in its scope. Small examples prove individual capabilities; representative buildings prove that those capabilities work together at scale.

The foundation should be the smallest implementation that supports this workflow. Reuse established geometry and version-control tools. Add abstractions when a demonstrated requirement needs them. Product behavior determines the architecture; existing internal APIs and data structures do not have to survive unchanged.

**Settled product requirements**

| Area | Required behavior |
| --- | --- |
| Authoring | The agent writes and edits CadQuery designs in ordinary Python project files. Users request design changes through conversation. A parameter editor or direct geometry editor is not required now. |
| Live review | Show real geometry as it becomes available, without requiring a separate prompt for each layer. Keep the viewer inspectable while work continues. Preserve the established addition animation and use motion where it helps explain changes. |
| Inspection | Support perspective and orthographic views, dimensions, part inspection and search, assembly isolation, transparency, and exploded views. The agent can focus attention on a part or region. |
| Errors | Display usable new geometry with its errors highlighted. Retain the last valid version for comparison. Clearly distinguish incomplete work, failed generation, and completed geometry with failed checks. |
| Validation | Check geometric fit and intended relationships against the resulting shapes. Make the evidence, coverage, failures, and unchecked requirements inspectable. |
| Feedback | Comments are prompts attached to a part or captured region of a particular design version, analogous to code-review comments. Preserve their original context and link the changes that address them. |
| History | Automatically checkpoint each completed design-changing request. A checkpoint is a Git commit; a named design option is a branch. Users can compare versions, restore a design, or explore an alternative without losing later work. |
| Materials and costs | Produce material quantities and estimates; accept supplier quotes, quantity overrides, and spreadsheet pricing. Comparing estimates between design versions is essential. Preserve pricing inputs and historical estimates in Git. |
| Printable plans | Produce dimensioned drawings, labeled parts, material and cut lists, and assembly views in a PDF usable on a home printer. Step-by-step assembly instructions are the target for the standard packet. |
| Ownership and installation | Projects remain local, portable folders separate from the app. Package the runtime for macOS and Windows so users do not need to install Python or Node. Preserve project discovery, setup, and updates. |
| Host | Support the conversation and browser-review workflow in ChatGPT for desktop. A future standalone app should be able to use the same project and modeling capabilities. |

Exports are a priority. Imports, editable round trips through other design applications, and automated structural analysis are deferred until user demand warrants them.

**Foundation**

**Python is the authored design; CadQuery provides solid geometry.** Use ordinary functions and modules for reusable construction logic. stud adds the information required to inspect and explain a design: meaningful part and assembly identities, placements, materials, stock requirements, intended relationships, dimensions, and assembly steps. Introduce these fields as the working examples require them. Do not create a second general modeling language or a configurable geometry-backend framework.

An assembly organizes its parts. Reusing a function or component definition should support both a shared change and an intentional instance-specific detail. An agent must be able to trace selected geometry to the source that created it. Store intentional exceptions in source so regeneration preserves them or reports when their supporting assumptions no longer hold.

**One evaluated design version supplies every result.** Viewer meshes, measurements, geometry checks, drawing views, quantities, and exports derive from the same CadQuery shapes and associated design data. The viewer does not independently reconstruct cuts or rotations. Use explicit units and composable local placements, with one documented numerical tolerance policy. Display precision and required construction clearances are separate concerns.

Keep persistent object identity separate from display labels, list positions, geometry hashes, and version IDs. A resized opening can remain the same opening; a deleted member must not silently pass its comments to a new member occupying its old list position. Use named geometric references where relationships need to survive an edit. Ambiguous or invalid references require attention.

**Keep project data straightforward.** Version the Python source, project settings, supplier quotes, estimating inputs, and compact estimate snapshots in Git. Preserve comments, their captured context, and resolution history with the project. Record the runtime and generator versions needed to explain a result. Generated geometry and display caches should be rebuildable; an estimate snapshot deliberately preserves the amount actually reported at that checkpoint.

Begin with correct full evaluation. Stream outputs when runnable Python produces them. Add caching and incremental computation only where measurements justify them and their dependencies are understood. Saving a file is not the same event as completing a user request.

**Validation follows requirements independently of generation.** Define what a check measures, the shapes and relationships it covers, its tolerances, and the evidence it returns. Establish checks for collisions, stock fit, and specified contact, support, clearance, and alignment relationships against the actual geometry. A successful generator call does not establish correct fit, quantities, or assembly. Use independent expected dimensions and deliberately faulty designs to test the checks. Present what passed, what failed, and what could not be checked, without inheriting a fixed validation vocabulary or coverage model from an earlier implementation.

**Delivery sequence**

| Milestone | User-visible result | Completion evidence |
| --- | --- | --- |
| 1. Prove the project foundation | An agent-authored component becomes inspectable geometry, a material list, and a dimensioned printable sheet. | Independent geometry and quantity checks, repeatable rebuilds, persistent identity, and a packaged-runtime trial. |
| 2. Complete live conversation and review | Users watch changes, inspect failures, and attach prompts that survive revisions. | Successful, invalid, partial, and superseded builds behave consistently. |
| 3. Deliver history, alternatives, and cost comparison | Users revisit and compare designs and understand changes in their estimates. | Commits, branches, restoration, comment history, and both pricing comparison modes work together. |
| 4. Deliver a useful DIY plan packet | A complete project produces readable drawings, cut lists, and assembly guidance. | A DIY reader can follow a verified packet, and revisions update every affected output. |
| 5. Prove building-scale use and release readiness | The same workflow supports a representative mansion and ordinary desktop installation. | Measured performance, correct large-model changes, coherent plan sets, and native installation/update checks. |

Work on drawings and packaging starts in milestone 1. Scale measurements begin there too; milestone 5 establishes their performance across the complete workflow.

**1. Prove the project foundation.**

Build one thin path from Python source to inspectable output. Exercise a workbench component, a rotated wall with an opening, and a roof joint with a sloped cut. Include a bore, nearly coincident geometry, and an invalid operation. These cases should expose failures in placements, geometry queries, identity, and diagnostics before a large component catalog depends on them.

Use CadQuery directly through the small amount of integration stud needs. Measure geometry generation, display generation, startup, memory, and packaging on the chosen examples. Verify that the runtime can be distributed on the supported desktop platforms early; do not postpone discovering a deployment problem until the product is complete.

Demonstrate an agent changing a dimension, a shared definition, and one intentional local exception. For example, a special rafter notch must either regenerate correctly after a pitch change or identify why it needs revision. Test member insertion, removal, changed repetition counts, and replacement. Confirm that selections and source references remain meaningful.

Produce a basic dimensioned PDF sheet and a material list from the same evaluated design. This tests drawing projection, dimension references, part labeling, and print legibility while the geometry integration is still small. Establish the minimum saved estimate and revision information needed by later comparisons.

**Completion gate:** independently specified dimensions, cuts, placements, and quantities agree with the outputs. A saved project rebuilds with its recorded inputs. Invalid operations produce useful diagnostics. The printable sheet agrees with the 3D model. Record the small set of implementation decisions and measured baselines; do not reopen the settled authoring workflow.

**2. Complete live conversation and review.**

Make a wall with an opening and a surface layer the first complete editing scenario. The reusable construction logic owns the framing displaced by the opening and the corresponding surface cut. Add a second instance so shared-definition changes and instance-only changes are distinguishable.

The user asks for a wider opening. As runnable revisions execute, stud shows available named, placed geometry and applies subsequent changes to the viewer. Preserve the existing addition animation. Use movement and other transitions when they make a change understandable, while preserving the user's inspection context.

Live progress reflects actual execution. Geometry cannot appear before the agent has saved runnable code, and a generator that returns everything at the end offers no intermediate geometry. Arrange normal component generation to expose useful completed outputs where practical; users should not have to prompt the agent separately for each stage.

Associate every build and partial result with its source version. Mark partial previews as incomplete, and never mix them silently with older geometry or quantities. A usable design with failed checks remains inspectable with highlighted findings. If execution fails before usable new geometry exists, retain a clearly labeled earlier model and show the failure. Keep the last valid design available for comparison. Superseded work cannot overwrite a newer result.

Implement part comments and frozen area captures as anchored prompts. Preserve the prompt, target or captured region, screenshot when applicable, and original design version. Resolve and reopen without erasing history. Link an addressed prompt to its resulting checkpoint. If a target disappears or becomes ambiguous, show its original context rather than attaching it to another part. Viewing or restoring history does not resubmit addressed prompts.

Preserve the explicit feedback handoff in the current host: users can ask the agent to read their saved comments. Let the agent focus the viewer on a part or region with a version check. Showing a design does not record user approval. A future host may provide richer selection context without changing the design model.

**Completion gate:** exercise successful edits, failed geometry checks, generation failures, partial previews, and rapidly superseded requests. Independent checks catch wrong clearances, missing required contact, and omitted check coverage. Selection, comments, findings, material changes, and the displayed version agree. Complete requests can create named checkpoints; intermediate saves remain grouped under their request.

**3. Deliver history, design options, and cost comparison.**

Make project history understandable without requiring Git knowledge. Each completed design-changing request produces one automatic commit with a plain-language description of its intent. A checkpoint may contain unresolved findings; saving work is not approval. Preserve enough result information to inspect the checkpoint and associate its diagnostics and preview with the correct source.

Named alternatives use branches. Users can compare any two checkpoints without changing the agent's active option or starting version. Provide coordinated views that make geometry differences visible, alongside material and estimate differences. An editing request has an explicit target option and starting checkpoint so browsing history cannot redirect active work accidentally.

Restoring an older design creates a new commit that brings back that design and its design-specific estimating inputs while preserving later history, review prompts, and the chosen current pricing basis. Starting an alternative from an older checkpoint creates a branch. Choosing an option makes it the continuation point and preserves the other options. Combining ideas requires the agent to edit the design and rebuild it; a clean text merge alone does not establish a coherent physical result.

Version three kinds of cost information in simple project files:

- Supplier quotes: product and specification, purchase unit, price, currency, supplier, source evidence, and quote date.
- Design-specific estimating inputs: selected products and quotes, quantity overrides, allowances, and other assumptions.
- Estimate snapshots: the line-item quantities, applied prices, totals, and calculation version reported at each checkpoint.

Keep supplier unit prices separate from design quantity overrides. Preserve direct quote editing and spreadsheet paste, with manual quotes taking precedence over sourced quotes and estimates. Show where prices came from and when they were recorded.

Offer two explicit comparison modes. Price both designs with the same selected saved quotes to explain the effect of design changes. Compare their original recorded estimates to show historical totals. In both cases, explain line-item changes in materials, quantities, and prices. By default, revisiting an old design recalculates what it would cost using the latest saved quotes while retaining its original estimate. The active branch's files alone must not silently determine what “current prices” means.

Use one checkpoint per completed pricing update or spreadsheet import as the working default. Group related edits automatically; refine the grouping through interface testing rather than introducing a separate pricing-history system. A later estimator must not rewrite an earlier checkpoint's recorded total.

**Completion gate:** compare, branch, restore, and resume while retaining the correct agent target and comment anchors. Independently verify quantity changes and both estimate comparison modes, including changes to prices without geometry changes. Reload the project and reproduce the historical figures and their explanation.

**4. Deliver a useful DIY plan packet.**

Complete a workbench and a shed through reusable definitions, with explicit connections and intentional custom details. Use them to prove the whole path from a prompt to a packet a DIY user can follow. Expand floors, walls, openings, roofs, and panel detailing as these projects require; construction methods belong in reusable Python definitions rather than a universal building ontology.

Generate the standard packet from one saved design version:

- Dimensioned plans, elevations, sections, and enlarged details appropriate to the project.
- Part labels that agree across drawings, the viewer, material lists, and instructions.
- Material and cut lists identifying stock, finished sizes, relevant cuts, and required quantities.
- Assembly and exploded views explaining connections and orientation.
- Step-by-step assembly instructions as the intended standard, with the relevant parts, dimensions, and connections shown at each step.

Treat assembly sequence as authored project information that the agent can revise. Geometric fit alone does not establish a sensible assembly order. Steps reference actual model parts and details; a design change must update or flag affected instructions. Start with the demonstrated projects and test the result with DIY readers before generalizing automatic sequencing.

Make printable PDFs readable on ordinary home printers. Use clear units, labeled drawing scale, legible linework and dimensions, sensible sheet breaks, and enlarged details where needed. Include the design version so people can identify the packet they are using. Check the actual printed pages, not just the screen preview.

Distinguish modeled finished parts, stock blanks, sheet panels, purchased items, and material allowances. A continuous surface is not automatically a panel layout. A stock estimate is not automatically a cutting plan. Add panel subdivision, joints, supported edges, opening cuts, and cutting loss where the packet depends on them. State missing dimensions, unspecified connections, and unresolved findings instead of silently presenting an incomplete packet as finished.

**Completion gate:** a DIY reader can identify the required pieces, understand their cuts and orientation, and follow the assembly sequence from the packet. Verify dimensions, quantities, labels, and step references independently. Resize the project, move an opening, and revise a connection; regenerate the drawings, affected instructions, material list, and estimate from the same checkpoint. Retain the earlier packet's version and historical estimate.

**5. Prove building-scale use and release readiness.**

Exercise the complete workflow on a representative mansion with multiple floors, interacting roof sections, repeated assemblies, many openings, surface detailing, and intentional exceptions. Include a local opening move, a shared-definition edit, a global dimension change, alternative designs, and a multi-sheet plan set. Document the construction systems and detail demonstrated; a large collection of identical boxes cannot establish building capability.

Measure source execution, solid generation, checks, drawing generation, material planning, transfer, viewer updates, comparison, navigation, and memory on documented machines. Set release targets from actual interaction needs and measurements. There is no arbitrary product part-count limit; supported workloads and observed performance must still be reported accurately.

Optimize the measured bottlenecks. Reuse unchanged display resources, instance repeated shapes, patch changed objects, and load detail on demand where useful. Cache component geometry only when its inputs are known, including source, parameters, referenced data, and runtime dependencies. Use conservative rebuilding when they are not. Introduce dependency tracking and spatial indexes to solve demonstrated costs.

Any incremental path must agree with full evaluation. An edited component can affect neighboring contacts, clearances, shared relationships, drawing annotations, assembly instructions, quantities, and stock planning. Validate edit sequences that expose those interactions. Cancellation, branching, and restoration must prevent stale work from becoming current.

Complete native macOS and Windows installation and update checks with the bundled CadQuery runtime. Preserve the remembered project catalog, explicit Add project flow, and missing-folder state. Registering a folder does not execute its design; stud does not scan the user's disk for projects. App updates leave project folders intact. The conversation and local browser viewer remain the supported workflow; keep host-specific integration small so a standalone app can reuse the same capabilities later.

**Completion gate:** the representative building meets agreed interaction and resource targets, and its model, checks, plans, history, and costs remain coherent through the edit scenarios. Incremental results agree with full builds. Installation, reopen, update, and project preservation work on both operating systems.

**Exports and deferred work**

PDF plans and CSV parts, materials, and estimates are the first export deliverables. Each output identifies the saved design version and relevant pricing basis. Incomplete live previews must not masquerade as complete plan packets. Add geometry or building-information formats when a concrete receiving workflow establishes what must survive the handoff.

Defer model imports, external editable round trips, and automated structural analysis until users establish demand. Direct geometry editing, a user parameter editor, and a standalone design host are not required for this roadmap's initial delivery. Other substantial capabilities enter through demonstrated needs rather than speculative extension points.

**First implementation task:** connect an agent-authored CadQuery component to stud's viewer, material list, and a dimensioned printable sheet. Prove identity, placements, an intentional exception, independent geometry checks, and bundled execution with the workbench, rotated opening, and roof joint. Carry those results into the live editing loop.
