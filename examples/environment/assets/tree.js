// Seeded oak, in inches with Z up. No textures, downloads, or animation loops.
export function create({THREE, parameters}) {
  const {trunk_diameter = 24, height = 360, seed = 42,
    trunk_reference_height = height * .3} = parameters;
  if (![trunk_diameter, height].every(n => Number.isFinite(n) && n > 0) ||
      !Number.isFinite(trunk_reference_height) || trunk_reference_height < 0 || trunk_reference_height > height * .45) {
    throw new Error('Tree diameter/height must be positive; trunk reference height must be within the lower 45%');
  }
  let state = seed >>> 0;
  const random = () => ((state = (Math.imul(1664525, state) + 1013904223) >>> 0) / 4294967296);
  const tree = new THREE.Group();
  const positions = [], colors = [], indices = [];
  const barkColor = new THREE.Color();
  const radius = trunk_diameter / 2;
  // A single indexed mesh for all wood. Longitudinal ridges are inset from
  // the requested envelope; the reference cross-section is exactly circular.
  function wood(points, radii, sides = 9, trunk = false) {
    const base = positions.length / 3;
    points.forEach((point, ring) => {
      const direction = points[Math.min(ring + 1, points.length - 1)].clone().sub(points[Math.max(0, ring - 1)]).normalize();
      const u = new THREE.Vector3(0, 1, 0).cross(direction).normalize();
      const v = direction.clone().cross(u).normalize();
      for (let side = 0; side < sides; side++) {
        const angle = side / sides * Math.PI * 2;
        const ridge = .5 + .5 * Math.sin(side * 2.7);
        const referenceBlend = trunk ? Math.min(1, Math.abs(point.z - trunk_reference_height) / (height * .06)) : 1;
        // Form roots from the trunk surface itself, avoiding intersecting tubes.
        let rootFlare = 0;
        if (trunk) {
          for (let root = 0; root < 7; root++) {
            const rootAngle = root * Math.PI * 2 / 7 + .13 * Math.sin(root * 5 + (seed >>> 0));
            const lobe = Math.exp(10 * (Math.cos(angle - rootAngle) - 1));
            rootFlare += radius * (.23 + .065 * Math.sin(root * 3 + (seed >>> 0))) * lobe;
          }
          rootFlare *= Math.exp(-point.z / (radius * 1.15)) * referenceBlend ** 2;
        }
        const r = radii[ring] * (1 - .065 * ridge * referenceBlend) + rootFlare;
        const vertex = point.clone().addScaledVector(u, Math.cos(angle) * r).addScaledVector(v, Math.sin(angle) * r);
        positions.push(vertex.x, vertex.y, vertex.z);
        barkColor.setHSL(.075 + random() * .018, .19 + random() * .13, .20 + ridge * .095 + random() * .025);
        colors.push(barkColor.r, barkColor.g, barkColor.b);
        if (ring) {
          const a = base + (ring - 1) * sides + side, b = base + (ring - 1) * sides + (side + 1) % sides;
          const c = base + ring * sides + side, d = base + ring * sides + (side + 1) % sides;
          indices.push(a, b, c, b, d, c);
        }
      }
    });
    for (let side = 1; side < sides - 1; side++) {
      indices.push(base, base + side + 1, base + side);
      const end = base + (points.length - 1) * sides;
      indices.push(end, end + side, end + side + 1);
    }
  }
  const trunkLevels = [...new Set([0, trunk_reference_height, ...Array.from({length:20}, (_, i) => Math.min(radius * 3, height * .4) * ((i + 1) / 20) ** 2), ...Array.from({length:25}, (_, i) => height * .92 * (i + 1) / 25)])].sort((a,b) => a-b);
  const trunkCenter = z => {
    const bend = Math.max(0, z / height - .45);
    return new THREE.Vector3(Math.sin(z / height * 5) * height * .045 * bend, height * .035 * bend, z);
  };
  const trunkPoints = trunkLevels.map(trunkCenter);
  const trunkRadii = trunkLevels.map(z => {
    const taper = z <= height * .45 ? 1 - .28 * (z - trunk_reference_height) / height :
      (1 - .28 * (.45 - trunk_reference_height / height)) * Math.pow((.98 - z / height) / .53, .8);
    return radius * (taper + .14 * Math.exp(-z / (radius * 1.1)) * Math.min(1, Math.abs(z-trunk_reference_height)/radius));
  });
  // Dense base rings and shared vertex normals blend buttresses into the trunk.
  wood(trunkPoints, trunkRadii, 72, true);
  const sprays = [];
  function branch(start, end, thickness, depth) {
    const delta = end.clone().sub(start);
    const middle = start.clone().lerp(end, .5).add(new THREE.Vector3(delta.y * .09, -delta.x * .09, -height * .016));
    wood([start, middle, end], [thickness, thickness*.66, thickness*.22]);
    if (depth === 0) { sprays.push({start:middle, end}); return; }
    const direction = Math.atan2(delta.y, delta.x);
    for (let j = 0; j < 3; j++) {
      const angle = direction + (j - 1) * .82 + (random() - .5) * .55;
      const spread = delta.length() * (.40 + random() * .16);
      // Follow the same two segments used by wood(), so the child starts
      // inside its parent's solid rather than on the endpoint chord.
      const t = .55 + j * .18;
      const origin = t <= .5 ? start.clone().lerp(middle, t * 2) : middle.clone().lerp(end, (t - .5) * 2);
      const tip = origin.clone().add(new THREE.Vector3(Math.cos(angle)*spread, Math.sin(angle)*spread, spread*(.35+random()*.55)));
      tip.z = Math.min(tip.z, height * .955);
      branch(origin, tip, thickness * .40, depth - 1);
    }
  }
  for (let i = 0; i < 16; i++) {
    const level = .43 + i / 16 * .43;
    const angle = i * 2.399963 + (random() - .5) * .5;
    const spread = height * (.27 * Math.sin((level - .24) * Math.PI) + random() * .035) * (1 - (level - .43));
    const start = trunkCenter(height*level);
    const end = new THREE.Vector3(Math.cos(angle)*spread, Math.sin(angle)*spread, height*Math.min(.92, level+.12+random()*.045));
    branch(start, end, radius*(.32 - (level-.43)*.3), 2);
  }
  const woodGeometry = new THREE.BufferGeometry();
  woodGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  woodGeometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  woodGeometry.setIndex(indices); woodGeometry.computeVertexNormals();
  const trunk = new THREE.Mesh(woodGeometry, new THREE.MeshStandardMaterial({vertexColors:true, roughness:1}));
  trunk.name = 'Trunk, limbs and roots'; tree.add(trunk);

  // Folded, lobed leaf silhouette; instancing keeps the entire canopy one draw call.
  const outline = [[0,-1],[-.25,-.65],[-.55,-.5],[-.3,-.28],[-.65,-.08],[-.35,.12],[-.55,.35],[-.28,.48],[0,1],
    [.28,.48],[.55,.35],[.35,.12],[.65,-.08],[.3,-.28],[.55,-.5],[.25,-.65]];
  const leafVertices = [0,0,.12], leafIndices = [];
  outline.forEach(([x,y]) => leafVertices.push(x,y,0));
  outline.forEach((_,i) => leafIndices.push(0,i+1,(i+1)%outline.length+1));
  const leafGeometry = new THREE.BufferGeometry();
  leafGeometry.setAttribute('position',new THREE.Float32BufferAttribute(leafVertices,3));
  leafGeometry.setIndex(leafIndices); leafGeometry.computeVertexNormals();
  const leavesPerSpray = 55;
  const foliage = new THREE.InstancedMesh(leafGeometry,
    new THREE.MeshStandardMaterial({color:'#ffffff',roughness:.88,side:THREE.DoubleSide}), sprays.length*leavesPerSpray);
  const dummy = new THREE.Object3D(), leafColor = new THREE.Color();
  let index = 0;
  for (const spray of sprays) for (let i=0;i<leavesPerSpray;i++) {
    const angle=random()*Math.PI*2, z=random()*2-1, reach=Math.cbrt(random());
    const width=height*.052, radial=Math.sqrt(1-z*z)*reach;
    dummy.position.copy(spray.start).lerp(spray.end,random()).add(new THREE.Vector3(Math.cos(angle)*width*radial,Math.sin(angle)*width*radial,z*width*.64*reach));
    const size=height*(.010+random()*.005);
    dummy.position.z=Math.min(dummy.position.z,height-size);
    dummy.rotation.set(random()*Math.PI,random()*Math.PI,random()*Math.PI*2);
    dummy.scale.set(size*.85,size, size); dummy.updateMatrix();
    foliage.setMatrixAt(index,dummy.matrix);
    leafColor.setHSL(.20+random()*.065,.34+random()*.24,.20+random()*.16);
    foliage.setColorAt(index++,leafColor);
  }
  foliage.name='Oak foliage'; foliage.instanceMatrix.needsUpdate=true;
  foliage.computeBoundingBox(); foliage.computeBoundingSphere(); tree.add(foliage);
  tree.userData = {trunk_diameter, trunk_reference_height, seed};
  return tree;
}
