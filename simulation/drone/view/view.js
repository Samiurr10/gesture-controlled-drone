// PalmPilot flight view: the SITL drone's true state, drawn over a field.
// World axes: x = east, y = up, z = -north. The drone group's forward is -z, right +x.
// Data: live frames over SSE from demo_view.py, or a recorded tour (flight.json) for replay.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Sky } from 'three/addons/objects/Sky.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

const SOURCE = window.PALMPILOT_SOURCE || 'replay';
const OAK = { N: 35, E: 25 };            // demo_view.py's circuit centre
const PILOT_SPOT = { N: -14, E: -8 };
const WIND_FROM = 250;                   // demo_view.py WIND
const DEG = Math.PI / 180;
const $ = (id) => document.getElementById(id);

let seed = 11;
const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const world = (N, E, up = 0) => new THREE.Vector3(E, up, -N);

function hash(x, y) { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); }
function vnoise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function fbm(x, y, octaves = 4) {
  let s = 0, amp = 0.5, f = 1;
  for (let i = 0; i < octaves; i++) { s += amp * vnoise(x * f, y * f); f *= 2.03; amp *= 0.5; }
  return s;
}

// --- renderer, sky, light ----------------------------------------------------------------
const canvas = $('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.6;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const ANISO = renderer.capabilities.getMaxAnisotropy();

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 9000);
scene.fog = new THREE.Fog(0xc3d1dc, 320, 3200);

const sunDir = new THREE.Vector3().setFromSphericalCoords(1, (90 - 36) * DEG, 200 * DEG);
function makeSky(scale) {
  const s = new Sky();
  s.scale.setScalar(scale);
  const u = s.material.uniforms;
  u.turbidity.value = 4.5; u.rayleigh.value = 1.25; u.mieCoefficient.value = 0.004; u.mieDirectionalG.value = 0.8;
  u.sunPosition.value.copy(sunDir);
  return s;
}
scene.add(makeSky(40000));
const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
envScene.add(makeSky(1000));
scene.environment = pmrem.fromScene(envScene, 0.02).texture;

scene.add(new THREE.HemisphereLight(0xd6e6ff, 0x4f5e34, 1.1));
const sun = new THREE.DirectionalLight(0xfff0d8, 3.4);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -24, right: 24, top: 24, bottom: -24, near: 1, far: 260 });
sun.shadow.bias = -0.0002;
sun.shadow.normalBias = 0.03;
scene.add(sun, sun.target);

