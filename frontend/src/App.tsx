import { useState, useEffect } from 'react';
import type { Message, LogEntry, SceneSequence } from './types';
import { streamGenerate, streamTestRender, projectVideoUrl } from './services/api';
import { ChatPanel } from './components/ChatPanel';
import { VideoPlayer } from './components/VideoPlayer';
import { ProjectPanel } from './components/ProjectPanel';
import { ModelLibraryPanel } from './components/ModelLibraryPanel';
import { SceneReviewPanel } from './components/SceneReviewPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { settingsStore } from './services/settingsStore';

const WELCOME: Message = {
  id: '0',
  type: 'ai',
  text: '你好！我是练习时长两年半的个人 AI 导演助理。请告诉我你想要渲染什么画面？',
};

export type ModelSelection = 'deepseek-chat' | 'deepseek-reasoner' | 'deepseek-v4-flash' | 'deepseek-v4-pro' | 'GLM-4.7-Flash' | 'Kimi-K2.6' | 'astron-code-latest';
export type RendererSelection = 'godot' | 'blender';
export type ViewMode = 'director' | 'modeling' | 'library' | 'settings';

// ── Icons ──────────────────────────────────────────────────────────────────
const IconDirector = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 21V3"/></svg>;
const IconModeling = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/></svg>;
const IconBox = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>;
const IconLogo = () => <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>;
const IconSettings = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h1.56a2 2 0 0 1 1.91 1.44l.36 1.2a1 1 0 0 0 1.18.72l1.24-.27a2 2 0 0 1 2.22.99l.78 1.35a2 2 0 0 1-.44 2.39l-.91.83a1 1 0 0 0 0 1.36l.91.83a2 2 0 0 1 .44 2.39l-.78 1.35a2 2 0 0 1-2.22.99l-1.24-.27a1 1 0 0 0-1.18.72l-.36 1.2a2 2 0 0 1-1.91 1.44h-1.56a2 2 0 0 1-1.91-1.44l-.36-1.2a1 1 0 0 0-1.18-.72l-1.24.27a2 2 0 0 1-2.22-.99l-.78-1.35a2 2 0 0 1 .44-2.39l.91-.83a1 1 0 0 0 0-1.36l-.91-.83a2 2 0 0 1-.44-2.39l.78-1.35a2 2 0 0 1 2.22-.99l1.24.27a1 1 0 0 0 1.18-.72l.36-1.2A2 2 0 0 1 12.22 2z"/><circle cx="12" cy="12" r="3"/></svg>;

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
  const [currentTokens, setCurrentTokens] = useState<{ input: number; output: number } | undefined>(undefined);

  const [viewingProject, setViewingProject] = useState<{ id: string; videoUrl: string | null } | null>(null);
  const [view, setView] = useState<ViewMode>('director');

  // Keep model and renderer state when switching views
  const [savedModel, setSavedModel] = useState<ModelSelection>(settingsStore.getSettings().directorModel);
  const [savedRenderer, setSavedRenderer] = useState<RendererSelection>(settingsStore.getSettings().renderer);
  
  // Sync state with settings store
  useEffect(() => {
    const s = settingsStore.getSettings();
    setModel(s.directorModel);
    setRenderer(s.renderer);
    return settingsStore.subscribe(() => {
       const ns = settingsStore.getSettings();
       setModel(ns.directorModel);
       setRenderer(ns.renderer);
    });
  }, []);

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

        // Update token usage when we get token info
        if (event.tokens) {
          setCurrentTokens(event.tokens);
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
      }, model, renderer, settingsStore.getSettings().workerModel);
    } catch (err: unknown) {
      appendEntry(logId, {
        step: 'error',
        msg: `出错了：${err instanceof Error ? err.message : String(err)}`,
        ts: Date.now(),
      });
      setIsRendering(false);
      setReviewState(null);
    }
  };

  const handleViewChange = (newView: ViewMode) => {
    // Save current model and renderer before switching
    if (view !== newView) {
      if (view === 'director') {
        setSavedModel(model);
        setSavedRenderer(renderer);
      } else if (view === 'modeling' || view === 'library') {
        // Restore saved model and renderer
        setModel(savedModel);
        setRenderer(savedRenderer);
      }
    }
    setView(newView);
  };

  return (
    <div className="app-layout">
      {/* 侧边导航栏 */}
      <nav className="side-nav">
        <div className="nav-logo"><IconLogo /></div>
        <button className={`nav-item ${view === 'director' ? 'active' : ''}`} onClick={() => handleViewChange('director')} title="导演中心">
          <span className="nav-icon"><IconDirector /></span>
          <span className="nav-label">导演</span>
        </button>
        <button className={`nav-item ${view === 'modeling' ? 'active' : ''}`} onClick={() => handleViewChange('modeling')} title="AI 建模">
          <span className="nav-icon"><IconModeling /></span>
          <span className="nav-label">建模</span>
        </button>
        <button className={`nav-item ${view === 'library' ? 'active' : ''}`} onClick={() => handleViewChange('library')} title="资产库">
          <span className="nav-icon"><IconBox /></span>
          <span className="nav-label">资产</span>
        </button>
        <div style={{ flex: 1 }} />
        <button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => handleViewChange('settings')} title="设置">
          <span className="nav-icon"><IconSettings /></span>
          <span className="nav-label">设置</span>
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
                  setTestMsg(`❌ 请求失败：${e instanceof Error ? e.message : String(e)}`);
                  setIsTesting(false);
                }
              }}
              currentTokens={currentTokens}
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
                  setView('director');
                }}
                onRejected={() => {
                  setReviewState(null);
                  setIsRendering(false);
                  setView('director');
                }}
              />
            ) : (
              <ModelLibraryPanel isStandalone={true} initialTab="ai" />
            )}
          </div>
        )}

        {view === 'library' && (
          <div className="library-view">
            <ModelLibraryPanel isStandalone={true} initialTab="library" />
          </div>
        )}
        
        {view === 'settings' && (
          <div className="settings-view">
            <SettingsPanel />
          </div>
        )}
      </main>
    </div>
  );
}
