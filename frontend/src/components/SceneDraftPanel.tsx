import { useState, useEffect } from 'react';
import type { SceneDraft } from '../services/api';
import { getSceneDraft, updateSceneDraft, confirmSceneDraft, deleteSceneDraft } from '../services/api';

interface Props {
  draftId: string | null;
  onClose: () => void;
  onConfirm: (draft: SceneDraft) => void;
}

export function SceneDraftPanel({ draftId, onClose, onConfirm }: Props) {
  const [draft, setDraft] = useState<SceneDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingActor, setEditingActor] = useState<number | null>(null);

  useEffect(() => {
    if (draftId) {
      setLoading(true);
      getSceneDraft(draftId)
        .then(setDraft)
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [draftId]);

  if (!draftId) return null;

  if (loading) return <div className="glass-panel">加载中...</div>;
  if (!draft) return <div className="glass-panel">草稿不存在</div>;

  const handleActorUpdate = (index: number, field: string, value: any) => {
    const newActors = [...draft.actors];
    newActors[index] = { ...newActors[index], [field]: value };
    setDraft({ ...draft, actors: newActors });
  };

  const handleSaveDraft = async () => {
    try {
      const updated = await updateSceneDraft(draft.draft_id, draft);
      setDraft(updated);
      alert('草稿已保存');
    } catch (e) {
      console.error('保存失败:', e);
      alert('保存失败');
    }
  };

  const handleConfirm = async () => {
    try {
      const approved = await confirmSceneDraft(draft.draft_id);
      onConfirm(approved);
    } catch (e) {
      console.error('确认失败:', e);
      alert('确认失败');
    }
  };

  const handleDelete = async () => {
    if (!confirm('确定删除此草稿？')) return;
    try {
      await deleteSceneDraft(draft.draft_id);
      onClose();
    } catch (e) {
      console.error('删除失败:', e);
      alert('删除失败');
    }
  };

  return (
    <div className="glass-panel scene-draft-panel">
      <div className="panel-header">
        <h3>🎬 场景草稿审核</h3>
        <button onClick={onClose}>✕</button>
      </div>

      <div className="draft-info">
        <div><strong>提示词：</strong>{draft.prompt}</div>
        <div><strong>状态：</strong>{draft.status}</div>
        <div><strong>创建时间：</strong>{new Date(draft.created_at).toLocaleString()}</div>
      </div>

      <div className="draft-section">
        <h4>🎭 演员 ({draft.actors.length})</h4>
        {draft.actors.map((actor, index) => (
          <div key={actor.actor_id} className="actor-card">
            <div className="actor-header">
              <strong>{actor.actor_id}</strong>
              <span className="actor-type">{actor.type}</span>
              <button onClick={() => setEditingActor(editingActor === index ? null : index)}>
                {editingActor === index ? '收起' : '编辑'}
              </button>
            </div>
            <div className="actor-model">
              <span>模型：{actor.model_filename}</span>
              <span className="model-source">{actor.model_source}</span>
            </div>
            {editingActor === index && (
              <div className="actor-editor">
                <div className="editor-row">
                  <label>位置 X:</label>
                  <input
                    type="number"
                    step="0.1"
                    value={actor.position.x}
                    onChange={(e) => handleActorUpdate(index, 'position', { ...actor.position, x: parseFloat(e.target.value) })}
                  />
                  <label>Y:</label>
                  <input
                    type="number"
                    step="0.1"
                    value={actor.position.y}
                    onChange={(e) => handleActorUpdate(index, 'position', { ...actor.position, y: parseFloat(e.target.value) })}
                  />
                  <label>Z:</label>
                  <input
                    type="number"
                    step="0.1"
                    value={actor.position.z}
                    onChange={(e) => handleActorUpdate(index, 'position', { ...actor.position, z: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="editor-row">
                  <label>旋转 X:</label>
                  <input
                    type="number"
                    step="1"
                    value={actor.rotation.x}
                    onChange={(e) => handleActorUpdate(index, 'rotation', { ...actor.rotation, x: parseFloat(e.target.value) })}
                  />
                  <label>Y:</label>
                  <input
                    type="number"
                    step="1"
                    value={actor.rotation.y}
                    onChange={(e) => handleActorUpdate(index, 'rotation', { ...actor.rotation, y: parseFloat(e.target.value) })}
                  />
                  <label>Z:</label>
                  <input
                    type="number"
                    step="1"
                    value={actor.rotation.z}
                    onChange={(e) => handleActorUpdate(index, 'rotation', { ...actor.rotation, z: parseFloat(e.target.value) })}
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="draft-section">
        <h4>🎥 相机 ({draft.cameras.length})</h4>
        {draft.cameras.map((camera) => (
          <div key={camera.id} className="camera-card">
            <strong>{camera.id}</strong>
            <div>位置: ({camera.position.x}, {camera.position.y}, {camera.position.z})</div>
            <div>旋转: ({camera.rotation.x}, {camera.rotation.y}, {camera.rotation.z})</div>
            <div>FOV: {camera.fov}</div>
          </div>
        ))}
      </div>

      <div className="draft-section">
        <h4>📝 用户备注</h4>
        <textarea
          value={draft.user_notes}
          onChange={(e) => setDraft({ ...draft, user_notes: e.target.value })}
          placeholder="添加审核意见..."
          rows={3}
        />
      </div>

      <div className="draft-actions">
        <button onClick={handleSaveDraft} className="btn-secondary">💾 保存草稿</button>
        <button onClick={handleDelete} className="btn-danger">🗑️ 删除</button>
        <button onClick={handleConfirm} className="btn-primary" disabled={draft.status !== 'draft'}>
          ✅ 确认并生成视频
        </button>
      </div>
    </div>
  );
}
