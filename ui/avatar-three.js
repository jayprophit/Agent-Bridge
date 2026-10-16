/* Three.js avatar renderer (v1.1).
 *
 * Same event protocol as avatar.js (v0.8 reference API), extended with:
 *  - jaw/gaze smoothing (targets lerp every frame, no snap)
 *  - viseme lip-sync events ({viseme: "aa"|...}) drive the Jaw node
 *  - event-name guarded labels so VISEME/EMOTION steps never clobber state
 *
 * Lazily imported by app.js when the user flips the 3D toggle. Loads the
 * procedural reference-avatar.glb via the vendored GLB pipeline (needs the
 * page-level importmap "three" -> ./vendor/three.module.js). Any failure is
 * caught by the caller and the image-state renderer stays in charge.
 */
import * as THREE from './vendor/three.module.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

const JAW = { sil: 0.0, PP: 0.05, FF: 0.15, TH: 0.2, DD: 0.35, kk: 0.3,
  CH: 0.35, SS: 0.25, nn: 0.3, RR: 0.4, aa: 1.0, E: 0.55, I: 0.35,
  O: 0.7, U: 0.4 };

export async function createThreeRenderer(canvas, glbUrl) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setSize(canvas.width, canvas.height, false);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0d11);
  const camera = new THREE.PerspectiveCamera(40, canvas.width / canvas.height, 0.1, 10);
  camera.position.set(0, 1.2, 3.2);
  camera.lookAt(0, 1.1, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.2));
  const key = new THREE.DirectionalLight(0xffffff, 1.0);
  key.position.set(2, 4, 3);
  scene.add(key);

  const gltf = await new GLTFLoader().loadAsync(glbUrl);
  scene.add(gltf.scene);
  const nodes = {};
  gltf.scene.traverse((o) => { if (o.name) nodes[o.name] = o; });
  const jawBaseY = nodes.Jaw ? nodes.Jaw.position.y : 0;

  let jawTarget = 0, jawCurrent = 0, gazeTarget = 0, gazeCurrent = 0;
  let lastEvent = 'IDLE';
  let running = true;

  function loop() {
    if (!running) return;
    jawCurrent += (jawTarget - jawCurrent) * 0.28;
    gazeCurrent += (gazeTarget - gazeCurrent) * 0.28;
    if (nodes.Jaw) nodes.Jaw.position.y = jawBaseY - jawCurrent * 0.06;
    if (nodes.EyeL && nodes.EyeR) {
      const g = gazeCurrent * 0.04;
      nodes.EyeL.position.x = -0.07 + g;
      nodes.EyeR.position.x = 0.07 + g;
    }
    if (nodes.Head) {
      const tilt = lastEvent === 'SPEAKING' ? 0.02 : 0;
      nodes.Head.rotation.z += (tilt - nodes.Head.rotation.z) * 0.1;
    }
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  const api = {
    three: true,
    nodeNames: Object.keys(nodes),
    meshCount: gltf.scene.children.length,
    apply(ev) {
      if (ev.viseme && JAW[ev.viseme] !== undefined) jawTarget = JAW[ev.viseme];
      if (typeof ev.intensity === 'number') gazeTarget = (ev.intensity - 0.5) * 0.8;
      const name = ev.event || '';
      if (name && name !== 'VISEME' && name !== 'EMOTION') {
        lastEvent = name;
        if (name === 'IDLE' || name === 'ERROR') { jawTarget = 0; gazeTarget = 0; }
        const label = document.getElementById('avatar-state');
        if (label) label.textContent = name + ' [3d]';
      }
      if (ev.emotion === 'happy') {
        gazeTarget = Math.max(-0.5, Math.min(0.5, gazeTarget + 0.1));
      }
    },
    dispose() { running = false; },
  };
  api.apply({ event: 'IDLE' });
  return api;
}

window.AvatarThree = { createThreeRenderer, JAW };
