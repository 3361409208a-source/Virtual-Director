import { useRef, useEffect } from 'react';
import type { SceneSequence, ActorKeyframe, CameraKeyframe } from '../types';

interface Props {
  sequence: SceneSequence;
}

type Vec3 = { x: number; y: number; z: number };
const ZERO: Vec3 = { x: 0, y: 0, z: 0 };

function getPos(kf: ActorKeyframe | CameraKeyframe): Vec3 {
  // Support both field name variants the LLM might produce
  const p = (kf as ActorKeyframe).position ?? (kf as CameraKeyframe).position;
  if (!p) return ZERO;
  return { x: p.x ?? 0, y: p.y ?? 0, z: p.z ?? 0 };
}

function getTime(kf: ActorKeyframe | CameraKeyframe): number {
  return (kf as ActorKeyframe).time ?? 0;
}

function lerpPos(track: (ActorKeyframe | CameraKeyframe)[], t: number): Vec3 {
  if (!track || track.length === 0) return ZERO;
  if (t <= getTime(track[0])) return getPos(track[0]);
  if (t >= getTime(track[track.length - 1])) return getPos(track[track.length - 1]);
  for (let i = 0; i < track.length - 1; i++) {
    const a = track[i], b = track[i + 1];
    const ta = getTime(a), tb = getTime(b);
    if (t >= ta && t <= tb) {
      const u = tb === ta ? 0 : (t - ta) / (tb - ta);
      const pa = getPos(a), pb = getPos(b);
      return {
        x: pa.x + (pb.x - pa.x) * u,
        y: pa.y + (pb.y - pa.y) * u,
        z: pa.z + (pb.z - pa.z) * u,
      };
    }
  }
  return getPos(track[track.length - 1]);
}

export function ScenePreview({ sequence }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef   = useRef<number>(0);
  const t0Ref    = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const PAD = 32;
    const duration = sequence.meta?.total_duration || 10;

    // Compute world bounds from all tracks
    let x0 = -8, x1 = 8, z0 = -8, z1 = 8;
    const expand = (pos: { x: number; z: number }) => {
      x0 = Math.min(x0, pos.x - 1.5);
      x1 = Math.max(x1, pos.x + 1.5);
      z0 = Math.min(z0, pos.z - 1.5);
      z1 = Math.max(z1, pos.z + 1.5);
    };
    for (const a of sequence.actors || []) {
      for (const kf of sequence.actor_tracks?.[a.actor_id] || []) {
        const p = getPos(kf); expand(p);
      }
    }
    for (const kf of sequence.camera_track || []) {
      const p = getPos(kf); if (p !== ZERO) expand(p);
    }

    const px  = (x: number) => PAD + ((x - x0) / (x1 - x0)) * (W - PAD * 2);
    const pz  = (z: number) => PAD + ((z - z0) / (z1 - z0)) * (H - PAD * 2 - 20);
    const col = (c: number[]) => `rgb(${Math.round(c[0]*255)},${Math.round(c[1]*255)},${Math.round(c[2]*255)})`;

    const draw = (t: number) => {
      // Background
      const bg = sequence.scene_setup?.background_color;
      ctx.fillStyle = bg ? col(bg) : '#0b0e1a';
      ctx.fillRect(0, 0, W, H);

      // Grid
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1;
      for (let gx = Math.ceil(x0 / 5) * 5; gx <= x1; gx += 5) {
        ctx.beginPath(); ctx.moveTo(px(gx), PAD); ctx.lineTo(px(gx), H - PAD - 20); ctx.stroke();
      }
      for (let gz = Math.ceil(z0 / 5) * 5; gz <= z1; gz += 5) {
        ctx.beginPath(); ctx.moveTo(PAD, pz(gz)); ctx.lineTo(W - PAD, pz(gz)); ctx.stroke();
      }

      // Ground label (top-down hint)
      ctx.fillStyle = 'rgba(255,255,255,0.15)';
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      ctx.fillText('TOP VIEW  (X→  Z↓)', PAD, 14);

      // Camera path
      const camTrack = sequence.camera_track || [];
      if (camTrack.length >= 2) {
        ctx.strokeStyle = 'rgba(255,220,50,0.25)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 5]);
        ctx.beginPath();
        camTrack.forEach((kf, i) => {
          const p = getPos(kf);
          i === 0 ? ctx.moveTo(px(p.x), pz(p.z))
                  : ctx.lineTo(px(p.x), pz(p.z));
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Actor paths
      for (const actor of sequence.actors || []) {
        const track = sequence.actor_tracks?.[actor.actor_id] || [];
        if (track.length < 2) continue;
        const c = actor.color || [0.5, 0.5, 1];
        ctx.strokeStyle = `rgba(${Math.round(c[0]*255)},${Math.round(c[1]*255)},${Math.round(c[2]*255)},0.2)`;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        track.forEach((kf, i) => {
          const p = getPos(kf);
          i === 0 ? ctx.moveTo(px(p.x), pz(p.z))
                  : ctx.lineTo(px(p.x), pz(p.z));
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Actors at time t
      for (const actor of sequence.actors || []) {
        const track = sequence.actor_tracks?.[actor.actor_id] || [];
        const pos = lerpPos(track, t);
        const cx = px(pos.x), cy = pz(pos.z);
        const c = actor.color || [0.4, 0.6, 1];
        const r = Math.round(c[0]*255), g = Math.round(c[1]*255), b = Math.round(c[2]*255);

        // Glow halo
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 16);
        grad.addColorStop(0, `rgba(${r},${g},${b},0.35)`);
        grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(cx, cy, 16, 0, Math.PI * 2); ctx.fill();

        // Dot
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.beginPath(); ctx.arc(cx, cy, 6, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.85)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Label
        ctx.fillStyle = 'rgba(255,255,255,0.9)';
        ctx.font = 'bold 11px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(actor.actor_id, cx, cy - 12);
      }

      // Camera at time t
      if (camTrack.length > 0) {
        const cpos = lerpPos(camTrack, t);
        const cx = px(cpos.x), cy = pz(cpos.z);
        ctx.fillStyle = '#ffd700';
        ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.fillStyle = 'rgba(255,215,0,0.85)';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('📷', cx, cy - 10);
      }

      // Progress bar
      const pct = t / duration;
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.fillRect(PAD, H - 18, W - PAD * 2, 5);
      ctx.fillStyle = '#3af';
      ctx.fillRect(PAD, H - 18, (W - PAD * 2) * pct, 5);

      ctx.fillStyle = 'rgba(255,255,255,0.4)';
      ctx.font = '10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`${t.toFixed(1)}s / ${duration}s`, W - PAD, H - 22);
    };

    t0Ref.current = performance.now();
    const animate = (now: number) => {
      const t = ((now - t0Ref.current) / 1000) % duration;
      draw(t);
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [sequence]);

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
      <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.05em' }}>
        ▶ SCENE MAP — Godot 渲染中...
      </div>
      <canvas
        ref={canvasRef}
        width={560}
        height={370}
        style={{ width: '100%', maxWidth: 560, borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)' }}
      />
    </div>
  );
}
