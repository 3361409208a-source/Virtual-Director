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
  currentTokens?: { input: number; output: number };
}

const MODEL_LABELS: Record<ModelSelection, { short: string; desc: string; name: string }> = {
  'deepseek-chat':     { short: 'V3',  name: 'DeepSeek V3 (经典)', desc: '快速 · 适合常规场景' },
  'deepseek-reasoner': { short: 'R1',  name: 'DeepSeek R1 (经典)', desc: '深度推理 · 复杂场景更准确' },
  'deepseek-v4-flash': { short: 'V4',  name: 'DeepSeek V4 Flash', desc: '最新旗舰 · 极速生成' },
  'deepseek-v4-pro':   { short: 'PRO', name: 'DeepSeek V4 Pro',   desc: '深度思考 · 逻辑大师' },
  'GLM-4.7-Flash':     { short: 'GLM', name: 'GLM-4.7-Flash',     desc: '模力方舟 · 智谱轻快模型' },
  'astron-code-latest': { short: 'ASTR', name: 'Astron Code',       desc: '阿里云 Maas · 代码生成专家' },
};

// ── Icons ──────────────────────────────────────────────────────────────────
const IconChart = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>;
const IconDownload = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>;
const IconUpload = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>;
const IconDirector = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>;
const IconSearch = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>;
const IconBox = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>;
const IconTest = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 2v7.5"/><path d="M14 2v7.5"/><path d="M8.5 2h7"/><path d="M14 22H10c-1.1 0-2-.9-2-2V9.5C8 8.12 9.12 7 10.5 7h3c1.38 0 2.5 1.12 2.5 2.5V20c0 1.1-.9 2-2 2z"/></svg>;

export function ChatPanel({ messages, input, isRendering, model, renderer, isTesting, testMsg, onInputChange, onSend, onModelChange, onRendererChange, onTestRender, currentTokens }: Props) {
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

  const formatTokens = (tokens?: { input: number; output: number }) => {
    if (!tokens) return '0';
    const total = tokens.input + tokens.output;
    return total.toLocaleString();
  };

  const tokenDisplay = currentTokens ? (
    <span className="token-usage">
      <IconChart /> {formatTokens(currentTokens)} tokens
      <span className="token-breakdown">
        (<IconDownload /> {currentTokens.input.toLocaleString()} + <IconUpload /> {currentTokens.output.toLocaleString()})
      </span>
    </span>
  ) : null;

  return (
    <div className="glass-panel chat-section">
      <div className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <IconDirector />
          <h2 style={{ fontSize: 16, margin: 0 }}>导演意图分析</h2>
        </div>
        <div className="model-info">
          {tokenDisplay}
          <span className="model-name">{MODEL_LABELS[model]?.name}</span>
        </div>
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
            <span className="toggle-label">
              {enableModelSearch ? <><IconSearch /> 搜索模式</> : <><IconBox /> 建模模式</>}
            </span>
          </label>
        </div>
        <button
          className={`test-render-btn ${isTesting ? 'testing' : ''}`}
          onClick={() => onTestRender(renderer)}
          disabled={isRendering || isTesting}
          title={`测试 ${renderer} 渲染器（跳过AI，直接渲染最小场景）`}
        >
          {isTesting ? '⏳ 测试中...' : <><IconTest /> 测试渲染</>}
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
