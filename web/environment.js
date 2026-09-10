// Environment objects never enter the construction mesh collection.
export function disposeEnvironment(root) {
  const resources = new Set();
  root.traverse(object => {
    if (object.isInstancedMesh) resources.add(object);
    if (object.geometry) resources.add(object.geometry);
    for (const material of object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []) {
      resources.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) resources.add(value);
      for (const uniform of Object.values(material.uniforms || {})) if (uniform?.value?.isTexture) resources.add(uniform.value);
    }
  });
  for (const resource of resources) resource.dispose();
  root.removeFromParent();
  root.clear();
}

export function createEnvironment({THREE, scene, onChange = () => {}, importer = url => import(url)}) {
  const group = new THREE.Group();
  group.rotation.x = -Math.PI / 2;
  scene.add(group);
  const entries = new Map(), visibility = new Map();
  let enabled = true;
  function release(entry) {
    if (entry.object) disposeEnvironment(entry.object);
  }
  function visible(entry) { return enabled && (visibility.get(entry.asset.id) ?? entry.asset.visible ?? true); }
  function applyVisibility() {
    group.visible = enabled;
    for (const entry of entries.values()) if (entry.object) entry.object.visible = visible(entry);
  }
  async function load(entry) {
    let object;
    try {
      if (entry.asset.error) throw new Error(entry.asset.error);
      const base = `/environment/${entry.asset.revision}/`;
      const url = base + entry.asset.source.split('/').map(encodeURIComponent).join('/');
      const module = await importer(url);
      if (typeof module.create !== 'function') throw new Error('Module must export create()');
      object = await module.create({THREE, parameters: structuredClone(entry.asset.parameters), assetUrl: path => {
        const result = new URL(path, new URL(url, 'http://stud.local'));
        if (result.origin !== 'http://stud.local' || !result.pathname.startsWith(base + 'assets/')) throw new Error('Resources must be inside assets/');
        return result.pathname + result.search;
      }});
      if (!object?.isObject3D) throw new Error('create() must return a Three.js Object3D');
      if (entries.get(entry.asset.id) !== entry) { disposeEnvironment(object); return; }
      const wrapper = new THREE.Group();
      wrapper.position.fromArray(entry.asset.origin);
      wrapper.rotation.set(...entry.asset.rotation.map(n => n * Math.PI / 180), 'XYZ');
      wrapper.add(object);
      release(entry);
      entry.object = wrapper;
      group.add(wrapper);
      entry.error = null;
    } catch (error) {
      if (object?.isObject3D) disposeEnvironment(object);
      if (entries.get(entry.asset.id) !== entry) return;
      entry.error = error.message || String(error);
    }
    entry.loading = false;
    applyVisibility();
    onChange();
  }
  return {
    group, entries,
    update(assets = []) {
      const ids = new Set(assets.map(asset => asset.id));
      for (const [id, entry] of entries) if (!ids.has(id)) { release(entry); entries.delete(id); visibility.delete(id); }
      const pending = [];
      for (const asset of assets) {
        const signature = JSON.stringify(asset), previous = entries.get(asset.id);
        if (previous?.signature === signature) continue;
        const entry = {asset, signature, object: previous?.object, loading: true, error: null};
        // Transfer the last good object; stale asynchronous loads cannot replace it.
        if (previous) previous.object = null;
        entries.set(asset.id, entry);
        pending.push(load(entry));
      }
      applyVisibility(); onChange();
      return Promise.all(pending);
    },
    get enabled() { return enabled; },
    visibilityFor(id) { return visibility.get(id) ?? entries.get(id)?.asset.visible ?? true; },
    setEnabled(value) { enabled = value; applyVisibility(); onChange(); },
    setVisible(id, value) { visibility.set(id, value); applyVisibility(); onChange(); },
    isVisible: visible,
    bounds() {
      group.updateWorldMatrix(true, true);
      const box = new THREE.Box3();
      for (const entry of entries.values()) if (entry.object && visible(entry)) box.expandByObject(entry.object);
      return box;
    },
    pick(ray) {
      group.updateWorldMatrix(true, true);
      const targets = [...entries.values()].filter(entry => entry.object && visible(entry));
      const hits = ray.intersectObjects(targets.map(entry => entry.object), true).filter(hit => {
        for (let node = hit.object; node && node !== group; node = node.parent) if (!node.visible) return false;
        return true;
      });
      const hit = hits[0];
      if (!hit) return null;
      let node = hit.object;
      while (node.parent && node.parent !== group) node = node.parent;
      return {entry: targets.find(entry => entry.object === node), distance: hit.distance};
    },
  };
}
