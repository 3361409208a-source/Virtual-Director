import { useRef, useEffect } from 'react';
import type { Message } from '../types';
import { WorkflowLog } from './WorkflowLog';

type Model = 'deepseek-chat' | 'deepseek-reasoner';

interface Props {
  messages: Message[];
  input: string;
  isRendering: boolean;
  model: Model;
  onInputChange: (val: string) => void;
  onSend: () => void;
  onModelChange: (m: Model) => void;
}

const MODEL_LABELS: Record<Model, { short: string; desc: string }> = {
  'deepseek-chat':     { short: 'V3',  desc: '快速 · 适合常规场景' },
  'deepseek-reasoner': { short: 'R1',  desc: '深度推理 · 复杂场景更准确' },
};

export function ChatPanel({ messages, input, isRendering, model, onInputChange, onSend, onModelChange }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const toggleModel = () =>
    onModelChange(model === 'deepseek-chat' ? 'deepseek-reasoner' : 'deepseek-chat');

  return (
    <div className="glass-panel chat-section">
      <div className="header">
        <h1>Virtual Director</h1>
        <p>AI-Powered Godot Production</p>
      </div>

      <div className="chat-history">
        {messages.map(msg =>
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
        <button
          className="model-toggle"
          onClick={toggleModel}
          disabled={isRendering}
          title={MODEL_LABELS[model].desc}
        >
          <span className="model-badge">{MODEL_LABELS[model].short}</span>
          <span className="model-name">{model === 'deepseek-chat' ? 'DeepSeek-V3' : 'DeepSeek-R1'}</span>
        </button>
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
