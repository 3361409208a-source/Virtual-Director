import { useState, useEffect } from 'react';
import type { ProjectMeta, ProjectDetail, SceneSequence } from '../types';
import { listProjects, getProject, projectVideoUrl } from '../services/api';
import { ScenePreview } from './ScenePreview';

interface Props {
  activeProjectId: string | null;
  onSelectProject: (pid: string | null, sequence: SceneSequence | null) => void;
}

export function ProjectPanel({ activeProjectId, onSelectProject }: Props) {
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [detail, setDetail]     = useState<ProjectDetail | null>(null);
  const [loading, setLoading]   = useState(false);
  const [open, setOpen]         = useState(false);

  const loadList = async () => {
    try {
      const list = await listProjects();
      setProjects(list);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    // Initial load on mount
    loadList();
  }, []);

  useEffect(() => {
    // Only poll the server if the panel is open OR if a project is actively generating
    const hasGenerating = projects.some(p => p.status === 'generating');
    let id: number | undefined;
    
    if (open || hasGenerating) {
      id = window.setInterval(loadList, 5000);
    }
    return () => {
      if (id) window.clearInterval(id);
    };
  }, [open, projects]);


  const openProject = async (pid: string) => {
    setLoading(true);
    try {
      const d = await getProject(pid);
      setDetail(d);
      onSelectProject(pid, d.sequence ?? null);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const closeDetail = () => {
    setDetail(null);
    onSelectProject(null, null);
  };

  const formatDate = (s: string) => {
    const d = new Date(s);
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className={`project-panel ${open ? 'open' : ''}`}>
      <button className="project-toggle" onClick={() => setOpen(!open)} title="工程库">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span className="project-count">{projects.length}</span>
      </button>

      {open && (
        <div className="project-drawer">
          <div className="project-drawer-header">
            <h3>工程库</h3>
            <button className="project-refresh" onClick={loadList} title="刷新">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </button>
          </div>

          {loading && <div className="project-empty">加载中...</div>}
          {detail ? (
            <div className="project-detail">
              <button className="project-back" onClick={closeDetail}>
                ← 返回列表
              </button>
              <div className="project-meta">
                <div className="project-prompt">{detail.prompt}</div>
                <div className="project-info">
                  <span>{formatDate(detail.created_at)}</span>
                  <span className={`status-badge ${detail.status}`}>{detail.status === 'done' ? '已完成' : detail.status}</span>
                </div>
              </div>
              {detail.has_video && (
                <div className="project-video">
                  <video src={projectVideoUrl(detail.id)} controls width="100%" />
                </div>
              )}
              {detail.sequence && (
                <div className="project-preview-wrap">
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>分镜预览</div>
                  <div className="project-preview-canvas">
                    <ScenePreview sequence={detail.sequence} />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="project-list">
              {projects.length === 0 && <div className="project-empty">暂无工程</div>}
              {projects.map(p => (
                <div
                  key={p.id}
                  className={`project-card ${activeProjectId === p.id ? 'active' : ''}`}
                  onClick={() => openProject(p.id)}
                >
                  <div className="project-card-title">{p.prompt.slice(0, 40)}{p.prompt.length > 40 ? '…' : ''}</div>
                  <div className="project-card-meta">
                    <span>{formatDate(p.created_at)}</span>
                    {p.has_video && <span className="video-tag">🎬</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
