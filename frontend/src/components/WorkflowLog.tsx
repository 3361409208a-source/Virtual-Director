import { useState, useEffect } from 'react';
import type { LogEntry } from '../types';

interface Props {
  entries: LogEntry[];
}

// Phase definition — groups steps into labelled sections
const PHASES = [
  { label: '总导演 · 剧本分析',       match: (s: string) => s.startsWith('director') },
  { label: '工作组 · 并行制作',       match: (s: string) => ['workers','scene_done','actor_done','camera_done','physics_done','asset_done','asset_progress','asset_searching'].includes(s) },
  { label: '后期合成 · 数据整合',     match: (s: string) => s.startsWith('merge') },
  { label: '渲染农场 · 引擎输出',     match: (s: string) => s.startsWith('rendering') },
  { label: '输出压制 · 母带生成',     match: (s: string) => ['converting','done'].includes(s) },
];

function stepIcon(step: string, isLast: boolean): string {
  if (step === 'error')              return '❌';
  if (step === 'done')               return '🎥';
  if (step.endsWith('_done'))        return '✅';
  if (isLast)                        return '⏳';
  return '▸';
}

function elapsed(a: number, b: number): string {
  const s = ((b - a) / 1000).toFixed(1);
  return `${s}s`;
}

function phaseFor(step: string): number {
  return PHASES.findIndex(p => p.match(step));
}

export function WorkflowLog({ entries }: Props) {
  const [now, setNow] = useState(Date.now());

  const active = entries[entries.length - 1];
  const isDone = !active || active.step === 'done' || active.step === 'error';

  // Tick every 200ms while still in progress
  useEffect(() => {
    if (isDone) return;
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, [isDone]);

  if (entries.length === 0) return null;

  const firstTs   = entries[0].ts;
  const lastTs    = entries[entries.length - 1].ts;
  const displayTs = isDone ? lastTs : now;  // live clock when running

  // Build flat index map for correct prev-ts lookup
  const globalIndex = new Map<LogEntry, number>(entries.map((e, i) => [e, i]));

  // Group entries by phase
  const grouped: { phase: number; phaseLabel: string; rows: LogEntry[] }[] = [];
  for (const e of entries) {
    const pi   = phaseFor(e.step);
    const last = grouped[grouped.length - 1];
    if (!last || last.phase !== pi) {
      grouped.push({ phase: pi, phaseLabel: PHASES[pi]?.label ?? '其他', rows: [e] });
    } else {
      last.rows.push(e);
    }
  }

  return (
    <div className="workflow-log">
      {/* Header */}
      <div className="wf-header">
        <span className={`wf-badge ${isDone ? 'done' : 'active'}`}>
          {isDone ? '✅ 完成' : '⏳ 进行中'}
        </span>
        <span className="wf-total">总耗时 {elapsed(firstTs, displayTs)}</span>
      </div>

      {/* Phases */}
      {grouped.map((g, gi) => (
        <div key={gi} className="wf-phase">
          <div className="wf-phase-label">{g.phaseLabel}</div>

          {g.rows.map((e, ri) => {
            const isLastInAll = gi === grouped.length - 1 && ri === g.rows.length - 1;
            const isRunning   = isLastInAll && !isDone;

            // prev ts: the global entry just before this one
            const gIdx   = globalIndex.get(e) ?? 0;
            const prevTs = gIdx > 0 ? entries[gIdx - 1].ts : firstTs;
            // next ts: the global entry just after this one (for measuring how long a step took)
            const nextTs = entries[gIdx + 1]?.ts ?? lastTs;

            // Show timing: live counter on running row, static on completed rows
            const showDoneTime = e.step.endsWith('_done') || e.step === 'done' || e.step === 'error';

            return (
              <div key={ri} className={`wf-row${isRunning ? ' running' : ''}`}>
                <span className="wf-icon">{stepIcon(e.step, isRunning)}</span>
                <span className="wf-msg">{e.msg.replace(/^[\u{1F300}-\u{1FAFF}\u2600-\u27BF\s]+/u, '')}</span>
                {isRunning && (
                  <span className="wf-time live">{elapsed(e.ts, now)}</span>
                )}
                {!isRunning && showDoneTime && (
                  <span className="wf-time">{elapsed(prevTs, nextTs)}</span>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
