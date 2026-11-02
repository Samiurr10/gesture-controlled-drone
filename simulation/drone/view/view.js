// PalmPilot flight view: the SITL drone's true state, drawn over a field.
// World axes: x = east, y = up, z = -north. The drone group's forward is -z, right +x.
// Data: live frames over SSE from demo_view.py, or a recorded tour (flight.json) for replay.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Sky } from 'three/addons/objects/Sky.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const SOURCE = window.PALMPILOT_SOURCE || 'replay';
const OAK = { N: 35, E: 25 };            // demo_view.py's circuit centre
const PILOT_SPOT = { N: -14, E: -8 };
const WIND_FROM = 250;                   // demo_view.py WIND
const FIELD = { x: 10, z: -10, hx: 95, hz: 75 };          // mown field, world coordinates
const TRACK = { x: -30, z: 40, angle: 0.12, half: 1.7 };  // farm track: a point, its tilt from north-south, half width
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
const GLSL_NOISE = `
float pHash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float pNoise(vec2 p) { vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(pHash(i), pHash(i + vec2(1.0, 0.0)), u.x), mix(pHash(i + vec2(0.0, 1.0)), pHash(i + vec2(1.0, 1.0)), u.x), u.y); }
float pFbm(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * pNoise(p); p = p * 2.03 + vec2(17.1, 9.2); a *= 0.5; } return s; }
`;

// --- renderer, sky, light ----------------------------------------------------------------
const canvas = $('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
let pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
renderer.setPixelRatio(pixelRatio);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.5;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const ANISO = renderer.capabilities.getMaxAnisotropy();

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 12000);
const HAZE = new THREE.Color(0xb7c8d8);
scene.fog = new THREE.FogExp2(HAZE, 0.00042);

const sunDir = new THREE.Vector3().setFromSphericalCoords(1, (90 - 38) * DEG, 200 * DEG);
function makeSky(scale) {
  const s = new Sky();
  s.scale.setScalar(scale);
  const u = s.material.uniforms;
  u.turbidity.value = 3.2; u.rayleigh.value = 1.1; u.mieCoefficient.value = 0.003; u.mieDirectionalG.value = 0.85;
  u.sunPosition.value.copy(sunDir);
  return s;
}
scene.add(makeSky(45000));
const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
envScene.add(makeSky(1000));
scene.environment = pmrem.fromScene(envScene, 0.03).texture;

scene.add(new THREE.HemisphereLight(0xcfe0f5, 0x46502c, 1.25));
const sun = new THREE.DirectionalLight(0xfff1dc, 4.2);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -32, right: 32, top: 32, bottom: -32, near: 1, far: 320 });
sun.shadow.bias = -0.00025;
sun.shadow.normalBias = 0.04;
scene.add(sun, sun.target);

const U = {                                     // shared by the grass, leaves and clouds
  uTime: { value: 0 }, uCam: { value: new THREE.Vector3() }, uDrone: { value: new THREE.Vector3(0, -50, 0) },
  uWash: { value: 0 }, uWind: { value: new THREE.Vector2(Math.sin((WIND_FROM + 180) * DEG), -Math.cos((WIND_FROM + 180) * DEG)) },
};