// --- textures ------------------------------------------------------------------------------
function canvasTexture(size, draw, { repeat = 1, srgb = true } = {}) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  draw(c.getContext('2d'), size);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat, repeat);
  t.anisotropy = ANISO;
  return t;
}
function wrapped(g, s, x, y, r, paint) {          // a blob drawn so the tile repeats seamlessly
  for (const dx of [-s, 0, s]) for (const dy of [-s, 0, s]) {
    if (x + dx + r < 0 || x + dx - r > s || y + dy + r < 0 || y + dy - r > s) continue;
    paint(x + dx, y + dy);
  }
}
const grassTex = canvasTexture(1024, (g, s) => {
  g.fillStyle = '#58783a'; g.fillRect(0, 0, s, s);
  for (let i = 0; i < 260; i++) {
    const x = rand() * s, y = rand() * s, r = 30 + rand() * 120;
    const tone = rand() < 0.5 ? '120,150,70' : '60,90,40';
    wrapped(g, s, x, y, r, (px, py) => {
      const grd = g.createRadialGradient(px, py, 0, px, py, r);
      grd.addColorStop(0, `rgba(${tone},0.16)`); grd.addColorStop(1, `rgba(${tone},0)`);
      g.fillStyle = grd; g.fillRect(px - r, py - r, 2 * r, 2 * r);
    });
  }
  for (let i = 0; i < 90000; i++) {
    const h = 78 + rand() * 30, sat = 30 + rand() * 25, l = 20 + rand() * 24;
    g.fillStyle = `hsl(${h},${sat}%,${l}%)`;
    g.fillRect(rand() * s, rand() * s, 1, 2 + rand() * 3);
  }
  for (let i = 0; i < 900; i++) {                   // the odd dry blade and clover leaf
    g.fillStyle = rand() < 0.7 ? 'rgba(196,186,120,0.5)' : 'rgba(230,236,210,0.55)';
    g.fillRect(rand() * s, rand() * s, 2, 2);
  }
}, { repeat: 1 });
const stripeTex = canvasTexture(256, (g, s) => {
  g.clearRect(0, 0, s, s);
  g.fillStyle = 'rgba(255,255,240,0.065)'; g.fillRect(0, 0, s / 2, s);
  g.fillStyle = 'rgba(0,20,0,0.045)'; g.fillRect(s / 2, 0, s / 2, s);
});
const padTex = canvasTexture(1024, (g, s) => {
  const c = s / 2;
  g.fillStyle = '#9b9a95'; g.fillRect(0, 0, s, s);
  for (let i = 0; i < 26000; i++) { const v = 120 + rand() * 60; g.fillStyle = `rgba(${v},${v},${v - 6},0.35)`; g.fillRect(rand() * s, rand() * s, 2, 2); }
  for (let i = 0; i < 14; i++) { g.strokeStyle = 'rgba(60,58,54,0.25)'; g.lineWidth = 1; g.beginPath(); let x = rand() * s, y = rand() * s; g.moveTo(x, y); for (let k = 0; k < 6; k++) { x += (rand() - 0.5) * 90; y += (rand() - 0.5) * 90; g.lineTo(x, y); } g.stroke(); }
  g.strokeStyle = '#f2b23a'; g.lineWidth = 34; g.beginPath(); g.arc(c, c, c - 40, 0, Math.PI * 2); g.stroke();
  g.strokeStyle = '#f4f4ef'; g.lineWidth = 16; g.beginPath(); g.arc(c, c, c - 110, 0, Math.PI * 2); g.stroke();
  g.fillStyle = '#f4f4ef'; const w = 60, h = 360, gap = 120;
  g.fillRect(c - gap - w / 2, c - h / 2, w, h); g.fillRect(c + gap - w / 2, c - h / 2, w, h); g.fillRect(c - gap, c - w / 2, 2 * gap, w);
});
const carbonTex = canvasTexture(128, (g, s) => {
  g.fillStyle = '#121416'; g.fillRect(0, 0, s, s);
  const n = 16, q = s / n;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const grd = (i + j) % 2 ? g.createLinearGradient(i * q, 0, (i + 1) * q, 0) : g.createLinearGradient(0, j * q, 0, (j + 1) * q);
    grd.addColorStop(0, '#1b1e22'); grd.addColorStop(0.5, '#2c3036'); grd.addColorStop(1, '#16181b');
    g.fillStyle = grd; g.fillRect(i * q + 0.5, j * q + 0.5, q - 1, q - 1);
  }
}, { repeat: 3 });
const glowTex = canvasTexture(128, (g, s) => {
  const grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.25, 'rgba(255,255,255,0.55)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.fillRect(0, 0, s, s);
});
const discTex = canvasTexture(256, (g, s) => {
  const c = s / 2;
  const grd = g.createRadialGradient(c, c, c * 0.12, c, c, c);
  grd.addColorStop(0, 'rgba(255,255,255,0)'); grd.addColorStop(0.2, 'rgba(255,255,255,0.55)');
  grd.addColorStop(0.85, 'rgba(255,255,255,0.35)'); grd.addColorStop(0.97, 'rgba(255,255,255,0.6)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.beginPath(); g.arc(c, c, c, 0, Math.PI * 2); g.fill();
});
const blobTex = canvasTexture(128, (g, s) => {
  const grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grd.addColorStop(0, 'rgba(0,0,0,0.55)'); grd.addColorStop(0.6, 'rgba(0,0,0,0.3)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grd; g.fillRect(0, 0, s, s);
}, { srgb: false });
const ringTex = canvasTexture(128, (g, s) => {
  g.strokeStyle = 'rgba(255,190,90,0.95)'; g.lineWidth = 6;
  g.beginPath(); g.arc(s / 2, s / 2, s / 2 - 10, 0, Math.PI * 2); g.stroke();
  g.fillStyle = 'rgba(255,190,90,0.95)'; g.beginPath(); g.arc(s / 2, s / 2, 7, 0, Math.PI * 2); g.fill();
});
const corrugatedTex = canvasTexture(256, (g, s) => {
  for (let x = 0; x < s; x++) { const v = 150 + 40 * Math.sin(x / s * Math.PI * 2 * 24); g.fillStyle = `rgb(${v},${v + 4},${v + 8})`; g.fillRect(x, 0, 1, s); }
  for (let i = 0; i < 400; i++) { g.fillStyle = 'rgba(110,80,50,0.12)'; g.fillRect(rand() * s, rand() * s, 2, 6 + rand() * 20); }
}, { repeat: 1 });
const sockTex = canvasTexture(256, (g, s) => {
  for (let i = 0; i < 5; i++) { g.fillStyle = i % 2 ? '#f5f2ea' : '#ef5a23'; g.fillRect(0, i * s / 5, s, s / 5); }
});

// --- ground and scenery ----------------------------------------------------------------
function buildGround() {
  const size = 9000, seg = 280;
  const geo = new THREE.PlaneGeometry(size, size, seg, seg);
  geo.rotateX(-Math.PI / 2);
  const p = geo.attributes.position, colors = new Float32Array(p.count * 3);
  const uv = geo.attributes.uv, tile = 5.5;
  const a = new THREE.Color('#e2ecd0'), b = new THREE.Color('#b9c79a'), dry = new THREE.Color('#d8d2a4'), c = new THREE.Color();
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i), r = Math.hypot(x, z);
    const hills = (fbm(x / 1100 + 3.1, z / 1100 - 7.4, 5) - 0.42) * 260 + fbm(x / 260, z / 260, 3) * 40;
    p.setY(i, hills * smooth(650, 1900, r));
    const n = fbm(x / 140, z / 140, 4), m = fbm(x / 40 + 9, z / 40, 2);
    c.copy(a).lerp(b, n).lerp(dry, smooth(0.62, 0.8, m) * 0.5);
    colors.set([c.r, c.g, c.b], i * 3);
    uv.setXY(i, x / tile, z / tile);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ map: grassTex, vertexColors: true, roughness: 0.96, metalness: 0 });
  const ground = new THREE.Mesh(geo, mat);
  ground.receiveShadow = true;
  scene.add(ground);

  const field = new THREE.Mesh(new THREE.PlaneGeometry(190, 150), new THREE.MeshBasicMaterial({ map: stripeTex, transparent: true, depthWrite: false }));
  field.rotation.x = -Math.PI / 2;
  field.position.copy(world(10, 10, 0.02));
  stripeTex.repeat.set(19, 1);
  scene.add(field);

  const pad = new THREE.Mesh(new THREE.CircleGeometry(3.2, 96), new THREE.MeshStandardMaterial({ map: padTex, roughness: 0.85 }));
  pad.rotation.x = -Math.PI / 2;
  pad.position.y = 0.035;
  pad.receiveShadow = true;
  scene.add(pad);

  const track = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 260), new THREE.MeshStandardMaterial({ color: 0x9d8b67, roughness: 1 }));
  track.rotation.x = -Math.PI / 2;
  track.position.copy(world(-40, -30, 0.025));
  track.rotation.z = 0.12;
  track.receiveShadow = true;
  scene.add(track);
}

function crownGeometry(lumps, detail, wobble) {
  const parts = [];
  for (let i = 0; i < lumps; i++) {
    const g = mergeVertices(new THREE.IcosahedronGeometry(1, detail));   // shared vertices: smooth normals
    const p = g.attributes.position;
    for (let k = 0; k < p.count; k++) {
      const v = new THREE.Vector3().fromBufferAttribute(p, k);
      const n = fbm(v.x * 2.1 + i * 3, v.y * 2.1 + v.z * 1.7, 3);
      v.multiplyScalar(1 + (n - 0.5) * wobble);
      p.setXYZ(k, v.x, v.y, v.z);
    }
    const s = i === 0 ? 1 : 0.55 + rand() * 0.3;
    g.scale(s, s * 0.85, s);
    if (i) g.translate((rand() - 0.5) * 1.1, (rand() - 0.3) * 0.7, (rand() - 0.5) * 1.1);
    parts.push(g);
  }
  const merged = mergeGeometries(parts);
  merged.computeVertexNormals();
  // Light from inside the crown is darker: shade by height and a little noise, as foliage self-shadows.
  const p = merged.attributes.position, col = new Float32Array(p.count * 3);
  for (let k = 0; k < p.count; k++) {
    const y = p.getY(k), n = fbm(p.getX(k) * 3 + 5, p.getZ(k) * 3 + y, 2);
    const v = clamp(0.55 + 0.35 * (y + 0.6) + (n - 0.5) * 0.5, 0.35, 1.15);
    col.set([v, v * 1.02, v * 0.95], k * 3);
  }
  merged.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return merged;
}

