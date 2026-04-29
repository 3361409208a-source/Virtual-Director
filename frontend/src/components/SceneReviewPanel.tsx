import { useState, useCallback, useRef, useEffect } from 'react';
import type { SceneSequence } from '../types';
import { confirmReview, rejectReview, streamAiGenerateModel, type AIModelEvent } from '../services/api';
import { ThreeModelPreview } from './ThreeModelPreview';

// ── Icons ──────────────────────────────────────────────────────────────────
const IconSparkles = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>;
const IconBox = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>;
const IconChevronDown = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>;
const IconChevronUp = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m18 15-6-6-6 6"/></svg>;
const IconTerminal = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>;
const IconActor = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>;
const IconTrack = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 18l5-5-5-5"/><path d="M6 18l5-5-5-5"/></svg>;
const IconCamera = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><path d="M8 21h8"/><path d="M12 17v4"/><path d="m3 7 9 9 9-9"/></svg>;
const IconEnvironment = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 18a5 5 0 0 0-10 0"/><line x1="12" x2="12" y1="2" y2="9"/><line x1="4.22" x2="5.64" y1="10.22" y2="11.64"/><line x1="1" x2="3" y1="18" y2="18"/><line x1="21" x2="23" y1="18" y2="18"/><line x1="18.36" x2="19.78" y1="11.64" y2="10.22"/><line x1="23" x2="23" y1="22" y2="22"/><line x1="1" x2="1" y1="22" y2="22"/></svg>;

interface Props {
  sid: string;
  sequence: SceneSequence;
  model: string;
  onConfirmed: () => void;
  onRejected: () => void;
}

// ────────────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────────────

function jsonPretty(v: unknown): string {
  return JSON.stringify(v, null, 2);
}

