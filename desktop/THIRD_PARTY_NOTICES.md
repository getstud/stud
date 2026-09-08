# Bundled components

stud desktop uses Tauri v2 and the Tauri updater plugin (MIT or Apache-2.0),
CPython and its bundled runtime libraries from Astral's python-build-standalone,
and Three.js (MIT).

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