function buildTrees() {
  const leafMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.92, vertexColors: true });
  const pineMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95, vertexColors: true });
  const barkMat = new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 1 });
  const crown = crownGeometry(6, 3, 0.6);
  const pine = mergeGeometries([0, 1, 2].map((i) => {
    const g = new THREE.ConeGeometry(1 - i * 0.22, 1.1 - i * 0.15, 10, 3);
    g.translate(0, i * 0.55, 0);
    return g;
  }));
  pine.computeVertexNormals();
  const pp = pine.attributes.position, pc = new Float32Array(pp.count * 3);
  for (let k = 0; k < pp.count; k++) { const v = 0.45 + 0.35 * clamp(pp.getY(k) + 0.6, 0, 1.6) / 1.6 + (hash(k, 3) - 0.5) * 0.15; pc.set([v, v, v], k * 3); }
  pine.setAttribute('color', new THREE.BufferAttribute(pc, 3));
  const trunk = new THREE.CylinderGeometry(0.07, 0.11, 1, 7);
  trunk.translate(0, 0.5, 0);

  const spots = [];
  const edge = (n0, e0, n1, e1, count) => {
    for (let i = 0; i < count; i++) {
      const t = i / count + rand() * 0.02;
      spots.push([lerp(n0, n1, t) + (rand() - 0.5) * 7, lerp(e0, e1, t) + (rand() - 0.5) * 7, rand() < 0.75 ? 'leaf' : 'pine']);
    }
  };
  edge(95, -95, 95, 125, 46); edge(-80, -95, -80, 125, 40); edge(-80, 128, 95, 128, 38); edge(-80, -98, 95, -98, 30);
  for (let i = 0; i < 420; i++) {
    const r = 150 + Math.pow(rand(), 0.7) * 1400, a = rand() * Math.PI * 2;
    spots.push([r * Math.cos(a), r * Math.sin(a), rand() < 0.55 ? 'leaf' : 'pine']);
  }
  const keep = spots.filter(([n, e]) => Math.hypot(n + 70, e + 55) > 22 && Math.abs(e + 30 - (n + 40) * 0.12) > 6);
  const leaf = keep.filter((s) => s[2] === 'leaf'), pines = keep.filter((s) => s[2] === 'pine');
  const crowns = new THREE.InstancedMesh(crown, leafMat, leaf.length);
  const cones = new THREE.InstancedMesh(pine, pineMat, pines.length);
  const trunks = new THREE.InstancedMesh(trunk, barkMat, keep.length);
  const blobs = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }), keep.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), col = new THREE.Color();
  const shadowShift = new THREE.Vector3(-sunDir.x, 0, -sunDir.z).normalize();
  let ti = 0;
  const place = (list, mesh, kind) => list.forEach(([n, e], i) => {
    const h = kind === 'leaf' ? 7 + rand() * 7 : 9 + rand() * 9, w = kind === 'leaf' ? h * (0.32 + rand() * 0.12) : h * 0.2;
    const base = world(n, e, 0);
    const dist = Math.hypot(n, e);
    const ground = dist > 650 ? 0 : 0;
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), rand() * Math.PI * 2);
    const crownY = kind === 'leaf' ? h * 0.62 : h * 0.18;
    m.compose(base.clone().setY(ground + crownY), q, new THREE.Vector3(w, kind === 'leaf' ? h * 0.42 : h * 0.75, w));
    mesh.setMatrixAt(i, m);
    col.setHSL(kind === 'leaf' ? 0.24 + rand() * 0.06 : 0.33 + rand() * 0.04, 0.35 + rand() * 0.2, kind === 'leaf' ? 0.2 + rand() * 0.1 : 0.14 + rand() * 0.06);
    mesh.setColorAt(i, col);
    m.compose(base.clone().setY(ground), q, new THREE.Vector3(w * 0.6, kind === 'leaf' ? h * 0.55 : h * 0.3, w * 0.6));
    trunks.setMatrixAt(ti, m);
    m.compose(base.clone().addScaledVector(shadowShift, h * 0.35).setY(0.05), new THREE.Quaternion(), new THREE.Vector3(w * 2.8, 1, w * 2.8));
    blobs.setMatrixAt(ti, m);
    ti++;
  });
  place(leaf, crowns, 'leaf');
  place(pines, cones, 'pine');
  for (const mesh of [crowns, cones, trunks]) { mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh); }
  scene.add(blobs);

  // The oak the circuit goes round: larger and drawn on its own.
  const oak = new THREE.Group();
  const oakLeaf = new THREE.MeshStandardMaterial({ color: 0x4a6a2a, roughness: 0.9, vertexColors: true });
  const body = new THREE.Mesh(crownGeometry(9, 3, 0.5), oakLeaf);
  body.scale.set(6.4, 4.6, 6.4); body.position.y = 9.2;
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.75, 7.5, 12), barkMat);
  stem.position.y = 3.75;
  for (let i = 0; i < 4; i++) {
    const br = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.25, 4, 7), barkMat);
    br.position.set(Math.cos(i * 1.7) * 1.1, 6.6, Math.sin(i * 1.7) * 1.1);
    br.rotation.set(Math.sin(i * 1.7) * 0.7, 0, -Math.cos(i * 1.7) * 0.7);
    oak.add(br);
  }
  oak.add(body, stem);
  oak.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  oak.position.copy(world(OAK.N, OAK.E));
  scene.add(oak);
  const oakBlob = new THREE.Mesh(new THREE.PlaneGeometry(18, 18).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }));
  oakBlob.position.copy(world(OAK.N, OAK.E, 0.05)).addScaledVector(shadowShift, 4);
  scene.add(oakBlob);
}

