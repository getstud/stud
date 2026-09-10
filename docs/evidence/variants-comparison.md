# Variants & comparison acceptance — 2026-09-10

Issue: getstud/stud#19. Base: `77315ae6cd6aacbf2a597e12319b2064ab282adf`.

## Automated checks

- Python: 250 tests exercised. 248 passed in the filesystem sandbox; the two existing loopback-server tests failed because socket binding was denied. Both passed when rerun with loopback permission. The final focused option-comparison tests also passed after the selection-path optimization.
- JavaScript: 91 tests passed, including comparison controller and mesh-cache regressions.
- `node --check web/app.js`, `node --check web/option-tabs.js`, and `git diff --check` passed.
- Independent review found canceled mesh installation being acknowledged as success, and overlapping metadata responses restoring obsolete options. Both were fixed and covered by regressions, including an initial reader awaiting the newest metadata request.

The Python comparison fixture creates three distinct saved options, leaves an editing request open, prepares and selects each option, then checks the exact request workspace bytes, checkout source bytes, Git branch refs, active option and active request. It also verifies stale-head/wrong-evidence rejection and receipt replay after return-to-live.

Controller tests cover N-option switching, repeated cached selections, natural-name ambiguity, stale references, failed preparation and retry, earlier slow preparation versus newer selection, canceled rendering, metadata races, changed-part classification, and using prepared geometry without a full-model refresh on the critical path. CadScene tests verify three retained shapes reuse geometry and that unused retention remains bounded.

## Browser and real WebMCP

Used the Codex in-app browser's actual `webmcp` capability and registered page tools, with a disposable local CadQuery roof study. Options were **Gabled roof**, **Dormered roof**, and **Dormered roof with porch**. The editing request remained open on Gabled roof throughout.

| Exercise | Observed result |
| --- | --- |
| `list_options` | All three IDs/names/heads/summaries, displayed source/build/checkpoint, separate editing identity, exact camera and visible IDs returned. |
| `show` a roof region, then `compare_options("dormered version")` | Returned `AMBIGUOUS_OPTION` with the two dormered candidates; no tab change. |
| `compare_options("Dormered roof")` | Switched the displayed tab; returned `roof.dormer` as added. The added geometry was visible in the retained close-up. Baseline identified the actual live build, not merely its branch head. |
| Perspective detail across all three tabs | Full camera JSON equality: position, quaternion, up, target, zoom, projection, matrix, near/far, FOV and aspect. Same open editing request and option. |
| Orthographic front detail | Same pose, frustum, projection matrix and zoom after switching. |
| Roof plan drawing, manually panned and zoomed | All three tabs preserved full camera JSON, including zoom `1.5189819629616947`. Roof isolation remained; the porch stayed hidden outside the selected assembly. |
| Select `roof.main`, then switch all three options | Part selection and inspector remained on `roof.main`; exact viewpoint and editing identity retained. |
| Keyboard Home on a named tab | Selected Live design and preserved full camera JSON and editing request. |
| 390 × 844 viewport | Horizontal tab overflow worked; selected tab scrolled into view; Parts panel and warning control cleared the comparison header. |
| Final fixed 1100 × 760 viewport, cached switches | Exact full camera JSON and retained part selection for repeated Gabled/Dormered swaps. |

Camera comparisons use a fixed viewport or an immediately captured baseline. Resizing the browser naturally changes aspect/frustum; it is separate from option switching.

Two final cached selection HTTP requests measured **30.1 ms** and **38.4 ms**. The final scene update measured **1.7 ms**, with **0 ms** asset preparation and four mesh assets cached in this small fixture. These are local fixture measurements, not a performance guarantee for large designs. Uncached views may need materialization; the previous design remains visible while loading.

## Integration with #24

The comparison feature works independently with direct WebMCP registration. When combining #24, pass its `registerControlledTools` function through the tab installer's `registerTools` hook, and expose the returned controller to the optional `viewer-operations` comparison adapter. Keep one shared `updateViewerControls` helper. Preserve #19's prepared-display commit verification, metadata sequencing, queued native refresh, exact drawing-view retention and tab status (a successful history notice must not resize the canvas).

The existing Versions page's two-checkpoint report and plan packets remain available. Swipe comparison and microphone/transcription implementation are outside this change; the voice agent uses the verified WebMCP operations.