// --- textures ------------------------------------------------------------------------------
function canvasTexture(size, draw, { repeat = 1, srgb = true, w = size, h = size } = {}) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat, repeat);
  t.anisotropy = ANISO;
  return t;
}
// A cluster of broad leaves, the way a leaf card in a game engine is painted.
const leafTex = canvasTexture(512, (g, s) => {
  g.clearRect(0, 0, s, s);
  for (let i = 0; i < 420; i++) {
    const r = Math.sqrt(rand()) * s * 0.44, a = rand() * Math.PI * 2;
    const x = s / 2 + Math.cos(a) * r, y = s / 2 + Math.sin(a) * r * 0.92;
    const len = 14 + rand() * 16, wid = len * (0.45 + rand() * 0.15), rot = rand() * Math.PI;
    const l = 20 + rand() * 26 - (1 - r / (s * 0.44)) * 8;
    g.save(); g.translate(x, y); g.rotate(rot);
    g.fillStyle = `hsl(${88 + rand() * 26}, ${42 + rand() * 22}%, ${l}%)`;
    g.beginPath(); g.ellipse(0, 0, len / 2, wid / 2, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = `hsla(80, 30%, ${l + 14}%, 0.5)`; g.lineWidth = 1;
    g.beginPath(); g.moveTo(-len / 2, 0); g.lineTo(len / 2, 0); g.stroke();
    g.restore();
  }
  g.strokeStyle = 'rgba(70,50,30,0.8)'; g.lineWidth = 3;
  for (let i = 0; i < 6; i++) { const a = rand() * Math.PI * 2; g.beginPath(); g.moveTo(s / 2, s / 2); g.lineTo(s / 2 + Math.cos(a) * s * 0.3, s / 2 + Math.sin(a) * s * 0.3); g.stroke(); }
});
// Spruce needles on a drooping branch.
const needleTex = canvasTexture(512, (g, w, h) => {
  g.clearRect(0, 0, w, h);
  g.strokeStyle = '#3b2b1e'; g.lineWidth = 6; g.beginPath(); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
  for (let i = 0; i < 2600; i++) {
    const x = rand() * w, spread = (1 - x / w) * 0.75 + 0.25, y = h / 2 + (rand() - 0.5) * h * 0.9 * spread;
    const l = 10 + rand() * 18;
    g.strokeStyle = `hsl(${120 + rand() * 25}, ${25 + rand() * 25}%, ${12 + rand() * 18}%)`; g.lineWidth = 1.6;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + l * 0.8, y + (y < h / 2 ? -l : l) * 0.35); g.stroke();
  }
}, { w: 512, h: 256 });
const barkTex = canvasTexture(256, (g, s) => {
  g.fillStyle = '#4a3b2d'; g.fillRect(0, 0, s, s);
  for (let i = 0; i < 900; i++) {
    const x = rand() * s, v = 40 + rand() * 50;
    g.fillStyle = `rgba(${v + 20},${v + 8},${v - 6},0.35)`; g.fillRect(x, rand() * s, 1 + rand() * 3, 20 + rand() * 80);
  }
  for (let i = 0; i < 200; i++) { g.fillStyle = 'rgba(20,14,10,0.35)'; g.fillRect(rand() * s, rand() * s, 2, 30 + rand() * 60); }
}, { repeat: 1 });
const padTex = canvasTexture(1024, (g, s) => {
  const c = s / 2;
  g.fillStyle = '#8f8e8a'; g.fillRect(0, 0, s, s);
  for (let i = 0; i < 40000; i++) { const v = 110 + rand() * 70; g.fillStyle = `rgba(${v},${v},${v - 5},0.3)`; g.fillRect(rand() * s, rand() * s, 2, 2); }
  for (let i = 0; i < 30; i++) { const x = rand() * s, y = rand() * s, r = 20 + rand() * 80; const grd = g.createRadialGradient(x, y, 0, x, y, r); grd.addColorStop(0, 'rgba(60,58,50,0.12)'); grd.addColorStop(1, 'rgba(60,58,50,0)'); g.fillStyle = grd; g.fillRect(x - r, y - r, 2 * r, 2 * r); }
  for (let i = 0; i < 14; i++) { g.strokeStyle = 'rgba(55,52,48,0.3)'; g.lineWidth = 1; g.beginPath(); let x = rand() * s, y = rand() * s; g.moveTo(x, y); for (let k = 0; k < 6; k++) { x += (rand() - 0.5) * 90; y += (rand() - 0.5) * 90; g.lineTo(x, y); } g.stroke(); }
  g.globalAlpha = 0.9;
  g.strokeStyle = '#e9a93a'; g.lineWidth = 34; g.beginPath(); g.arc(c, c, c - 40, 0, Math.PI * 2); g.stroke();
  g.strokeStyle = '#eceae2'; g.lineWidth = 16; g.beginPath(); g.arc(c, c, c - 110, 0, Math.PI * 2); g.stroke();
  g.fillStyle = '#eceae2'; const w = 60, hh = 360, gap = 120;
  g.fillRect(c - gap - w / 2, c - hh / 2, w, hh); g.fillRect(c + gap - w / 2, c - hh / 2, w, hh); g.fillRect(c - gap, c - w / 2, 2 * gap, w);
  g.globalAlpha = 1;
  for (let i = 0; i < 9000; i++) { g.fillStyle = 'rgba(70,66,60,0.25)'; g.fillRect(rand() * s, rand() * s, 1, 1); }
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
const discTex = canvasTexture(256, (g, s) => {           // a prop seen at speed: faint streaks, not a solid disc
  const c = s / 2;
  for (let a = 0; a < 360; a += 1) {
    const k = 0.25 + 0.75 * Math.pow(Math.abs(Math.cos(a * DEG)), 6);
    g.strokeStyle = `rgba(255,255,255,${0.18 * k})`; g.lineWidth = 2;
    g.beginPath(); g.moveTo(c + Math.cos(a * DEG) * c * 0.14, c + Math.sin(a * DEG) * c * 0.14); g.lineTo(c + Math.cos(a * DEG) * c * 0.98, c + Math.sin(a * DEG) * c * 0.98); g.stroke();
  }
  g.strokeStyle = 'rgba(255,255,255,0.35)'; g.lineWidth = 3; g.beginPath(); g.arc(c, c, c * 0.97, 0, Math.PI * 2); g.stroke();
});
const blobTex = canvasTexture(128, (g, s) => {
  const grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grd.addColorStop(0, 'rgba(0,0,0,0.55)'); grd.addColorStop(0.6, 'rgba(0,0,0,0.28)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grd; g.fillRect(0, 0, s, s);
}, { srgb: false });
const ringTex = canvasTexture(128, (g, s) => {
  g.strokeStyle = 'rgba(255,190,90,0.95)'; g.lineWidth = 6;
  g.beginPath(); g.arc(s / 2, s / 2, s / 2 - 10, 0, Math.PI * 2); g.stroke();
  g.fillStyle = 'rgba(255,190,90,0.95)'; g.beginPath(); g.arc(s / 2, s / 2, 7, 0, Math.PI * 2); g.fill();
});
const corrugatedTex = canvasTexture(256, (g, s) => {
  for (let x = 0; x < s; x++) { const v = 140 + 45 * Math.sin(x / s * Math.PI * 2 * 24); g.fillStyle = `rgb(${v},${v + 4},${v + 8})`; g.fillRect(x, 0, 1, s); }
  for (let i = 0; i < 500; i++) { g.fillStyle = 'rgba(110,80,50,0.14)'; g.fillRect(rand() * s, rand() * s, 2, 6 + rand() * 30); }
}, { repeat: 1 });
const sockTex = canvasTexture(256, (g, s) => {
  for (let i = 0; i < 5; i++) { g.fillStyle = i % 2 ? '#f0ede4' : '#e8521f'; g.fillRect(0, i * s / 5, s, s / 5); }
});

// --- ground: one shader, no repeating texture --------------------------------------------
function buildGround() {
  const size = 12000, seg = 300;
  const geo = new THREE.PlaneGeometry(size, size, seg, seg);
  geo.rotateX(-Math.PI / 2);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i), r = Math.hypot(x, z);
    const hills = (fbm(x / 1300 + 3.1, z / 1300 - 7.4, 5) - 0.4) * 320 + fbm(x / 300, z / 300, 3) * 45;
    p.setY(i, hills * smooth(700, 2200, r));
  }
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.97, metalness: 0 });
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying vec3 vWPos;\n${GLSL_NOISE}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec2 gp = vWPos.xz;
        float camDist = length(vWPos - cameraPosition);
        float fine = 1.0 - smoothstep(60.0, 240.0, camDist);
        float n1 = pFbm(gp * 0.018), n2 = pFbm(gp * 0.09 + 13.0), n3 = pNoise(gp * 0.7 + 7.0), n4 = pNoise(gp * 3.1);
        vec3 lush = vec3(0.085, 0.16, 0.035), mid = vec3(0.13, 0.20, 0.05), dry = vec3(0.30, 0.27, 0.11), forest = vec3(0.04, 0.075, 0.03);
        vec3 c = mix(lush, mid, smoothstep(0.3, 0.7, n1));
        c = mix(c, dry, smoothstep(0.6, 0.85, n2) * 0.5);
        c *= 0.82 + 0.3 * mix(0.5, n3, fine) + 0.12 * (n4 - 0.5) * fine;
        vec2 fd = abs(gp - vec2(${FIELD.x.toFixed(1)}, ${FIELD.z.toFixed(1)})) - vec2(${FIELD.hx.toFixed(1)}, ${FIELD.hz.toFixed(1)});
        float inField = 1.0 - smoothstep(-2.0, 2.0, max(fd.x, fd.y));
        float stripe = smoothstep(0.42, 0.58, abs(fract(gp.x / 12.0) * 2.0 - 1.0));
        c *= mix(1.0, mix(0.9, 1.1, stripe), inField * 0.8);
        c = mix(c, c * vec3(1.15, 1.1, 0.9), inField * 0.25);
        vec2 tp = gp - vec2(${TRACK.x.toFixed(1)}, ${TRACK.z.toFixed(1)});
        float td = abs(dot(tp, vec2(cos(${TRACK.angle}), sin(${TRACK.angle}))));
        float track = 1.0 - smoothstep(${TRACK.half.toFixed(2)} - 0.3, ${TRACK.half.toFixed(2)} + 0.4, td + (pNoise(gp * 1.3) - 0.5) * 0.5);
        float rut = smoothstep(0.3, 0.0, abs(td - 0.75)) * 0.15;
        vec3 dirt = mix(vec3(0.24, 0.17, 0.09), vec3(0.33, 0.25, 0.14), pNoise(gp * 0.8));
        c = mix(c, dirt * (0.85 + 0.25 * n4 - rut), track * (1.0 - step(160.0, abs(tp.y))));
        float far = smoothstep(450.0, 1200.0, length(gp));
        c = mix(c, mix(forest, mid * 0.8, smoothstep(0.35, 0.65, pFbm(gp * 0.0035 + 3.0))), far * 0.85);
        diffuseColor.rgb = c;`);
  };
  const ground = new THREE.Mesh(geo, mat);
  ground.receiveShadow = true;
  scene.add(ground);

  const rim = new THREE.MeshStandardMaterial({ color: 0x7c7b77, roughness: 0.9 });
  const pad = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.25, 0.06, 96), [rim, new THREE.MeshStandardMaterial({ map: padTex, roughness: 0.82 }), rim]);
  pad.position.y = 0.03;
  pad.receiveShadow = true;
  scene.add(pad);
}

// --- grass: blades that follow the camera, sway in the breeze and flatten under the props ---
const GRASS_TILE = 72, GRASS_COUNT = 170000;
function buildGrass() {
  const seg = 4, verts = [], idx = [];
  for (let i = 0; i <= seg; i++) {
    const t = i / seg, w = 0.5 * Math.pow(1 - t, 0.85) * 0.032 + 0.0015;
    verts.push(-w, t, t * t * 0.03, w, t, t * t * 0.03);
    if (i < seg) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  }
  const geo = new THREE.InstancedBufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(verts.map((_, i) => (i % 3 === 1 ? 1 : 0)), 3));
  geo.setIndex(idx);
  const blades = new Float32Array(GRASS_COUNT * 4);
  for (let i = 0; i < GRASS_COUNT; i++) blades.set([rand() * GRASS_TILE, rand() * GRASS_TILE, rand() * Math.PI * 2, 0.7 + rand() * 0.6], i * 4);
  geo.setAttribute('aBlade', new THREE.InstancedBufferAttribute(blades, 4));
  geo.instanceCount = GRASS_COUNT;
  const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(0.11, 0.2, 0.045), roughness: 0.75, side: THREE.DoubleSide });
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec4 aBlade; uniform float uTime; uniform vec3 uCam; uniform vec3 uDrone; uniform float uWash; uniform vec2 uWind;
        varying vec3 vTint; ${GLSL_NOISE}
        float bladeHeight(vec2 w) {
          float h = 0.32 + 0.22 * pNoise(w * 0.15);
          vec2 fd = abs(w - vec2(${FIELD.x.toFixed(1)}, ${FIELD.z.toFixed(1)})) - vec2(${FIELD.hx.toFixed(1)}, ${FIELD.hz.toFixed(1)});
          h = mix(h, 0.11 + 0.03 * pNoise(w * 0.9), 1.0 - smoothstep(-1.5, 1.5, max(fd.x, fd.y)));
          h *= smoothstep(3.35, 3.7, length(w));
          vec2 tp = w - vec2(${TRACK.x.toFixed(1)}, ${TRACK.z.toFixed(1)});
          float td = abs(dot(tp, vec2(cos(${TRACK.angle}), sin(${TRACK.angle}))));
          h *= mix(1.0, smoothstep(${TRACK.half.toFixed(2)} - 0.2, ${TRACK.half.toFixed(2)} + 0.5, td), 1.0 - step(160.0, abs(tp.y)));
          return h;
        }`)
      .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = vec3(0.0, 1.0, 0.0);')
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        vec2 wp = uCam.xz + mod(aBlade.xy - uCam.xz + ${(GRASS_TILE / 2).toFixed(1)}, ${GRASS_TILE.toFixed(1)}) - ${(GRASS_TILE / 2).toFixed(1)};
        float fade = 1.0 - smoothstep(${(GRASS_TILE * 0.3).toFixed(1)}, ${(GRASS_TILE * 0.48).toFixed(1)}, length(wp - uCam.xz));
        float h = bladeHeight(wp) * aBlade.w * fade;
        float t = position.y;
        float c = cos(aBlade.z), s = sin(aBlade.z);
        vec3 lp = vec3(position.x * (0.7 + 0.5 * aBlade.w), t * h, position.z * h * 4.0);
        lp = vec3(c * lp.x - s * lp.z, lp.y, s * lp.x + c * lp.z);
        float gust = 0.55 + 0.45 * pNoise(wp * 0.05 + uWind * uTime * 0.35);
        vec2 bend = uWind * (0.22 + 0.16 * sin(uTime * 2.1 + dot(wp, vec2(0.31, 0.23)))) * gust;
        bend += vec2(sin(aBlade.z * 3.1), cos(aBlade.z * 2.3)) * 0.12;
        vec2 away = wp - uDrone.xz; float dd = length(away);
        bend += away / max(dd, 0.05) * uWash * exp(-dd * dd / 6.0) * (1.6 + 0.4 * sin(uTime * 23.0 + dd * 4.0));
        float k = t * t;
        transformed = vec3(wp.x, 0.0, wp.y) + lp + vec3(bend.x, 0.0, bend.y) * k * h;
        transformed.y -= min(length(bend), 1.2) * k * h * 0.45;
        float var = pHash(aBlade.xy);
        vTint = mix(vec3(0.45, 0.5, 0.42), vec3(1.25, 1.25, 0.95), t) * (0.75 + 0.5 * var) * mix(vec3(1.0), vec3(1.35, 1.2, 0.75), step(0.93, var));`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vTint;')
      .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb *= vTint;');
  };
  const grass = new THREE.Mesh(geo, mat);
  grass.frustumCulled = false;
  grass.receiveShadow = true;
  scene.add(grass);
}

// --- trees: trunks and branches with leaf cards, instanced --------------------------------
const frontFace = THREE.ShaderChunk.normal_fragment_begin.replace('gl_FrontFacing ? 1.0 : - 1.0', '1.0');
function foliageMaterial(map, tint) {
  const m = new THREE.MeshStandardMaterial({ map, color: tint, alphaTest: 0.42, side: THREE.DoubleSide, vertexColors: true, roughness: 0.82 });
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uTime = U.uTime;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uTime;')
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        #ifdef USE_INSTANCING
          vec3 root = instanceMatrix[3].xyz;
        #else
          vec3 root = vec3(0.0);
        #endif
        float sway = sin(uTime * 1.3 + root.x * 0.07 + position.y * 0.15) + 0.5 * sin(uTime * 3.1 + position.x * 0.9);
        transformed.xz += vec2(0.6, 0.4) * sway * 0.003 * max(position.y - 2.0, 0.0);`);
    sh.fragmentShader = sh.fragmentShader.replace('#include <normal_fragment_begin>', frontFace);   // both sides lit from the crown's outward normal
  };
  return m;
}
const leafDepth = (map) => new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map, alphaTest: 0.42, side: THREE.DoubleSide });
function shadeGeo(g, fn) {
  const p = g.attributes.position, col = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) { const v = fn(p.getX(i), p.getY(i), p.getZ(i)); col.set([v, v, v], i * 3); }
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return g;
}
function setNormals(g, n) {
  const nrm = g.attributes.normal;
  for (let k = 0; k < nrm.count; k++) nrm.setXYZ(k, n.x, n.y, n.z);
}
function makeBroadleaf(height, crownR) {
  const wood = [], leaves = [];
  const trunkH = height * 0.42;
  const trunk = new THREE.CylinderGeometry(0.13 * crownR / 3, 0.26 * crownR / 3, trunkH, 10, 4);
  trunk.translate(0, trunkH / 2, 0);
  wood.push(shadeGeo(trunk, (x, y) => 0.55 + 0.45 * smooth(0, 3, y)));
  const center = new THREE.Vector3(0, trunkH + crownR * 0.75, 0);
  for (let i = 0; i < 6; i++) {
    const a = i / 6 * Math.PI * 2 + rand(), len = crownR * (0.7 + rand() * 0.35);
    const br = new THREE.CylinderGeometry(0.04, 0.12, len, 6);
    br.translate(0, len / 2, 0);
    br.rotateZ(0.5 + rand() * 0.5); br.rotateY(a);
    br.translate(0, trunkH * (0.85 + rand() * 0.15), 0);
    wood.push(shadeGeo(br, () => 0.8));
  }
  for (let i = 0; i < 150; i++) {
    const u = rand() * 2 - 1, th = rand() * Math.PI * 2, r = Math.pow(rand(), 0.35);
    const dir = new THREE.Vector3(Math.sqrt(1 - u * u) * Math.cos(th), u * 0.8, Math.sqrt(1 - u * u) * Math.sin(th));
    const pos = center.clone().add(dir.multiply(new THREE.Vector3(crownR, crownR * 0.82, crownR)).multiplyScalar(r));
    const size = crownR * (0.55 + rand() * 0.35);
    const card = new THREE.PlaneGeometry(size, size);
    card.rotateX(rand() * Math.PI); card.rotateY(rand() * Math.PI); card.rotateZ(rand() * Math.PI);
    card.translate(pos.x, pos.y, pos.z);
    setNormals(card, pos.clone().sub(center).normalize().lerp(new THREE.Vector3(0, 1, 0), 0.25).normalize());
    const shade = 0.42 + 0.58 * r * (0.7 + 0.3 * smooth(-1, 1, u));       // darker inside the crown and underneath
    leaves.push(shadeGeo(card, () => shade));
  }
  return { wood: mergeGeometries(wood), leaves: mergeGeometries(leaves) };
}
function makeConifer(height) {
  const wood = [], leaves = [];
  const trunk = new THREE.CylinderGeometry(0.06, 0.28, height, 9, 4);
  trunk.translate(0, height / 2, 0);
  wood.push(shadeGeo(trunk, () => 0.7));
  const levels = 13;
  for (let l = 0; l < levels; l++) {
    const y = 1.6 + (height - 2.2) * (l / (levels - 1));
    const r = (height * 0.24) * Math.pow(1 - l / levels, 0.95) + 0.35;
    const count = Math.max(5, Math.round(9 - l * 0.3));
    for (let k = 0; k < count; k++) {
      const a = k / count * Math.PI * 2 + l * 0.7 + rand() * 0.4;
      const card = new THREE.PlaneGeometry(r, r * 0.5);
      card.translate(r / 2, 0, 0);
      card.rotateX(Math.PI / 2 * (rand() < 0.5 ? 1 : 0.8));
      card.rotateZ(-0.35 - rand() * 0.15);
      card.rotateY(a);
      card.translate(0, y, 0);
      setNormals(card, new THREE.Vector3(Math.cos(a), 0.6, -Math.sin(a)).normalize());
      leaves.push(shadeGeo(card, () => 0.55 + 0.4 * (l / levels)));
    }
  }
  return { wood: mergeGeometries(wood), leaves: mergeGeometries(leaves) };
}

