import * as THREE from 'three';

// Carry the current focus and apparent scale between projection types.
export function preserveCamera(previous, next, name, target, distance) {
  const forward = previous.getWorldDirection(new THREE.Vector3());
  const focus = target?.clone() ?? previous.position.clone().addScaledVector(forward, distance);
  const depth = target ? previous.position.distanceTo(target) : distance;
  const height = previous.isPerspectiveCamera
    ? 2 * depth * Math.tan(THREE.MathUtils.degToRad(previous.getEffectiveFOV()) / 2)
    : (previous.top - previous.bottom) / previous.zoom;
  let nextDepth = depth;
  if (next.isPerspectiveCamera) {
    if (previous.isPerspectiveCamera) {
      next.position.copy(previous.position);
      next.quaternion.copy(previous.quaternion);
      next.zoom = previous.zoom;
    } else {
      nextDepth = height / (2 * Math.tan(THREE.MathUtils.degToRad(next.fov) / 2));
      next.position.copy(focus).addScaledVector(forward, -nextDepth);
      next.quaternion.copy(previous.quaternion);
    }
  } else {
    next.zoom = (next.top - next.bottom) / height;
    const direction = name === 'top' ? new THREE.Vector3(0,1,0)
      : name === 'front' ? new THREE.Vector3(0,0,1) : new THREE.Vector3(1,0,0);
    next.position.copy(focus).addScaledVector(direction, depth);
    next.lookAt(focus);
  }
  next.updateProjectionMatrix();
  return {focus, distance: nextDepth};
}
