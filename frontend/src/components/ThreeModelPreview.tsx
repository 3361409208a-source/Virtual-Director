import { useRef, useEffect, useCallback, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { HDRLoader } from 'three/examples/jsm/loaders/HDRLoader';

type LightingPreset = 'studio' | 'sunset' | 'forest' | 'cyberpunk' | 'city' | 'desert' | 'snow';

interface Props {
  url: string | null;
  parts?: any[]; // New: support real-time parts
  backgroundColor?: string;
}

export function ThreeModelPreview({ url, parts, backgroundColor = '#0d1117' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const currentModelRef = useRef<THREE.Group | null>(null);
  const rafRef = useRef<number>(0);
  const loaderRef = useRef<GLTFLoader>(new GLTFLoader());

  const [preset, setPreset] = useState<LightingPreset>('studio');

  // References to lights for dynamic updates
  const lightsRef = useRef<{
    ambient: THREE.AmbientLight;
    key: THREE.DirectionalLight;
    fill: THREE.DirectionalLight;
    rim: THREE.DirectionalLight;
  } | null>(null);

  const applyPreset = useCallback((p: LightingPreset) => {
    const lights = lightsRef.current;
    const scene = sceneRef.current;
    if (!lights || !scene) return;

    switch (p) {
      case 'studio':
        lights.ambient.intensity = 0.5;
        lights.ambient.color.set(0xffffff);
        lights.key.intensity = 1.2;
        lights.key.color.set(0xfff5e6);
        lights.key.position.set(3, 5, 4);
        lights.fill.intensity = 0.4;
        lights.fill.color.set(0xc4d4ff);
        lights.rim.intensity = 0.3;
        lights.rim.color.set(0xffffff);
        scene.background = new THREE.Color(backgroundColor);
        break;
      case 'sunset':
        lights.ambient.intensity = 0.3;
        lights.ambient.color.set(0xffdcb4);
        lights.key.intensity = 2.0;
        lights.key.color.set(0xff8c00);
        lights.key.position.set(5, 3, 2);
        lights.fill.intensity = 0.2;
        lights.fill.color.set(0x334466);
        lights.rim.intensity = 1.5;
        lights.rim.color.set(0xffcc00);
        scene.background = new THREE.Color('#1a0f00');
        break;
      case 'forest':
        lights.ambient.intensity = 0.4;
        lights.ambient.color.set(0xccffcc);
        lights.key.intensity = 1.0;
        lights.key.color.set(0xe6fffa);
        lights.key.position.set(-2, 5, 3);
        lights.fill.intensity = 0.6;
        lights.fill.color.set(0x113311);
        lights.rim.intensity = 0.8;
        lights.rim.color.set(0xaaffaa);
        scene.background = new THREE.Color('#051105');
        break;
      case 'cyberpunk':
        lights.ambient.intensity = 0.2;
        lights.ambient.color.set(0xff00ff);
        lights.key.intensity = 1.8;
        lights.key.color.set(0x00ffff);
        lights.key.position.set(4, 2, 4);
        lights.fill.intensity = 1.2;
        lights.fill.color.set(0xff00ff);
        lights.rim.intensity = 2.0;
        lights.rim.color.set(0x00ff00);
        scene.background = new THREE.Color('#0a000a');
        break;
      case 'city':
        loadHDR('/hdri/city.hdr');
        break;
      case 'desert':
        loadHDR('/hdri/sunset.hdr');
        break;
      case 'forest':
        loadHDR('/hdri/forest.hdr');
        break;
      case 'snow':
        lights.ambient.intensity = 0.8;
        lights.ambient.color.set(0xffffff);
        scene.background = new THREE.Color('#0b1a2a');
        break;
    }
  }, [backgroundColor]);

  const loadHDR = (url: string) => {
    const scene = sceneRef.current;
    const renderer = rendererRef.current;
    if (!scene || !renderer) return;

    new HDRLoader().load(url, (texture) => {
      texture.mapping = THREE.EquirectangularReflectionMapping;
      scene.environment = texture;
      scene.background = texture;
    }, undefined, (err) => {
      console.warn(`HDR load failed for ${url}:`, err);
      if (sceneRef.current) {
        sceneRef.current.environment = null;
        sceneRef.current.background = new THREE.Color(backgroundColor);
      }
    });
  };

  const setupScene = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(backgroundColor);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(50, w / h, 0.01, 100);
    camera.position.set(2, 1.5, 3);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0, 0.5, 0);
    controlsRef.current = controls;

    // Create lights
    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);

    const key = new THREE.DirectionalLight(0xffffff, 1.0);
    key.position.set(3, 5, 4);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    scene.add(key);

    const fill = new THREE.DirectionalLight(0xffffff, 0.4);
    fill.position.set(-3, 2, -2);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0xffffff, 0.3);
    rim.position.set(0, 3, -5);
    scene.add(rim);

    lightsRef.current = { ambient, key, fill, rim };
    applyPreset('studio');

    // Ground & Grid
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 20),
      new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    scene.add(new THREE.GridHelper(10, 20, 0x222222, 0x1a1a1a));

    const animate = () => {
      rafRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();
  }, [backgroundColor, applyPreset]);

  useEffect(() => {
    setupScene();
    return () => {
      cancelAnimationFrame(rafRef.current);
      rendererRef.current?.dispose();
    };
  }, [setupScene]);

  // Handle Preset Change
  useEffect(() => {
    applyPreset(preset);
  }, [preset, applyPreset]);

  // Load Model
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !url) return;
    if (currentModelRef.current) scene.remove(currentModelRef.current);

    const fullUrl = url.startsWith('http') ? url : `http://localhost:8000${url}`;
    loaderRef.current.load(fullUrl, (gltf) => {
      const model = gltf.scene;
      model.traverse((child) => {
        if ((child as THREE.Mesh).isMesh) {
          child.castShadow = true;
          child.receiveShadow = true;
        }
      });
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());
      const scale = 2.0 / Math.max(size.x, size.y, size.z || 1);
      model.scale.setScalar(scale);
      const box2 = new THREE.Box3().setFromObject(model);
      const center2 = box2.getCenter(new THREE.Vector3());
      model.position.sub(center2);
      model.position.y += box2.getSize(new THREE.Vector3()).y / 2;
      scene.add(model);
      currentModelRef.current = model;
    });
  }, [url]);
  
  // Real-time Parts Rendering
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !parts || parts.length === 0) return;
    if (currentModelRef.current && !url) {
       scene.remove(currentModelRef.current);
       currentModelRef.current = null;
    }

    const group = new THREE.Group();
    parts.forEach(p => {
      let geo;
      const size = p.size || {x:1, y:1, z:1};
      switch(p.shape) {
        case 'sphere': geo = new THREE.SphereGeometry(size.x/2); break;
        case 'capsule': geo = new THREE.CapsuleGeometry(size.x/2, size.y); break;
        case 'cylinder': geo = new THREE.CylinderGeometry(size.x/2, size.x/2, size.y); break;
        default: geo = new THREE.BoxGeometry(size.x, size.y, size.z);
      }
      const color = p.color ? new THREE.Color(p.color.r, p.color.g, p.color.b) : new THREE.Color(0x888888);
      const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.2 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(p.position?.x || 0, p.position?.y || 0, p.position?.z || 0);
      if (p.rotation) mesh.rotation.set(p.rotation.x || 0, p.rotation.y || 0, p.rotation.z || 0);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
    });
    
    if (currentModelRef.current) scene.remove(currentModelRef.current);
    scene.add(group);
    currentModelRef.current = group;
  }, [parts, url]);

  const presets: { id: LightingPreset; label: string; icon: string }[] = [
    { id: 'studio', label: '工作室', icon: '🏢' },
    { id: 'city', label: '城市', icon: '🏙️' },
    { id: 'desert', label: '荒漠', icon: '🏜️' },
    { id: 'snow', label: '冰原', icon: '❄️' },
    { id: 'sunset', label: '夕阳', icon: '🌅' },
    { id: 'forest', label: '森林', icon: '🌲' },
    { id: 'cyberpunk', label: '赛博', icon: '🧬' },
  ];

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div style={{
        position: 'absolute',
        bottom: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        gap: 6,
        padding: '6px',
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(8px)',
        borderRadius: 12,
        border: '1px solid rgba(255,255,255,0.1)',
        zIndex: 10
      }}>
        {presets.map(p => (
          <button
            key={p.id}
            onClick={() => setPreset(p.id)}
            style={{
              padding: '1px 4px',
              borderRadius: 4,
              border: 'none',
              background: preset === p.id ? 'rgba(56,139,253,0.3)' : 'transparent',
              color: preset === p.id ? '#58a6ff' : '#8b949e',
              fontSize: 9,
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: 2,
              transition: 'all 0.2s',
              whiteSpace: 'nowrap'
            } as any}
          >
            <span>{p.icon}</span>
            <span>{p.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
