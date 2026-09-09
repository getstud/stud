import * as THREE from 'three';

// Focus-scoped controls let the rest of the workshop keep its keyboard shortcuts.
export class FlyControls {
  constructor(camera, canvas) {
    this.camera = camera;
    this.canvas = canvas;
    this.keys = new Set();
    this.enabled = true;
    this.lastTime = performance.now();
    const previousTabIndex = canvas.getAttribute('tabindex');
    canvas.tabIndex = 0;
    const rotation = new THREE.Euler(0, 0, 0, 'YXZ');
    let pointer = null;
    const clear = () => { this.keys.clear(); pointer = null; };
    const down = event => {
      if (!this.enabled || event.button !== 0) return;
      canvas.focus({preventScroll: true});
      pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
      canvas.setPointerCapture(event.pointerId);
    };
    const move = event => {
      if (!this.enabled || pointer?.id !== event.pointerId) return;
      rotation.setFromQuaternion(camera.quaternion, 'YXZ');
      rotation.y -= (event.clientX - pointer.x) * .004;
      rotation.x = THREE.MathUtils.clamp(rotation.x - (event.clientY - pointer.y) * .004, -Math.PI/2 + .001, Math.PI/2 - .001);
      camera.quaternion.setFromEuler(rotation);
      pointer.x = event.clientX; pointer.y = event.clientY;
    };
    const keydown = event => {
      if (event.code === 'Escape') { clear(); canvas.blur(); return; }
      if (!this.enabled || event.ctrlKey || event.metaKey || event.altKey) return;
      if (['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowLeft','ArrowDown','ArrowRight','KeyQ','KeyE','ShiftLeft','ShiftRight'].includes(event.code)) {
        event.preventDefault(); this.keys.add(event.code);
      }
    };
    const keyup = event => this.keys.delete(event.code);
    const bindings = [[canvas,'pointerdown',down],[canvas,'pointermove',move],
      [canvas,'pointerup',() => {pointer = null;}],[canvas,'pointercancel',clear],
      [canvas,'lostpointercapture',() => {pointer = null;}],
      [canvas,'keydown',keydown],[canvas,'keyup',keyup],[canvas,'blur',clear],
      [window,'blur',clear],[document,'visibilitychange',clear]];
    bindings.forEach(([target, type, listener]) => target.addEventListener(type, listener));
    canvas.focus({preventScroll: true});
    this.dispose = () => {
      clear();
      bindings.forEach(([target, type, listener]) => target.removeEventListener(type, listener));
      if (previousTabIndex === null) canvas.removeAttribute('tabindex');
      else canvas.setAttribute('tabindex', previousTabIndex);
    };
  }

  update(now = performance.now()) {
    const seconds = Math.min(Math.max((now - this.lastTime)/1000, 0), .05);
    this.lastTime = now;
    if (!this.enabled || document.activeElement !== this.canvas) {this.keys.clear(); return;}
    const held = code => Number(this.keys.has(code));
    const direction = (letter, arrow) => Number(this.keys.has(letter) || this.keys.has(arrow));
    const movement = new THREE.Vector3(direction('KeyD','ArrowRight')-direction('KeyA','ArrowLeft'), 0, direction('KeyS','ArrowDown')-direction('KeyW','ArrowUp'));
    movement.applyQuaternion(this.camera.quaternion);
    movement.y += held('KeyE')-held('KeyQ');
    // World units are inches: ordinary flight is six feet per second.
    const speed = this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 288 : 72;
    this.camera.position.addScaledVector(movement.normalize(), speed * seconds);
  }
}
