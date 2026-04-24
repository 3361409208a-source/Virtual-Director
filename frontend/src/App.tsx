import { useState } from 'react';
import type { Message, LogEntry, SceneSequence } from './types';
import { streamGenerate, projectVideoUrl } from './services/api';
import { ChatPanel } from './components/ChatPanel';
import { VideoPlayer } from './components/VideoPlayer';
import { ProjectPanel } from './components/ProjectPanel';

const WELCOME: Message = {
  id: '0',
  type: 'ai',
  text: '你好！我是练习时长两年半的个人 AI 导演助理。请告诉我你想要渲染什么画面？',
};

export type ModelSelection = 'deepseek-chat' | 'deepseek-reasoner' | 'deepseek-v4-flash' | 'deepseek-v4-pro' | 'GLM-4.7-Flash';

export default function App() {
  const [messages, setMessages]       = useState<Message[]>([WELCOME]);
  const [input, setInput]             = useState('');
  const [isRendering, setIsRendering] = useState(false);
  const [videoUrl, setVideoUrl]       = useState<string | null>(null);
  const [sequence, setSequence]       = useState<SceneSequence | null>(null);
  const [model, setModel]             = useState<ModelSelection>('deepseek-v4-flash');

  const [viewingProject, setViewingProject] = useState<{ id: string; videoUrl: string | null; sequence: SceneSequence | null } | null>(null);

  const appendEntry = (logId: string, entry: LogEntry) =>
    setMessages(prev => prev.map(m =>
      m.id === logId
        ? { ...m, entries: [...(m.entries ?? []), entry] }
        : m
    ));

  const handleSend = async () => {
    if (!input.trim() || isRendering) return;

    const userMsg: Message = { id: Date.now().toString(), type: 'user', text: input };
    const logId             = (Date.now() + 1).toString();
    const logMsg: Message   = { id: logId, type: 'log', text: '', entries: [] };

    setMessages(prev => [...prev, userMsg, logMsg]);
    setInput('');
    setIsRendering(true);
    setVideoUrl(null);
    setSequence(null);
    setViewingProject(null);

    try {
      await streamGenerate(input, event => {
        appendEntry(logId, { step: event.step, msg: event.msg, ts: Date.now() });
        if (event.step === 'scene_preview' && event.sequence) {
          setSequence(event.sequence);
        } else if (event.step === 'done') {
          if (event.video_url) setVideoUrl(event.video_url);
          setIsRendering(false);
        } else if (event.step === 'error') {
          setIsRendering(false);
        }
      }, model);
    } catch (err: unknown) {
      appendEntry(logId, {
        step: 'error',
        msg: `❌ 出错了：${err instanceof Error ? err.message : String(err)}`,
        ts: Date.now(),
      });
      setIsRendering(false);
    }
  };

  return (
    <div className="app-container">
      <ChatPanel
        messages={messages}
        input={input}
        isRendering={isRendering}
        model={model}
        onInputChange={setInput}
        onSend={handleSend}
        onModelChange={setModel}
      />
      <VideoPlayer videoUrl={viewingProject?.videoUrl ?? videoUrl} isRendering={isRendering} sequence={viewingProject?.sequence ?? sequence} />
      <ProjectPanel
        activeProjectId={viewingProject?.id ?? null}
        onSelectProject={(pid, seq) => {
          if (pid) {
            setViewingProject({ id: pid, videoUrl: projectVideoUrl(pid), sequence: seq });
          } else {
            setViewingProject(null);
          }
        }}
      />
    </div>
  );
}

