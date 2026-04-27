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

export interface AIModelEvent {
  step: 'start' | 'token' | 'thinking' | 'building' | 'done' | 'error';
  msg: string;
  filename?: string;
  model_name?: string;
  description?: string;
  parts_count?: number;
  size_kb?: number;
  url?: string;
}

export async function streamAiGenerateModel(
  prompt: string,
  onEvent: (e: AIModelEvent) => void,
  model = 'deepseek-chat',
  baseModel = '',
): Promise<void> {
  const res = await fetch(`${API_BASE}/models/ai-generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model, base_model: baseModel }),
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

// ── Scene Draft ─────────────────────────────────────────────────────────────

export interface SceneDraft {
  draft_id: string;
  prompt: string;
  status: 'draft' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
  scene: {
    sky?: { top_color?: string; horizon_color?: string; bottom_color?: string };
    sun?: { euler_degrees?: { x: number; y: number; z: number }; color?: string; energy: number };
    ambient_energy?: number;
    fog?: { enabled: boolean; density: number; color: string };
    ground?: { color: string; size: number };
  };
  actors: Array<{
    actor_id: string;
    type: string;
    model_source: string;
    model_filename: string;
    composite_data: object | null;
    position: { x: number; y: number; z: number };
    rotation: { x: number; y: number; z: number };
    scale: { x: number; y: number; z: number };
    actions: Array<{ frame: number; position: { x: number; y: number; z: number }; rotation: { x: number; y: number; z: number } }>;
  }>;
  cameras: Array<{
    id: string;
    position: { x: number; y: number; z: number };
    rotation: { x: number; y: number; z: number };
    fov: number;
  }>;
  user_notes: string;
}

export interface SceneDraftRequest {
  prompt: string;
  scene: object;
  actors: object[];
  cameras: object[];
}

export async function createSceneDraft(req: SceneDraftRequest): Promise<SceneDraft> {
  const res = await fetch(`${API_BASE}/scene/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error('创建场景草稿失败');
  return res.json();
}

export async function getSceneDraft(draftId: string): Promise<SceneDraft> {
  const res = await fetch(`${API_BASE}/scene/draft/${draftId}`);
  if (!res.ok) throw new Error('获取场景草稿失败');
  return res.json();
}

export async function listSceneDrafts(): Promise<SceneDraft[]> {
  const res = await fetch(`${API_BASE}/scene/drafts`);
  if (!res.ok) throw new Error('获取场景草稿列表失败');
  const data = await res.json();
  return data.drafts ?? [];
}

export async function updateSceneDraft(draftId: string, updates: Partial<SceneDraft>): Promise<SceneDraft> {
  const res = await fetch(`${API_BASE}/scene/draft/${draftId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error('更新场景草稿失败');
  return res.json();
}

export async function deleteSceneDraft(draftId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/scene/draft/${draftId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('删除场景草稿失败');
}

export async function confirmSceneDraft(draftId: string): Promise<SceneDraft> {
  const res = await fetch(`${API_BASE}/scene/draft/${draftId}/confirm`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('确认场景草稿失败');
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
): Promise<void> {
  const response = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model, renderer }),
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
