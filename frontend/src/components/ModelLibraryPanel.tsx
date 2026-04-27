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
  const [libPage, setLibPage]     = useState(0);
  const LIB_PAGE_SIZE = 5;

  // AI modeling state
  const [aiPrompt, setAiPrompt]         = useState('');
  const [aiBaseModel, setAiBaseModel]   = useState<ModelMeta | null>(null);
  const [aiLlm, setAiLlm]              = useState('astron-code-latest');
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiResult, setAiResult]         = useState<AIGenerateResult | null>(null);
  const [aiError, setAiError]           = useState('');
  const [aiLog, setAiLog]               = useState<string[]>([]);
  const logEndRef                       = useRef<HTMLDivElement>(null);

  // Base model modal
  const [showBaseModal, setShowBaseModal] = useState(false);
  const [modalPage, setModalPage]         = useState(0);
  const [modalFilter, setModalFilter]     = useState<'all' | 'builtin' | 'downloaded' | 'custom'>('all');
  const [tempBaseModel, setTempBaseModel] = useState<ModelMeta | null>(null);
  const MODAL_PAGE_SIZE = 6;

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
          if (ev.step === 'thinking') {
            // Real-time thinking content from reasoning models (R1, etc.)
            setAiLog(prev => {
              const updated = [...prev];
              const lastIdx = updated.length - 1;
              if (lastIdx >= 0 && updated[lastIdx].startsWith('💭')) {
                updated[lastIdx] = '💭 ' + ev.msg;
              } else {
                updated.push('💭 ' + ev.msg);
              }
              return updated;
            });
            setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 30);
          } else if (ev.step === 'token') {
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
  const pagedVisible = visible.slice(libPage * LIB_PAGE_SIZE, (libPage + 1) * LIB_PAGE_SIZE);

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
                  <button key={cat} className={`model-tab ${filter === cat ? 'active' : ''}`}
                    onClick={() => { setFilter(cat); setLibPage(0); }}>
                    {cat === 'all' ? '全部' : CAT_LABEL[cat]}
                    <span className="model-tab-count">{counts[cat]}</span>
                  </button>
                ))}
              </div>
              {error && <div className="model-lib-error">{error}</div>}
              {loading && <div className="model-lib-loading">加载中...</div>}
              <div className="model-lib-body">
                <div className="model-lib-grid-col">
                  <div className="model-grid">
                    {visible.length === 0 && !loading && <div className="model-empty">暂无模型</div>}
                    {pagedVisible.map(m => (
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
                  {/* Library pagination — pinned at bottom of grid column */}
                  {visible.length > LIB_PAGE_SIZE && (
                    <div className="lib-pager">
                      <button className="ai-pager-btn" onClick={() => setLibPage(p => Math.max(0, p - 1))} disabled={libPage === 0}>‹</button>
                      <span className="ai-pager-info">
                        {libPage * LIB_PAGE_SIZE + 1}–{Math.min((libPage + 1) * LIB_PAGE_SIZE, visible.length)}
                        &nbsp;/&nbsp;{visible.length}
                      </span>
                      <button className="ai-pager-btn" onClick={() => setLibPage(p => p + 1)} disabled={(libPage + 1) * LIB_PAGE_SIZE >= visible.length}>›</button>
                    </div>
                  )}
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

                  {/* Reference model — modal trigger */}
                  <div className="ai-section-label">① 选择参考模型（可选）</div>
                  <div className="ai-base-trigger" onClick={() => { setTempBaseModel(aiBaseModel); setModalFilter('all'); setModalPage(0); setShowBaseModal(true); }}>
                    {aiBaseModel ? (
                      <>
                        <span className="ai-base-trigger-name">{aiBaseModel.name}</span>
                        <span className="model-cat-badge" style={{ background: CAT_COLOR[aiBaseModel.category] + '22', color: CAT_COLOR[aiBaseModel.category] }}>
                          {CAT_LABEL[aiBaseModel.category]}
                        </span>
                      </>
                    ) : (
                      <span className="ai-base-trigger-placeholder">+ 点击选择参考模型</span>
                    )}
                  </div>

                  {/* LLM selector */}
                  <div className="ai-section-label">② 选择推理模型</div>
                  <div className="ai-llm-selector">
                    {[
                      { id: 'astron-code-latest', label: 'Astron Code',    desc: '阿里云 · 代码专家' },
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

                {/* Right: preview (top) + reasoning log (bottom) */}
                <div className="ai-model-right">
                  {/* Result preview — main area, stays visible after save */}
                  {aiResult ? (
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
                          <button className="ai-save-btn" onClick={() => { load(); }}>
                            ✅ 保存到模型库
                          </button>
                          <button className="ai-delete-btn" onClick={handleAiDelete}>🗑 删除</button>
                        </div>
                        <button className="ai-regenerate-btn" onClick={handleAiGenerate} disabled={aiGenerating}>🔄 重新生成</button>
                      </div>
                    </div>
                  ) : (
                    <div className="ai-placeholder">
                      <div className="ai-placeholder-icon">✨</div>
                      <div>选择参考模型，输入描述，点击生成</div>
                      <div style={{ fontSize: 11, color: '#6e7681', marginTop: 4 }}>推理过程将实时显示在底部</div>
                    </div>
                  )}

                  {/* Reasoning log — always at bottom */}
                  {(aiLog.length > 0 || aiGenerating) && (
                    <div className="ai-log-panel">
                      <div className="ai-log-title">
                        {aiGenerating && <span className="ai-spinner" style={{ width: 10, height: 10, borderWidth: 1.5, marginRight: 6 }} />}
                        推理过程
                      </div>
                      <div className="ai-log-body">
                        {aiLog.map((line, i) => (
                          <div key={i} className={`ai-log-line ${(line.startsWith('📝') || line.startsWith('💭')) ? 'thinking' : ''}`}>
                            {line}
                          </div>
                        ))}
                        <div ref={logEndRef} />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Base Model Selection Modal ── */}
            {showBaseModal && (() => {
              const modalVisible = modalFilter === 'all' ? models : models.filter(m => m.category === modalFilter);
              const modalPaged = modalVisible.slice(modalPage * MODAL_PAGE_SIZE, (modalPage + 1) * MODAL_PAGE_SIZE);
              return (
                <div className="base-model-modal-overlay" onClick={() => setShowBaseModal(false)}>
                  <div className="base-model-modal" onClick={e => e.stopPropagation()}>
                    <div className="base-model-modal-header">
                      <h3>选择参考模型</h3>
                      <button className="model-lib-close" onClick={() => setShowBaseModal(false)}>✕</button>
                    </div>
                    <div className="base-model-modal-body">
                      <div className="base-model-modal-left">
                        <div className="model-lib-tabs">
                          {(['all', 'builtin', 'downloaded', 'custom'] as const).map(cat => (
                            <button key={cat} className={`model-tab ${modalFilter === cat ? 'active' : ''}`}
                              onClick={() => { setModalFilter(cat); setModalPage(0); }}>
                              {cat === 'all' ? '全部' : CAT_LABEL[cat]}
                            </button>
                          ))}
                        </div>
                        <div className="model-grid" style={{ padding: 10, gap: 8 }}>
                          {modalPaged.map(m => (
                            <div key={m.id} className={`model-card ${tempBaseModel?.id === m.id ? 'selected' : ''}`}
                              onClick={() => setTempBaseModel(tempBaseModel?.id === m.id ? null : m)}>
                              <div className="model-card-viewer" style={{ height: 90 }}>
                                {/* @ts-ignore */}
                                <model-viewer src={`http://localhost:8000${m.url}`} auto-rotate camera-controls shadow-intensity="1"
                                  style={{ width: '100%', height: '100%', background: 'transparent' }} />
                              </div>
                              <div className="model-card-info" style={{ padding: '6px 8px' }}>
                                <span className="model-card-name" title={m.filename}>{m.name}</span>
                                <span className="model-cat-badge" style={{ background: CAT_COLOR[m.category] + '22', color: CAT_COLOR[m.category], fontSize: 9, padding: '1px 4px' }}>
                                  {CAT_LABEL[m.category]}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                        {modalVisible.length > MODAL_PAGE_SIZE && (
                          <div className="lib-pager">
                            <button className="ai-pager-btn" onClick={() => setModalPage(p => Math.max(0, p - 1))} disabled={modalPage === 0}>‹</button>
                            <span className="ai-pager-info">
                              {modalPage * MODAL_PAGE_SIZE + 1}–{Math.min((modalPage + 1) * MODAL_PAGE_SIZE, modalVisible.length)}
                              &nbsp;/&nbsp;{modalVisible.length}
                            </span>
                            <button className="ai-pager-btn" onClick={() => setModalPage(p => p + 1)} disabled={(modalPage + 1) * MODAL_PAGE_SIZE >= modalVisible.length}>›</button>
                          </div>
                        )}
                      </div>
                      {tempBaseModel && (
                        <div className="base-model-modal-preview">
                          <div className="model-preview-viewer" style={{ flex: 1, minHeight: 0 }}>
                            {/* @ts-ignore */}
                            <model-viewer src={`http://localhost:8000${tempBaseModel.url}`} auto-rotate camera-controls shadow-intensity="1" exposure="1"
                              style={{ width: '100%', height: '100%' }} />
                          </div>
                          <div className="model-preview-info" style={{ padding: '10px 12px' }}>
                            <div className="model-preview-name">{tempBaseModel.name}</div>
                            <div className="model-preview-details">
                              <span className="model-cat-badge" style={{ background: CAT_COLOR[tempBaseModel.category] + '22', color: CAT_COLOR[tempBaseModel.category] }}>
                                {CAT_LABEL[tempBaseModel.category]}
                              </span>
                              <span className="model-size">{tempBaseModel.size_kb} KB</span>
                            </div>
                            <div className="model-preview-filename">{tempBaseModel.filename}</div>
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="base-model-modal-footer">
                      <button className="ai-base-none" style={{ padding: '8px 16px' }} onClick={() => { setTempBaseModel(null); }}>
                        不选择
                      </button>
                      <button className="ai-generate-btn" style={{ padding: '8px 24px' }} onClick={() => { setAiBaseModel(tempBaseModel); setShowBaseModal(false); }}>
                        确认选择
                      </button>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </>
  );
}