function buildProps() {
  // Hangar at the field's south-west corner.
  const hangar = new THREE.Group();
  const wall = new THREE.MeshStandardMaterial({ map: corrugatedTex, roughness: 0.6, metalness: 0.5 });
  corrugatedTex.repeat.set(3, 1);
  const box = new THREE.Mesh(new THREE.BoxGeometry(26, 8, 16), wall);
  box.position.y = 4;
  const roofShape = new THREE.Shape();
  roofShape.moveTo(-8.6, 0); roofShape.lineTo(0, 3.6); roofShape.lineTo(8.6, 0); roofShape.lineTo(-8.6, 0);
  const roof = new THREE.Mesh(new THREE.ExtrudeGeometry(roofShape, { depth: 27, bevelEnabled: false }),
    new THREE.MeshStandardMaterial({ color: 0x6f3a2c, roughness: 0.7, metalness: 0.3 }));
  roof.rotation.y = Math.PI / 2; roof.position.set(-13.5, 8, 0);
  const door = new THREE.Mesh(new THREE.PlaneGeometry(12, 6.5), new THREE.MeshStandardMaterial({ color: 0x2c3036, roughness: 0.8 }));
  door.position.set(0, 3.25, 8.01);
  hangar.add(box, roof, door);
  hangar.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  hangar.position.copy(world(-70, -55));
  hangar.rotation.y = 0.5;
  scene.add(hangar);

  // Windsock, streaming downwind.
  const sock = new THREE.Group();
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.07, 6, 10), new THREE.MeshStandardMaterial({ color: 0xe8e8e2, roughness: 0.5, metalness: 0.4 }));
  pole.position.y = 3;
  const cone = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.14, 2.4, 20, 1, true), new THREE.MeshStandardMaterial({ map: sockTex, side: THREE.DoubleSide, roughness: 0.8 }));
  cone.rotation.z = Math.PI / 2;
  cone.position.x = 1.25;
  const arm = new THREE.Group();
  arm.position.y = 5.8;
  arm.add(cone);
  sock.add(pole, arm);
  sock.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  sock.position.copy(world(-9, 10));
  arm.rotation.y = -((WIND_FROM + 180) * DEG - Math.PI / 2);     // downwind bearing to the sock's +x
  scene.add(sock);

  // The pilot at the field edge, wearing the hand controllers.
  const person = new THREE.Group();
  const jeans = new THREE.MeshStandardMaterial({ color: 0x2f3e57, roughness: 0.9 });
  const jacket = new THREE.MeshStandardMaterial({ color: 0xff7a1f, roughness: 0.7 });
  const skin = new THREE.MeshStandardMaterial({ color: 0xc58c64, roughness: 0.7 });
  const glove = new THREE.MeshStandardMaterial({ color: 0x1d2227, roughness: 0.6 });
  for (const s of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.72, 4, 10), jeans);
    leg.position.set(s * 0.1, 0.45, 0);
    const armM = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.5, 4, 10), jacket);
    armM.position.set(s * 0.25, 1.22, -0.16); armM.rotation.x = -1.0;
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.06, 12, 10), glove);
    hand.position.set(s * 0.25, 1.07, -0.42);
    person.add(leg, armM, hand);
  }
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, 0.42, 6, 14), jacket);
  torso.position.y = 1.25;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 18, 14), skin);
  head.position.y = 1.66;
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.115, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x222831, roughness: 0.8 }));
  cap.position.y = 1.68;
  person.add(torso, head, cap);
  person.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  person.position.copy(world(PILOT_SPOT.N, PILOT_SPOT.E));
  person.lookAt(world(10, 10));
  person.rotateY(Math.PI);
  scene.add(person);

  // Traffic cones round the pad.
  const coneMat = new THREE.MeshStandardMaterial({ color: 0xff6b1a, roughness: 0.6 });
  for (let i = 0; i < 4; i++) {
    const c = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.45, 16), coneMat);
    const a = i * Math.PI / 2 + Math.PI / 4;
    c.position.set(Math.cos(a) * 4.6, 0.225, Math.sin(a) * 4.6);
    c.castShadow = true;
    scene.add(c);
  }
  return { sock: arm };
}

// --- the drone ------------------------------------------------------------------------------
// ArduPilot quad X: motor 1 front-right CCW, 2 rear-left CCW, 3 front-left CW, 4 rear-right CW.
const MOTORS = [{ bearing: 45, ccw: true }, { bearing: 225, ccw: true }, { bearing: 315, ccw: false }, { bearing: 135, ccw: false }];
const ARM_R = 0.175;                       // SITL --model x: 0.35 m motor to motor across the diagonal
const GEAR = 0.092;                        // body origin above the skids

function buildDrone() {
  const g = new THREE.Group();
  const carbon = new THREE.MeshPhysicalMaterial({ map: carbonTex, color: 0xffffff, roughness: 0.42, metalness: 0.15, clearcoat: 0.7, clearcoatRoughness: 0.25 });
  const shell = new THREE.MeshPhysicalMaterial({ color: 0x23272d, roughness: 0.3, metalness: 0.1, clearcoat: 1, clearcoatRoughness: 0.12 });
  const accent = new THREE.MeshStandardMaterial({ color: 0xff6a1a, roughness: 0.38 });
  const alu = new THREE.MeshStandardMaterial({ color: 0xb6bec7, metalness: 1, roughness: 0.26 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x0f1012, roughness: 0.6 });
  const glass = new THREE.MeshPhysicalMaterial({ color: 0x0b1a2a, metalness: 0.6, roughness: 0.05, clearcoat: 1 });

  const plate = new THREE.Mesh(new RoundedBoxGeometry(0.15, 0.006, 0.2, 2, 0.003), carbon);
  plate.position.y = -0.028;
  const body = new THREE.Mesh(new RoundedBoxGeometry(0.12, 0.05, 0.17, 5, 0.018), shell);
  const canopy = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), shell);
  canopy.scale.set(0.052, 0.026, 0.078); canopy.position.y = 0.024;
  const stripe = new THREE.Mesh(new RoundedBoxGeometry(0.016, 0.004, 0.12, 2, 0.002), accent);
  stripe.position.set(0, 0.051, -0.01);
  const nose = new THREE.Mesh(new RoundedBoxGeometry(0.05, 0.012, 0.012, 2, 0.004), accent);
  nose.position.set(0, 0.012, -0.088);
  const battery = new THREE.Mesh(new RoundedBoxGeometry(0.058, 0.034, 0.13, 3, 0.006), new THREE.MeshStandardMaterial({ color: 0x2a3a52, roughness: 0.55 }));
  battery.position.y = -0.05;
  const strap = new THREE.Mesh(new THREE.BoxGeometry(0.062, 0.036, 0.012), accent);
  strap.position.set(0, -0.05, 0.02);
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.06, 8), dark);
  mast.position.set(0, 0.075, 0.06);
  const gps = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.008, 24), new THREE.MeshStandardMaterial({ color: 0xdedfdc, roughness: 0.4 }));
  gps.position.set(0, 0.106, 0.06);
  const gimbal = new THREE.Mesh(new THREE.SphereGeometry(0.019, 24, 16), dark);
  gimbal.position.set(0, -0.04, -0.085);
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.009, 0.01, 20), glass);
  lens.rotation.x = Math.PI / 2; lens.position.set(0, -0.04, -0.104);
  g.add(plate, body, canopy, stripe, nose, battery, strap, mast, gps, gimbal, lens);

  for (const s of [-1, 1]) {                 // skids
    for (const f of [-1, 1]) {
      const strut = new THREE.Mesh(new THREE.CylinderGeometry(0.0035, 0.0035, 0.07, 8), dark);
      strut.position.set(s * 0.06, -0.06, f * 0.045);
      strut.rotation.z = s * 0.35;
      g.add(strut);
    }
    const skid = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.21, 10), dark);
    skid.rotation.x = Math.PI / 2; skid.position.set(s * 0.074, -GEAR + 0.004, 0);
    g.add(skid);
  }

  const props = [], leds = [];
  const bladeShape = new THREE.Shape();
  bladeShape.moveTo(0.008, -0.005);
  bladeShape.bezierCurveTo(0.035, -0.014, 0.08, -0.013, 0.112, -0.004);
  bladeShape.quadraticCurveTo(0.117, 0, 0.111, 0.004);
  bladeShape.bezierCurveTo(0.08, 0.009, 0.035, 0.011, 0.008, 0.005);
  bladeShape.closePath();
  const bladeGeo = new THREE.ExtrudeGeometry(bladeShape, { depth: 0.0014, bevelEnabled: true, bevelThickness: 0.0005, bevelSize: 0.0005, bevelSegments: 1, curveSegments: 18 });
  bladeGeo.rotateX(-Math.PI / 2);
  const discGeo = new THREE.CircleGeometry(0.116, 64).rotateX(-Math.PI / 2);

  MOTORS.forEach((m, i) => {
    const a = m.bearing * DEG, dir = new THREE.Vector3(Math.sin(a), 0, -Math.cos(a));
    const arm = new THREE.Mesh(new RoundedBoxGeometry(0.02, 0.013, ARM_R, 2, 0.004), carbon);
    arm.position.copy(dir).multiplyScalar(ARM_R / 2); arm.rotation.y = Math.PI - a;
    const mount = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.006, 24), carbon);
    mount.position.copy(dir).multiplyScalar(ARM_R).setY(0.006);
    const stator = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.017, 0.012, 24), dark);
    stator.position.copy(dir).multiplyScalar(ARM_R).setY(0.015);
    const bell = new THREE.Mesh(new THREE.CylinderGeometry(0.0185, 0.0185, 0.016, 32), alu);
    bell.position.copy(dir).multiplyScalar(ARM_R).setY(0.029);
    const capColor = m.ccw ? alu : accent;
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.008, 0.008, 16), capColor);
    cap.position.copy(dir).multiplyScalar(ARM_R).setY(0.044);
    g.add(arm, mount, stator, bell, cap);

    const prop = new THREE.Group();
    prop.position.copy(dir).multiplyScalar(ARM_R).setY(0.04);
    const bladeMat = new THREE.MeshStandardMaterial({ color: 0x1b1e23, roughness: 0.4, metalness: 0.1, side: THREE.DoubleSide, transparent: true });
    for (const k of [0, 1]) {
      const blade = new THREE.Mesh(bladeGeo, bladeMat);
      const holder = new THREE.Group();
      holder.rotation.y = k * Math.PI;
      blade.rotation.x = (m.ccw ? 1 : -1) * 11 * DEG;
      holder.add(blade);
      prop.add(holder);
    }
    const disc = new THREE.Mesh(discGeo, new THREE.MeshBasicMaterial({ map: discTex, color: 0x30343a, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
    disc.position.y = 0.001;
    g.add(prop, disc);
    disc.position.copy(prop.position);
    props.push({ group: prop, bladeMat, disc, dir: m.ccw ? 1 : -1, angle: rand() * 6 });

    const front = m.bearing === 45 || m.bearing === 315;
    const color = front ? 0xffffff : 0xff2a1a;
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.0045, 10, 8), new THREE.MeshBasicMaterial({ color }));
    led.position.copy(dir).multiplyScalar(ARM_R).setY(0.0);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.9 }));
    glow.scale.setScalar(front ? 0.05 : 0.06);
    glow.position.copy(led.position);
    g.add(led, glow);
    leds.push({ glow, front });
  });
  const status = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: 0xffb547, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  status.scale.setScalar(0.035);
  status.position.set(0, 0.03, 0.08);
  g.add(status);

  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  props.forEach((p) => { p.disc.castShadow = false; });
  scene.add(g);
  return { group: g, props, leds, status };
}

