/* Three.js avatar renderer (v0.8 reference). Same event API as avatar.js.
 *
 * Loads the procedural reference-avatar.glb (or any user VRM/GLB) and drives
 * Jaw/EyeL/EyeR nodes from VISEME/GAZE events. Used by ui/three.html; the
 * default index.html stays on the offline 2D fallback.
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
  scene.background = new THREE.Color(0x1a1a1a);
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

  const api = {
    three: true,
    nodeNames: Object.keys(nodes),
    meshCount: gltf.scene.children.length,
    apply(ev) {
      if (ev.viseme && JAW[ev.viseme] !== undefined && nodes.Jaw) {
        nodes.Jaw.position.y = jawBaseY - JAW[ev.viseme] * 0.06;
      }
      if (typeof ev.intensity === 'number' && nodes.EyeL && nodes.EyeR) {
        const g = (ev.intensity - 0.5) * 0.04;
        nodes.EyeL.position.x = -0.07 + g;
        nodes.EyeR.position.x = 0.07 + g;
      }
      if (ev.emotion === 'happy' && nodes.Head) {
        nodes.Head.rotation.z = 0.06 * (ev.intensity || 0.5);
      } else if (nodes.Head) {
        nodes.Head.rotation.z = 0;
      }
      renderer.render(scene, camera);
      const label = document.getElementById('avatar-state');
      if (label) label.textContent = (ev.event || 'IDLE') + ' [3d]';
    },
  };
  api.apply({ event: 'IDLE' });
  return api;
}

window.AvatarThree = { createThreeRenderer, JAW };
