import * as THREE from 'three';

// Follow successive build bounds until the user takes over this viewer session.
export class BuildCamera {
  enabled = true;
  destination = null;
  lastTime = null;

  stop() {
    this.enabled = false;
    this.cancel();
  }

  cancel() {
    this.destination = null;
    this.lastTime = null;
  }

  follow(box, camera, controls, now, reducedMotion = false) {
    this.cancel();
    if (!this.enabled || reducedMotion || !controls?.target || box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const direction = camera.position.clone().sub(controls.target).normalize();
    let distance = camera.position.distanceTo(controls.target);
    if (camera.isPerspectiveCamera) {
      const halfFov = THREE.MathUtils.degToRad(camera.getEffectiveFOV()) / 2;
      const limiting = Math.min(halfFov, Math.atan(Math.tan(halfFov) * camera.aspect));
      distance = Math.max(size.length() / 2, 10) / Math.sin(limiting) * 1.15;
    }
    this.destination = {center, position: center.clone().addScaledVector(direction, distance)};
    this.lastTime = now;
  }

  update(camera, controls, now) {
    if (!this.destination || !controls?.target) return;
    const alpha = 1 - Math.exp(-Math.min(Math.max(now - this.lastTime, 0), 100) / 1000);
    this.lastTime = now;
    camera.position.lerp(this.destination.position, alpha);
    controls.target.lerp(this.destination.center, alpha);
    if (camera.position.distanceTo(this.destination.position) < .01 &&
        controls.target.distanceTo(this.destination.center) < .01) {
      camera.position.copy(this.destination.position);
      controls.target.copy(this.destination.center);
      this.cancel();
    }
  }
}

// A stationary click selects a part; only a camera gesture takes over tracking.
export function stopOnCameraInput(canvas, tracking) {
  const pointers = new Map();
  canvas.addEventListener('pointerdown', event => {
    pointers.set(event.pointerId, [event.clientX, event.clientY]);
  });
  canvas.addEventListener('pointermove', event => {
    const origin = pointers.get(event.pointerId);
    if (origin && Math.hypot(event.clientX - origin[0], event.clientY - origin[1]) > 4) tracking.stop();
  });
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    canvas.addEventListener(type, event => pointers.delete(event.pointerId));
  }
  canvas.addEventListener('wheel', () => tracking.stop(), {passive: true});
}
