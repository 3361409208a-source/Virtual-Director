import type { SSEEvent, ProjectMeta, ProjectDetail } from '../types';

const API_BASE = 'http://localhost:8000/api';

export async function streamTestRender(
  renderer: 'godot' | 'blender',
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/test-render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ renderer }),
  });
  if (!response.body) throw new Error('无响应流');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try { onEvent(JSON.parse(line.slice(6))); } catch { /* skip */ }
    }
  }
}

// ── Model Library ──────────────────────────────────────────────────────────

export interface ModelMeta {
  id: string;
  category: 'builtin' | 'downloaded' | 'custom';
  filename: string;
  name: string;
  size_kb: number;
  url: string;
}

export async function listModels(): Promise<ModelMeta[]> {
  const res = await fetch(`${API_BASE}/models`);
  if (!res.ok) throw new Error('获取模型列表失败');
  const data = await res.json();
  return data.models ?? [];
}

export async function uploadModel(file: File): Promise<ModelMeta> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/models/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error('上传失败');
  const d = await res.json();
  return { id: `custom/${d.filename}`, category: 'custom', filename: d.filename, name: d.filename.replace('.glb',''), size_kb: d.size_kb, url: d.url };
}

// ── Scene Library ───────────────────────────────────────────────────────────

export interface SceneMeta {
  filename: string;
  scene_name: string;
  scene_description: string;
  objects: SceneObject[];
  success_count: number;
  total_objects: number;
  mtime: number;
}

export async function listScenes(): Promise<SceneMeta[]> {
  const res = await fetch(`${API_BASE}/models/scenes`);
  if (!res.ok) throw new Error('获取场景列表失败');
  const data = await res.json();
  return data.scenes ?? [];
}

export interface RigResult {
  ok: boolean;
  filename: string;
  url: string;
  size_kb: number;
  body_type: string;
  bones: number;
  mesh_nodes: number;
}

export async function rigModel(filename: string, category = 'custom'): Promise<RigResult> {
  const res = await fetch(`${API_BASE}/models/rig`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, category }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '骨骼生成失败');
  }
  return res.json();
}

export async function deleteCustomModel(filename: string): Promise<void> {
  await fetch(`${API_BASE}/models/custom/${filename}`, { method: 'DELETE' });
}

export interface AIGenerateResult {
  ok: boolean;
  filename: string;
  model_name: string;
  description: string;
  parts_count: number;
  size_kb: number;
  url: string;
  parts: object[];
}

export interface SceneObject {
  id: string;
  name: string;
  filename: string;
  url: string;
  parts_count: number;
  size_kb: number;
  position: number[];
  rotation_y?: number;
  scale: number;
  category: string;
}

export interface AIModelEvent {
  step: 'start' | 'token' | 'thinking' | 'building' | 'done' | 'scene_done' | 'error';
  msg: string;
  filename?: string;
  model_name?: string;
  description?: string;
  parts_count?: number;
  size_kb?: number;
  url?: string;
  tokens?: { input: number; output: number; };
  // scene_done specific
  scene_name?: string;
  scene_description?: string;
  objects?: SceneObject[];
  success_count?: number;
  total_objects?: number;
}

export async function streamAiGenerateModel(
  prompt: string,
  onEvent: (e: AIModelEvent) => void,
  model = 'deepseek-chat',
  baseModel = '',
  style = 'realistic',
): Promise<void> {
  const res = await fetch(`${API_BASE}/models/ai-generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model, base_model: baseModel, style }),
  });
  if (!res.body) throw new Error('无响应流');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try { onEvent(JSON.parse(line.slice(6)) as AIModelEvent); } catch { /* skip */ }
    }
  }
}

export function modelFileUrl(category: string, filename: string): string {
  return `${API_BASE}/models/${category}/${filename}`;
}

// ── Projects ───────────────────────────────────────────────────────────────

export async function listProjects(): Promise<ProjectMeta[]> {
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) throw new Error('获取项目列表失败');
  const data = await res.json();
  return data.projects ?? [];
}

export async function getProject(pid: string): Promise<ProjectDetail> {
  const res = await fetch(`${API_BASE}/projects/${pid}`);
  if (!res.ok) throw new Error('获取项目详情失败');
  return res.json();
}

export function projectVideoUrl(pid: string): string {
  return `${API_BASE}/projects/${pid}/video`;
}

export async function optimizePrompt(prompt: string, context: 'director' | 'modeling' = 'director'): Promise<string> {
  const res = await fetch(`${API_BASE}/optimize-prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, context }),
  });
  if (!res.ok) return prompt;
  const d = await res.json();
  return d.optimized || prompt;
}

// ── Config ─────────────────────────────────────────────────────────────────

export interface Config {
  enable_model_search: boolean;
}

export async function getConfig(): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error('获取配置失败');
  return res.json();
}

export async function updateConfig(config: Partial<Config>): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error('更新配置失败');
  return res.json();
}

/**
 * Stream the /api/generate SSE endpoint.
 * Calls onEvent for each parsed SSE frame until the stream closes.
 */
export async function streamGenerate(
  prompt: string,
  onEvent: (event: SSEEvent) => void,
  model: string = 'deepseek-chat',
  renderer: 'godot' | 'blender' = 'godot',
  workerModel: string = 'auto',
  baseModel: string = '',
): Promise<void> {
  const response = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model, renderer, worker_model: workerModel, base_model: baseModel }),
  });

  if (!response.body) throw new Error('无响应流');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const event: SSEEvent = JSON.parse(line.slice(6));
        onEvent(event);
      } catch {
        // malformed frame — skip
      }
    }
  }
}

// ── Review (半自动审核) ──────────────────────────────────────────────────────

/** 用户确认方案（同时提交最终 sequence） */
export async function confirmReview(sid: string, sequence: object): Promise<void> {
  const res = await fetch(`${API_BASE}/review/${sid}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sequence }),
  });
  if (!res.ok) throw new Error('确认失败');
}

/** 用户取消方案 */
export async function rejectReview(sid: string): Promise<void> {
  await fetch(`${API_BASE}/review/${sid}/reject`, { method: 'POST' });
}

/** 从模型库分配模型给演员 */
export async function assignModel(category: string, filename: string, actorId: string): Promise<{ path: string; url: string; filename: string }> {
  const res = await fetch(`${API_BASE}/models/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, filename, actor_id: actorId }),
  });
  if (!res.ok) throw new Error('模型分配失败');
  return res.json();
}
