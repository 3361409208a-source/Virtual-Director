import { useState, useEffect, useRef } from 'react';

interface Props {
  videoUrl: string | null;
  isRendering: boolean;
  currentStep: string;
  currentMsg: string;
  streamLog?: Record<string, unknown>[];
}

// ── Step metadata ────────────────────────────────────────────────────────────
const STEP_META: Record<string, { label: string; mood: string; progress: number; icon: string }> = {
  director:       { label: '总导演正在开会',   mood: '讨论爆炸要大还是更大',       progress: 8,  icon: '🎯' },
  director_done:  { label: '导演拍板了',       mood: '五个 AI 组收到传呼机振动',    progress: 14, icon: '📟' },
  workers:        { label: '五路并发，齐头并进', mood: '这才叫真正的多线程人生',     progress: 20, icon: '⚡' },
  asset_progress: { label: 'AI 积木师在拼模型', mood: '认真用 sphere 替代了那个方块地球', progress: 32, icon: '🧱' },
  scene_done:     { label: '布景完工',         mood: '灯光师表示今天的太阳角度很满意',  progress: 38, icon: '🏗️' },
  actor_done:     { label: '演员就位',         mood: '关键帧已安排，缓入缓出有品位',   progress: 44, icon: '🎭' },
  camera_done:    { label: '摄影机对好焦',     mood: '180° 法则已遵守（这次）',      progress: 50, icon: '🎬' },
  physics_done:   { label: '物理引擎就绪',     mood: '重力已校准，东西该掉就掉',      progress: 54, icon: '🍎' },
  asset_done:     { label: '模型图纸交付',     mood: '地球终于是球了',              progress: 58, icon: '🌍' },
  merge:          { label: '五路数据合流',     mood: '有点像五个厨师在挤同一扇门',    progress: 63, icon: '�' },
  merge_done:     { label: '剧本杀完成',       mood: '每帧都知道自己该干嘛了',       progress: 68, icon: '�' },
  scene_preview:  { label: '分镜图出炉',       mood: '渲染倒计时：3、2、1…',        progress: 72, icon: '🎞️' },
  cover:          { label: '封面设计中',       mood: 'Kolors 在努力画一张好看的图',  progress: 76, icon: '🎨' },
  rendering:      { label: '渲染农场开机',     mood: '光子们正在讨论加班费',         progress: 82, icon: '🖥️' },
  rendering_done: { label: '渲染杀青',         mood: '每一帧都很辛苦，请珍惜观看',   progress: 92, icon: '🎊' },
  converting:     { label: '封装进母带',       mood: 'ffmpeg 正在打包行李',         progress: 95, icon: '�' },
};

// 导演语录，每隔几秒轮换
const DIRECTOR_QUOTES = [
  '「再来一条！不对，就这条！」— AI 导演，永远如此',
  '「这个爆炸能再大一点吗？预算不够？我们是 AI，没有预算！」',
  '「摄影机再往左 0.1°…好，回来。再往左。完美。」',
  '「本剧组没有 NG，只有意外收获。」',
  '「光线不对，重来。演员不对，重来。地球是方的，重来。」',
  '「温馨提示：爆米花自备，本 AI 不负责零食。」',
  '「五路 AI 同时工作 > 一个人类剧组忙三年。」',
  '「用量子纠缠技术确保每帧的情感真实性（开玩笑的）。」',
  '「GPU：这活儿比挖矿还累。导演：继续。」',
  '「场景已渲染 42 帧，离宇宙真理还差 83 帧。」',
];

// ── Stream Log ───────────────────────────────────────────────────────────────
const SKIP_KEYS = new Set(['step', 'msg']);

