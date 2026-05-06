import type { AIModelEvent, AIGenerateResult, SceneObject } from './api';
import { streamAiGenerateModel } from './api';

type Listener = (state: ModelingState) => void;

export interface ModelingState {
  isGenerating: boolean;
  logs: string[];
  result: AIGenerateResult | null;
  sceneResult: { scene_name: string; scene_description: string; objects: SceneObject[]; success_count: number; total_objects: number } | null;
  error: string;
  prompt: string;
  llm: string;
  style: string;
  tokens?: { input: number; output: number };
  parts: any[];
}

class ModelingStore {
  private state: ModelingState = {
    isGenerating: false,
    logs: [],
    result: null,
    sceneResult: null,
    error: '',
    prompt: '',
    llm: 'astron-code-latest',
    style: 'realistic',
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

  setStyle(style: string) {
    this.state.style = style;
    this.notify();
  }

  async startGenerate(prompt: string, llm: string, baseModel: string = '', style: string = this.state.style) {
    if (this.state.isGenerating) return;

    this.state.isGenerating = true;
    this.state.logs = [];
    this.state.result = null;
    this.state.sceneResult = null;
    this.state.parts = [];
    this.state.error = '';
    this.state.prompt = prompt;
    this.state.llm = llm;
    this.state.style = style;
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
            const text = ev.msg;
            tokenBuf += text;

            // ── 日志显示：只展示 JSON 开始前的纯文字思考内容 ──
            // 一旦检测到 { 开始了 JSON 块，就不再更新文字日志
            // （避免 JSON 数据被积累进日志行后，被过滤器整行隐藏）
            const jsonStart = tokenBuf.indexOf('{');
            const preText = (jsonStart === -1 ? tokenBuf : tokenBuf.slice(0, jsonStart)).trim();

            if (preText) {
              const lastIdx = this.state.logs.length - 1;
              if (lastIdx >= 0 && this.state.logs[lastIdx].startsWith('📝')) {
                this.state.logs[lastIdx] = '📝 ' + preText;
              } else {
                this.state.logs.push('📝 ' + preText);
              }
            } else if (jsonStart !== -1 && jsonStart === 0) {
              // 纯 JSON 模型，没有文字前缀——显示一条进度提示
              const lastIdx = this.state.logs.length - 1;
              const hasProgress = lastIdx >= 0 && this.state.logs[lastIdx] === '⚙️ AI 正在生成零件数据...';
              if (!hasProgress) this.state.logs.push('⚙️ AI 正在生成零件数据...');
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
          } else if (ev.step === 'scene_done') {
            this.state.sceneResult = {
              scene_name: ev.scene_name || '',
              scene_description: ev.scene_description || '',
              objects: ev.objects || [],
              success_count: ev.success_count || 0,
              total_objects: ev.total_objects || 0,
            };
            if (ev.tokens) this.state.tokens = ev.tokens;
            this.state.logs.push(`🏙️ 场景完成！${ev.success_count}/${ev.total_objects} 个物体已入库`);
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
        baseModel,
        style
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
