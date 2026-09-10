# Bundled components

stud desktop uses Tauri v2 and the Tauri updater plugin (MIT or Apache-2.0),
CPython and its bundled runtime libraries from Astral's python-build-standalone,
and Three.js (MIT).

The bundled Python environment also includes CadQuery (Apache-2.0), Open CASCADE
Technology through cadquery-ocp (LGPL-2.1 with its additional exception),
ReportLab (BSD), svglib (LGPL-3.0), and their pinned dependencies. Full package
license metadata and license files remain in the runtime's site-packages.
`engine/requirements.lock` records the exact dependency distributions and hashes.

Git and supporting tools are distributed from GitHub Desktop's dugite-native
bundles, with their upstream license files retained under `git/`. Git is GPL-2.0;
its corresponding source and build sources are available from the upstream
release and linked repositories:

- https://github.com/desktop/dugite-native/releases/tag/v2.53.0-4
- https://github.com/git/git/tree/v2.53.0
- https://github.com/git-for-windows/git/tree/v2.53.0.windows.4

- Python and dependency license files are retained inside `runtime/`.
- Three.js's full license is in `engine/node_modules/three/LICENSE`.
- The Tauri dependency graph and license identifiers are recorded in
  `src-tauri/Cargo.lock` and the respective upstream crates.
- Runtime download URLs and SHA-256 checksums are recorded in `runtime-info.json`.

Sources:
https://github.com/tauri-apps/tauri
https://github.com/tauri-apps/plugins-workspace
https://github.com/astral-sh/python-build-standalone
https://github.com/mrdoob/three.js
