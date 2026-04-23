import type { SceneSequence } from '../types';
import { ScenePreview } from './ScenePreview';

interface Props {
  videoUrl: string | null;
  isRendering: boolean;
  sequence: SceneSequence | null;
}

export function VideoPlayer({ videoUrl, isRendering, sequence }: Props) {
  return (
    <div className="glass-panel video-section">
      <div className="video-container">
        {videoUrl ? (
          <video src={videoUrl} controls autoPlay loop />
        ) : isRendering && sequence ? (
          <ScenePreview sequence={sequence} />
        ) : isRendering ? (
          <div className="placeholder-content">
            <div className="loader" />
            <div className="status-text">AI 规划场景中...</div>
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
