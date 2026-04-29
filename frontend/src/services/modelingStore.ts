import type { AIModelEvent, AIGenerateResult } from './api';
import { streamAiGenerateModel } from './api';

type Listener = (state: ModelingState) => void;

export interface ModelingState {
  isGenerating: boolean;
  logs: string[];
  result: AIGenerateResult | null;
  error: string;
  prompt: string;
  llm: string;
  tokens?: { input: number; output: number };
  parts: any[]; // New: captured parts
}

class ModelingStore {
  private state: ModelingState = {
    isGenerating: false,
    logs: [],
    result: null,
    error: '',
    prompt: '',
    llm: 'astron-code-latest',
    parts: [],
  };

  private listeners: Set<Listener> = new Set();

  getState() {
    return this.state;
  }

  subscribe(l: Listener) {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  private notify() {
    this.listeners.forEach(l => l({ ...this.state }));
  }

  setPrompt(p: string) {
    this.state.prompt = p;
    this.notify();
  }

  setLlm(l: string) {
    this.state.llm = l;
    this.notify();
  }

  async startGenerate(prompt: string, llm: string, baseModel: string = '') {
    if (this.state.isGenerating) return;

    this.state.isGenerating = true;
    this.state.logs = [];
    this.state.result = null;
    this.state.parts = [];
    this.state.error = '';
    this.state.prompt = prompt;
    this.state.llm = llm;
    this.state.tokens = { input: 0, output: 0 };
    this.notify();

    let tokenBuf = '';
    try {
      await streamAiGenerateModel(
        prompt,
        (ev: AIModelEvent) => {
          if (ev.tokens) this.state.tokens = ev.tokens;

          if (ev.step === 'thinking') {
            const lastIdx = this.state.logs.length - 1;
            if (lastIdx >= 0 && this.state.logs[lastIdx].startsWith('💭')) {
              this.state.logs[lastIdx] += ev.msg;
            } else {
              this.state.logs.push('💭 ' + ev.msg);
            }
          } else if (ev.step === 'token') {
            tokenBuf += ev.msg;
            if (this.state.logs.length > 0 && this.state.logs[this.state.logs.length - 1].startsWith('📝')) {
              this.state.logs[this.state.logs.length - 1] = '📝 ' + tokenBuf;
            } else {
              this.state.logs.push('📝 ' + tokenBuf);
            }
            
            // Real-time parts extraction from token buffer
            try {
              // Look for patterns like {"color":..., "name":..., "position":..., "shape":...}
              // This is a naive but effective way to catch parts as they stream
              const matches = tokenBuf.match(/\{"color":.+?\}\}/g);
              if (matches) {
                const parsed = matches.map(m => {
                   try { return JSON.parse(m); } catch(e) { return null; }
                }).filter(x => x && x.position);
                if (parsed.length > this.state.parts.length) {
                   this.state.parts = parsed;
                }
              }
            } catch(e) {}

          } else if (ev.step === 'done') {
            this.state.result = ev as unknown as AIGenerateResult;
            if (this.state.result.parts) this.state.parts = this.state.result.parts;
            this.state.logs.push('✨ 建模完成！');
          } else if (ev.step === 'error') {
            this.state.error = ev.msg;
            this.state.logs.push('❌ ' + ev.msg);
          } else {
            tokenBuf = '';
            this.state.logs.push(ev.msg);
          }
          this.notify();
        },
        llm,
        baseModel
      );
    } catch (e) {
      this.state.error = e instanceof Error ? e.message : String(e);
      this.notify();
    } finally {
      this.state.isGenerating = false;
      this.notify();
    }
  }

  reset() {
    this.state.result = null;
    this.state.logs = [];
    this.state.error = '';
    this.notify();
  }
}

export const modelingStore = new ModelingStore();
