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
