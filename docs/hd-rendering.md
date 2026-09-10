# HD rendering in conversation

Ask your agent to show a realistic image of the design. The viewer supplies an untextured geometry reference; the agent supplies materials, finishes and lighting to its available image-generation tool and displays the resulting image in chat. The interactive stud viewer stays available for inspection and further viewpoints.

“Show me how this would look with cedar siding” includes two actions: change the design's siding material to cedar, then visualize the resulting design. The agent saves that material change as a normal request checkpoint before capturing its reference. “Render this in morning light” changes only the visualization. Capturing a saved option uses the displayed option, and never switches the active editing target.

## Agent workflow

1. Read the displayed version and editing target (`list_options` or the viewer context tools). If a material/geometry change is requested, follow the normal `status` → `begin` → source edit → `source` → `evaluate --wait` → inspect → `finish` workflow. File saves do not start builds, and `finish` requires a completed evaluation of the current source. When the displayed option differs from the editing target, resolve which design the user means before editing; a visualization alone uses the displayed design.
2. Display the completed intended build. Use the existing `show`/camera tools for the requested viewpoint. With no viewpoint request, retain the current camera. A failed build or partial preview must not stand in for the requested change.
3. Call `capture_render_reference` with the displayed `expected_revision`, plus optional `finishes` and `lighting`. Material IDs, part/assembly labels and available purchasing specifications are included automatically. Finish text guides image generation; it does not edit project source. Retain deliberately hidden parts when appropriate; use `show` first if the user wants the whole assembled design.
4. Inspect the returned local `reference_path`, read `brief.prompt`, and invoke the available image-generation skill/tool with the PNG as a **geometry and camera reference**. The preparation tool does not itself generate an image. Use the normal image-generation tool; if it is unavailable, report that boundary instead of labeling a viewer screenshot as generated output.
5. Present the generated image directly in the conversation. Compare it with the reference for silhouette, proportions, opening/part counts, joints, roof pitch, viewpoint and material assignment. Call out visible drift and iterate when it compromises the requested decision. Use the live 3D model for dimensional inspection.

For another viewpoint, navigate the existing viewer, capture a fresh reference, and generate from that new capture. Generated imagery is an appearance study, not dimensionally authoritative evidence or a model edit. Placement in photographs of the user's surroundings is outside this workflow.

## Capture contract

```json
{
  "expected_revision": "displayed-build:final",
  "finishes": "Clear matte western red cedar lap siding; satin white trim",
  "lighting": "Soft afternoon daylight"
}
```

The tool captures visible design meshes at their final animated positions in a separate neutral scene. It strips textures/colors, transparency, inspection helpers, selection and validation highlights, grids, environment assets and HTML annotations. Neutral shading and fine physical edges make openings and trim legible. It keeps the camera's projection, pose, zoom and framing, rendering at 2048 pixels on the long edge. The live renderer, camera, visibility, selection, version picker and editing target are untouched. Exploded/assembly drawing views are refused until the assembled design is shown. Capture pauses guided playback; if a paused transition leaves parts displaced, use `viewer` reset or `show` to restore the assembled geometry before capturing.

Successful results contain `reference_path`, `brief_path`, image dimensions and SHA-256, the exact displayed source/build/checkpoint identity, camera, visible and hidden part IDs, material descriptions, finishes, lighting, and the generation prompt. Files live under `exports/render-references/<id>/geometry.png` and `brief.json` in the design project. Captures are separate from source checkpoints, comment records and generated images. A new capture gets a new directory; prior references retain their original context.

Both native and legacy viewers save through the loopback `/api/render-references` JSON endpoint, using the existing same-origin and request-size controls. The server chooses paths, bounds and validates PNG inputs, and rejects oversized/non-finite briefs. Saving never evaluates the design or modifies its editing state.

The tool runs through the shared viewer queue, visible control activity and Stop handling, and accepts its `AbortSignal`. Cancellation suppresses a late successful result; if a save has already reached the server, its reference may remain on disk. No image-generation job is started by this endpoint.

## Verification

Run `node --test tests/test_render_reference.mjs` and `python -m unittest discover -s tests -p test_render_references.py`. These exercise version/material binding, failure and cancellation paths, isolated scene state, and bounded project-local persistence. The full repository checks remain `npm test` and `node --check web/app.js`.

`scripts/render-reference-fixture.py` starts a temporary native project from `tests/fixtures/hd-shed.py` for actual browser and image-generation checks. It is a simplified appearance fixture, not a construction-ready shed. See [the demo and fidelity findings](evidence/hd-rendering.md) for the exercised conversation workflow and actual reference/output images.