// --- overlays in the scene: trail, drop line, locator ---------------------------------------
const TRAIL_MAX = 1800;
const trailGeo = new THREE.BufferGeometry();
trailGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(TRAIL_MAX * 3), 3));
trailGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(TRAIL_MAX * 3), 3));
const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.85 }));
trail.frustumCulled = false;
const trailPts = [];
const dropGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
const drop = new THREE.Line(dropGeo, new THREE.LineDashedMaterial({ color: 0x74d0ff, dashSize: 0.3, gapSize: 0.2, transparent: true, opacity: 0.7 }));
drop.frustumCulled = false;
const footRing = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.34, 48).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x74d0ff, transparent: true, opacity: 0.6, depthWrite: false }));
const locator = new THREE.Sprite(new THREE.SpriteMaterial({ map: ringTex, sizeAttenuation: false, depthTest: false, transparent: true }));
locator.scale.setScalar(0.04);
locator.renderOrder = 10;
scene.add(trail, drop, footRing, locator);

function pushTrail(p) {
  const last = trailPts[trailPts.length - 1];
  if (last && last.distanceTo(p) < 0.12) return;
  trailPts.push(p.clone());
  if (trailPts.length > TRAIL_MAX) trailPts.shift();
  const pos = trailGeo.attributes.position, col = trailGeo.attributes.color, n = trailPts.length;
  const fresh = new THREE.Color(0xffb547), old = new THREE.Color(0x24313c), c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    pos.setXYZ(i, trailPts[i].x, trailPts[i].y, trailPts[i].z);
    c.copy(old).lerp(fresh, Math.pow(i / Math.max(1, n - 1), 1.6));
    col.setXYZ(i, c.r, c.g, c.b);
  }
  pos.needsUpdate = col.needsUpdate = true;
  trailGeo.setDrawRange(0, n);
}

// --- data: live or replay -------------------------------------------------------------------
const frames = [];
let playhead = null, playing = true, speed = 1;

function sample(t) {
  if (!frames.length) return null;
  let lo = 0, hi = frames.length - 1;
  if (t <= frames[0].t) return frames[0];
  if (t >= frames[hi].t) return frames[hi];
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (frames[mid].t <= t) lo = mid; else hi = mid; }
  const a = frames[lo], b = frames[hi], k = (t - a.t) / Math.max(1e-6, b.t - a.t);
  const mix = (x, y) => x.map((v, i) => lerp(v, y[i], k));
  const att = [lerp(a.att[0], b.att[0], k), lerp(a.att[1], b.att[1], k),
    a.att[2] + (((b.att[2] - a.att[2] + 540) % 360) - 180) * k];
  return { ...a, pos: mix(a.pos, b.pos), vel: mix(a.vel, b.vel), att,
    motors: a.motors && b.motors ? mix(a.motors, b.motors) : a.motors,
    hands: a.hands && b.hands ? {
      enable: a.hands.enable,
      left: { curl: lerp(a.hands.left.curl, b.hands.left.curl, k), roll: lerp(a.hands.left.roll, b.hands.left.roll, k) },
      right: { roll: lerp(a.hands.right.roll, b.hands.right.roll, k), pitch: lerp(a.hands.right.pitch, b.hands.right.pitch, k) },
    } : a.hands };
}

function connectLive() {
  $('note').textContent = 'Live from ArduCopter SITL. The drone moves only from ArduCopter\'s motor outputs through ArduPilot\'s physics.';
  const es = new EventSource('/state');
  es.onmessage = (ev) => {
    const f = JSON.parse(ev.data);
    if (f.t === undefined) return;
    frames.push(f);
    while (frames.length && frames[0].t < f.t - 4) frames.shift();
  };
  es.onerror = () => { $('wait-title').textContent = 'Lost the connection to demo_view.py'; $('wait-sub').textContent = 'Retrying…'; $('wait').hidden = false; };
}

