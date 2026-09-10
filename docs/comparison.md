# Comparing design options

The centered version pill shows the currently displayed option. Open it to switch options, return to the live editing preview, or create a new option. New options start from the displayed saved checkpoint (or the live option's latest saved checkpoint). Creating an option displays it without changing the active editing request. Click outside or press Escape to close the menu.

Move to a detail, orbit or pan, and zoom before switching options. The same camera remains in use: position, orientation, target, zoom, projection, orthographic frustum and view offset stay unchanged. Plan, front and side assembly drawings keep their viewpoint too. Existing assembly visibility and part selection are retained where the referenced part exists in the other option.

Options use the original geometry and colors. They do not activate a Git option, alter source files, or change the agent's editing request. The selected menu item marks the displayed option; the editing option is identified in its tooltip. Choose the **Live** entry to return to the latest preview at the same viewpoint. Explicit editing-target activation remains a separate action in Versions.

Use Up/Down arrow keys to focus menu options, Home/End for the first/last item, and Enter to select. Long option lists scroll vertically. The pill dims while an option loads and the previous design remains visible. Geometry is prepared before an atomic swap; repeated switches reuse mesh assets. Missing geometry and stale branch heads produce an error rather than a partial or silently substituted design.

The existing Versions page still provides checkpoint history, the two-checkpoint parts/estimate report, and plan packets. Before/after swipe comparison belongs to the separate renovation workflow.

## Voice and WebMCP

A compatible browser exposes these comparison tools through `document.modelContext`. The buttons and tools call the same `OptionComparison` controller; browsers without WebMCP retain the complete tab interface.

| Tool | Behavior |
| --- | --- |
| `list_options({})` | Lists IDs, names, branch heads and checkpoint summaries; reports the actual displayed source/build/checkpoint, editing option and open request, exact camera, selected part and visible part IDs. |
| `switch_option({option, expected_head?})` | Selects a saved option by ID or an unambiguous name without reframing or activating it. Returns after the model is installed. |
| `compare_options({option})` | Compares the actual displayed model with a saved option, switches to that tab, and returns added, removed, reshaped, moved and appearance changes with both displayed identities. The baseline can be an unfinished draft. |
| `return_to_editing_view({})` | Returns to the current editing preview without changing its editing target or the camera. |

For “How does this compare to the dormered version?”:

1. Read `list_options` and resolve the reference from names, summaries and the displayed design. Exact IDs are the most reliable references.
2. If both “Dormered roof” and “Dormered roof with porch” match, ask which one the user means. An ambiguous call returns `AMBIGUOUS_OPTION` and the matching candidates without switching.
3. Call `compare_options` with the resolved ID. Inspect the visible canvas and explain the relevant differences using the changed-part evidence. Changes outside the current viewpoint should be described as outside the visible area.
4. Flip back and forth with `switch_option`; use `return_to_editing_view` when the baseline was live. Use the existing `show` tool only when the user wants to move to a different detail, since `show` deliberately frames its target.

Model difference dimensions use inches, consistent with the viewer's physical scale. Native geometry is converted once by the existing CAD display adapter. Inspection is not a design approval or a choice of editing target.

## Integration

`installOptionTabs(adapter)` returns `{controller, tools, refresh}`. `createComparisonTools(controller)` produces the four descriptors above. The optional `registerTools(tools)` adapter hook allows a shared registry to wrap them with common activity reporting; the standalone fallback registers them directly. Issue #24's shared registry should pass `registerTools: registerControlledTools`, and its existing `versions.inspect({option_id})` operation can delegate to `controller.switchOption(option_id)`.

The adapter supplies the current displayed model/camera, asset preparation, atomic installation of prepared models, and live refresh. The main viewer suppresses stale in-flight model responses during a tab change and keeps native events queued until the display settles. `studprojectchange` carries the originating event in `detail` so option metadata refreshes can skip display-only notifications.

The coordinator's `prepare_option` operation reuses the immutable checkpoint comparison pipeline without selecting a view. `inspect_option` checks the current option head against `expected_head` and verifies the prepared comparison's checkpoint before selecting isolated history display. It returns the editing identity independently. Both operations leave the request workspace and Git refs intact. Checkpoint advancement requires fresh preparation; a response retry cannot undo a newer display action.
