
export type ModelSelection = 'deepseek-chat' | 'deepseek-reasoner' | 'deepseek-v4-flash' | 'deepseek-v4-pro' | 'GLM-4.7-Flash' | 'astron-code-latest';
export type RendererSelection = 'godot' | 'blender';

interface Settings {
  directorModel: ModelSelection;
  workerModel: ModelSelection | 'auto';
  renderer: RendererSelection;
  theme: 'dark' | 'light';
  autoHdri: boolean;
  hdriPreset: string;
}

const DEFAULT_SETTINGS: Settings = {
  directorModel: 'astron-code-latest',
  workerModel: 'auto',
  renderer: 'godot',
  theme: 'dark',
  autoHdri: true,
  hdriPreset: 'city',
};

class SettingsStore {
  private settings: Settings = { ...DEFAULT_SETTINGS };
  private listeners: Set<() => void> = new Set();

  constructor() {
    const saved = localStorage.getItem('ai_director_settings');
    if (saved) {
      try {
        this.settings = { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
      } catch (e) {
        console.error('Failed to load settings', e);
      }
    }
  }

  getSettings() {
    return { ...this.settings };
  }

  updateSettings(updates: Partial<Settings>) {
    this.settings = { ...this.settings, ...updates };
    localStorage.setItem('ai_director_settings', JSON.stringify(this.settings));
    this.notify();
  }

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    this.listeners.forEach(l => l());
  }
}

export const settingsStore = new SettingsStore();
