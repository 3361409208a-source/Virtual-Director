import { useState, useCallback, useRef, useEffect } from 'react';
import type { SceneSequence } from '../types';
import { confirmReview, rejectReview, streamAiGenerateModel, type AIModelEvent } from '../services/api';

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
  // Expected path format: "assets/category/filename.glb"
  // API format: "/api/models/category/filename"
  const parts = path.split('/');
  if (parts.length >= 3) {
    const cat = parts[parts.length - 2];
    const file = parts[parts.length - 1];
    return `/api/models/${cat}/${file}`;
  }
  // Fallback: if it's already a full URL
  if (path.startsWith('http') || path.startsWith('/')) return path;
  return null;
}

// ────────────────────────────────────────────────────────────────────────────
// 单个可编辑数据块
// ────────────────────────────────────────────────────────────────────────────

interface BlockProps {
  label: string;
  icon: string;
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
    if (!result.ok) {
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
          <span className="review-block-toggle">{collapsed && !editing ? '▶' : '▼'}</span>
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
  // 使用当前资产名称或 ID 作为初始描述，并去除下划线
  const initialPrompt = currentAsset?.name || safeId.replace(/_/g, ' ');
  const [prompt, setPrompt] = useState(initialPrompt);
  const [generating, setGenerating] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);

  const handleGenerate = async () => {
    if (generating) return;
    setGenerating(true);
    setLog(['🚀 开始重新建模...']);
    let tokenBuf = '';
    try {
      await streamAiGenerateModel(prompt, (ev: AIModelEvent) => {
        if (ev.step === 'token') {
          tokenBuf += ev.msg;
          setLog(prev => {
            const last = prev[prev.length - 1];
            if (last && last.startsWith('📝')) {
              return [...prev.slice(0, -1), '📝 ' + tokenBuf];
            }
            return [...prev, '📝 ' + tokenBuf];
          });
        } else if (ev.step === 'done') {
          setLog(prev => [...prev, '✅ 生成成功！']);
          if (ev.url) onDone(ev.url);
        } else if (ev.step === 'error') {
          setLog(prev => [...prev, '❌ ' + ev.msg]);
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
          <span className="asset-regen-id">🎭 {safeId}</span>
          <span className="asset-regen-status">
            {isComposite ? '🧱 积木拼装' : `🧊 外部模型: ${currentAsset?.path?.split('/').pop()}`}
          </span>
        </div>
        {!isComposite && currentAsset?.path && (
          <div className="asset-preview-container">
            {/* @ts-ignore */}
            <model-viewer
              src={getAssetUrl(currentAsset.path)}
              auto-rotate
              camera-controls
              shadow-intensity="1"
              style={{ width: '100%', height: '100%', background: '#1a1a1a', borderRadius: '4px' }}
            >
              {/* @ts-ignore */}
            </model-viewer>
          </div>
        )}
      </div>
      
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
          {generating ? '⏳ 生成中...' : '✨ AI 重新建模'}
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
            资产建模
          </button>
          <button
            className={`review-tab ${activeTab === 'data' ? 'active' : ''}`}
            onClick={() => setActiveTab('data')}
          >
            数据编辑
          </button>
        </div>

        {/* Content */}
        <div className="scene-review-content">

          {activeTab === 'assets' && (
            <div className="scene-review-assets">
              <div className="review-section-hint">
                💡 如果 AI 下载或拼装的模型不满意，可以在此处输入描述重新生成专属 GLB 模型。
              </div>
              {(seq.actors ?? []).map((actor, idx) => {
                // actors 可能用 actor_id 或 id 字段
                const aid: string = actor.actor_id ?? actor.id ?? `actor_${idx}`;
                return (
                <AssetRegenerator
                  key={aid + '_' + idx}
                  actorId={aid}
                  currentAsset={seq.asset_manifest?.[aid]}
                  model={model}
                  onDone={(newUrl) => {
                    // Update asset_manifest with the new model
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
                icon="🏗️"
                data={seq.scene_setup}
                onChange={v => update('scene_setup', v as SceneSequence['scene_setup'])}
              />
              <EditableBlock
                label="演员列表"
                icon="🎭"
                data={seq.actors}
                onChange={v => update('actors', v as SceneSequence['actors'])}
              />
              <EditableBlock
                label="演员运动轨迹"
                icon="🚶"
                data={seq.actor_tracks}
                onChange={v => update('actor_tracks', v as SceneSequence['actor_tracks'])}
              />
              <EditableBlock
                label="摄影机轨迹"
                icon="🎬"
                data={seq.camera_track}
                onChange={v => update('camera_track', v as SceneSequence['camera_track'])}
              />
              <EditableBlock
                label="资产配置 (asset_manifest)"
                icon="📦"
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
