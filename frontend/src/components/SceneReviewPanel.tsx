import { useState, useCallback, useRef, useEffect } from 'react';
import type { SceneSequence } from '../types';
import { ScenePreview } from './ScenePreview';
import { confirmReview, rejectReview, streamAiGenerateModel, type AIModelEvent } from '../services/api';

interface Props {
  sid: string;
  sequence: SceneSequence;
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
  onDone: (newPath: string) => void;
}

function AssetRegenerator({ actorId, currentAsset, onDone }: RegeneratorProps) {
  const [prompt, setPrompt] = useState(actorId.replace(/_/g, ' '));
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
      });
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
      <div className="asset-regen-info">
        <span className="asset-regen-id">🎭 {actorId}</span>
        <span className="asset-regen-status">
          {isComposite ? '🧱 积木拼装' : `🧊 外部模型: ${currentAsset?.path?.split('/').pop()}`}
        </span>
      </div>
      
      <div className="asset-regen-controls">
        <input 
          className="asset-regen-input"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
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

export function SceneReviewPanel({ sid, sequence: initialSequence, onConfirmed, onRejected }: Props) {
  const [seq, setSeq] = useState<SceneSequence>(initialSequence);
  const [loading, setLoading] = useState<'confirm' | 'reject' | null>(null);
  const [activeTab, setActiveTab] = useState<'map' | 'data' | 'assets'>('map');

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
    <div className="scene-review-overlay">
      <div className="scene-review-panel">
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
            className={`review-tab ${activeTab === 'map' ? 'active' : ''}`}
            onClick={() => setActiveTab('map')}
          >
            分镜地图
          </button>
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
          {activeTab === 'map' && (
            <div className="scene-review-map">
              <ScenePreview sequence={seq} />
              <div className="scene-review-meta-grid">
                <div className="meta-item">
                  <span className="meta-label">总时长</span>
                  <span className="meta-value">{seq.meta?.total_duration ?? '?'}s</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">演员数</span>
                  <span className="meta-value">{seq.actors?.length ?? 0}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">摄影节点</span>
                  <span className="meta-value">{seq.camera_track?.length ?? 0}</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'assets' && (
            <div className="scene-review-assets">
              <div className="review-section-hint">
                💡 如果 AI 下载或拼装的模型不满意，可以在此处输入描述重新生成专属 GLB 模型。
              </div>
              {seq.actors.map(actor => (
                <AssetRegenerator
                  key={actor.actor_id}
                  actorId={actor.actor_id}
                  currentAsset={seq.asset_manifest?.[actor.actor_id]}
                  onDone={(newUrl) => {
                    // Update asset_manifest with the new model
                    const newFilename = newUrl.split('/').pop() || '';
                    const newPath = `assets/custom/${newFilename}`;
                    setSeq(prev => ({
                      ...prev,
                      asset_manifest: {
                        ...prev.asset_manifest,
                        [actor.actor_id]: {
                          actor_id: actor.actor_id,
                          type: 'downloaded',
                          path: newPath,
                          target_size: { x: 1, y: 1, z: 1 }
                        }
                      }
                    }));
                  }}
                />
              ))}
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
