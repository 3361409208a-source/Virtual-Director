import { useRef, useEffect, useState } from 'react';
import type { Message } from '../types';
import { WorkflowLog } from './WorkflowLog';
import { getConfig, updateConfig } from '../services/api';

import type { ModelSelection, RendererSelection } from '../App';

interface Props {
  messages: Message[];
  input: string;
  isRendering: boolean;
  model: ModelSelection;
  renderer: RendererSelection;
  isTesting: boolean;
  testMsg: string;
  onInputChange: (val: string) => void;
  onSend: () => void;
  onModelChange: (m: ModelSelection) => void;
  onRendererChange: (r: RendererSelection) => void;
  onTestRender: (r: RendererSelection) => void;
}

const MODEL_LABELS: Record<ModelSelection, { short: string; desc: string; name: string }> = {
  'deepseek-chat':     { short: 'V3',  name: 'DeepSeek V3 (经典)', desc: '快速 · 适合常规场景' },
  'deepseek-reasoner': { short: 'R1',  name: 'DeepSeek R1 (经典)', desc: '深度推理 · 复杂场景更准确' },
  'deepseek-v4-flash': { short: 'V4',  name: 'DeepSeek V4 Flash', desc: '最新旗舰 · 极速生成' },
  'deepseek-v4-pro':   { short: 'PRO', name: 'DeepSeek V4 Pro',   desc: '深度思考 · 逻辑大师' },
  'GLM-4.7-Flash':     { short: 'GLM', name: 'GLM-4.7-Flash',     desc: '模力方舟 · 智谱轻快模型' },
  'astron-code-latest': { short: 'ASTR', name: 'Astron Code',       desc: '阿里云 Maas · 代码生成专家' },
};

export function ChatPanel({ messages, input, isRendering, model, renderer, isTesting, testMsg, onInputChange, onSend, onModelChange, onRendererChange, onTestRender }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [enableModelSearch, setEnableModelSearch] = useState(true);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    getConfig().then(config => setEnableModelSearch(config.enable_model_search)).catch(console.error);
  }, []);

  const toggleModelSearch = async () => {
    const newValue = !enableModelSearch;
    try {
      const config = await updateConfig({ enable_model_search: newValue });
      setEnableModelSearch(config.enable_model_search);
    } catch (e) {
      console.error('Failed to update config:', e);
    }
  };

  return (
    <div className="glass-panel chat-section">
      <div className="header">
        <h2>🎬 导演意图分析</h2>
        <div className="model-select-wrap">
          <select 
            className={`model-select model-${model}`}
            value={model} 
            onChange={(e) => onModelChange(e.target.value as ModelSelection)}
            disabled={isRendering}
            title={MODEL_LABELS[model]?.desc || '选择模型'}
          >
            {Object.entries(MODEL_LABELS).map(([key, info]) => (
              <option key={key} value={key}>
                {info.short} | {info.name}
              </option>
            ))}
          </select>
        </div>
        <div className="renderer-toggle">
          <button
            className={`renderer-btn ${renderer === 'godot' ? 'active' : ''}`}
            onClick={() => onRendererChange('godot')}
            disabled={isRendering}
            title="Godot 4 实时渲染"
          >Godot</button>
          <button
            className={`renderer-btn ${renderer === 'blender' ? 'active' : ''}`}
            onClick={() => onRendererChange('blender')}
            disabled={isRendering || isTesting}
            title="Blender Cycles CPU 渲染"
          >Blender</button>
        </div>
        <div className="model-search-toggle">
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={enableModelSearch}
              onChange={toggleModelSearch}
              disabled={isRendering}
            />
            <span className="toggle-slider"></span>
            <span className="toggle-label">{enableModelSearch ? '🔍 搜索模型' : '🧱 AI建模'}</span>
          </label>
        </div>
        <button
          className={`test-render-btn ${isTesting ? 'testing' : ''}`}
          onClick={() => onTestRender(renderer)}
          disabled={isRendering || isTesting}
          title={`测试 ${renderer} 渲染器（跳过AI，直接渲染最小场景）`}
        >
          {isTesting ? '⏳ 测试中...' : '🧪 测试渲染'}
        </button>
        {testMsg && <div className="test-msg">{testMsg}</div>}
      </div>

      <div className="chat-history">
        {messages.map((msg) =>
          msg.type === 'log' ? (
            <div key={msg.id} className="message ai">
              <WorkflowLog entries={msg.entries ?? []} />
            </div>
          ) : (
            <div key={msg.id} className={`message ${msg.type}`}>
              {msg.text}
            </div>
          )
        )}
        <div ref={bottomRef} />
      </div>

      <div className="input-area">
        <input
          type="text"
          placeholder="输入导演意图..."
          value={input}
          onChange={e => onInputChange(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && onSend()}
          disabled={isRendering}
        />
        <button onClick={onSend} disabled={isRendering}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  );
}