function StreamLog({ events }: { events: Record<string, unknown>[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  return (
    <div className="stream-log">
      {events.map((ev, idx) => {
        const step = String(ev.step ?? '');
        const msg  = String(ev.msg ?? '');
        const extras = Object.entries(ev).filter(([k]) => !SKIP_KEYS.has(k));
        if (step === 'stream') {
          const agent = String(ev.agent ?? '');
          const tail = msg.length > 300 ? '…' + msg.slice(-300) : msg;
          return (
            <div key={idx} className="stream-log-entry step-stream">
              <span className="stream-log-step stream-agent">{agent}</span>
              <span className="stream-log-chars">{msg.length}字</span>
              <span className="stream-log-token">{tail}</span>
            </div>
          );
        }
        return (
          <div key={idx} className={`stream-log-entry step-${step}`}>
            <span className="stream-log-step">{step}</span>
            <span className="stream-log-msg">{msg}</span>
            {extras.map(([k, v]) => (
              <div key={k} className="stream-log-field">
                <span className="stream-log-key">{k}:</span>
                <span className="stream-log-val">
                  {typeof v === 'object' ? JSON.stringify(v, null, 0) : String(v)}
                </span>
              </div>
            ))}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}

function RenderingOverlay({ step, msg }: { step: string; msg: string }) {
  const meta = STEP_META[step] ?? {
    label: 'AI 热身中', mood: '多智能体流水线正在启动…', progress: 3, icon: '✨',
  };

  const [quoteIdx, setQuoteIdx] = useState(() => Math.floor(Math.random() * DIRECTOR_QUOTES.length));
  const [quoteVisible, setQuoteVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setQuoteVisible(false);
      setTimeout(() => {
        setQuoteIdx(i => (i + 1) % DIRECTOR_QUOTES.length);
        setQuoteVisible(true);
      }, 400);
    }, 4200);
    return () => clearInterval(interval);
  }, []);

  const stages = [
    { key: 'director',  label: '导演' },
    { key: 'workers',   label: '制作' },
    { key: 'merge',     label: '合成' },
    { key: 'rendering', label: '渲染' },
  ];
  const activeStageIdx = stages.findIndex(s => meta.progress >= (STEP_META[s.key]?.progress ?? 0));

  return (
    <div className="render-overlay">
      <div className="render-overlay-body">
        {/* Icon */}
        <div className="render-icon-wrap">
          <span className="render-icon-emoji">{meta.icon}</span>
        </div>

        {/* Step label + mood */}
        <div className="render-step-label">{meta.label}</div>
        <div className="render-mood">{meta.mood}</div>

        {/* Live render progress message */}
        {step === 'rendering' && msg && (
          <div className="render-render-msg">
            {msg.replace('🎬 [渲染农场] ', '')}
          </div>
        )}

        {/* Thin progress bar */}
        <div className="render-progress-wrap">
          <div className="render-progress-bar" style={{ width: `${meta.progress}%` }} />
        </div>
        <div className="render-progress-pct">{meta.progress}%</div>

        {/* Stage dots */}
        <div className="render-stages">
          {stages.map((s, i) => (
            <div key={s.key} className="render-stage-item">
              <div className={`render-stage-dot ${i < activeStageIdx ? 'done' : i === activeStageIdx ? 'active' : ''}`} />
              <span className={`render-stage-name ${i === activeStageIdx ? 'active' : i < activeStageIdx ? 'done' : ''}`}>{s.label}</span>
            </div>
          ))}
        </div>

        {/* Quote */}
        <div className={`render-quote ${quoteVisible ? 'visible' : ''}`}>
          {DIRECTOR_QUOTES[quoteIdx]}
        </div>
      </div>
    </div>
  );
}

export function VideoPlayer({ videoUrl, isRendering, currentStep, currentMsg, streamLog = [] }: Props) {
  return (
    <div className="glass-panel video-section">
      <div className="video-container">
        {videoUrl ? (
          <video src={videoUrl} controls autoPlay loop />
        ) : isRendering ? (
          <div className="rendering-split">
            <RenderingOverlay step={currentStep} msg={currentMsg} />
            <StreamLog events={streamLog} />
          </div>
        ) : (
          <div className="placeholder-content">
            <div className="placeholder-icon">🎬</div>
            <p>等待导演下达指令</p>
          </div>
        )}
      </div>
    </div>
  );
}
