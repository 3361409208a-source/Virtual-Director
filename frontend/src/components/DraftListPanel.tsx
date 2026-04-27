import { useState, useEffect } from 'react';
import { listSceneDrafts, deleteSceneDraft } from '../services/api';
import type { SceneDraft } from '../services/api';

interface Props {
  onSelectDraft: (draftId: string) => void;
}

export function DraftListPanel({ onSelectDraft }: Props) {
  const [drafts, setDrafts] = useState<SceneDraft[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadDrafts();
  }, []);

  const loadDrafts = async () => {
    setLoading(true);
    try {
      const data = await listSceneDrafts();
      setDrafts(data);
    } catch (e) {
      console.error('加载草稿列表失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (draftId: string) => {
    if (!confirm('确定删除此草稿？')) return;
    try {
      await deleteSceneDraft(draftId);
      loadDrafts();
    } catch (e) {
      console.error('删除失败:', e);
      alert('删除失败');
    }
  };

  return (
    <div className="glass-panel draft-list-panel">
      <div className="panel-header">
        <h3>📝 场景草稿列表</h3>
        <button onClick={loadDrafts}>🔄 刷新</button>
      </div>
      {loading ? (
        <div>加载中...</div>
      ) : drafts.length === 0 ? (
        <div>暂无草稿</div>
      ) : (
        <div className="draft-list">
          {drafts.map((draft) => (
            <div key={draft.draft_id} className="draft-item">
              <div className="draft-item-header">
                <strong>{draft.prompt.substring(0, 30)}...</strong>
                <span className={`draft-status draft-${draft.status}`}>
                  {draft.status === 'draft' ? '待审核' : draft.status === 'approved' ? '已确认' : '已拒绝'}
                </span>
              </div>
              <div className="draft-item-info">
                <div>创建时间: {new Date(draft.created_at).toLocaleString()}</div>
                <div>演员数: {draft.actors.length}</div>
              </div>
              <div className="draft-item-actions">
                <button onClick={() => onSelectDraft(draft.draft_id)} className="btn-secondary">查看/编辑</button>
                <button onClick={() => handleDelete(draft.draft_id)} className="btn-danger">删除</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