function tryParse(s: string): { ok: true; value: unknown } | { ok: false; error: string } {
  try {
    return { ok: true, value: JSON.parse(s) };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

function getAssetUrl(path: string): string | null {
  if (!path) return null;
  const parts = path.split('/');
  if (parts.length >= 3) {
    const cat = parts[parts.length - 2];
    const file = parts[parts.length - 1];
    return `/api/models/${cat}/${file}`;
  }
  if (path.startsWith('http') || path.startsWith('/')) return path;
  return null;
}

// ────────────────────────────────────────────────────────────────────────────
// 单个可编辑数据块
// ────────────────────────────────────────────────────────────────────────────

interface BlockProps {
  label: string;
  icon: React.ReactNode;
  data: unknown;
  onChange: (newVal: unknown) => void;
}

function EditableBlock({ label, icon, data, onChange }: BlockProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [err, setErr] = useState('');
  const [collapsed, setCollapsed] = useState(true);

  const startEdit = () => {
    setDraft(jsonPretty(data));
    setErr('');
    setEditing(true);
    setCollapsed(false);
  };

  const save = () => {
    const result = tryParse(draft);
    if ('error' in result) {
      setErr(`JSON 解析错误：${result.error}`);
      return;
    }
    onChange(result.value);
    setEditing(false);
    setErr('');
  };

  const cancel = () => {
    setEditing(false);
    setErr('');
  };

  const summary = (() => {
    if (Array.isArray(data)) return `[${data.length} 项]`;
    if (data && typeof data === 'object') return `{${Object.keys(data as object).join(', ')}}`;
    return String(data);
  })();

  return (
    <div className="review-block">
      <div className="review-block-header" onClick={() => !editing && setCollapsed(c => !c)}>
        <span className="review-block-icon">{icon}</span>
        <span className="review-block-label">{label}</span>
        <span className="review-block-summary">{summary}</span>
        <div className="review-block-actions" onClick={e => e.stopPropagation()}>
          {!editing && (
            <button className="review-edit-btn" onClick={startEdit} title="编辑此块">
              编辑
            </button>
          )}
          <span className="review-block-toggle">{collapsed && !editing ? <IconChevronDown /> : <IconChevronUp />}</span>
        </div>
      </div>

      {(!collapsed || editing) && (
        <div className="review-block-body">
          {editing ? (
            <>
              <textarea
                className={`review-json-editor ${err ? 'has-error' : ''}`}
                value={draft}
                onChange={e => setDraft(e.target.value)}
                spellCheck={false}
                rows={Math.min(30, draft.split('\n').length + 2)}
              />
              {err && <div className="review-json-error">{err}</div>}
              <div className="review-edit-actions">
                <button className="review-save-btn" onClick={save}>保存修改</button>
                <button className="review-cancel-btn" onClick={cancel}>取消</button>
              </div>
            </>
          ) : (
            <pre className="review-json-view">{jsonPretty(data)}</pre>
          )}
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// AI 资产重新建模组件
// ────────────────────────────────────────────────────────────────────────────

interface RegeneratorProps {
  actorId: string;
  currentAsset: any;
  model: string;
  onDone: (newPath: string) => void;
}

function AssetRegenerator({ actorId, currentAsset, model, onDone }: RegeneratorProps) {
  const safeId = actorId || 'object';
  const initialPrompt = currentAsset?.name || safeId.replace(/_/g, ' ');
  const [prompt, setPrompt] = useState(initialPrompt);
  const [generating, setGenerating] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [currentTokens, setCurrentTokens] = useState<{ input: number; output: number } | undefined>(undefined);
  const logEndRef = useRef<HTMLDivElement>(null);

  const formatTokens = (tokens?: { input: number; output: number }) => {
    if (!tokens) return '0';
    const total = tokens.input + tokens.output;
    return total.toLocaleString();
  };

  const handleGenerate = async () => {
    if (generating) return;
    setGenerating(true);
    setLog(['开始重新建模...']);
    let tokenBuf = '';
    setCurrentTokens(undefined);
    try {
      await streamAiGenerateModel(prompt, (ev: AIModelEvent) => {
        if (ev.step === 'thinking') {
          setLog(prev => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (lastIdx >= 0 && updated[lastIdx].startsWith('💭')) {
              updated[lastIdx] = updated[lastIdx] + ev.msg;
            } else {
              updated.push('💭 ' + ev.msg);
            }
            return updated;
          });
        } else if (ev.step === 'token') {
          tokenBuf += ev.msg;
          setLog(prev => {
            const updated = [...prev];
            if (updated.length > 0 && updated[updated.length - 1].startsWith('📝')) {
              updated[updated.length - 1] = '📝 ' + tokenBuf;
            } else {
              updated.push('📝 ' + tokenBuf);
            }
            return updated;
          });
        } else if (ev.step === 'done') {
          setLog(prev => [...prev, '✨ 生成成功！']);
          if (ev.url) onDone(ev.url);
        } else if (ev.step === 'error') {
          setLog(prev => [...prev, '❌ ' + ev.msg]);
        } else if (ev.step === 'building' || ev.step === 'start') {
          setCurrentTokens(ev.tokens);
          tokenBuf = '';
          setLog(prev => [...prev, ev.msg]);
        } else {
          tokenBuf = '';
          setLog(prev => [...prev, ev.msg]);
        }
      }, model);
    } catch (e) {
      setLog(prev => [...prev, '❌ ' + String(e)]);
    } finally {
      setGenerating(false);
    }
  };

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [log]);

  const isComposite = currentAsset?.type === 'composite' || !currentAsset;

  return (
    <div className="asset-regen-item">
      <div className="asset-regen-header">
        <div className="asset-regen-info">
          <span className="asset-regen-id"><IconActor /> {safeId}</span>
          <span className="asset-regen-status">
             {isComposite ? <><IconBox /> 积木拼装</> : <><IconBox /> 外部模型：{currentAsset?.path?.split('/').pop()}</>}
          </span>
        </div>
        {currentTokens && (
          <div className="asset-token-usage">
            <IconTerminal /> {formatTokens(currentTokens)} tokens
            <span className="token-breakdown">
              (📥 {currentTokens.input.toLocaleString()} + 📤 {currentTokens.output.toLocaleString()})
            </span>
          </div>
        )}
      </div>

      {currentAsset && (
        <div className="asset-preview-container-large">
          <ThreeModelPreview
            url={currentAsset.path ? getAssetUrl(currentAsset.path) + (currentAsset.path.includes('?') ? '&' : '?') + 't=' + Date.now() : null}
            parts={currentAsset.parts || []}
          />
        </div>
      )}

      <div className="asset-regen-controls">
        <input
          className="asset-regen-input"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onMouseDown={e => e.stopPropagation()}
          placeholder="描述你想要的样子..."
          disabled={generating}
        />
        <button
          className="asset-regen-btn"
          onClick={handleGenerate}
          disabled={generating}
        >
          {generating ? '⏳ 生成中...' : <><IconSparkles /> AI 重新建模</>}
        </button>
      </div>

      {log.length > 0 && (
        <div className="asset-regen-log">
          {log.map((line, i) => <div key={i}>{line}</div>)}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Main Panel
// ────────────────────────────────────────────────────────────────────────────

export function SceneReviewPanel({ sid, sequence: initialSequence, model, onConfirmed, onRejected }: Props) {
  const [seq, setSeq] = useState<SceneSequence>(initialSequence);
  const [loading, setLoading] = useState<'confirm' | 'reject' | null>(null);
  const [activeTab, setActiveTab] = useState<'data' | 'assets'>('assets');

  const update = useCallback(<K extends keyof SceneSequence>(key: K, val: SceneSequence[K]) => {
    setSeq(prev => ({ ...prev, [key]: val }));
  }, []);

  const handleConfirm = async () => {
    setLoading('confirm');
    try {
      await confirmReview(sid, seq);
      onConfirmed();
    } catch (e) {
      console.error(e);
      setLoading(null);
    }
  };

  const handleReject = async () => {
    setLoading('reject');
    try {
      await rejectReview(sid);
      onRejected();
    } catch (e) {
      console.error(e);
    }
    onRejected();
  };

  return (
    <div className="scene-review-overlay" onMouseDown={(e) => e.stopPropagation()}>
      <div className="scene-review-panel" onMouseDown={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="scene-review-header">
          <div className="scene-review-title">
            <span className="scene-review-badge">REVIEW</span>
            <h2>场景方案审核</h2>
            <p>AI 已完成建模，请逐块确认并可自定义修改后，再提交渲染</p>
          </div>
          <div className="scene-review-actions">
            <button
              className="review-reject-btn"
              onClick={handleReject}
              disabled={loading !== null}
            >
              {loading === 'reject' ? '处理中...' : '放弃重来'}
            </button>
            <button
              className="review-confirm-btn"
              onClick={handleConfirm}
              disabled={loading !== null}
            >
              {loading === 'confirm' ? '提交中...' : '确认开始渲染'}
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="scene-review-tabs">
          <button
            className={`review-tab ${activeTab === 'assets' ? 'active' : ''}`}
            onClick={() => setActiveTab('assets')}
          >
            <IconBox /> 资产建模
          </button>
          <button
            className={`review-tab ${activeTab === 'data' ? 'active' : ''}`}
            onClick={() => setActiveTab('data')}
          >
            <IconTerminal /> 数据编辑
          </button>
        </div>

        {/* Content */}
        <div className="scene-review-content">

          {activeTab === 'assets' && (
            <div className="scene-review-assets">
              <div className="review-section-hint">
                <IconSparkles /> 如果 AI 下载或拼装的模型不满意，可以在此处输入描述重新生成专属 GLB 模型。
              </div>
              {(seq.actors ?? []).map((actor, idx) => {
                const aid: string = actor.actor_id ?? `actor_${idx}`;
                return (
                <AssetRegenerator
                  key={aid + '_' + idx}
                  actorId={aid}
                  currentAsset={seq.asset_manifest?.[aid]}
                  model={model}
                  onDone={(newUrl) => {
                    const newFilename = newUrl.split('/').pop() || '';
                    const newPath = `assets/custom/${newFilename}`;
                    setSeq(prev => ({
                      ...prev,
                      asset_manifest: {
                        ...prev.asset_manifest,
                        [aid]: {
                          actor_id: aid,
                          type: 'downloaded',
                          path: newPath,
                          target_size: { x: 1, y: 1, z: 1 }
                        }
                      }
                    }));
                  }}
                />
              );
              })}
            </div>
          )}

          {activeTab === 'data' && (
            <div className="scene-review-data">
              <EditableBlock
                label="场景环境"
                icon={<IconEnvironment />}
                data={seq.scene_setup}
                onChange={v => update('scene_setup', v as SceneSequence['scene_setup'])}
              />
              <EditableBlock
                label="演员列表"
                icon={<IconActor />}
                data={seq.actors}
                onChange={v => update('actors', v as SceneSequence['actors'])}
              />
              <EditableBlock
                label="演员运动轨迹"
                icon={<IconTrack />}
                data={seq.actor_tracks}
                onChange={v => update('actor_tracks', v as SceneSequence['actor_tracks'])}
              />
              <EditableBlock
                label="摄影机轨迹"
                icon={<IconCamera />}
                data={seq.camera_track}
                onChange={v => update('camera_track', v as SceneSequence['camera_track'])}
              />
              <EditableBlock
                label="资产配置 (asset_manifest)"
                icon={<IconBox />}
                data={seq.asset_manifest}
                onChange={v => update('asset_manifest', v as SceneSequence['asset_manifest'])}
              />
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="scene-review-footer">
          <span>在「数据编辑」标签页中可以直接修改任何 JSON 数据块，修改后点击「确认开始渲染」即可</span>
        </div>
      </div>
    </div>
  );
}
