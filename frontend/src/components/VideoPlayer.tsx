import { useEffect, useRef } from 'react';

interface Props {
  videoUrl: string | null;
  isRendering: boolean;
  streamLog?: Record<string, unknown>[];
}

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

export function VideoPlayer({ videoUrl, isRendering, streamLog = [] }: Props) {
  return (
    <div className="glass-panel video-section">
      <div className="video-container">
        {videoUrl ? (
          <video src={videoUrl} controls autoPlay loop />
        ) : isRendering ? (
          <StreamLog events={streamLog} />
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
