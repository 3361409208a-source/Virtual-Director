import { useState } from 'react';
import { flushSync } from 'react-dom';
import type { Message, LogEntry, SceneSequence } from './types';
import { streamGenerate, streamTestRender, projectVideoUrl } from './services/api';
import { ChatPanel } from './components/ChatPanel';
import { VideoPlayer } from './components/VideoPlayer';
import { ProjectPanel } from './components/ProjectPanel';
import { ModelLibraryPanel } from './components/ModelLibraryPanel';
import { SceneReviewPanel } from './components/SceneReviewPanel';

const WELCOME: Message = {
  id: '0',
  type: 'ai',
  text: '你好！我是练习时长两年半的个人 AI 导演助理。请告诉我你想要渲染什么画面？',
};

export type ModelSelection = 'deepseek-chat' | 'deepseek-reasoner' | 'deepseek-v4-flash' | 'deepseek-v4-pro' | 'GLM-4.7-Flash' | 'astron-code-latest';
export type RendererSelection = 'godot' | 'blender';

export default function App() {
  const [messages, setMessages]       = useState<Message[]>([WELCOME]);
  const [input, setInput]             = useState('');
  const [isRendering, setIsRendering] = useState(false);
  const [videoUrl, setVideoUrl]       = useState<string | null>(null);
  const [model, setModel]             = useState<ModelSelection>('astron-code-latest');
  const [renderer, setRenderer]       = useState<RendererSelection>('godot');
  const [isTesting, setIsTesting]     = useState(false);
  const [testMsg, setTestMsg]         = useState('');
  const [streamLog, setStreamLog]      = useState<Record<string, unknown>[]>([]);

  const [viewingProject, setViewingProject] = useState<{ id: string; videoUrl: string | null } | null>(null);

  // ── 半自动审核状态 ──────────────────────────────────────────────────────────
  const [reviewState, setReviewState] = useState<{
    sid: string;
    sequence: SceneSequence;
  } | null>(null);

  const appendEntry = (logId: string, entry: LogEntry) =>
    setMessages(prev => prev.map(m =>
      m.id === logId
        ? { ...m, entries: [...(m.entries ?? []), entry] }
        : m
    ));

  const updateLastEntry = (logId: string, step: string, msg: string) =>
    setMessages(prev => prev.map(m => {
      if (m.id !== logId) return m;
      const entries = [...(m.entries ?? [])];
      for (let i = entries.length - 1; i >= 0; i--) {
        if (entries[i].step === step) {
          entries[i] = { ...entries[i], msg, ts: Date.now() };
          return { ...m, entries };
        }
      }
      return { ...m, entries: [...entries, { step, msg, ts: Date.now() }] };
    }));

  const handleSend = async () => {
    if (!input.trim() || isRendering) return;

    const userMsg: Message = { id: Date.now().toString(), type: 'user', text: input };
    const logId             = (Date.now() + 1).toString();
    const logMsg: Message   = { id: logId, type: 'log', text: '', entries: [] };

    setMessages(prev => [...prev, userMsg, logMsg]);
    setInput('');
    setIsRendering(true);
    setVideoUrl(null);
    setViewingProject(null);
    setStreamLog([]);
    setReviewState(null);

    try {
      await streamGenerate(input, event => {
        if (event.step === 'rendering') {
          updateLastEntry(logId, 'rendering', event.msg);
        } else if (event.step !== 'stream') {
          appendEntry(logId, { step: event.step, msg: event.msg, ts: Date.now() });
        }
        const raw = event as unknown as Record<string, unknown>;
        if (raw.step === 'stream') {
          flushSync(() => {
            setStreamLog(prev => {
              const idx = prev.findIndex(e => e.step === 'stream' && e.agent === raw.agent);
              if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = { ...updated[idx], msg: String(updated[idx].msg ?? '') + String(raw.msg ?? '') };
                return updated;
              }
              return [...prev, raw];
            });
          });
        } else {
          setStreamLog(prev => [...prev, raw]);
        }

        // ── 半自动：收到 scene_preview 后进入审核等待模式 ──────────────────
        if (event.step === 'scene_preview' && event.sequence && event.review_sid) {
          setReviewState({ sid: event.review_sid, sequence: event.sequence });
          // isRendering 保持 true，让 VideoPlayer 继续显示进度（但实际挂起等用户确认）
        }

        if (event.step === 'done') {
          if (event.video_url) setVideoUrl(event.video_url);
          setIsRendering(false);
          setReviewState(null);
        } else if (event.step === 'error') {
          setIsRendering(false);
          setReviewState(null);
        }
      }, model, renderer);
    } catch (err: unknown) {
      appendEntry(logId, {
        step: 'error',
        msg: `❌ 出错了：${err instanceof Error ? err.message : String(err)}`,
        ts: Date.now(),
      });
      setIsRendering(false);
      setReviewState(null);
    }
  };

  return (
    <div className="app-container">
      <ChatPanel
        messages={messages}
        input={input}
        isRendering={isRendering}
        model={model}
        renderer={renderer}
        onInputChange={setInput}
        onSend={handleSend}
        onModelChange={setModel}
        onRendererChange={setRenderer}
        isTesting={isTesting}
        testMsg={testMsg}
        onTestRender={async (r) => {
          setIsTesting(true);
          setTestMsg('');
          setVideoUrl(null);
          try {
            await streamTestRender(r, ev => {
              setTestMsg(ev.msg);
              if (ev.step === 'test_done') {
                if ((ev as unknown as Record<string, unknown>).video_url) setVideoUrl(`http://localhost:8000/api/test-video/${r}?t=${Date.now()}`);
                setIsTesting(false);
              } else if (ev.step === 'test_error') {
                setIsTesting(false);
              }
            });
          } catch (e) {
            setTestMsg(`❌ 请求失败: ${e instanceof Error ? e.message : String(e)}`);
            setIsTesting(false);
          }
        }}
      />
      <VideoPlayer videoUrl={viewingProject?.videoUrl ?? videoUrl} isRendering={isRendering && !reviewState} streamLog={streamLog} />
      <ProjectPanel
        activeProjectId={viewingProject?.id ?? null}
        onSelectProject={(pid) => {
          if (pid) {
            setViewingProject({ id: pid, videoUrl: projectVideoUrl(pid) });
          } else {
            setViewingProject(null);
          }
        }}
      />
      <ModelLibraryPanel />

      {/* 半自动审核面板：覆盖整个界面，等待用户操作 */}
      {reviewState && (
        <SceneReviewPanel
          sid={reviewState.sid}
          sequence={reviewState.sequence}
          onConfirmed={() => {
            // 告知用户已确认，UI 恢复渲染等待状态
            setReviewState(null);
          }}
          onRejected={() => {
            setReviewState(null);
            setIsRendering(false);
          }}
        />
      )}
    </div>
  );
}
