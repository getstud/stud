# Plan implementation and evidence

Scope: every contract, work package, and verification gate in [PLAN.md](PLAN.md), with the product outcomes in [ROADMAP.md](ROADMAP.md). Owner decisions are in [DECISIONS.md](DECISIONS.md).

The imported plan and roadmap are specifications, not evidence of shipped functionality.

| Package | State | Evidence required |
| --- | --- | --- |
| 1A Project and version spine | In progress | Stable IDs, frozen source, isolated requests, idempotent save/recovery, unrelated edits excluded. |
| 1B CadQuery evaluation | In progress | Native archives and queries, nested placements, bores, sloped stock, immutable registration and reference invalidation tested. Broader edit fixtures remain. |
| 1C Outputs and packaging trials | In progress | Vector packet and scale tests pass; macOS ARM installed-layout smoke passes. Windows/Intel trials remain. |
| 2A Live jobs and viewer | In progress | Mesh patches, bounded event replay/reset, cancellation and watcher implemented; new browser interaction and recovery proof remains. |
| 2B Review loop | In progress | Original source/capture records, prompt actions, native measurements and acknowledged focus implemented; full browser review scenario remains. |
| 3A Alternatives and recovery | In progress | Read-only compare backend, branch creation/activation, restore, record union and recovery implemented. Viewer comparison and option rename remain. |
| 3B Cost comparison | In progress | Decimal purchase lines, stock lengths, packs, overrides, saved snapshots and both comparison modes tested. Final combined verification remains. Migration was removed from scope by the owner. |
| 4A Detailed DIY projects | In progress | Detailed bench and shed framing, sheet cutouts, sloped rafters, ties, housed blocking and local bore exception implemented. Revision and purchasing fixtures remain. |
| 4B Standard plan packet | In progress | Vector views/sections, cuts, stock/sheet layouts, topological steps, illustrations, completeness and immutable exports implemented. Detail views, final all-page PDF review and DIY reader remain. |
| 5A Building workloads | Pending | Representative mixed-complexity mansion, documented timings/memory and targets, adversarial edits/full equivalence. |
| 5B Native release | In progress | macOS ARM app build/smoke and copied-folder recovery pass. Intel/Windows, signed-update trial and final release packaging remain. |

## Verification ledger

Acceptance is unproven until the relevant command, runtime observation, or field result is recorded here. A green unit suite does not by itself satisfy a broader product gate.

- Lifecycle foundation: `.venv/bin/python -m unittest discover -s tests -p test_session.py -v` passes 16 tests. Includes native CadQuery builds, expected solids/lengths, duplicate finish, no-change requests, source/price separation, ignored/unrelated-file preservation, cancel/late writes, uncooperative-worker termination, and several crash windows. Further transport, record and race checks remain.
- Existing browser unit checks: `node --test tests/*.mjs` passes 69 tests after the initial scene integration. New scene/event-specific tests and browser scenarios remain.
- Proving geometry: the workbench has 12 parts and 31 passing native checks; rotated opening 4 parts / 7 checks; roof joint 2 parts / 4 checks. These are initial results, not complete geometry-acceptance coverage.
- Baseline interaction recorded from the running application: `evidence/animation-baseline.webm`, with `animation-before.png` and `animation-after.png`. Three additions stagger into place while the camera gently follows. No JavaScript page errors were observed.
- First actual request produced checkpoint `373acea6151c5896fcf9312815320d1e8f34b52a` in the isolated proof project `/private/tmp/stud-first-vertical-baec4d20`. Its build produced a 9-page vector workbench packet. Initial rendered review found overly technical cut descriptions; these have been replaced with readable fabrication instructions and the final packet must be regenerated and rechecked.
- Existing baseline Python suite: 154 cases passed; two loopback-server cases failed due to sandbox socket permissions, not assertions about application behavior. Rerun the full suite with local networking allowed after integration.
- Native CI already exists in `.github/workflows/desktop.yml`, with macOS ARM/Intel and Windows runners, installer smoke tests and release signing gates. It still needs the new dependencies and workflow checks; no new native release has been verified.