function buildTrees() {
  const barkMat = new THREE.MeshStandardMaterial({ map: barkTex, vertexColors: true, roughness: 0.95 });
  const kinds = [
    { ...makeBroadleaf(12, 3.6), tex: leafTex, tint: 0x9fbf7a, list: [] },
    { ...makeBroadleaf(10, 3.0), tex: leafTex, tint: 0xb5c77e, list: [] },
    { ...makeBroadleaf(14, 4.2), tex: leafTex, tint: 0x8fb06e, list: [] },
    { ...makeConifer(15), tex: needleTex, tint: 0xa9c29a, list: [] },
    { ...makeConifer(11), tex: needleTex, tint: 0x9cb58f, list: [] },
  ];
  const spots = [];
  const edge = (n0, e0, n1, e1, count) => {
    for (let i = 0; i < count; i++) {
      const t = i / count + rand() * 0.02;
      spots.push([lerp(n0, n1, t) + (rand() - 0.5) * 8, lerp(e0, e1, t) + (rand() - 0.5) * 8, rand() < 0.75 ? 0 : 1]);
    }
  };
  edge(95, -95, 95, 125, 40); edge(-80, -95, -80, 125, 34); edge(-80, 128, 95, 128, 32); edge(-80, -100, 95, -100, 26);
  for (let i = 0; i < 300; i++) {
    const r = 160 + Math.pow(rand(), 0.75) * 1300, a = rand() * Math.PI * 2;
    spots.push([r * Math.cos(a), r * Math.sin(a), rand() < 0.5 ? 0 : 1]);
  }
  for (const [n, e, conifer] of spots) {
    if (Math.hypot(n + 70, e + 55) < 24) continue;                     // the hangar
    const tx = e - TRACK.x, tz = -n - TRACK.z;
    if (Math.abs(tx * Math.cos(TRACK.angle) + tz * Math.sin(TRACK.angle)) < 6 && Math.abs(tz) < 160) continue;
    const kind = conifer ? 3 + (rand() < 0.5 ? 0 : 1) : Math.floor(rand() * 3);
    kinds[kind].list.push([n, e]);
  }
  kinds[2].list.push([OAK.N, OAK.E, 1.35]);                            // the oak the circuit goes round
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), col = new THREE.Color(), up = new THREE.Vector3(0, 1, 0);
  const shadowShift = new THREE.Vector3(-sunDir.x, 0, -sunDir.z).normalize();
  const blobs = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }), spots.length + 1);
  let bi = 0;
  for (const k of kinds) {
    const leaves = new THREE.InstancedMesh(k.leaves, foliageMaterial(k.tex, k.tint), k.list.length);
    const wood = new THREE.InstancedMesh(k.wood, barkMat, k.list.length);
    leaves.customDepthMaterial = leafDepth(k.tex);
    k.list.forEach(([n, e, big], i) => {
      const s = big || 0.75 + rand() * 0.5;
      q.setFromAxisAngle(up, rand() * Math.PI * 2);
      m.compose(world(n, e), q, new THREE.Vector3(s, s * (0.9 + rand() * 0.2), s));
      leaves.setMatrixAt(i, m); wood.setMatrixAt(i, m);
      col.setHSL(0, 0, 0.85 + rand() * 0.3); leaves.setColorAt(i, col);
      m.compose(world(n, e, 0.05).addScaledVector(shadowShift, 3 * s), new THREE.Quaternion(), new THREE.Vector3(9 * s, 1, 9 * s));
      blobs.setMatrixAt(bi++, m);
    });
    for (const mesh of [leaves, wood]) { mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh); }
  }
  blobs.count = bi;
  scene.add(blobs);
}

