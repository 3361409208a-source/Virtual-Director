import { useState, useEffect, useRef } from 'react';
import type { ModelMeta } from '../services/api';
import { listModels, uploadModel, deleteCustomModel } from '../services/api';

const CAT_LABEL: Record<string, string> = {
  builtin:    '内置',
  downloaded: '已下载',
  custom:     '自定义',
};
const CAT_COLOR: Record<string, string> = {
  builtin:    '#388bfd',
  downloaded: '#3fb950',
  custom:     '#f0883e',
};

export function ModelLibraryPanel() {
  const [open, setOpen]           = useState(false);
  const [models, setModels]       = useState<ModelMeta[]>([]);
  const [filter, setFilter]       = useState<'all' | 'builtin' | 'downloaded' | 'custom'>('all');
  const [preview, setPreview]     = useState<ModelMeta | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      setModels(await listModels());
      setError('');
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (open) load(); }, [open]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const m = await uploadModel(file);
      setModels(prev => [...prev, m]);
    } catch (err) {
      setError(`上传失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleDelete = async (m: ModelMeta) => {
    if (!confirm(`删除 ${m.filename}？`)) return;
    await deleteCustomModel(m.filename);
    setModels(prev => prev.filter(x => x.id !== m.id));
    if (preview?.id === m.id) setPreview(null);
  };

  const visible = filter === 'all' ? models : models.filter(m => m.category === filter);

  const counts = {
    all:        models.length,
    builtin:    models.filter(m => m.category === 'builtin').length,
    downloaded: models.filter(m => m.category === 'downloaded').length,
    custom:     models.filter(m => m.category === 'custom').length,
  };

  return (
    <>
      {/* Trigger button */}
      <button className="model-lib-btn" onClick={() => setOpen(true)} title="模型库">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
        <span className="model-lib-count">{models.length || ''}</span>
      </button>

      {/* Drawer overlay */}
      {open && (
        <div className="model-lib-overlay" onClick={() => { setOpen(false); setPreview(null); }}>
          <div className="model-lib-drawer" onClick={e => e.stopPropagation()}>

            {/* Header */}
            <div className="model-lib-header">
              <span className="model-lib-title">🧊 模型库</span>
              <div className="model-lib-header-actions">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".glb"
                  style={{ display: 'none' }}
                  onChange={handleUpload}
                />
                <button
                  className="model-upload-btn"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  title="上传 GLB 模型"
                >
                  {uploading ? '上传中...' : '+ 上传模型'}
                </button>
                <button className="model-lib-close" onClick={() => { setOpen(false); setPreview(null); }}>✕</button>
              </div>
            </div>

            {/* Filter tabs */}
            <div className="model-lib-tabs">
              {(['all', 'builtin', 'downloaded', 'custom'] as const).map(cat => (
                <button
                  key={cat}
                  className={`model-tab ${filter === cat ? 'active' : ''}`}
                  onClick={() => setFilter(cat)}
                >
                  {cat === 'all' ? '全部' : CAT_LABEL[cat]}
                  <span className="model-tab-count">{counts[cat]}</span>
                </button>
              ))}
            </div>

            {error && <div className="model-lib-error">{error}</div>}
            {loading && <div className="model-lib-loading">加载中...</div>}

            {/* Body: grid + preview */}
            <div className="model-lib-body">
              {/* Grid */}
              <div className="model-grid">
                {visible.length === 0 && !loading && (
                  <div className="model-empty">暂无模型</div>
                )}
                {visible.map(m => (
                  <div
                    key={m.id}
                    className={`model-card ${preview?.id === m.id ? 'selected' : ''}`}
                    onClick={() => setPreview(m)}
                  >
                    <div className="model-card-viewer">
                      {/* @ts-ignore */}
                      <model-viewer
                        src={`http://localhost:8000${m.url}`}
                        auto-rotate
                        camera-controls
                        shadow-intensity="1"
                        style={{ width: '100%', height: '100%', background: 'transparent' }}
                      />
                    </div>
                    <div className="model-card-info">
                      <span className="model-card-name" title={m.filename}>{m.name}</span>
                      <div className="model-card-meta">
                        <span className="model-cat-badge" style={{ background: CAT_COLOR[m.category] + '22', color: CAT_COLOR[m.category] }}>
                          {CAT_LABEL[m.category]}
                        </span>
                        <span className="model-size">{m.size_kb} KB</span>
                      </div>
                    </div>
                    {m.category === 'custom' && (
                      <button
                        className="model-delete-btn"
                        onClick={e => { e.stopPropagation(); handleDelete(m); }}
                        title="删除"
                      >✕</button>
                    )}
                  </div>
                ))}
              </div>

              {/* Large preview panel */}
              {preview && (
                <div className="model-preview-panel">
                  <div className="model-preview-viewer">
                    {/* @ts-ignore */}
                    <model-viewer
                      src={`http://localhost:8000${preview.url}`}
                      auto-rotate
                      camera-controls
                      shadow-intensity="1"
                      exposure="1"
                      style={{ width: '100%', height: '100%' }}
                    />
                  </div>
                  <div className="model-preview-info">
                    <div className="model-preview-name">{preview.name}</div>
                    <div className="model-preview-details">
                      <span className="model-cat-badge" style={{ background: CAT_COLOR[preview.category] + '22', color: CAT_COLOR[preview.category] }}>
                        {CAT_LABEL[preview.category]}
                      </span>
                      <span className="model-size">{preview.size_kb} KB</span>
                    </div>
                    <div className="model-preview-filename">{preview.filename}</div>
                    <div className="model-preview-hint">💡 拖动旋转 · 滚轮缩放</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