## Subsequent verification

- Full Python suite: 188 tests passed in 188.6 seconds with local networking enabled. This includes the previous server tests and the new session, records, versions, estimates and native operations. Later construction/relocation additions have focused results below and still require a final combined run.
- Browser unit suite: 74 tests passed, including five native mesh/event tests for immutable asset integrity, object reuse, retained prior context, asynchronous generation races and event replay/reset.
- Native operations: five focused tests passed after adding packet illustrations/layouts. They cover exact model-to-sheet distance, Letter page size, immutable export retry, mismatched sources, altered manifests, path confinement, snapped solid measurements and actual viewer acknowledgements.
- Relocation: three tests passed. A copied project can reopen its draft, cached geometry, historical source and PDF while the original session stays alive. Original worktree links and jobs remain byte-for-byte unchanged. Copied endpoints cannot attach to the original folder; Windows-form paths rebase on macOS.
- Native geometry: eight independent fixtures passed in 1.6 seconds. Includes nested rotations with hand-calculated coordinates, cylindrical hole clearance and volume, nearly coincident faces, unsupported coverage, full publication rollback, local bore preservation, door void and panel quantities, and floor/stair cuts.
- Detailed shed: 169 physical parts and 332 passing checks in a direct native run (~5 seconds). This includes a whole-component native interference query. Site-dependent construction details remain explicit packet-review findings.
- macOS ARM: checksum-pinned Python, CAD/PDF packages and Git staged successfully; a native Tauri `.app` built. The installed-layout smoke ran with system Python/Git removed from PATH and passed CAD evaluation, one-checkpoint finish/retry, quotes/prompts, vector PDF output, copied-folder reopening, catalog, legacy project compatibility, detached coordinator shutdown and update locking. Evidence: `evidence/macos-arm64-runtime.json` and `evidence/macos-arm64-native-smoke.log`. This was a local app bundle, not a production signed/notarized release or DMG installation.
- The desktop CI matrix now installs the same dependency lock before its Python suite. Native signing includes Git as well as Python/CAD/PDF binaries. No Windows/Intel or signed-release run has been dispatched yet.
- An 11-page workbench packet was rendered and every page inspected. Scale and text were readable; follow-up improvements add a larger standalone sheet diagram, explicit purchased board lengths, a stock cutting plan and fuller precision where imperial fractions round metric dimensions. Regenerate and inspect the final packet after those changes.

## Baseline

- Starting application commit: `862a121`.
- Legacy build executes Python synchronously on `/api/model` reads, uses custom inch-based solids, and replaces JSON outputs independently.
- Legacy additions use the existing `BuildAnimation` and `BuildCamera`; record the running interaction before replacing the viewer path.

## Geometry and viewer verification after review

- Independent review found overlapping end members, unsupported panel seams, undirected bearing, unreconciled purchasing data, incomplete corner-cut instructions and a wrong birdsmouth datum. These were reproduced and corrected. The native suite now passes 13 tests in 5.1 seconds, including custom spacing and opening combinations, missing edge-check references, zero purchased part quantities and mismatched stock sections.
- The detailed shed now contains 181 parts and 377 passing native requirements, including continuous contact behind actual panel edges and cutouts. Gable base blocking and a profile that follows the ridge close the gaps found by these checks. Site-dependent connections remain packet findings.
- `scripts/verify-native-viewer.mjs` passed against a real coordinator and headless Chrome: content watching, coherent partial batches, animated additions, retained selection, unchanged-part continuity, two geometric comparison views, both price modes, historical estimate inspection, return to the current draft, and a fixed-checkpoint PDF download. The active editing request survived comparison, inspection and export. No JavaScript page errors were recorded. Evidence is in `evidence/native-viewer-acceptance.json`, `evidence/cadquery-live-animation.webm`, and the `native-*.png` images.
- The new Versions report page uses the existing application styles; the workspace layout, navigation controls, parts tree, inspection, drawing controls and camera behavior remain in place. Original saved estimates are read-only during historical inspection. Option rename and comparison-view identities have coordinator tests; the expanded browser test also exercises option controls and restoration.