// --- clouds: one high layer of fbm cumulus, drifting --------------------------------------
function buildClouds() {
  const mat = new THREE.ShaderMaterial({
    uniforms: { uTime: U.uTime, uSun: { value: sunDir } },
    transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false,
    vertexShader: 'varying vec3 vW; void main() { vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }',
    fragmentShader: `uniform float uTime; uniform vec3 uSun; varying vec3 vW; ${GLSL_NOISE}
      void main() {
        vec2 p = vW.xz * 0.00042 + vec2(uTime * 0.0035, -uTime * 0.0015);
        float warp = pFbm(p * 1.7 + 4.0);
        float n = pFbm(p + warp * 0.55);
        float cov = smoothstep(0.5, 0.72, n);
        float thick = smoothstep(0.55, 0.85, n);
        float lit = 0.72 + 0.28 * smoothstep(0.3, 0.8, pFbm(p * 2.6 + uSun.xz * 0.8));
        vec3 col = mix(vec3(0.62, 0.66, 0.74), vec3(1.0, 0.99, 0.97), lit * (1.0 - 0.45 * thick)) * 2.4;
        float d = length(vW.xz - cameraPosition.xz);
        gl_FragColor = vec4(col, cov * 0.92 * (1.0 - smoothstep(5000.0, 11000.0, d)));
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
  const clouds = new THREE.Mesh(new THREE.PlaneGeometry(40000, 40000).rotateX(Math.PI / 2), mat);
  clouds.position.y = 1400;
  scene.add(clouds);
}

function buildProps() {
  const hangar = new THREE.Group();
  const wall = new THREE.MeshStandardMaterial({ map: corrugatedTex, roughness: 0.55, metalness: 0.55 });
  corrugatedTex.repeat.set(3, 1);
  const box = new THREE.Mesh(new THREE.BoxGeometry(26, 8, 16), wall);
  box.position.y = 4;
  const roofShape = new THREE.Shape();
  roofShape.moveTo(-8.6, 0); roofShape.lineTo(0, 3.6); roofShape.lineTo(8.6, 0); roofShape.lineTo(-8.6, 0);
  const roof = new THREE.Mesh(new THREE.ExtrudeGeometry(roofShape, { depth: 27, bevelEnabled: false }),
    new THREE.MeshStandardMaterial({ color: 0x5f3427, roughness: 0.6, metalness: 0.35 }));
  roof.rotation.y = Math.PI / 2; roof.position.set(-13.5, 8, 0);
  const door = new THREE.Mesh(new THREE.PlaneGeometry(12, 6.5), new THREE.MeshStandardMaterial({ color: 0x24282d, roughness: 0.8 }));
  door.position.set(0, 3.25, 8.01);
  hangar.add(box, roof, door);
  hangar.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  hangar.position.copy(world(-70, -55));
  hangar.rotation.y = 0.5;
  scene.add(hangar);

  const sock = new THREE.Group();
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.07, 6, 12), new THREE.MeshStandardMaterial({ color: 0xdedfd9, roughness: 0.45, metalness: 0.5 }));
  pole.position.y = 3;
  const cone = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.13, 2.4, 24, 6, true), new THREE.MeshStandardMaterial({ map: sockTex, side: THREE.DoubleSide, roughness: 0.85 }));
  cone.rotation.z = Math.PI / 2;
  cone.position.x = 1.25;
  const arm = new THREE.Group();
  arm.position.y = 5.8;
  arm.add(cone);
  sock.add(pole, arm);
  sock.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  sock.position.copy(world(-9, 10));
  arm.rotation.y = -((WIND_FROM + 180) * DEG - Math.PI / 2);
  scene.add(sock);

  const person = new THREE.Group();
  const jeans = new THREE.MeshStandardMaterial({ color: 0x2b3850, roughness: 0.9 });
  const jacket = new THREE.MeshStandardMaterial({ color: 0xf06a14, roughness: 0.7 });
  const skin = new THREE.MeshStandardMaterial({ color: 0xb98060, roughness: 0.65 });
  const glove = new THREE.MeshStandardMaterial({ color: 0x1d2227, roughness: 0.6 });
  for (const s of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.72, 4, 12), jeans);
    leg.position.set(s * 0.1, 0.45, 0);
    const armM = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.5, 4, 12), jacket);
    armM.position.set(s * 0.25, 1.22, -0.16); armM.rotation.x = -1.0;
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.06, 14, 10), glove);
    hand.position.set(s * 0.25, 1.07, -0.42);
    person.add(leg, armM, hand);
  }
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, 0.42, 6, 16), jacket);
  torso.position.y = 1.25;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 16), skin);
  head.position.y = 1.66;
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.115, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x20252c, roughness: 0.8 }));
  cap.position.y = 1.68;
  person.add(torso, head, cap);
  person.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  person.position.copy(world(PILOT_SPOT.N, PILOT_SPOT.E));
  person.lookAt(world(10, 10));
  person.rotateY(Math.PI);
  scene.add(person);

  const coneMat = new THREE.MeshStandardMaterial({ color: 0xf05f14, roughness: 0.55 });
  for (let i = 0; i < 4; i++) {
    const c = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.45, 20), coneMat);
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
  const accent = new THREE.MeshStandardMaterial({ color: 0xe8601a, roughness: 0.38 });
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

  for (const s of [-1, 1]) {
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

  MOTORS.forEach((mm) => {
    const a = mm.bearing * DEG, dir = new THREE.Vector3(Math.sin(a), 0, -Math.cos(a));
    const arm = new THREE.Mesh(new RoundedBoxGeometry(0.02, 0.013, ARM_R, 2, 0.004), carbon);
    arm.position.copy(dir).multiplyScalar(ARM_R / 2); arm.rotation.y = Math.PI - a;
    const mount = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.006, 24), carbon);
    mount.position.copy(dir).multiplyScalar(ARM_R).setY(0.006);
    const stator = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.017, 0.012, 24), dark);
    stator.position.copy(dir).multiplyScalar(ARM_R).setY(0.015);
    const bell = new THREE.Mesh(new THREE.CylinderGeometry(0.0185, 0.0185, 0.016, 32), alu);
    bell.position.copy(dir).multiplyScalar(ARM_R).setY(0.029);
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.008, 0.008, 16), mm.ccw ? alu : accent);
    cap.position.copy(dir).multiplyScalar(ARM_R).setY(0.044);
    g.add(arm, mount, stator, bell, cap);

    const prop = new THREE.Group();
    prop.position.copy(dir).multiplyScalar(ARM_R).setY(0.04);
    const bladeMat = new THREE.MeshStandardMaterial({ color: 0x1b1e23, roughness: 0.4, metalness: 0.1, side: THREE.DoubleSide, transparent: true });
    for (const k of [0, 1]) {
      const blade = new THREE.Mesh(bladeGeo, bladeMat);
      const holder = new THREE.Group();
      holder.rotation.y = k * Math.PI;
      blade.rotation.x = (mm.ccw ? 1 : -1) * 11 * DEG;
      holder.add(blade);
      prop.add(holder);
    }
    const disc = new THREE.Mesh(discGeo, new THREE.MeshBasicMaterial({ map: discTex, color: 0x3a3f46, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
    disc.position.copy(prop.position).setY(0.041);
    g.add(prop, disc);
    props.push({ group: prop, bladeMat, disc, dir: mm.ccw ? 1 : -1, angle: rand() * 6 });

    const front = mm.bearing === 45 || mm.bearing === 315;
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
const TRAIL_MAX = 4000;
const trailGeo = new THREE.BufferGeometry();
trailGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(TRAIL_MAX * 3), 3));
const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0xffb547, transparent: true, opacity: 0.55 }));
trail.frustumCulled = false;
let trailN = 0;
const trailLast = new THREE.Vector3(1e9, 0, 0);
const dropGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
const drop = new THREE.Line(dropGeo, new THREE.LineDashedMaterial({ color: 0x74d0ff, dashSize: 0.3, gapSize: 0.2, transparent: true, opacity: 0.55 }));
drop.frustumCulled = false;
const footRing = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.33, 48).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x74d0ff, transparent: true, opacity: 0.5, depthWrite: false }));
const locator = new THREE.Sprite(new THREE.SpriteMaterial({ map: ringTex, sizeAttenuation: false, depthTest: false, transparent: true }));
locator.scale.setScalar(0.04);
locator.renderOrder = 10;
scene.add(trail, drop, footRing, locator);

function pushTrail(p) {                    // append only, one vertex per 0.15 m; halve it when full
  if (trailLast.distanceToSquared(p) < 0.0225) return;
  trailLast.copy(p);
  const pos = trailGeo.attributes.position;
  if (trailN >= TRAIL_MAX) {
    pos.array.copyWithin(0, (TRAIL_MAX / 2) * 3, TRAIL_MAX * 3);
    trailN = TRAIL_MAX / 2;
  }
  pos.setXYZ(trailN++, p.x, p.y, p.z);
  pos.needsUpdate = true;
  trailGeo.setDrawRange(0, trailN);
}
function clearTrail() { trailN = 0; trailLast.set(1e9, 0, 0); trailGeo.setDrawRange(0, 0); }

// --- data: live or replay, sampled on a smooth clock -----------------------------------------
const frames = [];
const tmpE = new THREE.Euler();
function prepare(f) {                       // a quaternion per frame, for slerp
  tmpE.set(f.att[1] * DEG, -f.att[2] * DEG, -f.att[0] * DEG, 'YXZ');
  f.q = new THREE.Quaternion().setFromEuler(tmpE);
  return f;
}
// Position between frames by cubic Hermite on position and velocity, attitude by slerp.
function sample(t) {
  if (!frames.length) return null;
  let lo = 0, hi = frames.length - 1;
  if (t <= frames[0].t) hi = 0;
  else if (t >= frames[hi].t) lo = hi;
  else while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (frames[mid].t <= t) lo = mid; else hi = mid; }
  const a = frames[lo], b = frames[hi];
  if (lo === hi) {
    const ext = clamp(t - a.t, 0, 0.12);       // a short extrapolation if the stream hiccups
    return { f: a, pos: new THREE.Vector3(a.pos[1] + a.vel[1] * ext, a.pos[2] - a.vel[2] * ext, -(a.pos[0] + a.vel[0] * ext)), quat: a.q };
  }
  const h = b.t - a.t, s = (t - a.t) / h, s2 = s * s, s3 = s2 * s;
  const h00 = 2 * s3 - 3 * s2 + 1, h10 = s3 - 2 * s2 + s, h01 = -2 * s3 + 3 * s2, h11 = s3 - s2;
  const herm = (pa, va, pb, vb) => h00 * pa + h10 * h * va + h01 * pb + h11 * h * vb;
  const N = herm(a.pos[0], a.vel[0], b.pos[0], b.vel[0]);
  const E = herm(a.pos[1], a.vel[1], b.pos[1], b.vel[1]);
  const A = herm(a.pos[2], -a.vel[2], b.pos[2], -b.vel[2]);
  const mix = (x, y) => x.map((v, i) => lerp(v, y[i], s));
  const f = { ...a, vel: mix(a.vel, b.vel),
    att: [lerp(a.att[0], b.att[0], s), lerp(a.att[1], b.att[1], s), a.att[2] + (((b.att[2] - a.att[2] + 540) % 360) - 180) * s],
    pos: [N, E, A], motors: a.motors && b.motors ? mix(a.motors, b.motors) : a.motors };
  return { f, pos: new THREE.Vector3(E, A, -N), quat: a.q.clone().slerp(b.q, s) };
}

// Live clock: render a fixed delay behind the server, against the lowest latency seen lately.
const RENDER_DELAY = 0.07;
const lat = [];
let offset = null;
function connectLive() {
  $('note').hidden = true;
  $('fly').hidden = false;
  const es = new EventSource('/state');
  es.onmessage = (ev) => {
    const f = JSON.parse(ev.data);
    if (f.t === undefined) return;
    if (frames.length && f.t <= frames[frames.length - 1].t) return;
    frames.push(prepare(f));
    while (frames.length > 2 && frames[0].t < f.t - 4) frames.shift();
    lat.push(performance.now() / 1000 - f.t);
    if (lat.length > 150) lat.shift();
    $('wait').hidden = true;
  };
  es.onerror = () => { $('wait-title').textContent = 'Lost the connection to demo_view.py'; $('wait-sub').textContent = 'Retrying…'; $('wait').hidden = false; };
}
function liveTime(now) {
  if (!lat.length) return null;
  const target = Math.min(...lat);
  offset = offset === null ? target : offset + (target - offset) * 0.02;   // drift slowly, never jump
  return now - offset - RENDER_DELAY;
}

let playhead = null, playing = true, speed = 1;
async function loadReplay() {
  $('replay').hidden = false;
  $('wait-title').textContent = 'Loading the recorded flight…';
  $('wait-sub').textContent = 'One tour of ArduCopter SITL flown by the virtual pilot.';
  const res = await fetch('flight.json');
  const data = await res.json();
  frames.push(...data.map(prepare));
  playhead = frames[0].t;
  $('wait').hidden = true;
  $('note').textContent = 'Recorded from ArduCopter SITL. The drone moves only from ArduCopter\'s motor outputs through ArduPilot\'s physics; the hands are a scripted virtual pilot.';
  const scrub = $('scrub');
  scrub.addEventListener('input', () => { playhead = lerp(frames[0].t, frames[frames.length - 1].t, scrub.value / 1000); clearTrail(); });
  $('play').addEventListener('click', () => { playing = !playing; $('play').textContent = playing ? 'Pause' : 'Play'; });
  const speeds = [1, 2, 4, 0.5];
  $('speed').addEventListener('click', () => { speed = speeds[(speeds.indexOf(speed) + 1) % speeds.length]; $('speed').textContent = `${speed}×`; });
}

// --- cameras: critically damped springs ----------------------------------------------------
function damp(cur, target, vel, smoothTime, dt) {
  const omega = 2 / smoothTime, x = omega * dt, e = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  for (const k of ['x', 'y', 'z']) {
    const change = cur[k] - target[k], temp = (vel[k] + omega * change) * dt;
    vel[k] = (vel[k] - omega * temp) * e;
    cur[k] = target[k] + (change + temp) * e;
  }
}
function dampAngle(cur, target, state, smoothTime, dt) {
  const t = cur + ((((target - cur) % 360) + 540) % 360 - 180);
  const omega = 2 / smoothTime, x = omega * dt, e = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const change = cur - t, temp = (state.v + omega * change) * dt;
  state.v = (state.v - omega * temp) * e;
  return t + (change + temp) * e;
}
const controls = new OrbitControls(camera, canvas);
controls.enabled = false;
controls.enableDamping = true;
controls.minDistance = 0.6;
controls.maxDistance = 150;
controls.maxPolarAngle = Math.PI * 0.495;
let camMode = 'cine';
const look = new THREE.Vector3(0, 0.5, 0), lookVel = new THREE.Vector3(), camVel = new THREE.Vector3();
const camYaw = { v: 0 };
let chaseYaw = 0;
const shot = { kind: 'chase', until: 0, anchor: new THREE.Vector3(), angle: 0 };
const SHOTS = ['chase', 'tripod', 'pilot', 'circle', 'chase', 'wide', 'tripod', 'low'];
let shotIndex = 0;
const dronePos = new THREE.Vector3(0, GEAR, 0);
const droneVel = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);

function setCam(mode) {
  camMode = mode;
  document.querySelectorAll('.cams button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.cam === mode)));
  controls.enabled = mode === 'orbit';
  camera.up.set(0, 1, 0);
  if (mode === 'orbit') { controls.target.copy(dronePos); camera.position.copy(dronePos).add(new THREE.Vector3(2.2, 1.0, 3.0)); }
  shot.until = 0;
  camVel.set(0, 0, 0);
}
document.querySelectorAll('.cams button').forEach((b) => b.addEventListener('click', () => { setCam(b.dataset.cam); b.blur(); }));
window.addEventListener('keydown', (e) => {
  const m = { 1: 'cine', 2: 'chase', 3: 'pilot', 4: 'orbit', 5: 'top' }[e.key];
  if (m) setCam(m);
  if (e.key === ' ' && SOURCE === 'replay') { e.preventDefault(); $('play').click(); }
});
function behind(dist, up, yawDeg) {
  return new THREE.Vector3(0, up, dist).applyAxisAngle(UP, -yawDeg * DEG).add(dronePos);
}

function updateCamera(dt, now, f) {
  const yaw = f ? f.att[2] : 0;
  const speedH = Math.hypot(droneVel.x, droneVel.z);
  // Chase heading: the drone's nose, or its track when it moves fast, eased so turns sweep.
  const track = Math.atan2(droneVel.x, -droneVel.z) / DEG;
  chaseYaw = dampAngle(chaseYaw, speedH > 2.5 ? track : yaw, camYaw, 0.9, dt);
  let kind = camMode, fov = 50;
  if (camMode === 'cine') {
    if (now > shot.until) {
      shot.kind = SHOTS[shotIndex++ % SHOTS.length];
      shot.until = now + { chase: 12, tripod: 7, pilot: 9, circle: 10, wide: 8, low: 7 }[shot.kind];
      const side = rand() < 0.5 ? -1 : 1;
      shot.anchor.copy(dronePos).addScaledVector(droneVel, 2.5).add(new THREE.Vector3(side * 7, 0, 0).applyAxisAngle(UP, -yaw * DEG));
      shot.anchor.y = Math.max(1.2, dronePos.y * 0.5 + 1);
      shot.angle = Math.atan2(camera.position.z - dronePos.z, camera.position.x - dronePos.x);
      camVel.set(0, 0, 0);
      if (shot.kind === 'chase') camera.position.copy(behind(3, 0.8, chaseYaw));
      if (shot.kind === 'tripod') camera.position.copy(shot.anchor);
      if (shot.kind === 'low') camera.position.copy(dronePos).addScaledVector(droneVel, 3).setY(0.35).add(new THREE.Vector3(side * 3, 0, 0));
      look.copy(dronePos); lookVel.set(0, 0, 0);
    }
    kind = shot.kind;
  }
  const lead = dronePos.clone().addScaledVector(droneVel, 0.15);
  const dist = camera.position.distanceTo(dronePos);
  if (kind === 'chase') {
    const want = behind(1.7 + clamp(speedH * 0.08, 0, 0.9), 0.45 + clamp(speedH * 0.03, 0, 0.35), chaseYaw);
    want.y = Math.max(want.y, 0.3);
    damp(camera.position, want, camVel, 0.18, dt);
    damp(look, lead.clone().setY(lead.y + 0.12), lookVel, 0.06, dt);
    fov = 55;
  } else if (kind === 'pilot') {
    camera.position.copy(world(PILOT_SPOT.N, PILOT_SPOT.E, 1.68));
    damp(look, lead, lookVel, 0.12, dt);
    fov = clamp(2 * Math.atan(4.5 / dist) / DEG, 10, 58);
  } else if (kind === 'tripod' || kind === 'low') {
    damp(look, lead, lookVel, 0.1, dt);
    fov = clamp(2 * Math.atan((kind === 'low' ? 3.5 : 4.5) / dist) / DEG, 12, 62);
  } else if (kind === 'circle') {
    shot.angle += dt * 0.25;
    const want = dronePos.clone().add(new THREE.Vector3(Math.cos(shot.angle) * 4.5, 1.3, Math.sin(shot.angle) * 4.5));
    want.y = Math.max(want.y, 0.4);
    damp(camera.position, want, camVel, 0.3, dt);
    damp(look, lead, lookVel, 0.08, dt);
    fov = 45;
  } else if (kind === 'wide') {
    damp(camera.position, world(-55, -60, 22), camVel, 1.2, dt);
    damp(look, dronePos.clone().multiplyScalar(0.7), lookVel, 0.4, dt);
    fov = 44;
  } else if (kind === 'top') {
    camera.up.set(0, 0, -1);
    damp(camera.position, dronePos.clone().add(new THREE.Vector3(0, 12, 0.001)), camVel, 0.25, dt);
    damp(look, dronePos, lookVel, 0.08, dt);
    fov = 50;
  } else if (kind === 'orbit') {
    const delta = dronePos.clone().sub(controls.target);
    controls.target.add(delta); camera.position.add(delta);
    controls.update();
  }
  if (kind !== 'orbit') camera.lookAt(look);
  if (kind !== 'top') camera.up.set(0, 1, 0);
  if (kind !== 'orbit') { camera.fov = lerp(camera.fov, fov, 1 - Math.exp(-dt * 3)); camera.updateProjectionMatrix(); }
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
  const f = fingers.map(([x, lift]) => {
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
  chip('chip-src', SOURCE === 'replay' ? 'warn' : 'ok', SOURCE === 'replay' ? 'Recorded tour'
    : { hub: 'Physical hub', manual: 'You are flying', virtual: 'Virtual pilot' }[f.source] || '—');
  if (SOURCE === 'live') syncFlying(f);
  $('caption').textContent = f.caption || '';
  const recent = (f.texts || []).filter(([t]) => f.t - t < 8);
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

// --- flying it yourself: the keyboard is the two hands --------------------------------------
const you = { curl: 0, lroll: 0, rroll: 0, rpitch: 0, enable: false };
const held = new Set();
let flying = false, newest = null;
const post = (path, body) => fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }).catch(() => {});

function showFlying(on) {
  flying = on;
  $('fly-body').hidden = !on;
  $('fly-hint').hidden = on;
  $('fly-toggle').textContent = on ? 'Give back' : 'Take the hands';
  $('fly-toggle').className = on ? 'quiet' : '';
}
function syncFlying(f) {
  newest = f;
  if ((f.source === 'manual') !== flying) {
    if (f.source === 'manual' && f.hands) Object.assign(you, { curl: f.hands.left.curl, enable: f.hands.enable });
    showFlying(f.source === 'manual');
  }
  $('fly-notice').textContent = f.notice || '';
  if (!flying || !f.hands) return;
  // What state you are in, and the one key to press next.
  const en = f.hands.enable, airborne = f.pos[2] > 0.3, thr = Math.round(you.curl * 100);
  const control = f.mode === 'ALT HOLD';
  $('fly-state').innerHTML = [
    [`Enable ${en ? 'on' : 'off'}`, en ? 'on' : 'bad'], [f.armed ? 'Armed' : 'Disarmed', f.armed ? 'on' : ''],
    [f.mode, control ? 'on' : 'bad'], [`Throttle ${thr}%`, ''],
  ].map(([t, c]) => `<span class="${c}">${t}</span>`).join('');
  let next;
  if (!en) next = thr > 4 ? 'Hold S until throttle reads 0%, then press E' : 'Press E to turn ENABLE on';
  else if (!f.armed) next = thr > 8 ? 'Hold S until throttle reads 0%, then press R to arm' : 'Press R to arm';
  else if (!control) next = `ArduCopter is in ${f.mode} and ignores the sticks. Press H to take control`;
  else if (!airborne && thr < 60) next = 'Hold W until throttle passes 60% to take off, then press Q';
  else if (airborne && thr < 40) next = 'Throttle is low, so it is descending. Press Q to hold height';
  else if (airborne && thr > 60) next = 'Climbing. Press Q to hold height';
  else if (airborne) next = 'Flying. Arrows tilt, A/D yaw. To land, hold S to about 25%';
  else next = 'On the ground. Hold S to 0%, then F to disarm';
  $('fly-next').textContent = next;
}
$('fly-toggle').addEventListener('click', (e) => {
  const on = !flying;
  if (on && newest && newest.hands) Object.assign(you, { curl: newest.hands.left.curl, enable: newest.hands.enable });
  showFlying(on);
  post('/control', { manual: on });
  e.currentTarget.blur();
});
const FLY_KEYS = ['KeyW', 'KeyS', 'KeyA', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'KeyE', 'KeyR', 'KeyF', 'KeyH', 'KeyQ'];
window.addEventListener('keydown', (e) => {
  if (e.key === 'Shift') held.add(e.code);
  if (!flying || !FLY_KEYS.includes(e.code)) return;
  e.preventDefault();
  held.add(e.code);
  if (e.repeat) return;
  if (e.code === 'KeyE') you.enable = !you.enable;
  if (e.code === 'KeyR') post('/arm', { on: true });
  if (e.code === 'KeyF') post('/arm', { on: false });
  if (e.code === 'KeyH') post('/althold');
  if (e.code === 'KeyQ') you.curl = 0.52;          // back to about half curl: ALT HOLD holds height
});
window.addEventListener('keyup', (e) => held.delete(e.code));
window.addEventListener('blur', () => held.clear());
let lastSend = performance.now();
setInterval(() => {
  const now = performance.now(), dt = (now - lastSend) / 1000;
  lastSend = now;
  if (!flying) return;
  const k = (c) => (held.has(c) ? 1 : 0);
  const tilt = held.has('ShiftLeft') || held.has('ShiftRight') ? 30 : 17;
  you.curl = clamp(you.curl + (k('KeyW') - k('KeyS')) * 0.22 * dt, 0, 1);
  you.lroll = (k('KeyD') - k('KeyA')) * (tilt + 4);
  you.rroll = (k('ArrowRight') - k('ArrowLeft')) * tilt;
  you.rpitch = (k('ArrowUp') - k('ArrowDown')) * tilt;
  post('/hands', you);
}, 33);

// --- main loop --------------------------------------------------------------------------------
buildGround();
buildGrass();
buildTrees();
buildClouds();
const scenery = buildProps();
const drone = buildDrone();
camera.position.set(-5, 2.6, 7);
look.set(0, 0.6, 0);

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

let last = performance.now(), hudDue = 0, frameTimes = [], prAdjustAt = 0;
function frame(nowMs) {
  const dt = Math.min(0.05, (nowMs - last) / 1000);
  last = nowMs;
  const now = nowMs / 1000;
  let t = null;
  if (SOURCE === 'live') t = liveTime(now);
  else if (frames.length && playhead !== null) {
    if (playing) playhead += dt * speed;
    const end = frames[frames.length - 1].t;
    if (playhead > end) { playhead = frames[0].t; clearTrail(); }
    t = playhead;
    $('scrub').value = String(Math.round(1000 * (playhead - frames[0].t) / (end - frames[0].t)));
    const el = playhead - frames[0].t;
    $('rt').textContent = `${Math.floor(el / 60)}:${String(Math.floor(el % 60)).padStart(2, '0')}`;
  }
  const s = t !== null ? sample(t) : null;
  const f = s ? s.f : null;
  if (s) {
    dronePos.copy(s.pos);
    dronePos.y += GEAR;
    droneVel.set(f.vel[1], -f.vel[2], -f.vel[0]);
    drone.group.position.copy(dronePos);
    drone.group.quaternion.copy(s.quat);
    if (f.motors) drone.props.forEach((p, i) => {
      const spin = clamp((f.motors[i] - 1000) / 1000, 0, 1);
      p.angle += p.dir * spin * 62 * dt;
      p.group.rotation.y = p.angle;
      p.bladeMat.opacity = 1 - 0.85 * smooth(0.12, 0.42, spin);
      p.disc.material.opacity = 0.65 * smooth(0.08, 0.4, spin);
      p.disc.rotation.y = p.angle * 0.13;
    });
    const alt = f.pos[2];
    if (f.armed || alt > 0.2) pushTrail(dronePos.clone().setY(dronePos.y - GEAR + 0.05));
    const dp = drop.geometry.attributes.position;
    dp.setXYZ(0, dronePos.x, dronePos.y - GEAR, dronePos.z); dp.setXYZ(1, dronePos.x, 0.05, dronePos.z); dp.needsUpdate = true;
    drop.computeLineDistances();
    drop.visible = footRing.visible = alt > 0.8;
    footRing.position.set(dronePos.x, 0.06, dronePos.z);
    footRing.scale.setScalar(1 + alt * 0.04);
    drone.status.material.color.set(f.armed ? 0x5fe39a : 0xffb547);
    const thrust = f.motors ? f.motors.reduce((a, b) => a + b, 0) / 4 : 1000;
    U.uDrone.value.copy(dronePos);
    U.uWash.value = clamp((thrust - 1100) / 600, 0, 1) * smooth(4.5, 0.6, alt);
    if (now > hudDue) { updateHud(f); hudDue = now + 1 / 12; }
  }
  const blink = (now % 1.2) < 0.08;
  drone.leds.forEach((l) => { l.glow.material.opacity = l.front ? 0.85 : blink ? 1 : 0.35; });
  scenery.sock.rotation.z = Math.sin(now * 2.3) * 0.05 + Math.sin(now * 5.1) * 0.02;
  scenery.sock.rotation.x = Math.sin(now * 1.7) * 0.04;
  U.uTime.value = now;

  updateCamera(dt, now, f);
  U.uCam.value.copy(camera.position);
  const camDist = camera.position.distanceTo(dronePos);
  locator.position.copy(dronePos);
  locator.visible = camDist / (camera.fov * DEG) > 40;
  sun.position.copy(dronePos).addScaledVector(sunDir, 150);
  sun.target.position.copy(dronePos);
  renderer.render(scene, camera);

  // Hold the frame rate: drop the render resolution a step if frames take too long.
  frameTimes.push(dt);
  if (frameTimes.length > 90) frameTimes.shift();
  if (now > prAdjustAt && frameTimes.length === 90) {
    const avg = frameTimes.reduce((a, b) => a + b, 0) / 90;
    if (avg > 1 / 45 && pixelRatio > 0.75) { pixelRatio -= 0.25; renderer.setPixelRatio(pixelRatio); resize(); prAdjustAt = now + 3; frameTimes = []; }
  }
  requestAnimationFrame(frame);
}

if (SOURCE === 'live') connectLive(); else loadReplay().catch((e) => { $('wait-title').textContent = 'Could not load the recorded flight'; $('wait-sub').textContent = String(e); });
requestAnimationFrame(frame);
