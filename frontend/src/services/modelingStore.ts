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
    return () => {
      this.listeners.delete(l);
    };
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
            
            // ── Robust real-time parts extraction ──
            try {
              const partsFound: any[] = [];
              
              // 1. 全文搜索所有可能的对象块 {}
              let pos = 0;
              while (true) {
                const s = tokenBuf.indexOf('{', pos);
                if (s === -1) break;
                
                let bc = 0;
                let e = -1;
                for (let i = s; i < tokenBuf.length; i++) {
                  if (tokenBuf[i] === '{') bc++;
                  else if (tokenBuf[i] === '}') {
                    bc--;
                    if (bc === 0) { e = i; break; }
                  }
                }

                if (e !== -1) {
                  const chunk = tokenBuf.slice(s, e + 1);
                  try {
                    // 只要包含 shape 关键字，就尝试解析
                    if (chunk.includes('"shape"') || chunk.includes('shape:')) {
                      const obj = JSON.parse(chunk);
                      if (obj && (obj.shape || obj.type)) {
                        partsFound.push(obj);
                      }
                    }
                  } catch(ex) {}
                  pos = e + 1;
                } else break; // 还没写完的花括号
              }

              if (partsFound.length > 0) {
                // 如果解析出的零件数有增加，则更新状态
                if (partsFound.length !== this.state.parts.length) {
                  this.state.parts = partsFound;
                }
              }
            } catch(e) { }

          } else if (ev.step === 'done') {
            this.state.result = ev as unknown as AIGenerateResult;
            if (this.state.result.parts) this.state.parts = this.state.result.parts;
            this.state.logs.push('✨ 建模完成！');
          } else if (ev.step === 'error') {
            this.state.error = ev.msg;
            this.state.logs.push('❌ ' + ev.msg);
          } else {
            // 不再清空 tokenBuf，因为中间可能穿插着 building 等状态消息
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
