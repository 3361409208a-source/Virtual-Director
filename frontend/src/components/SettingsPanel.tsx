import React, { useEffect, useState } from 'react';
import { settingsStore, type ModelSelection } from '../services/settingsStore';

const IconCpu = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/><path d="M15 2v2"/><path d="M9 2v2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M15 20v2"/><path d="M9 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/></svg>;
const IconZap = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>;
const IconSun = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>;

export const SettingsPanel: React.FC = () => {
  const [settings, setSettings] = useState(settingsStore.getSettings());

  useEffect(() => {
    return settingsStore.subscribe(() => {
      setSettings(settingsStore.getSettings());
    });
  }, []);

  const models: ModelSelection[] = [
    'deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-flash', 'deepseek-v4-pro', 'GLM-4.7-Flash', 'Kimi-K2.6', 'astron-code-latest'
  ];

  return (
    <div className="settings-container">
      <header className="settings-header">
        <h2>系统设置</h2>
        <p>配置 AI 导演与工作组的核心运行参数</p>
      </header>

      <div className="settings-grid">
        {/* AI 模型配置 */}
        <section className="settings-section">
          <div className="section-title">
            <IconCpu /> <h3>AI 模型架构</h3>
          </div>
          <div className="section-content">
            <div className="setting-item">
              <div className="setting-info">
                <label>总导演模型 (Director)</label>
                <span>负责创意拆解、剧本分析。建议使用 Pro/Classic 模型。</span>
              </div>
              <select 
                value={settings.directorModel}
                onChange={(e) => settingsStore.updateSettings({ directorModel: e.target.value as ModelSelection })}
              >
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>

            <div className="setting-item">
              <div className="setting-info">
                <label>工作组加速模型 (Workers)</label>
                <span>负责关键帧、资产决策。建议使用 Flash 模型。</span>
              </div>
              <select 
                value={settings.workerModel}
                onChange={(e) => settingsStore.updateSettings({ workerModel: e.target.value as any })}
              >
                <option value="auto">自动选择 (智能加速)</option>
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
        </section>

        {/* 渲染与物理 */}
        <section className="settings-section">
          <div className="section-title">
            <IconZap /> <h3>渲染引擎偏好</h3>
          </div>
          <div className="section-content">
            <div className="setting-item">
              <div className="setting-info">
                <label>默认渲染器</label>
                <span>选择预览与导出的默认引擎。</span>
              </div>
              <div className="toggle-group">
                <button 
                  className={settings.renderer === 'godot' ? 'active' : ''}
                  onClick={() => settingsStore.updateSettings({ renderer: 'godot' })}
                >Godot</button>
                <button 
                  className={settings.renderer === 'blender' ? 'active' : ''}
                  onClick={() => settingsStore.updateSettings({ renderer: 'blender' })}
                >Blender</button>
              </div>
            </div>
          </div>
        </section>

        {/* 预览环境 */}
        <section className="settings-section">
          <div className="section-title">
            <IconSun /> <h3>全局环境预设</h3>
          </div>
          <div className="section-content">
            <div className="setting-item">
              <div className="setting-info">
                <label>自动加载 HDRI</label>
                <span>在 3D 预览中默认加载全景环境。</span>
              </div>
              <input 
                type="checkbox" 
                checked={settings.autoHdri}
                onChange={(e) => settingsStore.updateSettings({ autoHdri: e.target.checked })}
              />
            </div>
            
            <div className="setting-item">
              <div className="setting-info">
                <label>默认 HDRI 场景</label>
                <span>初始加载时的环境。</span>
              </div>
              <select 
                value={settings.hdriPreset}
                onChange={(e) => settingsStore.updateSettings({ hdriPreset: e.target.value })}
              >
                <option value="studio">工作室 (纯净)</option>
                <option value="city">皇家广场 (城市)</option>
                <option value="sunset">威尼斯 (日落)</option>
                <option value="forest">人行天桥 (自然)</option>
              </select>
            </div>
          </div>
        </section>
      </div>

      <footer className="settings-footer">
        <p>设置已实时保存至本地存储</p>
        <button className="reset-btn" onClick={() => {
           if(confirm('确定要恢复默认设置吗？')) {
             localStorage.removeItem('ai_director_settings');
             window.location.reload();
           }
        }}>重置全部设置</button>
      </footer>
    </div>
  );
};
