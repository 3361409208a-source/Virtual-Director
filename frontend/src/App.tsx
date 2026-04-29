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
export type ViewMode = 'director' | 'modeling' | 'library';

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
  const [view, setView] = useState<ViewMode>('director');

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
          setStreamLog(prev => {
            const idx = prev.findIndex(e => e.step === 'stream' && e.agent === raw.agent);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = { ...updated[idx], msg: String(updated[idx].msg ?? '') + String(raw.msg ?? '') };
              return updated;
            }
            return [...prev, raw];
          });
        } else {
          setStreamLog(prev => [...prev, raw]);
        }

        // ── 半自动：收到 scene_preview 后进入审核等待模式 ──────────────────
        if (event.step === 'scene_preview' && event.sequence && event.review_sid) {
          setReviewState({ sid: event.review_sid, sequence: event.sequence });
          setView('modeling'); // 自动跳转到建模页面
        }

        if (event.step === 'done') {
          if (event.video_url) setVideoUrl(event.video_url);
          setIsRendering(false);
          setReviewState(null);
          setView('director'); // 完成后回到导演页面
        } else if (event.step === 'error') {
          setIsRendering(false);
          setReviewState(null);
          setView('director');
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
    <div className="app-layout">
      {/* 侧边导航栏 */}
      <nav className="side-nav">
        <div className="nav-logo">🎬</div>
        <button className={`nav-item ${view === 'director' ? 'active' : ''}`} onClick={() => setView('director')} title="导演中心">
          <span className="nav-icon">📽️</span>
          <span className="nav-label">导演</span>
        </button>
        <button className={`nav-item ${view === 'modeling' ? 'active' : ''}`} onClick={() => setView('modeling')} title="AI 建模">
          <span className="nav-icon">🎨</span>
          <span className="nav-label">建模</span>
        </button>
        <button className={`nav-item ${view === 'library' ? 'active' : ''}`} onClick={() => setView('library')} title="资产库">
          <span className="nav-icon">📦</span>
          <span className="nav-label">资产</span>
        </button>
      </nav>

      <main className="main-stage">
        {view === 'director' && (
          <div className="director-view">
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
            <div className="center-content">
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
            </div>
          </div>
        )}

        {view === 'modeling' && (
          <div className="modeling-view">
            {reviewState ? (
              <SceneReviewPanel
                key={reviewState.sid}
                sid={reviewState.sid}
                sequence={reviewState.sequence}
                model={model}
                onConfirmed={() => {
                  setReviewState(null);
                  // 后端会自动继续，这里我们回到导演页面看进度
                  setView('director');
                }}
                onRejected={() => {
                  setReviewState(null);
                  setIsRendering(false);
                  setView('director');
                }}
              />
            ) : (
              <div className="modeling-placeholder">
                <div className="placeholder-content">
                  <span className="placeholder-icon">🎨</span>
                  <h2>AI 建模工作室</h2>
                  <p>当前没有正在进行的建模任务。请在导演中心发起新的创作请求。</p>
                  <button className="go-home-btn" onClick={() => setView('director')}>回到导演中心</button>
                </div>
              </div>
            )}
          </div>
        )}

        {view === 'library' && (
          <div className="library-view">
             <ModelLibraryPanel isStandalone={true} />
          </div>
        )}
      </main>
    </div>
  );
}
