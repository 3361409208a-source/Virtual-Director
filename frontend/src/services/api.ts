import type { SSEEvent, ProjectMeta, ProjectDetail } from '../types';

const API_BASE = 'http://localhost:8000/api';

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
