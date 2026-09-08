# Environment assets

Environment assets add visual context such as trees, terrain, people, or furniture. They are saved with the project but are not construction parts: they do not contribute to materials, pricing, CSV exports, assembly explosion, or geometry checks.

Register an asset in `design.py` alongside your construction parts:

```python
project.context_asset(
    'existing-tree',
    name='Existing tree',
    source='assets/tree.js',
    origin=(120, 96, 0),
    rotation=(0, 0, 0),
    parameters={'trunk_diameter': 24, 'height': 360, 'seed': 42, 'trunk_reference_height': 106},
    visible=True,
)
```

Copy [the procedural tree example](../examples/environment/assets/tree.js) into your project's `assets/tree.js`. The example generates an oak with tapered branching limbs, buttress roots, bark ridges, and instanced lobed leaves. `trunk_diameter` is the outside diameter at `trunk_reference_height` (106 inches in this example, matching the platform top). The reference height defaults to 30% of tree height and must lie within the lower 45%; the trunk stays centered on its origin through that region, with a circular cross-section at the reference height. Elsewhere it tapers and flares toward the roots, so the reference diameter is not a clearance envelope for the entire trunk. `height` controls the approximate canopy height. A seed makes its geometry and colors repeatable. Wood and foliage use two meshes, with no external textures. Change the module freely to suit the project; there is no catalog of permitted shapes.

## Module contract

Each module exports `create({THREE, parameters, assetUrl})`. It returns a fresh `THREE.Object3D` (usually a `Group`), or a promise resolving to one. Geometry uses inches and **Z up**. The viewer applies the registration's origin and XYZ Euler rotation in degrees, then converts to its rendering coordinates. Keep placement out of the module when it belongs to the registration.

```js
export function create({THREE, parameters}) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(parameters.radius, 24, 16),
    new THREE.MeshStandardMaterial({color: '#739752'}),
  );
  mesh.position.z = parameters.radius;
  return mesh;
}
```

Use the supplied `THREE` instance or `import * as THREE from 'three'`. Relative module imports under `assets/` work, including nested helpers. For textures and other resources, use `assetUrl('./bark.png')`; it resolves relative to the module's registered source. All resource files belong under `assets/`. The viewer exposes that directory's snapshot, so keep it limited to intended scene resources.

Modules run as trusted project code in the viewer, just as `design.py` runs as trusted project code on the computer. This is a static object factory, not a sandbox or an animation lifecycle. Avoid global event handlers and timers. Do not reuse objects, materials, or textures across factory calls; the viewer owns returned resources and disposes geometries, materials, and material textures when replacing or removing them. A factory that fails before returning must clean up resources it already created. Custom resources outside the returned scene graph remain the module's responsibility.

## Viewing and revisions

The **Environment** section provides a master toggle and individual visibility controls. Click an object or its **Inspect** button to see its parameters, origin, and environment designation. Part comments remain attached to construction parts; area screenshots can include the environment.

**Fit design** frames construction and displayed dimensions. **Fit scene** includes visible environment assets. Environment objects stay in place during assembly explosion and are not affected by transparent-surface display.

Edits anywhere under `assets/` trigger a rebuild. The builder saves immutable resource snapshots under `output/environment/`, and module imports use the snapshot revision in their URLs so helper edits reload too. These generated snapshots can be removed when the viewer is stopped; rebuilding recreates the current one. Keep the source `assets/` folder in backups and version control, not the generated snapshots.

A missing module, syntax error, or failed factory is reported on that asset. Construction remains visible; if the asset previously loaded, its last good appearance remains until the next successful edit. An invalid construction build still retains the last good complete model, as before.

Environment geometry is visual context only. A 24-inch tree trunk does not automatically become a clearance constraint or structural support. Declare applicable construction requirements separately; arbitrary environment meshes are not checked by the construction validator.
