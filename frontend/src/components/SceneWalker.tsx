/**
 * SceneWalker — 第三人称场景漫游器
 * 加载场景中所有 GLB 模型，支持 WASD 移动 + 鼠标视角，类 RPG 游戏体验
 */
import { useRef, useEffect, useState, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

interface SceneObj {
  id: string;
  name: string;
  url: string;
  position: number[];
  rotation_y?: number;
  scale: number;
  category?: string;
}

interface Props {
  objects: SceneObj[];
  sceneName: string;
  onClose: () => void;
}

export function SceneWalker({ objects, sceneName, onClose }: Props) {
  const mountRef    = useRef<HTMLDivElement>(null);
  const stateRef    = useRef({
    yaw: 0, pitch: 0.3,
    px: 0, py: 0, pz: 0,
    keys: { w: false, s: false, a: false, d: false, space: false },
    locked: false,
    sprint: false,
  });
  const rafRef      = useRef(0);
  const rendRef     = useRef<THREE.WebGLRenderer | null>(null);
  const sceneThree  = useRef<THREE.Scene | null>(null);
  const camRef      = useRef<THREE.PerspectiveCamera | null>(null);
  const charRef     = useRef<THREE.Group | null>(null);

  const [locked,   setLocked]   = useState(false);
  const [loading,  setLoading]  = useState(true);
  const [loadedN,  setLoadedN]  = useState(0);
  const [hint,     setHint]     = useState(true);

  const SPEED       = 0.08;
  const SPRINT_MUL  = 2.2;
  const CAM_DIST    = 5;
  const CAM_HEIGHT  = 2.8;
  const PITCH_MIN   = -0.25;
  const PITCH_MAX   = 0.85;

  // ── Build Three.js world ───────────────────────────────────────────────────
  const buildWorld = useCallback(() => {
    const container = mountRef.current;
    if (!container) return;

    const W = container.clientWidth, H = container.clientHeight;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // 不用 innerHTML='' 清空（避免与 React 虚拟DOM冲突），直接 append canvas
    container.appendChild(renderer.domElement);
    rendRef.current = renderer;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0a0e1a');
    scene.fog = new THREE.FogExp2('#0a0e1a', 0.018);
    sceneThree.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(65, W / H, 0.05, 300);
    camRef.current = camera;

    // Lights
    scene.add(new THREE.AmbientLight(0x334466, 1.2));
    const sun = new THREE.DirectionalLight(0xfff0d8, 2.8);
    sun.position.set(20, 40, 15);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left   = -60;
    sun.shadow.camera.right  =  60;
    sun.shadow.camera.top    =  60;
    sun.shadow.camera.bottom = -60;
    sun.shadow.camera.far    = 200;
    scene.add(sun);
    scene.add(new THREE.HemisphereLight(0x334466, 0x442211, 0.7));

    // Sky gradient quad
    const skyGeo = new THREE.SphereGeometry(250, 16, 8);
    const skyMat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      vertexShader: `
        varying vec3 vWorldPos;
        void main(){
          vWorldPos = (modelMatrix * vec4(position,1.0)).xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
        }`,
      fragmentShader: `
        varying vec3 vWorldPos;
        void main(){
          float t = clamp(normalize(vWorldPos).y * 0.5 + 0.5, 0.0, 1.0);
          vec3 bottom = vec3(0.04, 0.06, 0.14);
          vec3 top    = vec3(0.01, 0.03, 0.25);
          gl_FragColor = vec4(mix(bottom, top, t), 1.0);
        }`,
    });
    scene.add(new THREE.Mesh(skyGeo, skyMat));

    // Ground
    const groundGeo = new THREE.PlaneGeometry(200, 200, 80, 80);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x111822,
      roughness: 0.95,
      metalness: 0.1,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // Grid overlay
    const grid = new THREE.GridHelper(200, 80, 0x1a2a3a, 0x0d1520);
    (grid.material as THREE.Material).opacity = 0.5;
    (grid.material as THREE.Material).transparent = true;
    grid.position.y = 0.01;
    scene.add(grid);

    // Character (third-person capsule stand-in, glows)
    const charGroup = new THREE.Group();
    const bodyGeo   = new THREE.CylinderGeometry(0.25, 0.22, 1.5, 12);
    const bodyMat   = new THREE.MeshStandardMaterial({ color: 0x0088ff, emissive: 0x004499, roughness: 0.3 });
    const head      = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 8), bodyMat);
    head.position.y = 1.15;
    charGroup.add(new THREE.Mesh(bodyGeo, bodyMat));
    charGroup.add(head);
    // Aura ring
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.45, 0.04, 8, 24),
      new THREE.MeshBasicMaterial({ color: 0x00ccff, transparent: true, opacity: 0.6 })
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.1;
    charGroup.add(ring);
    charGroup.position.y = 0.75;
    charGroup.castShadow = true;
    scene.add(charGroup);
    charRef.current = charGroup;

    // Load all scene objects
    const loader = new GLTFLoader();
    let done = 0;
    const total = objects.length || 1;

    objects.forEach(obj => {
      const fullUrl = obj.url.startsWith('http') ? obj.url : `http://localhost:8000${obj.url}`;
      loader.load(
        fullUrl,
        gltf => {
          const model = gltf.scene;
          model.traverse(c => {
            if ((c as THREE.Mesh).isMesh) {
              c.castShadow = true;
              c.receiveShadow = true;
            }
          });

          // Normalize: max dimension → obj.scale meters
          const box1 = new THREE.Box3().setFromObject(model);
          const dim  = box1.getSize(new THREE.Vector3());
          const maxDim = Math.max(dim.x, dim.y, dim.z) || 1;
          const sc = (obj.scale ?? 1.0) / maxDim;
          model.scale.setScalar(sc);

          // Recalc bounds and sit on ground
          const box2 = new THREE.Box3().setFromObject(model);
          model.position.y = -box2.min.y;

          // World position from scene plan
          model.position.x = obj.position[0] ?? 0;
          model.position.z = obj.position[2] ?? 0;

          // Y-axis rotation
          model.rotation.y = ((obj.rotation_y ?? 0) * Math.PI) / 180;

          scene.add(model);
          done++;
          setLoadedN(done);
          if (done >= objects.length) setLoading(false);
        },
        undefined,
        () => {
          done++;
          setLoadedN(done);
          if (done >= total) setLoading(false);
        }
      );
    });

    if (objects.length === 0) setLoading(false);

    // ── Animate loop ──
    const s = stateRef.current;
    const tmpFwd   = new THREE.Vector3();
    const tmpRight = new THREE.Vector3();

    const animate = () => {
      rafRef.current = requestAnimationFrame(animate);

      // Movement
      const spd = SPEED * (s.sprint ? SPRINT_MUL : 1);
      tmpFwd.set(-Math.sin(s.yaw), 0, -Math.cos(s.yaw));
      tmpRight.set(Math.cos(s.yaw), 0, -Math.sin(s.yaw));

      if (s.keys.w) { s.px += tmpFwd.x * spd;  s.pz += tmpFwd.z * spd;  }
      if (s.keys.s) { s.px -= tmpFwd.x * spd;  s.pz -= tmpFwd.z * spd;  }
      if (s.keys.a) { s.px -= tmpRight.x * spd; s.pz -= tmpRight.z * spd; }
      if (s.keys.d) { s.px += tmpRight.x * spd; s.pz += tmpRight.z * spd; }

      // Clamp to ground
      s.py = 0;

      // Update character
      if (charRef.current) {
        charRef.current.position.set(s.px, s.py + 0.75, s.pz);
        charRef.current.rotation.y = s.yaw;
        // Animate aura ring
        charRef.current.children[2].rotation.z += 0.03;
      }

      // Third-person camera
      const cPitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, s.pitch));
      const cx = s.px + CAM_DIST * Math.sin(s.yaw) * Math.cos(cPitch);
      const cy = s.py + CAM_HEIGHT + CAM_DIST * Math.sin(cPitch);
      const cz = s.pz + CAM_DIST * Math.cos(s.yaw) * Math.cos(cPitch);
      camera.position.set(cx, cy, cz);
      camera.lookAt(s.px, s.py + 1.5, s.pz);

      renderer.render(scene, camera);
    };
    animate();

    // Resize
    const onResize = () => {
      const w = container.clientWidth, h = container.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(container);

    return () => {
      ro.disconnect();
      // 安全删除 canvas，防止 React 卸载时出现 removeChild 崩溃
      try {
        if (renderer.domElement.parentNode === container) {
          container.removeChild(renderer.domElement);
        }
      } catch { /* ignore */ }
    };
  }, [objects]);

  // ── Input handling ─────────────────────────────────────────────────────────
  useEffect(() => {
    const s = stateRef.current;

    const onKey = (e: KeyboardEvent, down: boolean) => {
      switch (e.code) {
        case 'KeyW': case 'ArrowUp':    s.keys.w = down; break;
        case 'KeyS': case 'ArrowDown':  s.keys.s = down; break;
        case 'KeyA': case 'ArrowLeft':  s.keys.a = down; break;
        case 'KeyD': case 'ArrowRight': s.keys.d = down; break;
        case 'ShiftLeft': case 'ShiftRight': s.sprint = down; break;
        case 'Escape': if (down) { document.exitPointerLock(); onClose(); } break;
      }
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!s.locked) return;
      s.yaw   -= e.movementX * 0.002;
      s.pitch -= e.movementY * 0.002;
      s.pitch  = Math.max(-0.25, Math.min(0.85, s.pitch));
    };

    const onPLChange = () => {
      s.locked = document.pointerLockElement === mountRef.current?.querySelector('canvas');
      setLocked(s.locked);
      if (s.locked) setHint(false);
    };

    window.addEventListener('keydown', e => onKey(e, true));
    window.addEventListener('keyup',   e => onKey(e, false));
    window.addEventListener('mousemove', onMouseMove);
    document.addEventListener('pointerlockchange', onPLChange);

    return () => {
      window.removeEventListener('keydown', e => onKey(e, true));
      window.removeEventListener('keyup',   e => onKey(e, false));
      window.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('pointerlockchange', onPLChange);
    };
  }, [onClose]);

  // ── Setup scene ────────────────────────────────────────────────────────────
  useEffect(() => {
    const cleanup = buildWorld();
    return () => {
      cleanup?.();
      cancelAnimationFrame(rafRef.current);
      // canvas 已由 buildWorld cleanup 删除，这里只停渲染器资源
      try { rendRef.current?.dispose(); } catch { /* ignore */ }
      rendRef.current = null;
    };
  }, [buildWorld]);

  const requestLock = () => {
    const canvas = mountRef.current?.querySelector('canvas');
    canvas?.requestPointerLock();
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: '#000',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* 3D Canvas */}
      <div ref={mountRef} style={{ flex: 1, position: 'relative', cursor: locked ? 'none' : 'crosshair' }}>

        {/* Loading overlay */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            background: 'rgba(10,14,26,0.92)', zIndex: 10,
          }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>🌍</div>
            <div style={{ fontSize: 14, color: '#58a6ff', fontWeight: 600, marginBottom: 8 }}>
              正在加载场景：{sceneName}
            </div>
            <div style={{ width: 240, height: 6, background: '#1c2333', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 3,
                background: 'linear-gradient(90deg, #1f6feb, #58a6ff)',
                width: `${Math.round((loadedN / Math.max(objects.length, 1)) * 100)}%`,
                transition: 'width 0.3s',
              }} />
            </div>
            <div style={{ fontSize: 11, color: '#8b949e', marginTop: 6 }}>
              {loadedN} / {objects.length} 个物体
            </div>
          </div>
        )}

        {/* Click to enter overlay */}
        {!loading && !locked && (
          <div
            onClick={requestLock}
            style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              background: 'rgba(10,14,26,0.78)', zIndex: 10, cursor: 'pointer',
            }}
          >
            <div style={{ fontSize: 36, marginBottom: 12, animation: 'pulse 1.5s infinite' }}>🎮</div>
            <div style={{ fontSize: 16, color: '#fff', fontWeight: 700, marginBottom: 6 }}>
              点击进入场景
            </div>
            <div style={{ fontSize: 12, color: '#8b949e' }}>
              WASD 移动 · 鼠标旋转视角 · Shift 加速 · ESC 退出
            </div>
          </div>
        )}

        {/* HUD — controls hint */}
        {locked && hint && (
          <div style={{
            position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)',
            borderRadius: 10, padding: '8px 20px', color: '#8b949e', fontSize: 11,
            border: '1px solid rgba(255,255,255,0.08)',
            display: 'flex', gap: 16, alignItems: 'center',
          }}>
            <span>⬆⬇⬅➡ / WASD 移动</span>
            <span>Shift 加速</span>
            <span>鼠标 转向</span>
            <span style={{ color: '#ff7b72' }}>ESC 退出</span>
          </div>
        )}

        {/* Scene name badge */}
        {locked && (
          <div style={{
            position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(8px)',
            borderRadius: 20, padding: '4px 16px', color: '#58a6ff', fontSize: 12,
            border: '1px solid rgba(88,166,255,0.2)',
          }}>
            🏙️ {sceneName}
          </div>
        )}

        {/* Object count crosshair */}
        {locked && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            width: 6, height: 6, borderRadius: '50%',
            background: 'rgba(255,255,255,0.7)',
            boxShadow: '0 0 6px rgba(255,255,255,0.4)',
            pointerEvents: 'none',
          }} />
        )}
      </div>

      {/* Top bar */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px', pointerEvents: 'none',
        zIndex: 20,
      }}>
        <div style={{ display: 'flex', gap: 8, pointerEvents: 'all' }}>
          <button
            onClick={() => { document.exitPointerLock(); onClose(); }}
            style={{
              background: 'rgba(22,27,34,0.85)', backdropFilter: 'blur(8px)',
              border: '1px solid rgba(255,255,255,0.1)', color: '#ff7b72',
              borderRadius: 8, padding: '5px 14px', cursor: 'pointer', fontSize: 12,
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            ✕ 退出场景
          </button>
        </div>

        {/* Mini object list */}
        <div style={{
          display: 'flex', gap: 6, pointerEvents: 'none',
          flexWrap: 'wrap', justifyContent: 'flex-end', maxWidth: '60%',
        }}>
          {objects.slice(0, 8).map(o => (
            <div key={o.id} style={{
              background: 'rgba(22,27,34,0.7)', backdropFilter: 'blur(4px)',
              border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6,
              padding: '2px 8px', fontSize: 10, color: '#8b949e',
            }}>
              {o.name}
            </div>
          ))}
          {objects.length > 8 && (
            <div style={{ background: 'rgba(22,27,34,0.7)', borderRadius: 6, padding: '2px 8px', fontSize: 10, color: '#8b949e' }}>
              +{objects.length - 8}
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.8; }
        }
      `}</style>
    </div>
  );
}