async function loadReplay() {
  $('replay').hidden = false;
  $('wait-title').textContent = 'Loading the recorded flight…';
  $('wait-sub').textContent = 'One tour of ArduCopter SITL flown by the virtual pilot.';
  const res = await fetch('flight.json');
  const data = await res.json();
  frames.push(...data);
  playhead = frames[0].t;
  $('note').textContent = 'Recorded from ArduCopter SITL. The drone moves only from ArduCopter\'s motor outputs through ArduPilot\'s physics; the hands are a scripted virtual pilot.';
  const scrub = $('scrub');
  scrub.addEventListener('input', () => {
    playhead = lerp(frames[0].t, frames[frames.length - 1].t, scrub.value / 1000);
    trailPts.length = 0;
  });
  $('play').addEventListener('click', () => { playing = !playing; $('play').textContent = playing ? 'Pause' : 'Play'; });
  const speeds = [1, 2, 4, 0.5];
  $('speed').addEventListener('click', () => { speed = speeds[(speeds.indexOf(speed) + 1) % speeds.length]; $('speed').textContent = `${speed}×`; });
}

// --- cameras --------------------------------------------------------------------------------
const controls = new OrbitControls(camera, canvas);
controls.enabled = false;
controls.enableDamping = true;
controls.minDistance = 0.8;
controls.maxDistance = 120;
controls.maxPolarAngle = Math.PI * 0.495;
let camMode = 'cine';
const lookAt = new THREE.Vector3(0, 0.5, 0);
const shot = { kind: 'chase', until: 0, anchor: new THREE.Vector3(), angle: 0 };
const SHOTS = ['chase', 'tripod', 'pilot', 'circle', 'chase', 'wide', 'tripod'];
let shotIndex = 0;

