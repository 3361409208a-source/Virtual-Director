import { useRef, useEffect, useCallback, useState } from 'react';
import type { ReactNode } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { HDRLoader } from 'three/examples/jsm/loaders/HDRLoader.js';

type LightingPreset = 'studio' | 'sunset' | 'forest' | 'cyberpunk' | 'city' | 'desert' | 'snow' | 'hills';

interface Props {
  url: string | null;
  parts?: any[]; // New: support real-time parts
  backgroundColor?: string;
  preset?: LightingPreset;
  isRefining?: boolean; // 新增：是否处于精修状态
  currentAction?: string; // 新增：当前播放的动作 (idle, wave, walk, dance)
}

export function ThreeModelPreview({ url, parts, backgroundColor = '#0d1117', preset: initialPreset = 'studio', isRefining = false, currentAction = 'idle' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const currentModelRef = useRef<THREE.Group | null>(null);
  const helperRef = useRef<THREE.SkeletonHelper | null>(null); // 新增：骨骼助手引用
  const scannerRef = useRef<THREE.Mesh | null>(null); // 扫描线引用
  const rafRef = useRef<number>(0);
  const loaderRef = useRef<GLTFLoader>(new GLTFLoader());
  const actionRef = useRef<string>(currentAction); // 新增：用于在渲染循环中实时获取动作

  const [preset, setPreset] = useState<LightingPreset>(initialPreset);

  // 同步动作到 Ref
  useEffect(() => {
    actionRef.current = currentAction;
  }, [currentAction]);

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
        lights.ambient.intensity = 0.8;
        lights.ambient.color.set(0xffffff);
        lights.key.intensity = 2.5; // Significantly boosted
        lights.key.color.set(0xfff5e6);
        lights.key.position.set(3, 5, 4);
        lights.fill.intensity = 1.2; // Boosted
        lights.fill.color.set(0xc4d4ff);
        lights.rim.intensity = 1.5; // Boosted
        lights.rim.color.set(0xffffff);
        scene.background = new THREE.Color(backgroundColor);
        if (rendererRef.current) rendererRef.current.toneMappingExposure = 1.3;
        break;
      case 'sunset':
        loadHDR('/hdri/sunset.hdr');
        lights.ambient.intensity = 0.5;
        lights.ambient.color.set(0xffdcb4);
        lights.key.intensity = 3.5;
        lights.key.color.set(0xffa500);
        lights.key.position.set(5, 3, 2);
        lights.fill.intensity = 1.0;
        lights.fill.color.set(0x334466);
        lights.rim.intensity = 2.5;
        lights.rim.color.set(0xffcc00);
        if (rendererRef.current) rendererRef.current.toneMappingExposure = 1.5; // Higher exposure for sunset
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
        lights.ambient.intensity = 0.6;
        lights.ambient.color.set(0xff00ff);
        lights.key.intensity = 3.0;
        lights.key.color.set(0x00ffff);
        lights.key.position.set(4, 2, 4);
        lights.fill.intensity = 2.0;
        lights.fill.color.set(0xff00ff);
        lights.rim.intensity = 3.5;
        lights.rim.color.set(0x00ff00);
        scene.background = new THREE.Color('#0a000a');
        if (rendererRef.current) rendererRef.current.toneMappingExposure = 1.4;
        break;
      case 'city':
        loadHDR('/hdri/city.hdr');
        break;
      case 'desert':
        loadHDR('/hdri/desert.hdr');
        break;
      case 'sunset':
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
      case 'hills':
        loadHDR('/hdri/golden_gate_hills_1k.hdr');
        lights.ambient.intensity = 0.6;
        lights.key.intensity = 2.8;
        lights.key.color.set(0xfffaee);
        lights.fill.intensity = 1.5;
        if (rendererRef.current) rendererRef.current.toneMappingExposure = 1.2;
        break;
    }
  }, [backgroundColor]);

  const loadHDR = (url: string) => {
    const scene = sceneRef.current;
    const renderer = rendererRef.current;
    if (!scene || !renderer) return;

    new HDRLoader().load(url, (texture: THREE.Texture) => {
      texture.mapping = THREE.EquirectangularReflectionMapping;
      scene.environment = texture;
      scene.background = texture;
    }, undefined, (err: unknown) => {
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
    renderer.toneMappingExposure = 1.3; // Increased from 1.0 for better clarity
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(backgroundColor);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 100);
    camera.position.set(1.5, 1.8, 2.5); // Slightly higher camera for better downward look
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 2.2; 
    controls.mouseButtons.MIDDLE = THREE.MOUSE.PAN;
    controls.target.set(0, 0.1, 0); // Much lower target to push ground to bottom
    controlsRef.current = controls;

    // Create lights
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444, 0.6);
    scene.add(hemiLight);

    const ambient = new THREE.AmbientLight(0xffffff, 0.8);
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

    // Ground (Shadow only to blend with HDR)
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(10, 10),
      new THREE.ShadowMaterial({ opacity: 0.4 }) // Only shows shadows
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.01; // Slightly below zero to avoid z-fighting with models
    ground.receiveShadow = true;
    scene.add(ground);

    // Subtle Static Grid for spatial reference
    const grid = new THREE.GridHelper(20, 20, 0x003366, 0x001133);
    grid.material.opacity = 0.4;
    grid.material.transparent = true;
    scene.add(grid);

    const animate = () => {
      rafRef.current = requestAnimationFrame(animate);
      
      const time = Date.now() * 0.001;

      // 自动动画系统（如果有骨骼）
      if (currentModelRef.current) {
        currentModelRef.current.traverse((child) => {
          if ((child as THREE.Bone).isBone) {
            const bone = child as THREE.Bone;
            const name = bone.name.toLowerCase();

            // 归位（在每一帧开始前轻微插值回到原始位置，防止动作突变）
            bone.rotation.x *= 0.8;
            bone.rotation.y *= 0.8;
            bone.rotation.z *= 0.8;

            const activeAct = actionRef.current;

            if (activeAct === 'idle') {
              if (name.includes('spine') || name.includes('hips') || name.includes('middle')) {
                bone.rotation.z = Math.sin(time * 1.5) * 0.03;
                bone.rotation.x = Math.cos(time * 1.2) * 0.02;
              }
              if (name.includes('arm') && !name.includes('leg')) bone.rotation.z += Math.sin(time * 2) * 0.01;
            } 
            else if (activeAct === 'wave') {
              // 招手：仅针对右臂，严格排除腿部
              if ((name.includes('right') && name.includes('arm')) && !name.includes('leg')) {
                bone.rotation.z = -1.3 + Math.sin(time * 5) * 0.4;
              }
              if (name.includes('spine')) bone.rotation.y = Math.sin(time * 2) * 0.05;
            }
            else if (activeAct === 'walk' || activeAct === 'run') {
              const speed = activeAct === 'run' ? 10 : 6;
              const amp = activeAct === 'run' ? 0.8 : 0.5;
              const swing = Math.sin(time * speed);
              // 腿部
              if (name.includes('leg')) {
                if (name.includes('left') && name.includes('upper')) bone.rotation.x = swing * amp;
                if (name.includes('right') && name.includes('upper')) bone.rotation.x = -swing * amp;
                if (name.includes('lower')) bone.rotation.x = (name.includes('left') ? (swing > 0 ? swing : 0) : (swing < 0 ? -swing : 0)) * 0.6;
              }
              // 手臂
              if (name.includes('arm')) {
                if (name.includes('left')) bone.rotation.x = -swing * (amp * 0.8);
                if (name.includes('right')) bone.rotation.x = swing * (amp * 0.8);
              }
              if (name.includes('spine')) bone.rotation.z = swing * 0.05;
            }
            else if (activeAct === 'dance') {
              const speed = 8;
              bone.rotation.y += Math.sin(time * speed) * 0.2;
              if (name.includes('spine')) {
                bone.rotation.z = Math.sin(time * speed) * 0.3;
                bone.rotation.x = Math.cos(time * speed * 0.5) * 0.2;
              }
              if (name.includes('arm') && !name.includes('leg')) bone.rotation.z = (name.includes('left') ? -1 : 1) * (1 + Math.sin(time * speed) * 0.5);
            }
            else if (activeAct === 'no') {
              if (name.includes('head') || name.includes('neck') || name.includes('top')) {
                bone.rotation.y = Math.sin(time * 8) * 0.4;
              }
            }
            else if (activeAct === 'think') {
              if (name.includes('head') || name.includes('neck') || name.includes('top')) {
                bone.rotation.x = 0.3;
                bone.rotation.z = Math.sin(time * 1) * 0.1;
              }
              if (name.includes('arm') && name.includes('left')) {
                bone.rotation.z = -0.8;
                bone.rotation.x = -0.5;
              }
            }
          }
        });
      }

      // 扫描线动画
      if (scannerRef.current) {
        if (isRefining) {
          scannerRef.current.visible = true;
          (scannerRef.current.material as THREE.MeshBasicMaterial).opacity = Math.sin(Date.now() * 0.005) * 0.3 + 0.4;
          scannerRef.current.position.y = Math.sin(Date.now() * 0.002) * 1.5 + 1.0;
        } else {
          scannerRef.current.visible = false;
        }
      }

      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Responsive resize handling
    const resizeObserver = new ResizeObserver(() => {
      if (!container || !rendererRef.current || !cameraRef.current) return;
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width === 0 || height === 0) return;

      rendererRef.current.setSize(width, height);
      cameraRef.current.aspect = width / height;
      cameraRef.current.updateProjectionMatrix();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
    };
  }, [backgroundColor, applyPreset]);

  useEffect(() => {
    const cleanup = setupScene();
    return () => {
      cleanup?.();
      cancelAnimationFrame(rafRef.current);
      rendererRef.current?.dispose();
    };
  }, [setupScene]);

  // Handle Preset Change
  useEffect(() => {
    applyPreset(preset);
  }, [preset, applyPreset]);

  useEffect(() => {
    setPreset(initialPreset);
  }, [initialPreset]);

  // Load Model (GLB)
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !url) return;

    // Clear any existing model or parts immediately when starting to load a new URL
    if (currentModelRef.current) {
      scene.remove(currentModelRef.current);
      currentModelRef.current = null;
    }

    // 核心修复：清理旧的骨骼辅助线
    if (helperRef.current) {
      scene.remove(helperRef.current);
      helperRef.current = null;
    }

    const fullUrl = url.startsWith('http') ? url : `http://localhost:8000${url}`;
    loaderRef.current.load(fullUrl, (gltf: { scene: THREE.Group }) => {
      const model = gltf.scene;
      
      // 查找骨骼并添加可视化
      let hasBones = false;
      model.traverse((child: THREE.Object3D) => {
        if ((child as THREE.SkinnedMesh).isSkinnedMesh) {
          hasBones = true;
          child.castShadow = true;
          child.receiveShadow = true;
        } else if ((child as THREE.Mesh).isMesh) {
          child.castShadow = true;
          child.receiveShadow = true;
        }
      });

      if (hasBones && sceneRef.current) {
        const helper = new THREE.SkeletonHelper(model);
        (helper.material as THREE.LineBasicMaterial).linewidth = 2;
        sceneRef.current.add(helper);
        helperRef.current = helper; // 记录引用以便下次清理
      }

      // Normalize scale and position
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());
      const scale = 0.85 / Math.max(size.x, size.y, size.z || 1); // 调整物体占据屏幕的比例
      model.scale.setScalar(scale);
      
      const box2 = new THREE.Box3().setFromObject(model);
      const center2 = box2.getCenter(new THREE.Vector3());
      model.position.sub(center2);
      model.position.y += box2.getSize(new THREE.Vector3()).y / 2;
      
      scene.add(model);
      currentModelRef.current = model;
      
      // 智能对焦：模型加载后，调整相机 target 为模型中心
      if (controlsRef.current) {
        controlsRef.current.target.set(0, box2.getSize(new THREE.Vector3()).y / 2, 0);
      }
    });
  }, [url]);
  
  // Real-time Parts Rendering
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    // 1. 清理：无论是否有新零件或 URL，先尝试寻找并移除旧零件组
    const existingParts = scene.children.find(c => c.userData.isParts);
    if (existingParts) {
      scene.remove(existingParts);
    }

    // 2. 如果已有最终 GLB URL，或者没有零件数据，则不执行零件渲染
    if (url || !parts || parts.length === 0) {
      if (currentModelRef.current?.userData.isParts) {
        currentModelRef.current = null;
      }
      return;
    }

    // 3. 构建新的零件组
    const group = new THREE.Group();
    group.userData.isParts = true;
    
    parts.forEach(p => {
      let geo;
      // 兼容 type 和 shape 字段
      const shape = p.shape || p.type || 'box';
      const sx = p.size?.x || 1;
      const sy = p.size?.y || 1;
      const sz = p.size?.z || 1;

      switch(shape) {
        case 'sphere': geo = new THREE.SphereGeometry(sx / 2, 16, 16); break;
        case 'capsule': geo = new THREE.CapsuleGeometry(sx / 2, sy, 4, 8); break;
        case 'cylinder': geo = new THREE.CylinderGeometry(sx / 2, sx / 2, sy, 16); break;
        default: geo = new THREE.BoxGeometry(sx, sy, sz);
      }

      // 颜色容错
      let color;
      if (p.color && typeof p.color === 'object') {
        color = new THREE.Color(p.color.r || 0.5, p.color.g || 0.5, p.color.b || 0.5);
      } else {
        color = new THREE.Color(0x888888);
      }

      const mat = new THREE.MeshStandardMaterial({ 
        color, 
        roughness: 0.15, 
        metalness: 0.8,
        envMapIntensity: 1.0 
      });

      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(p.position?.x || 0, p.position?.y || 0, p.position?.z || 0);
      
      if (p.rotation) {
        // 核心修复：将 AI 输出的角度（Degrees）转换为 Three.js 要求的弧度（Radians）
        const degToRad = Math.PI / 180;
        mesh.rotation.set(
          (p.rotation.x || 0) * degToRad,
          (p.rotation.y || 0) * degToRad,
          (p.rotation.z || 0) * degToRad
        );
      }
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
    });

    // Also normalize parts group scale for visual consistency
    const box = new THREE.Box3().setFromObject(group);
    const size = box.getSize(new THREE.Vector3());
    const scale = 2.0 / Math.max(size.x, size.y, size.z || 1);
    group.scale.setScalar(scale);
    
    const box2 = new THREE.Box3().setFromObject(group);
    const center2 = box2.getCenter(new THREE.Vector3());
    group.position.sub(center2);
    group.position.y += box2.getSize(new THREE.Vector3()).y / 2;
    
    scene.add(group);
    currentModelRef.current = group;
  }, [parts, url]);

  const presets: { id: LightingPreset; label: string; icon: ReactNode }[] = [
    { id: 'studio', label: '工作室', icon: <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg> },
    { id: 'city', label: '城市', icon: <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="9" y1="22" x2="9" y2="2"/><line x1="15" y1="22" x2="15" y2="2"/><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/></svg> },
    { id: 'sunset', label: '夕阳', icon: <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17 18a5 5 0 0 0-10 0"/><line x1="12" y1="2" x2="12" y2="9"/><line x1="4.22" y1="10.22" x2="5.64" y2="11.64"/><line x1="1" y1="18" x2="3" y2="18"/><line x1="21" y1="18" x2="23" y2="18"/><line x1="18.36" y1="11.64" x2="19.78" y2="10.22"/><line x1="23" y1="22" x2="1" y2="22"/></svg> },
    { id: 'hills', label: '山丘', icon: <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17 18a5 5 0 0 0-10 0"/><line x1="12" y1="9" x2="12" y2="2"/><path d="M4.22 10.22l1.42 1.42"/><path x1="1" y1="18" x2="3" y2="18"/><path x1="21" y1="18" x2="23" y2="18"/><path x1="18.36" y1="11.64" x2="19.78" y2="10.22"/></svg> },
    { id: 'cyberpunk', label: '赛博', icon: <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> },
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
