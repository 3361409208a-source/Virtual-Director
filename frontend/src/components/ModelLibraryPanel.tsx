import { useState, useEffect, useRef } from 'react';
import type { ModelMeta, AIGenerateResult, AIModelEvent } from '../services/api';
import { listModels, uploadModel, deleteCustomModel, streamAiGenerateModel } from '../services/api';

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

type Tab = 'library' | 'ai';

export function ModelLibraryPanel() {
  const [open, setOpen]           = useState(false);
  const [tab, setTab]             = useState<Tab>('library');
  const [models, setModels]       = useState<ModelMeta[]>([]);
  const [filter, setFilter]       = useState<'all' | 'builtin' | 'downloaded' | 'custom'>('all');
  const [preview, setPreview]     = useState<ModelMeta | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  // AI modeling state
  const [aiPrompt, setAiPrompt]         = useState('');
  const [aiBaseModel, setAiBaseModel]   = useState<ModelMeta | null>(null);
  const [aiLlm, setAiLlm]              = useState('deepseek-chat');
  const [aiModelPage, setAiModelPage]   = useState(0);
  const AI_PAGE_SIZE = 5;
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiResult, setAiResult]         = useState<AIGenerateResult | null>(null);
  const [aiError, setAiError]           = useState('');
  const [aiLog, setAiLog]               = useState<string[]>([]);
  const logEndRef                       = useRef<HTMLDivElement>(null);

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

  const handleAiGenerate = async () => {
    if (!aiPrompt.trim() || aiGenerating) return;
    setAiGenerating(true);
    setAiResult(null);
    setAiError('');
    setAiLog([]);
    try {
      let tokenBuf = '';
      await streamAiGenerateModel(
        aiPrompt.trim(),
        (ev: AIModelEvent) => {
          if (ev.step === 'token') {
            tokenBuf += ev.msg;
            setAiLog(prev => {
              const updated = [...prev];
              if (updated.length === 0 || updated[updated.length - 1].startsWith('📝')) {
                updated[updated.length - 1] = '📝 ' + tokenBuf;
              } else {
                updated.push('📝 ' + tokenBuf);
              }
              return updated;
            });
            setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 30);
          } else if (ev.step === 'done') {
            setAiResult(ev as unknown as AIGenerateResult);
            setAiLog(prev => [...prev, ev.msg]);
            load();
          } else if (ev.step === 'error') {
            setAiError(ev.msg);
            setAiLog(prev => [...prev, '❌ ' + ev.msg]);
          } else {
            tokenBuf = '';
            setAiLog(prev => [...prev, ev.msg]);
          }
        },
        aiLlm,
        aiBaseModel?.name ?? '',
      );
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiGenerating(false);
    }
  };

  const handleAiDelete = async () => {
    if (!aiResult) return;
    if (!confirm(`删除生成的模型 ${aiResult.filename}？`)) return;
    await deleteCustomModel(aiResult.filename);
    setAiResult(null);
    setAiPrompt('');
    await load();
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
              <div className="model-lib-top-tabs">
                <button className={`model-top-tab ${tab === 'library' ? 'active' : ''}`} onClick={() => setTab('library')}>🧊 模型库</button>
                <button className={`model-top-tab ${tab === 'ai' ? 'active' : ''}`} onClick={() => setTab('ai')}>✨ AI 建模</button>
              </div>
              <div className="model-lib-header-actions">
                {tab === 'library' && (
                  <>
                    <input ref={fileRef} type="file" accept=".glb" style={{ display: 'none' }} onChange={handleUpload} />
                    <button className="model-upload-btn" onClick={() => fileRef.current?.click()} disabled={uploading}>
                      {uploading ? '上传中...' : '+ 上传'}
                    </button>
                  </>
                )}
                <button className="model-lib-close" onClick={() => { setOpen(false); setPreview(null); }}>✕</button>
              </div>
            </div>

            {/* ── Library tab ── */}
            {tab === 'library' && (<>
              <div className="model-lib-tabs">
                {(['all', 'builtin', 'downloaded', 'custom'] as const).map(cat => (
                  <button key={cat} className={`model-tab ${filter === cat ? 'active' : ''}`} onClick={() => setFilter(cat)}>
                    {cat === 'all' ? '全部' : CAT_LABEL[cat]}
                    <span className="model-tab-count">{counts[cat]}</span>
                  </button>
                ))}
              </div>
              {error && <div className="model-lib-error">{error}</div>}
              {loading && <div className="model-lib-loading">加载中...</div>}
              <div className="model-lib-body">
                <div className="model-grid">
                  {visible.length === 0 && !loading && <div className="model-empty">暂无模型</div>}
                  {visible.map(m => (
                    <div key={m.id} className={`model-card ${preview?.id === m.id ? 'selected' : ''}`} onClick={() => setPreview(m)}>
                      <div className="model-card-viewer">
                        {/* @ts-ignore */}
                        <model-viewer src={`http://localhost:8000${m.url}`} auto-rotate camera-controls shadow-intensity="1"
                          style={{ width: '100%', height: '100%', background: 'transparent' }} />
                      </div>
                      <div className="model-card-info">
                        <span className="model-card-name" title={m.filename}>{m.name}</span>
                        <div className="model-card-meta">
                          <span className="model-cat-badge" style={{ background: CAT_COLOR[m.category] + '22', color: CAT_COLOR[m.category] }}>{CAT_LABEL[m.category]}</span>
                          <span className="model-size">{m.size_kb} KB</span>
                        </div>
                      </div>
                      {m.category === 'custom' && (
                        <button className="model-delete-btn" onClick={e => { e.stopPropagation(); handleDelete(m); }} title="删除">✕</button>
                      )}
                    </div>
                  ))}
                </div>
                {preview && (
                  <div className="model-preview-panel">
                    <div className="model-preview-viewer">
                      {/* @ts-ignore */}
                      <model-viewer src={`http://localhost:8000${preview.url}`} auto-rotate camera-controls shadow-intensity="1" exposure="1"
                        style={{ width: '100%', height: '100%' }} />
                    </div>
                    <div className="model-preview-info">
                      <div className="model-preview-name">{preview.name}</div>
                      <div className="model-preview-details">
                        <span className="model-cat-badge" style={{ background: CAT_COLOR[preview.category] + '22', color: CAT_COLOR[preview.category] }}>{CAT_LABEL[preview.category]}</span>
                        <span className="model-size">{preview.size_kb} KB</span>
                      </div>
                      <div className="model-preview-filename">{preview.filename}</div>
                      <div className="model-preview-hint">💡 拖动旋转 · 滚轮缩放</div>
                    </div>
                  </div>
                )}
              </div>
            </>)}

            {/* ── AI 建模 tab ── */}
            {tab === 'ai' && (
              <div className="ai-model-tab">

                {/* Left: selector + prompt */}
                <div className="ai-model-input-area">

                  {/* Reference model selector */}
                  <div className="ai-section-label">① 选择参考模型（可选）</div>
                  <div className="ai-model-selector">
                    <button
                      className={`ai-base-none ${!aiBaseModel ? 'selected' : ''}`}
                      onClick={() => setAiBaseModel(null)}
                    >不选择</button>
                    {models
                      .slice(aiModelPage * AI_PAGE_SIZE, (aiModelPage + 1) * AI_PAGE_SIZE)
                      .map(m => (
                        <button
                          key={m.id}
                          className={`ai-base-chip ${aiBaseModel?.id === m.id ? 'selected' : ''}`}
                          onClick={() => setAiBaseModel(aiBaseModel?.id === m.id ? null : m)}
                          title={m.filename}
                        >{m.name}</button>
                      ))}
                  </div>
                  {/* Pagination */}
                  {models.length > AI_PAGE_SIZE && (
                    <div className="ai-model-pager">
                      <button
                        className="ai-pager-btn"
                        onClick={() => setAiModelPage(p => Math.max(0, p - 1))}
                        disabled={aiModelPage === 0}
                      >‹</button>
                      <span className="ai-pager-info">
                        {aiModelPage * AI_PAGE_SIZE + 1}–{Math.min((aiModelPage + 1) * AI_PAGE_SIZE, models.length)}
                        &nbsp;/&nbsp;{models.length}
                      </span>
                      <button
                        className="ai-pager-btn"
                        onClick={() => setAiModelPage(p => p + 1)}
                        disabled={(aiModelPage + 1) * AI_PAGE_SIZE >= models.length}
                      >›</button>
                    </div>
                  )}
                  {aiBaseModel && (
                    <div className="ai-base-selected">
                      参考：<span>{aiBaseModel.name}</span>
                      <span className="model-cat-badge" style={{ background: CAT_COLOR[aiBaseModel.category] + '22', color: CAT_COLOR[aiBaseModel.category], marginLeft: 4 }}>
                        {CAT_LABEL[aiBaseModel.category]}
                      </span>
                    </div>
                  )}

                  {/* LLM selector */}
                  <div className="ai-section-label">② 选择推理模型</div>
                  <div className="ai-llm-selector">
                    {[
                      { id: 'deepseek-chat',      label: 'DeepSeek V3',    desc: '快速 · 推荐' },
                      { id: 'deepseek-reasoner',  label: 'DeepSeek R1',    desc: '深度推理' },
                      { id: 'GLM-4.7-Flash',      label: 'GLM-4.7 Flash',  desc: '极速' },
                      { id: 'deepseek-v4-pro',    label: 'DeepSeek V4 Pro',desc: '最强' },
                    ].map(m => (
                      <button
                        key={m.id}
                        className={`ai-llm-btn ${aiLlm === m.id ? 'active' : ''}`}
                        onClick={() => setAiLlm(m.id)}
                      >
                        <span className="ai-llm-name">{m.label}</span>
                        <span className="ai-llm-desc">{m.desc}</span>
                      </button>
                    ))}
                  </div>

                  {/* Prompt */}
                  <div className="ai-section-label">③ 描述你想要的模型</div>
                  <div className="ai-model-examples">
                    {['一辆红色警车', '穿金甲的武士', '喷火的龙', '宇宙飞船', '篮球运动员'].map(ex => (
                      <button key={ex} className="ai-example-chip" onClick={() => setAiPrompt(ex)}>{ex}</button>
                    ))}
                  </div>
                  <textarea
                    className="ai-model-textarea"
                    placeholder="描述模型外观、颜色、风格…（Ctrl+Enter 生成）"
                    value={aiPrompt}
                    onChange={e => setAiPrompt(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleAiGenerate(); }}
                    rows={3}
                  />
                  <button className="ai-generate-btn" onClick={handleAiGenerate} disabled={aiGenerating || !aiPrompt.trim()}>
                    {aiGenerating ? <><span className="ai-spinner" /> AI 建模中…</> : '✨ 生成模型'}
                  </button>
                  {aiError && <div className="ai-model-error">❌ {aiError}</div>}
                </div>

                {/* Right: reasoning log + preview */}
                <div className="ai-model-right">
                  {/* Reasoning log */}
                  {(aiLog.length > 0 || aiGenerating) && (
                    <div className="ai-log-panel">
                      <div className="ai-log-title">
                        {aiGenerating && <span className="ai-spinner" style={{ width: 10, height: 10, borderWidth: 1.5, marginRight: 6 }} />}
                        推理过程
                      </div>
                      <div className="ai-log-body">
                        {aiLog.map((line, i) => (
                          <div key={i} className={`ai-log-line ${line.startsWith('📝') ? 'thinking' : ''}`}>
                            {line}
                          </div>
                        ))}
                        <div ref={logEndRef} />
                      </div>
                    </div>
                  )}

                  {/* Result preview */}
                  {aiResult && (
                    <div className="ai-result">
                      <div className="ai-result-viewer">
                        {/* @ts-ignore */}
                        <model-viewer
                          src={`http://localhost:8000${aiResult.url}?t=${Date.now()}`}
                          auto-rotate camera-controls shadow-intensity="1" exposure="1"
                          style={{ width: '100%', height: '100%' }}
                        />
                      </div>
                      <div className="ai-result-info">
                        <div className="ai-result-name">{aiResult.model_name}</div>
                        <div className="ai-result-desc">{aiResult.description}</div>
                        <div className="ai-result-meta">
                          <span>{aiResult.parts_count} 个零件</span>
                          <span>{aiResult.size_kb} KB</span>
                          <span className="model-cat-badge" style={{ background: '#f0883e22', color: '#f0883e' }}>自定义</span>
                        </div>
                        <div className="ai-result-hint">💡 拖动旋转 · 滚轮缩放</div>
                        <div className="ai-result-actions">
                          <button className="ai-save-btn" onClick={() => { setAiResult(null); setAiPrompt(''); setTab('library'); setFilter('custom'); }}>
                            ✅ 保留，切到库
                          </button>
                          <button className="ai-delete-btn" onClick={handleAiDelete}>🗑 删除</button>
                        </div>
                        <button className="ai-regenerate-btn" onClick={handleAiGenerate} disabled={aiGenerating}>🔄 重新生成</button>
                      </div>
                    </div>
                  )}

                  {!aiResult && aiLog.length === 0 && (
                    <div className="ai-placeholder">
                      <div className="ai-placeholder-icon">✨</div>
                      <div>选择参考模型，输入描述，点击生成</div>
                      <div style={{ fontSize: 11, color: '#6e7681', marginTop: 4 }}>推理过程将实时显示在此区域</div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