function setCam(mode) {
  camMode = mode;
  document.querySelectorAll('.cams button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.cam === mode)));
  controls.enabled = mode === 'orbit';
  camera.up.set(0, 1, 0);
  if (mode === 'orbit') { controls.target.copy(dronePos); camera.position.copy(dronePos).add(new THREE.Vector3(3, 1.6, 4)); }
  shot.until = 0;
}
document.querySelectorAll('.cams button').forEach((b) => b.addEventListener('click', () => setCam(b.dataset.cam)));
window.addEventListener('keydown', (e) => {
  const m = { 1: 'cine', 2: 'chase', 3: 'pilot', 4: 'orbit', 5: 'top' }[e.key];
  if (m) setCam(m);
  if (e.key === ' ' && SOURCE === 'replay') { e.preventDefault(); $('play').click(); }
});

const dronePos = new THREE.Vector3(0, GEAR, 0);
let heading = 0;
function behind(dist, up, yawDeg) {
  return new THREE.Vector3(0, up, dist).applyAxisAngle(new THREE.Vector3(0, 1, 0), -yawDeg * DEG).add(dronePos);
}

function updateCamera(dt, now, f) {
  const follow = 1 - Math.exp(-dt * 2.6), aim = 1 - Math.exp(-dt * 6);
  const yaw = f ? f.att[2] : 0;
  let kind = camMode, fov = 50;
  if (camMode === 'cine') {
    if (now > shot.until) {
      shot.kind = SHOTS[shotIndex++ % SHOTS.length];
      shot.until = now + (shot.kind === 'chase' ? 11 : shot.kind === 'tripod' ? 6 : 8);
      const side = rand() < 0.5 ? -1 : 1;
      shot.anchor.copy(behind(-9, 0, yaw + side * 55)).setY(Math.max(1.1, dronePos.y * 0.4 + 1));
      shot.angle = Math.atan2(camera.position.z - dronePos.z, camera.position.x - dronePos.x);
      if (shot.kind === 'chase') camera.position.copy(behind(3.2, 0.9, yaw));
      if (shot.kind === 'tripod') camera.position.copy(shot.anchor);
    }
    kind = shot.kind;
  }
  const dist = camera.position.distanceTo(dronePos);
  if (kind === 'chase') {
    const want = behind(2.3 + clamp(Math.hypot(f?.vel[0] || 0, f?.vel[1] || 0) * 0.12, 0, 1.2), 0.7, yaw);
    want.y = Math.max(want.y, 0.35);
    camera.position.lerp(want, 1 - Math.exp(-dt * 5.5));        // stiff, so it stays behind in fast turns
    lookAt.lerp(dronePos.clone().add(new THREE.Vector3(0, 0.15, 0)), aim);
    fov = 55;
  } else if (kind === 'pilot') {
    camera.position.copy(world(PILOT_SPOT.N, PILOT_SPOT.E, 1.68));
    lookAt.lerp(dronePos, aim);
    fov = clamp(2 * Math.atan(5.5 / dist) / DEG, 12, 58);
  } else if (kind === 'tripod') {
    lookAt.lerp(dronePos, aim);
    fov = clamp(2 * Math.atan(4.5 / dist) / DEG, 10, 60);
  } else if (kind === 'circle') {
    shot.angle += dt * 0.22;
    const want = dronePos.clone().add(new THREE.Vector3(Math.cos(shot.angle) * 5.5, 1.6, Math.sin(shot.angle) * 5.5));
    want.y = Math.max(want.y, 0.4);
    camera.position.lerp(want, follow);
    lookAt.lerp(dronePos, aim);
    fov = 45;
  } else if (kind === 'wide') {
    const want = world(-55, -60, 22);
    camera.position.lerp(want, follow);
    lookAt.lerp(dronePos.clone().multiplyScalar(0.6), aim);
    fov = 46;
  } else if (kind === 'top') {
    camera.up.set(0, 0, -1);
    camera.position.lerp(dronePos.clone().add(new THREE.Vector3(0, 14, 0.001)), follow);
    lookAt.lerp(dronePos, aim);
    fov = 50;
  } else if (kind === 'orbit') {
    const delta = dronePos.clone().sub(controls.target);
    controls.target.add(delta); camera.position.add(delta);
    controls.update();
    fov = 50;
  }
  if (kind !== 'orbit') camera.lookAt(lookAt);
  if (kind !== 'top') camera.up.set(0, 1, 0);
  camera.fov = lerp(camera.fov, fov, 1 - Math.exp(-dt * 3));
  camera.updateProjectionMatrix();
}

// --- instruments ----------------------------------------------------------------------------
const ah = $('ah').getContext('2d'), tape = $('tape').getContext('2d');
function drawHorizon(roll, pitch) {
  const s = 224, c = s / 2, ppd = 3.2;
  ah.save();
  ah.clearRect(0, 0, s, s);
  ah.beginPath(); ah.arc(c, c, c - 1, 0, Math.PI * 2); ah.clip();
  ah.translate(c, c); ah.rotate(-roll * DEG); ah.translate(0, pitch * ppd);
  const skyG = ah.createLinearGradient(0, -s, 0, 0); skyG.addColorStop(0, '#1f5f9e'); skyG.addColorStop(1, '#6fb2e6');
  ah.fillStyle = skyG; ah.fillRect(-s, -s * 2, s * 2, s * 2);
  const gnd = ah.createLinearGradient(0, 0, 0, s); gnd.addColorStop(0, '#8a5a2e'); gnd.addColorStop(1, '#4a2f17');
  ah.fillStyle = gnd; ah.fillRect(-s, 0, s * 2, s * 2);
  ah.strokeStyle = '#fff'; ah.lineWidth = 2; ah.beginPath(); ah.moveTo(-s, 0); ah.lineTo(s, 0); ah.stroke();
  ah.font = '600 15px JetBrains Mono, monospace'; ah.fillStyle = '#fff'; ah.textAlign = 'left'; ah.textBaseline = 'middle';
  for (let p = -30; p <= 30; p += 5) {
    if (!p) continue;
    const y = -p * ppd, w = p % 10 ? 18 : 36;
    ah.lineWidth = 1.5; ah.beginPath(); ah.moveTo(-w, y); ah.lineTo(w, y); ah.stroke();
    if (!(p % 10)) ah.fillText(String(Math.abs(p)), w + 5, y);
  }
  ah.restore();
  ah.save(); ah.translate(c, c);
  ah.strokeStyle = 'rgba(255,255,255,0.8)'; ah.lineWidth = 2;
  for (const a of [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60]) {
    ah.save(); ah.rotate(a * DEG); ah.beginPath(); ah.moveTo(0, -c + 4); ah.lineTo(0, -c + (a % 30 ? 12 : 20)); ah.stroke(); ah.restore();
  }
  ah.save(); ah.rotate(-roll * DEG); ah.fillStyle = '#ffb547'; ah.beginPath(); ah.moveTo(0, -c + 22); ah.lineTo(-8, -c + 36); ah.lineTo(8, -c + 36); ah.fill(); ah.restore();
  ah.strokeStyle = '#ffb547'; ah.lineWidth = 5; ah.lineCap = 'round';
  ah.beginPath(); ah.moveTo(-58, 0); ah.lineTo(-22, 0); ah.lineTo(-12, 10); ah.moveTo(58, 0); ah.lineTo(22, 0); ah.lineTo(12, 10); ah.stroke();
  ah.fillStyle = '#ffb547'; ah.beginPath(); ah.arc(0, 0, 4, 0, Math.PI * 2); ah.fill();
  ah.restore();
}
function drawTape(yaw) {
  const w = 460, h = 60, ppd = 4;
  tape.clearRect(0, 0, w, h);
  tape.fillStyle = 'rgba(0,0,0,0.25)'; tape.fillRect(0, 0, w, h);
  tape.strokeStyle = 'rgba(255,255,255,0.75)'; tape.fillStyle = '#eef2f6';
  tape.font = '600 20px Barlow Semi Condensed, sans-serif'; tape.textAlign = 'center';
  const hdg = (yaw + 360) % 360;
  for (let d = Math.floor((hdg - 60) / 5) * 5; d <= hdg + 60; d += 5) {
    const x = w / 2 + (d - hdg) * ppd, n = ((d % 360) + 360) % 360;
    tape.lineWidth = n % 30 ? 1.5 : 2.5;
    tape.beginPath(); tape.moveTo(x, h); tape.lineTo(x, h - (n % 10 ? 10 : 18)); tape.stroke();
    if (!(n % 30)) tape.fillText({ 0: 'N', 90: 'E', 180: 'S', 270: 'W' }[n] ?? String(n / 10).padStart(2, '0'), x, 24);
  }
  tape.fillStyle = '#ffb547'; tape.beginPath(); tape.moveTo(w / 2 - 9, 0); tape.lineTo(w / 2 + 9, 0); tape.lineTo(w / 2, 12); tape.fill();
  tape.font = '600 18px JetBrains Mono, monospace'; tape.fillText(String(Math.round(hdg) % 360).padStart(3, '0') + '°', w / 2, 50);
}

const motorBox = $('motors');
const MOTOR_ORDER = [[2, 'FL'], [0, 'FR'], [1, 'RL'], [3, 'RR']];
motorBox.innerHTML = MOTOR_ORDER.map(([, l]) => `<div class="motor"><div class="bar"><span></span></div><label>${l}</label><output>—</output></div>`).join('');
const motorEls = [...motorBox.querySelectorAll('.motor')];

// The gloves: back of each hand, flex strips on the four fingers, the IMU board on the back.
function glove(curl, roll, pitch, mirror) {
  const fingers = [[-20, 2], [-7, 6], [6, 5], [19, -1]];
  const k = mirror ? -1 : 1, flex = Math.round(100 + 155 * curl);
  const f = fingers.map(([x, lift], i) => {
    const len = (34 + lift) * (1 - 0.68 * curl), knuckle = -14;
    const fx = x * k;
    return `<g><rect x="${fx - 6}" y="${knuckle - len}" width="12" height="${len + 8}" rx="6" fill="#2b333c" stroke="#3f4a56"/>
      <rect x="${fx - 1.4}" y="${knuckle - len + 5}" width="2.8" height="${Math.max(2, len - 2)}" rx="1.4" fill="rgb(255,${flex},60)" opacity="${0.55 + 0.45 * curl}"/></g>`;
  }).join('');
  const thumb = `<rect x="${k * 26}" y="2" width="11" height="30" rx="5.5" fill="#2b333c" stroke="#3f4a56" transform="rotate(${k * -38} ${k * 30} 26)"/>`;
  const sy = Math.max(0.35, Math.cos((pitch || 0) * DEG));
  return `<g transform="rotate(${roll || 0}) scale(1 ${sy.toFixed(3)})">
    <rect x="-28" y="-16" width="56" height="58" rx="16" fill="#252c34" stroke="#3f4a56"/>
    ${thumb}${f}
    <rect x="-11" y="6" width="22" height="16" rx="3" fill="#0e3a4a" stroke="#74d0ff" stroke-width="1"/>
    <circle cx="${k * 6}" cy="14" r="2" fill="#74d0ff"/>
  </g>
  <line x1="-62" y1="0" x2="62" y2="0" stroke="rgba(255,255,255,0.12)" stroke-dasharray="3 4"/>`;
}

let hudDue = 0;
function updateHud(f) {
  if (!f) return;
  const [N, E, alt] = f.pos, [vN, vE, vD] = f.vel, [roll, pitch, yaw] = f.att;
  drawHorizon(roll, pitch);
  drawTape(yaw);
  $('t-clock').textContent = `t ${f.t.toFixed(1)} s`;
  $('r-alt').innerHTML = `${alt.toFixed(1)}<small>m</small>`;
  $('r-vs').innerHTML = `${(-vD >= 0 ? '+' : '') + (-vD).toFixed(1)}<small>m/s</small>`;
  $('r-gs').innerHTML = `${Math.hypot(vN, vE).toFixed(1)}<small>m/s</small>`;
  $('r-dist').innerHTML = `${Math.hypot(N, E).toFixed(0)}<small>m</small>`;
  if (f.est) {
    const dr = f.est[0] - roll, dp = f.est[1] - pitch, sgn = (v) => (v >= 0 ? '+' : '') + v.toFixed(1);
    $('r-est').innerHTML = `Estimate − truth: <b>roll ${sgn(dr)}°</b> · <b>pitch ${sgn(dp)}°</b>`;
  }
  if (f.motors) MOTOR_ORDER.forEach(([i], j) => {
    const us = f.motors[i];
    motorEls[j].querySelector('span').style.height = `${clamp((us - 1000) / 10, 0, 100)}%`;
    motorEls[j].querySelector('output').textContent = Math.round(us);
  });
  const chip = (id, cls, text) => { const el = $(id); el.className = `chip glass ${cls}`; el.querySelector('span').textContent = text; };
  chip('chip-arm', f.armed ? 'ok' : '', f.armed ? 'Armed' : 'Disarmed');
  chip('chip-mode', /RTL|LAND/.test(f.mode) ? 'warn' : f.armed ? 'ok' : '', f.mode);
  const valid = f.cmd && f.cmd.valid;
  chip('chip-hub', valid ? (f.sending ? 'ok' : 'warn') : 'bad', valid ? 'Hub command valid' : 'Hub command invalid');
  chip('chip-rtf', f.rtf && Math.abs(f.rtf - 1) < 0.03 ? 'ok' : 'warn', f.rtf ? `${f.rtf.toFixed(2)}× real time` : 'real time —');
  chip('chip-src', SOURCE === 'replay' ? 'warn' : 'ok', SOURCE === 'replay' ? 'Recorded tour' : f.source === 'hub' ? 'Physical hub' : 'Virtual pilot');
  $('caption').textContent = f.caption || '';
  const recent = (f.texts || []).filter(([t]) => f.t - t < 8);       // a message stays up 8 s
  const msg = recent.length ? recent[recent.length - 1][1] : '';
  $('msgs').textContent = msg ? `ArduCopter: ${msg}` : '';
  const en = f.hands ? f.hands.enable : valid;
  $('enable').className = `enable${en ? ' on' : ''}`;
  if (f.hands) {
    const { left, right } = f.hands;
    $('hand-left').innerHTML = glove(left.curl, left.roll, 0, true);
    $('hand-right').innerHTML = glove(0.12, right.roll, right.pitch, false);
    $('v-left').innerHTML = `curl ${(left.curl * 100).toFixed(0)}% → throttle<br>roll ${left.roll >= 0 ? '+' : ''}${left.roll.toFixed(0)}° → yaw`;
    $('v-right').innerHTML = `roll ${right.roll >= 0 ? '+' : ''}${right.roll.toFixed(0)}° → roll<br>pitch ${right.pitch >= 0 ? '+' : ''}${right.pitch.toFixed(0)}° → pitch`;
  } else {
    $('hands-row').innerHTML = '<div class="pipe" style="grid-column:1/-1">A physical hub sends commands, not hand poses. The sticks below are its command.</div>';
  }
  if (f.cmd) {
    const dot = (id, x, y) => { const b = $(id).querySelector('b'); b.style.left = `${50 + x * 42}%`; b.style.top = `${50 - y * 42}%`; };
    dot('stick-left', f.cmd.yaw, f.cmd.throttle * 2 - 1);
    dot('stick-right', f.cmd.roll, f.cmd.pitch);
    $('cmd-valid').textContent = valid ? `thr ${(f.cmd.throttle * 100).toFixed(0)}%` : 'invalid';
  }
}

// --- main loop --------------------------------------------------------------------------------
buildGround();
buildTrees();
const scenery = buildProps();
const drone = buildDrone();
camera.position.set(-5, 3.2, 7);
lookAt.set(0, 0.6, 0);

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

let last = performance.now();
function frame(nowMs) {
  const dt = Math.min(0.1, (nowMs - last) / 1000);
  last = nowMs;
  const now = nowMs / 1000;
  let f = null;
  if (frames.length) {
    const newest = frames[frames.length - 1].t;
    if (SOURCE === 'live') {
      const target = newest - 0.12;
      if (playhead === null || Math.abs(playhead - target) > 0.4) playhead = target;
      playhead += dt + (target - playhead) * 0.05;
    } else if (playing) {
      playhead += dt * speed;
      if (playhead > newest) { playhead = frames[0].t; trailPts.length = 0; }
      $('scrub').value = String(Math.round(1000 * (playhead - frames[0].t) / (newest - frames[0].t)));
      const el = playhead - frames[0].t;
      $('rt').textContent = `${Math.floor(el / 60)}:${String(Math.floor(el % 60)).padStart(2, '0')}`;
    }
    f = sample(playhead);
    $('wait').hidden = true;
  }
  if (f) {
    const [N, E, alt] = f.pos, [roll, pitch, yaw] = f.att;
    dronePos.copy(world(N, E, alt + GEAR));
    drone.group.position.copy(dronePos);
    drone.group.rotation.set(pitch * DEG, -yaw * DEG, -roll * DEG, 'YXZ');
    heading = yaw;
    if (f.motors) drone.props.forEach((p, i) => {
      const spin = clamp((f.motors[i] - 1000) / 1000, 0, 1);
      p.angle += p.dir * spin * 62 * dt;
      p.group.rotation.y = p.angle;
      p.bladeMat.opacity = 1 - 0.78 * smooth(0.12, 0.45, spin);
      p.disc.material.opacity = 0.5 * smooth(0.08, 0.4, spin);
    });
    if (f.armed || alt > 0.2) pushTrail(dronePos.clone().setY(dronePos.y - GEAR + 0.05));
    drop.geometry.attributes.position.setXYZ(0, dronePos.x, dronePos.y - GEAR, dronePos.z);
    drop.geometry.attributes.position.setXYZ(1, dronePos.x, 0.05, dronePos.z);
    drop.geometry.attributes.position.needsUpdate = true;
    drop.computeLineDistances();
    drop.visible = footRing.visible = alt > 0.6;
    footRing.position.set(dronePos.x, 0.06, dronePos.z);
    footRing.scale.setScalar(1 + alt * 0.04);
    drone.status.material.color.set(f.armed ? 0x5fe39a : 0xffb547);
    if (now > hudDue) { updateHud(f); hudDue = now + 1 / 15; }
  }
  const blink = (now % 1.2) < 0.08;
  drone.leds.forEach((l) => { l.glow.material.opacity = l.front ? 0.85 : blink ? 1 : 0.35; });
  scenery.sock.rotation.z = Math.sin(now * 2.3) * 0.05 + Math.sin(now * 5.1) * 0.02;

  updateCamera(dt, now, f);
  const camDist = camera.position.distanceTo(dronePos);
  locator.position.copy(dronePos);
  locator.visible = camDist / (camera.fov * DEG) > 40;
  sun.position.copy(dronePos).addScaledVector(sunDir, 120);
  sun.target.position.copy(dronePos);
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

if (SOURCE === 'live') connectLive(); else loadReplay().catch((e) => { $('wait-title').textContent = 'Could not load the recorded flight'; $('wait-sub').textContent = String(e); });
requestAnimationFrame(frame);
