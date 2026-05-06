import { useState, useEffect, useRef } from 'react';
import type { ModelMeta } from '../services/api';
import { listModels, uploadModel, deleteCustomModel, optimizePrompt } from '../services/api';
import { ThreeModelPreview } from './ThreeModelPreview';
import { SceneWalker } from './SceneWalker';
import { modelingStore } from '../services/modelingStore';

import { IconSparkles, IconBox, IconTrash, IconChevronDown, IconChevronUp, IconPlus, IconUpload, IconTerminal, IconClose, IconError, IconEye, IconMagic } from './Icons';

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

export function ModelLibraryPanel({ isStandalone = false, initialTab = 'library', onStartVideo }: { 
  isStandalone?: boolean, 
  initialTab?: Tab,
  onStartVideo?: (prompt: string, baseModel: string) => Promise<void>
}) {
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
  const [pageSize, setPageSize]   = useState(12);
  const [showTemp, setShowTemp]   = useState(false);
  const [previewPreset] = useState<any>('studio');
  const [isOptimizing, setIsOptimizing] = useState(false);

  const [showWalker, setShowWalker] = useState(false);
  const [showActionInput, setShowActionInput] = useState(false);
  const [actionPrompt, setActionPrompt] = useState('');
  const [isStartingVideo, setIsStartingVideo] = useState(false);
  
  // Resizable split state
  const [splitWidth, setSplitWidth] = useState(window.innerWidth * 0.65); // Default ~70% for right panel
  const isResizing = useRef(false);

  // AI modeling state from global store
  const [mState, setMState] = useState(modelingStore.getState());
  const [aiBaseModel, setAiBaseModel] = useState<ModelMeta | null>(null);
  const [saving, setSaving] = useState(false);
  const [logCollapsed, setLogCollapsed] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return modelingStore.subscribe(setMState);
  }, []);

  const [refining, setRefining] = useState(false);
  const { isGenerating: aiGenerating, logs: aiLog, result: aiResult, sceneResult, error: aiError, prompt: aiPrompt, llm: aiLlm, style: aiStyle, tokens: aiTokens } = mState;
  const setAiPrompt = (p: string) => modelingStore.setPrompt(p);
  const setAiLlm = (l: string) => modelingStore.setLlm(l);
  const setAiStyle = (style: string) => modelingStore.setStyle(style);

  // Auto-collapse/expand log based on generation state
  useEffect(() => {
    if (aiGenerating) {
      setLogCollapsed(false);
      setRefining(false);
    } else if (mState.parts.length > 0) {
      // Trigger refining when generation finishes
      setRefining(true);
      const timerRefining = setTimeout(() => {
        setRefining(false);
        setLogCollapsed(true);
      }, 3000);
      return () => clearTimeout(timerRefining);
    }
  }, [aiGenerating, mState.parts.length]);

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

  const handleStartActionVideo = async () => {
    if (!preview || !actionPrompt.trim() || !onStartVideo) return;
    setIsStartingVideo(true);
    try {
      await onStartVideo(actionPrompt, preview.name);
      setShowActionInput(false);
      setActionPrompt('');
    } finally {
      setIsStartingVideo(false);
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
    modelingStore.startGenerate(aiPrompt, aiLlm, aiBaseModel?.name, aiStyle);
  };

  const handleOptimize = async () => {
    if (!aiPrompt.trim() || isOptimizing) return;
    setIsOptimizing(true);
    try {
      const optimized = await optimizePrompt(aiPrompt, 'modeling');
      setAiPrompt(optimized);
    } catch (err) {
      console.error('Failed to optimize prompt:', err);
    } finally {
      setIsOptimizing(false);
    }
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

  // Resize handler
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return;
      const container = document.querySelector('.model-lib-body');
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const newWidth = containerRect.right - e.clientX;
      if (newWidth > 200 && newWidth < containerRect.width - 200) {
        setSplitWidth(newWidth);
      }
    };
    const handleMouseUp = () => {
      isResizing.current = false;
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    const startResizing = (_e: React.MouseEvent) => {
      isResizing.current = true;
      document.body.style.cursor = 'col-resize';
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    };
    
    // @ts-ignore
    window.startResizing = startResizing;
  }, []);

  const filteredModels = models.filter(m => {
    const isCatMatch = filter === 'all' || m.category === filter;
    if (!isCatMatch) return false;
    // Hide ai_ prefixed custom models unless showTemp is true
    if (!showTemp && m.category === 'custom' && m.filename.startsWith('ai_')) return false;
    return true;
  });
  const pagedModels = filteredModels.slice(libPage * pageSize, (libPage + 1) * pageSize);

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
          {!isStandalone && <button className="model-lib-close" onClick={() => setOpen(false)}><IconClose /></button>}
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
                <div className="lib-page-size-selector">
                  <span>每页:</span>
                  {[12, 24, 48].map(size => (
                    <button key={size} className={`page-size-btn ${pageSize === size ? 'active' : ''}`} onClick={() => { setPageSize(size); setLibPage(0); }}>{size}</button>
                  ))}
                </div>
                <button 
                  className={`model-tab ${showTemp ? 'active' : ''}`} 
                  onClick={() => { setShowTemp(!showTemp); setLibPage(0); }}
                  style={{ marginLeft: 8, fontSize: 10, opacity: 0.7 }}
                >
                  {showTemp ? '显示全部' : '精简视图'}
                </button>
              </div>

              <div className="model-grid">
                {loading && <div className="model-lib-loading">加载中...</div>}
                {error && <div className="model-lib-error"><IconError /> {error}</div>}
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

              {filteredModels.length > pageSize && (
                <div className="lib-pager">
                  <button className="ai-pager-btn" onClick={() => setLibPage(p => Math.max(0, p - 1))} disabled={libPage === 0}>‹</button>
                  <span className="ai-pager-info">
                    {libPage * pageSize + 1}–{Math.min((libPage + 1) * pageSize, filteredModels.length)} / {filteredModels.length}
                  </span>
                  <button className="ai-pager-btn" onClick={() => setLibPage(p => p + 1)} disabled={(libPage + 1) * pageSize >= filteredModels.length}>›</button>
                </div>
              )}
            </div>

            <div className="lib-resize-handle" onMouseDown={(e) => (window as any).startResizing(e)} />

            <div className="model-preview-panel" style={{ width: splitWidth }}>
              {preview ? (
                <>
                  <div className="model-preview-viewer">
                    <ThreeModelPreview 
                      url={preview.url} 
                      parts={[]}
                      preset={previewPreset}
                    />
                  </div>
                  <div className="model-preview-info">
                    <div className="model-preview-name">{preview.name}</div>
                    <div className="model-preview-details">
                      <span className="model-cat-badge" style={{ background: CAT_COLOR[preview.category] + '22', color: CAT_COLOR[preview.category] }}>{CAT_LABEL[preview.category]}</span>
                      <span className="model-size">{preview.size_kb} KB</span>
                    </div>
                    <div className="model-preview-filename">{preview.filename}</div>
                  </div>
                  <div className="model-preview-actions" style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {!showActionInput ? (
                      <button 
                        className="model-action-btn" 
                        style={{ background: 'var(--accent-color)', color: 'white', border: 'none', padding: '8px 12px', borderRadius: 6, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontWeight: 600 }}
                        onClick={() => setShowActionInput(true)}
                      >
                        <IconSparkles /> 让它动起来
                      </button>
                    ) : (
                      <div className="model-action-input-group" style={{ display: 'flex', flexDirection: 'column', gap: 8, background: 'var(--bg-secondary)', padding: 12, borderRadius: 8, border: '1px solid var(--border-color)' }}>
                        <textarea 
                          placeholder="描述它要做什么... (例如: 在森林里奔跑)" 
                          value={actionPrompt}
                          onChange={e => setActionPrompt(e.target.value)}
                          style={{ width: '100%', background: 'transparent', border: 'none', color: 'inherit', resize: 'none', fontSize: 13, outline: 'none' }}
                          rows={3}
                          autoFocus
                        />
                        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                          <button onClick={() => setShowActionInput(false)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12 }}>取消</button>
                          <button 
                            disabled={!actionPrompt.trim() || isStartingVideo}
                            onClick={handleStartActionVideo}
                            style={{ background: 'var(--accent-color)', color: 'white', border: 'none', padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 12, opacity: (!actionPrompt.trim() || isStartingVideo) ? 0.5 : 1 }}
                          >
                            {isStartingVideo ? '启动中...' : '开始定制视频'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="ai-placeholder">
                <div className="ai-placeholder-icon"><IconEye /></div>
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
                  { id: 'Kimi-K2.6',           label: 'Kimi K2.6',      desc: '方舟 · Kimi' },
                  { id: 'astron-code-latest', label: 'Astron Code',    desc: '代码专家' },
                ].map(m => (
                  <button key={m.id} className={`ai-llm-btn ${aiLlm === m.id ? 'active' : ''}`} onClick={() => setAiLlm(m.id)}>
                    <span className="ai-llm-name">{m.label}</span>
                    <span className="ai-llm-desc">{m.desc}</span>
                  </button>
                ))}
              </div>

              <div className="ai-section-label">②.5 选择建模风格</div>
              <div className="ai-llm-selector">
                {[
                  { id: 'realistic', label: '🔮 写实风格', desc: '程序化 / 高精模型' },
                  { id: 'minecraft', label: '🟫 我的世界', desc: 'AI 体素拼装 · 极速' },
                  { id: 'scene',     label: '🏙️ 场景建模', desc: '多物体 · 整体搭建' },
                ].map(s => (
                  <button key={s.id} className={`ai-llm-btn ${aiStyle === s.id ? 'active' : ''}`} onClick={() => setAiStyle(s.id)}>
                    <span className="ai-llm-name">{s.label}</span>
                    <span className="ai-llm-desc">{s.desc}</span>
                  </button>
                ))}
              </div>
              {aiStyle === 'scene' && (
                <div style={{ background: 'rgba(56,139,253,0.08)', border: '1px solid rgba(56,139,253,0.25)', borderRadius: 8, padding: '8px 12px', fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  💡 <b>场景建模</b>：AI 会先规划整个场景的空间布局，再为每个物体并行生成独立 GLB 模型。<br />
                  例如：<i>「一个赛博朋克街头夜市，有摊位、霓虹灯牌、行人和路灯」</i>
                </div>
              )}

              <div className="ai-section-label">③ 描述你的建模需求</div>
              <div className="ai-input-wrapper" style={{ position: 'relative' }}>
                <textarea className="ai-model-textarea" 
                  placeholder="描述外观、颜色、零件构成…（支持 Ctrl+Enter 快速启动）" 
                  value={aiPrompt} 
                  onChange={e => setAiPrompt(e.target.value)} 
                  onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleAiGenerate(); }}
                  rows={4} 
                  style={{ width: '100%', paddingLeft: 40 }}
                />
                <button 
                  className={`ai-magic-btn ${isOptimizing ? 'spinning' : ''}`}
                  onClick={handleOptimize}
                  disabled={aiGenerating || isOptimizing || !aiPrompt.trim()}
                  title="专家魔法棒：优化当前建模描述"
                  style={{
                    position: 'absolute',
                    left: 10,
                    top: 10,
                    background: 'none',
                    border: 'none',
                    color: 'var(--accent-color)',
                    cursor: 'pointer',
                    opacity: aiPrompt.trim() ? 1 : 0.4,
                    transition: 'all 0.2s',
                    zIndex: 2
                  }}
                >
                  <IconMagic />
                </button>
              </div>
              <button className="ai-generate-btn" onClick={handleAiGenerate} disabled={aiGenerating || !aiPrompt.trim()}>
                {aiGenerating ? <><span className="ai-spinner" /> AI 建模中…</> : <><IconSparkles /> 启动深度建模引擎</>}
              </button>
              {aiError && <div className="ai-model-error"><IconError /> {aiError}</div>}
            </div>

            <div className="ai-model-right">
              {(aiResult || mState.parts.length > 0 || aiGenerating || refining) ? (
                <div className="ai-result">
                  <div className="ai-result-viewer">
                    <ThreeModelPreview 
                      url={(aiResult && !refining) ? `${aiResult.url}?t=${Date.now()}` : null} 
                      parts={mState.parts}
                      isRefining={refining}
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
                  {(aiGenerating || refining) && !aiResult && (
                    <div className="ai-building-overlay" style={{ pointerEvents: 'none' }}>
                      <div className="ai-building-text">
                        <span className="ai-spinner" />
                        {refining ? '正在深度精修 3D 实体...' : 'AI 正在构建 3D 实体...'}
                      </div>
                    </div>
                  )}
                </div>
              ) : sceneResult ? (
                <div style={{ padding: 12, overflowY: 'auto', flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>
                    🏙️ {sceneResult.scene_name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 10 }}>
                    {sceneResult.scene_description}
                    <span style={{ marginLeft: 8, color: 'var(--accent)', opacity: 0.8 }}>
                      {sceneResult.success_count}/{sceneResult.total_objects} 个物体
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px,1fr))', gap: 8 }}>
                    {sceneResult.objects.map((obj, i) => (
                      <div key={i} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, cursor: 'pointer' }}
                        onClick={() => setPreview({ id: `custom/${obj.filename}`, category: 'custom', filename: obj.filename, name: obj.name, size_kb: obj.size_kb, url: obj.url })}>
                        <div style={{ fontSize: 18, textAlign: 'center', marginBottom: 4 }}>
                          {obj.category === 'structure' ? '🏗️' : obj.category === 'vegetation' ? '🌳' : obj.category === 'character' ? '🧍' : obj.category === 'vehicle' ? '🚗' : obj.category === 'light' ? '💡' : '📦'}
                        </div>
                        <div style={{ fontSize: 10, fontWeight: 600, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{obj.name}</div>
                        <div style={{ fontSize: 9, color: 'var(--text-secondary)', textAlign: 'center' }}>{obj.parts_count} 零件 · {obj.size_kb}KB</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                    <button
                      onClick={() => setShowWalker(true)}
                      style={{
                        flex: 1, padding: '8px 0', borderRadius: 8, border: 'none', cursor: 'pointer',
                        background: 'linear-gradient(135deg, #1f6feb, #388bfd)',
                        color: '#fff', fontWeight: 700, fontSize: 13,
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                      }}
                    >
                      🎮 进入场景漫游
                    </button>
                    <button className="ai-save-btn" style={{ flex: 0.4 }} onClick={() => load()}>
                      <IconUpload /> 刷新库
                    </button>
                  </div>
                </div>
              ) : aiGenerating && aiStyle === 'scene' ? (
                <div className="ai-placeholder">
                  <div style={{ fontSize: 24, marginBottom: 8 }}>🌍</div>
                  <div style={{ fontWeight: 600 }}>场景建模进行中...</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>AI 正在为每个物体并行生成 GLB</div>
                </div>
              ) : (
                <div className="ai-placeholder">
                  <div className="ai-placeholder-icon"><IconBox /></div>
                  <div>描述你的需求并点击生成</div>
                </div>
              )}

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
                  {/* 💭 思考过程与文字说明保留，精准剔除大规模 JSON 块 */}
                  {aiLog.map((line, i) => {
                    // 如果是思维链，保留
                    if (line.startsWith('💭')) return <div key={i} className="ai-log-line thinking">{line}</div>;
                    
                    // 如果是 Token 输出，尝试清理其中的 JSON 块
                    if (line.startsWith('📝')) {
                      // 移除所有可能是零件 JSON 的部分，保留文字
                      // 匹配 {} 块，尤其是包含 shape 的块
                      let cleanLine = line.replace(/\{[^{}]*"shape"[^{}]*\}/g, ' [零件数据...] ');
                      cleanLine = cleanLine.replace(/\{[^{}]*"type"[^{}]*\}/g, ' [零件数据...] ');
                      
                      // 如果清理后只剩下前缀或太短且包含 JSON 关键字符，则隐藏
                      if (cleanLine.length < 10 && (cleanLine.includes('{') || cleanLine.includes('"'))) return null;
                      
                      // 再次过滤掉明显的 JSON 行
                      if (cleanLine.includes('"parts":') || cleanLine.includes('"model_name":')) return null;

                      return <div key={i} className="ai-log-line">{cleanLine}</div>;
                    }
                    
                    // 其他状态消息（start, building 等），保留
                    return <div key={i} className="ai-log-line">{line}</div>;
                  }).filter(Boolean)}
                  
                  {/* 🛠️ 结构化零件清单 (类似 C4D 对象管理器) */}
                  {mState.parts.length > 0 && (
                    <div className="parts-inventory">
                      <div className="parts-inventory-header">
                        <span>📦 零件装配清单</span>
                        <span className="parts-count-tag">{mState.parts.length} items</span>
                      </div>
                      <div className="parts-grid">
                        {mState.parts.map((p, idx) => (
                          <div key={idx} className="part-item-card" title={`${p.name || '未命名'}\n形状: ${p.shape || p.type}\n材质: 金属度 ${p.metallic || 0}`}>
                            <div className="part-icon">
                              {p.shape === 'sphere' ? '⚪' : (p.shape === 'cylinder' ? '▮' : '🧊')}
                            </div>
                            <div className="part-info">
                              <div className="part-name">{p.name || `零件_${idx}`}</div>
                              <div className="part-meta">
                                <span className="part-chip">{p.shape || p.type}</span>
                                {p.metallic > 0.5 && <span className="part-chip metal">金属</span>}
                              </div>
                            </div>
                            <div className="part-color-preview" style={{ background: `rgb(${(p.color?.r || 0.7)*255}, ${(p.color?.g || 0.7)*255}, ${(p.color?.b || 0.7)*255})` }} />
                          </div>
                        ))}
                        {aiGenerating && <div className="part-item-card printing">
                          <div className="part-icon">✨</div>
                          <div className="part-info">正在打印新零件...</div>
                        </div>}
                      </div>
                    </div>
                  )}
                  <div ref={logEndRef} />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {showBaseModal && (
        <div className="base-model-modal-overlay" onClick={() => setShowBaseModal(false)}>
          <div className="base-model-modal" onClick={e => e.stopPropagation()}>
            <div className="base-model-modal-header">
              <h3>选择参考底模</h3>
              <button className="model-lib-close" onClick={() => setShowBaseModal(false)}><IconClose /></button>
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

      {showWalker && sceneResult && (
        <SceneWalker
          objects={sceneResult.objects}
          sceneName={sceneResult.scene_name}
          onClose={() => setShowWalker(false)}
        />
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
