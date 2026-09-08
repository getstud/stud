// Drop additions into place in design order; model coordinates remain unchanged.
export class BuildAnimation {
  entries = [];

  start(meshes, now, reducedMotion = false) {
    this.finish();
    if (reducedMotion) return;
    const step = Math.min(200, 12000 / Math.max(1, meshes.length - 1));
    this.entries = meshes.map((mesh, index) => {
      const materials = [mesh.material, ...mesh.children.map(child => child.material)];
      return {mesh, targetY: mesh.position.y, start: now + index * step, materials: materials.map(material => ({
        material, opacity: material.opacity, transparent: material.transparent,
        depthWrite: material.depthWrite,
      }))};
    });
    this.update(now);
  }

  update(now) {
    this.entries = this.entries.filter(entry => {
      const progress = Math.max(0, Math.min(1, (now - entry.start) / 500));
      const eased = 1 - (1 - progress) ** 3;
      entry.mesh.position.y = entry.targetY + 48 * (1 - eased);
      for (const saved of entry.materials) {
        const {material, opacity, transparent, depthWrite} = saved;
        material.opacity = opacity * eased;
        material.transparent = progress < 1 || transparent;
        material.depthWrite = progress === 1 && depthWrite;
      }
      return progress < 1;
    });
  }

  // Refresh display settings without losing the reveal's timing or order.
  rebase(changeDisplay, now) {
    const entries = this.entries;
    this.finish();
    try {
      return changeDisplay();
    } finally {
      for (const entry of entries) {
        entry.targetY = entry.mesh.position.y;
        for (const saved of entry.materials) {
          const {opacity, transparent, depthWrite} = saved.material;
          Object.assign(saved, {opacity, transparent, depthWrite});
        }
      }
      this.entries = entries;
      this.update(now);
    }
  }

  // Camera fitting measures final positions without consuming animation time.
  atRest(measure) {
    const positions = this.entries.map(({mesh, targetY}) => {
      const y = mesh.position.y;
      mesh.position.y = targetY;
      return {mesh, y};
    });
    try {
      return measure();
    } finally {
      for (const {mesh, y} of positions) {
        mesh.position.y = y;
        mesh.updateMatrixWorld?.(true);
      }
    }
  }

  finish() {
    this.update(Infinity);
  }
}
