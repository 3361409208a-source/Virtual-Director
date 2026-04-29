import { useState, useEffect, useRef } from 'react';
import type { ModelMeta } from '../services/api';
import { listModels, uploadModel, deleteCustomModel } from '../services/api';
import { ThreeModelPreview } from './ThreeModelPreview';
import { modelingStore } from '../services/modelingStore';

// ── Icons ──────────────────────────────────────────────────────────────────
const IconSparkles = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>;
const IconBox = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>;
const IconTrash = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>;
const IconChevronDown = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>;
const IconChevronUp = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m18 15-6-6-6 6"/></svg>;
const IconPlus = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>;
const IconUpload = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>;
const IconTerminal = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>;

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

export type Tab = 'library' | 'ai';

export function ModelLibraryPanel({ isStandalone = false, initialTab = 'library' }: { isStandalone?: boolean, initialTab?: Tab }) {
  const [open, setOpen]           = useState(isStandalone);
  const [tab, setTab]             = useState<Tab>(initialTab);
  const [models, setModels]       = useState<ModelMeta[]>([]);
  const [filter, setFilter]       = useState<'all' | 'builtin' | 'downloaded' | 'custom'>('all');
  const [preview, setPreview]     = useState<ModelMeta | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [libPage, setLibPage]     = useState(0);
  const [showTemp, setShowTemp]   = useState(false);
  const LIB_PAGE_SIZE = 6;

  // AI modeling state from global store
  const [mState, setMState] = useState(modelingStore.getState());
  const [aiBaseModel, setAiBaseModel] = useState<ModelMeta | null>(null);
  const [saving, setSaving] = useState(false);
  const [logCollapsed, setLogCollapsed] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return modelingStore.subscribe(setMState);
  }, []);

  const { isGenerating: aiGenerating, logs: aiLog, result: aiResult, error: aiError, prompt: aiPrompt, llm: aiLlm, tokens: aiTokens } = mState;
  const setAiPrompt = (p: string) => modelingStore.setPrompt(p);
  const setAiLlm = (l: string) => modelingStore.setLlm(l);

  // Auto-collapse/expand log based on generation state
  useEffect(() => {
    if (aiGenerating) {
      setLogCollapsed(false);
    } else if (aiResult) {
      // Auto collapse after a short delay once success to show the final model better
      const timer = setTimeout(() => setLogCollapsed(true), 500);
      return () => clearTimeout(timer);
    }
  }, [aiGenerating, aiResult]);

  // Base model modal
  const [showBaseModal, setShowBaseModal] = useState(false);
  const [tempBaseModel, setTempBaseModel] = useState<ModelMeta | null>(null);

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

  useEffect(() => { if (open || isStandalone) load(); }, [open, isStandalone]);

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
    modelingStore.startGenerate(aiPrompt, aiLlm, aiBaseModel?.name);
  };

  // Scroll log to bottom when it updates
  useEffect(() => {
    if (aiLog.length > 0 && !logCollapsed) {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [aiLog, logCollapsed]);

  const handleAiDelete = async () => {
    if (!aiResult) return;
    if (!confirm(`删除生成的模型 ${aiResult.filename}？`)) return;
    await deleteCustomModel(aiResult.filename);
    modelingStore.reset();
    await load();
  };

  const filteredModels = models.filter(m => {
    const isCatMatch = filter === 'all' || m.category === filter;
    if (!isCatMatch) return false;
    // Hide ai_ prefixed custom models unless showTemp is true
    if (!showTemp && m.category === 'custom' && m.filename.startsWith('ai_')) return false;
    return true;
  });
  const pagedModels = filteredModels.slice(libPage * LIB_PAGE_SIZE, (libPage + 1) * LIB_PAGE_SIZE);

  const renderContent = () => (
    <>
      <div className="model-lib-header">
        <div className="model-lib-title">{isStandalone ? (tab === 'ai' ? "AI 深度建模工作室" : "资产库") : "资产库"}</div>
        <div className="model-lib-header-actions">
          {!isStandalone && (
            <div className="model-lib-top-tabs">
              <button className={`model-top-tab ${tab === 'library' ? 'active' : ''}`} onClick={() => setTab('library')}>
                <IconBox /> 浏览库
              </button>
              <button className={`model-top-tab ${tab === 'ai' ? 'active' : ''}`} onClick={() => setTab('ai')}>
                <IconSparkles /> AI 建模
              </button>
            </div>
          )}
          {!isStandalone && <button className="model-lib-close" onClick={() => setOpen(false)}>✕</button>}
        </div>
      </div>

      <div className="model-lib-body">
        {tab === 'library' && (
          <>
            <div className="model-lib-grid-col">
              <div className="model-lib-tabs">
                {(['all', 'builtin', 'downloaded', 'custom'] as const).map(cat => (
                  <button key={cat} className={`model-tab ${filter === cat ? 'active' : ''}`} onClick={() => { setFilter(cat); setLibPage(0); }}>
                    {cat === 'all' ? '全部' : CAT_LABEL[cat]}
                    <span className="model-tab-count">
                      {cat === 'all' ? models.length : models.filter(m => m.category === cat).length}
                    </span>
                  </button>
                ))}
                <button 
                  className={`model-tab ${showTemp ? 'active' : ''}`} 
                  onClick={() => { setShowTemp(!showTemp); setLibPage(0); }}
                  style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.7 }}
                >
                  {showTemp ? '显示全部' : '精简视图'}
                </button>
              </div>

              <div className="model-grid">
                {loading && <div className="model-lib-loading">加载中...</div>}
                {error && <div className="model-lib-error">❌ {error}</div>}
                {pagedModels.map(m => (
                  <div key={m.id} className={`model-card ${preview?.id === m.id ? 'selected' : ''}`} onClick={() => setPreview(m)}>
                    <div className="model-card-viewer">
                      {/* @ts-ignore */}
                      <model-viewer src={`http://localhost:8000${m.url}`} auto-rotate camera-controls shadow-intensity="1" style={{ width: '100%', height: '100%' }} />
                    </div>
                    <div className="model-card-info">
                      <span className="model-card-name" title={m.filename}>{m.name}</span>
                      <span className="model-cat-badge" style={{ background: CAT_COLOR[m.category] + '22', color: CAT_COLOR[m.category] }}>{CAT_LABEL[m.category]}</span>
                    </div>
                    {m.category === 'custom' && <button className="model-delete-btn" onClick={e => { e.stopPropagation(); handleDelete(m); }}><IconTrash /></button>}
                  </div>
                ))}
                {pagedModels.length === 0 && !loading && <div className="model-empty">暂无模型</div>}
              </div>

              {filteredModels.length > LIB_PAGE_SIZE && (
                <div className="lib-pager">
                  <button className="ai-pager-btn" onClick={() => setLibPage(p => Math.max(0, p - 1))} disabled={libPage === 0}>‹</button>
                  <span className="ai-pager-info">
                    {libPage * LIB_PAGE_SIZE + 1}–{Math.min((libPage + 1) * LIB_PAGE_SIZE, filteredModels.length)} / {filteredModels.length}
                  </span>
                  <button className="ai-pager-btn" onClick={() => setLibPage(p => p + 1)} disabled={(libPage + 1) * LIB_PAGE_SIZE >= filteredModels.length}>›</button>
                </div>
              )}
            </div>

            <div className="model-preview-panel">
              {preview ? (
                <>
                  <div className="model-preview-viewer">
                    {/* @ts-ignore */}
                    <model-viewer src={`http://localhost:8000${preview.url}`} auto-rotate camera-controls shadow-intensity="1" exposure="1" style={{ width: '100%', height: '100%' }} />
                  </div>
                  <div className="model-preview-info">
                    <div className="model-preview-name">{preview.name}</div>
                    <div className="model-preview-details">
                      <span className="model-cat-badge" style={{ background: CAT_COLOR[preview.category] + '22', color: CAT_COLOR[preview.category] }}>{CAT_LABEL[preview.category]}</span>
                      <span className="model-size">{preview.size_kb} KB</span>
                    </div>
                    <div className="model-preview-filename">{preview.filename}</div>
                  </div>
                </>
              ) : (
                <div className="ai-placeholder">
                  <div className="ai-placeholder-icon">👁️</div>
                  <div>选择模型进行预览</div>
                </div>
              )}
              <div className="model-lib-footer" style={{ padding: 16, borderTop: '1px solid var(--border-color)' }}>
                <input type="file" accept=".glb" ref={fileRef} style={{ display: 'none' }} onChange={handleUpload} />
                <button className="model-upload-btn" style={{ width: '100%' }} onClick={() => fileRef.current?.click()} disabled={uploading}>
                  {uploading ? '⏳ 上传中...' : <><IconUpload /> 上传本地 GLB 模型</>}
                </button>
              </div>
            </div>
          </>
        )}

        {tab === 'ai' && (
          <div className="ai-model-tab">
            <div className="ai-model-input-area">
              <div className="ai-section-label">① 选择参考底模（可选）</div>
              <button className="ai-base-trigger" onClick={() => { setTempBaseModel(aiBaseModel); setShowBaseModal(true); }}>
                {aiBaseModel ? (
                  <span className="ai-base-trigger-name"><IconBox /> {aiBaseModel.name}</span>
                ) : (
                  <span className="ai-base-trigger-placeholder"><IconPlus /> 点击选择底模...</span>
                )}
              </button>
              {aiBaseModel && (
                <button className="ai-base-none" style={{ marginTop: -5, marginBottom: 10, fontSize: 10 }} onClick={() => setAiBaseModel(null)}>清除参考</button>
              )}

              <div className="ai-section-label">② 选择推理模型</div>
              <div className="ai-llm-selector">
                {[
                  { id: 'deepseek-chat',      label: 'DeepSeek V3',    desc: '通用平衡 · 推荐' },
                  { id: 'deepseek-reasoner',  label: 'DeepSeek R1',    desc: '深度思考 · 细节' },
                  { id: 'deepseek-v4-pro',    label: 'DeepSeek V4 Pro',desc: '最强性能' },
                  { id: 'deepseek-v4-flash',  label: 'V4 Flash',       desc: '极速生成' },
                  { id: 'GLM-4.7-Flash',      label: 'GLM 4.7 Flash',  desc: '极速' },
                  { id: 'astron-code-latest', label: 'Astron Code',    desc: '代码专家' },
                ].map(m => (
                  <button key={m.id} className={`ai-llm-btn ${aiLlm === m.id ? 'active' : ''}`} onClick={() => setAiLlm(m.id)}>
                    <span className="ai-llm-name">{m.label}</span>
                    <span className="ai-llm-desc">{m.desc}</span>
                  </button>
                ))}
              </div>

              <div className="ai-section-label">③ 描述你的建模需求</div>
              <textarea className="ai-model-textarea" 
                placeholder="描述外观、颜色、零件构成…（支持 Ctrl+Enter 快速启动）" 
                value={aiPrompt} 
                onChange={e => setAiPrompt(e.target.value)} 
                onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleAiGenerate(); }}
                rows={4} 
              />
              <button className="ai-generate-btn" onClick={handleAiGenerate} disabled={aiGenerating || !aiPrompt.trim()}>
                {aiGenerating ? <><span className="ai-spinner" /> AI 建模中…</> : <><IconSparkles /> 启动深度建模引擎</>}
              </button>
              {aiError && <div className="ai-model-error">❌ {aiError}</div>}
            </div>

            <div className="ai-model-right">
              {(aiResult || mState.parts.length > 0) ? (
                <div className="ai-result">
                  <div className="ai-result-viewer">
                    <ThreeModelPreview 
                      url={aiResult ? `${aiResult.url}?t=${Date.now()}` : null} 
                      parts={mState.parts}
                    />
                  </div>
                  {aiResult && (
                    <div className="ai-result-info">
                      <div className="ai-result-name">{aiResult.model_name}</div>
                      <div className="ai-result-desc">{aiResult.description}</div>
                      <div className="ai-result-meta">
                        <span>{aiResult.parts_count} 零件</span>
                        <span>{aiResult.size_kb} KB</span>
                      </div>
                      <div className="ai-result-actions">
                        <button className="ai-save-btn" disabled={saving} onClick={async () => { setSaving(true); try { await load(); } finally { setSaving(false); } }}>
                          {saving ? '⏳ 保存中...' : <><IconUpload /> 存入资产库</>}
                        </button>
                        <button className="ai-delete-btn" onClick={handleAiDelete}><IconTrash /> 删除</button>
                      </div>
                    </div>
                  )}
                  {aiGenerating && !aiResult && (
                    <div className="ai-building-overlay">
                      <span className="ai-spinner" /> 正在实时同步建模参数...
                    </div>
                  )}
                </div>
              ) : (
                <div className="ai-placeholder">
                  {aiGenerating ? (
                    <div className="ai-building-wrapper">
                      <div className="ai-building-grid" />
                      <div className="ai-building-scanner" />
                      <div className="ai-building-text">
                        <span className="ai-spinner" />
                        AI 正在构建 3D 实体...
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="ai-placeholder-icon"><IconSparkles /></div>
                      <div>预览区域</div>
                      <div style={{ fontSize: 11, color: '#6e7681', marginTop: 4 }}>生成后将在此处展示 3D 预览</div>
                    </>
                  )}
                </div>
              )}

              {(aiLog.length > 0 || aiGenerating) && (
                <div className={`ai-log-panel ${logCollapsed ? 'collapsed' : ''}`}>
                  <div className="ai-log-title" onClick={() => setLogCollapsed(!logCollapsed)}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <IconTerminal /> 
                      推理日志
                      <span style={{ fontSize: 10, color: 'var(--text-secondary)', marginLeft: 8, fontWeight: 'normal' }}>
                        Token: <b>{aiTokens && aiTokens.input > 0 ? aiTokens.input : Math.floor(aiPrompt.length * 1.5)}</b> in / 
                        <b>{aiTokens && aiTokens.output > 0 ? aiTokens.output : Math.floor(aiLog.join('').length / 2)}</b> out
                      </span>
                    </div>
                    <button className="log-collapse-btn" style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
                      {logCollapsed ? <IconChevronUp /> : <IconChevronDown />}
                    </button>
                  </div>
                  <div className="ai-log-body">
                    {aiLog.map((line, i) => (
                      <div key={i} className={`ai-log-line ${line.startsWith('💭') ? 'thinking' : ''}`}>{line}</div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {showBaseModal && (
        <div className="base-model-modal-overlay" onClick={() => setShowBaseModal(false)}>
          <div className="base-model-modal" onClick={e => e.stopPropagation()}>
            <div className="base-model-modal-header">
              <h3>选择参考底模</h3>
              <button className="model-lib-close" onClick={() => setShowBaseModal(false)}>✕</button>
            </div>
            <div className="base-model-modal-body">
               <div className="base-model-modal-left" style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
                 <div className="model-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
                   {models.map(m => (
                     <div key={m.id} className={`model-card ${tempBaseModel?.id === m.id ? 'selected' : ''}`} onClick={() => setTempBaseModel(m)}>
                       <div className="model-card-info" style={{ padding: 8 }}>
                         <div className="model-card-name" style={{ fontSize: 12 }}>{m.name}</div>
                         <div className="model-cat-badge" style={{ fontSize: 9, padding: '1px 4px' }}>{CAT_LABEL[m.category]}</div>
                       </div>
                     </div>
                   ))}
                 </div>
               </div>
               {tempBaseModel && (
                 <div className="base-model-modal-preview" style={{ width: 240, background: '#000' }}>
                   {/* @ts-ignore */}
                   <model-viewer src={`http://localhost:8000${tempBaseModel.url}`} auto-rotate camera-controls style={{ width: '100%', height: '100%' }} />
                 </div>
               )}
            </div>
            <div className="base-model-modal-footer">
              <button className="review-cancel-btn" onClick={() => { setAiBaseModel(null); setShowBaseModal(false); }}>不使用</button>
              <button className="review-confirm-btn" disabled={!tempBaseModel} onClick={() => { setAiBaseModel(tempBaseModel); setShowBaseModal(false); }}>确定选择</button>
            </div>
          </div>
        </div>
      )}
    </>
  );

  if (isStandalone) {
    return <div className="modeling-page-container">{renderContent()}</div>;
  }

  return (
    <>
      <button className="model-lib-btn" onClick={() => setOpen(true)}>
        <IconBox />
        <span>资产库</span>
        {models.length > 0 && <span className="model-lib-count">{models.length}</span>}
      </button>
      {open && (
        <div className="model-lib-overlay" onClick={() => setOpen(false)}>
          <div className="model-lib-drawer" onClick={e => e.stopPropagation()}>
            {renderContent()}
          </div>
        </div>
      )}
    </>
  );
}
