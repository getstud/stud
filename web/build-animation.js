// Reveal additions in design order without changing their geometry or position.
export class BuildAnimation {
  entries = [];

  start(meshes, now, reducedMotion = false) {
    this.finish();
    if (reducedMotion) return;
    const step = Math.min(90, 1800 / Math.max(1, meshes.length - 1));
    this.entries = meshes.map((mesh, index) => {
      const materials = [mesh.material, ...mesh.children.map(child => child.material)];
      return {start: now + index * step, materials: materials.map(material => ({
        material, opacity: material.opacity, transparent: material.transparent,
        depthWrite: material.depthWrite,
      }))};
    });
    this.update(now);
  }

  update(now) {
    this.entries = this.entries.filter(entry => {
      const progress = Math.max(0, Math.min(1, (now - entry.start) / 350));
      for (const saved of entry.materials) {
        const {material, opacity, transparent, depthWrite} = saved;
        material.opacity = opacity * progress;
        material.transparent = progress < 1 || transparent;
        material.depthWrite = progress === 1 && depthWrite;
      }
      return progress < 1;
    });
  }

  finish() {
    this.update(Infinity);
  }
}
