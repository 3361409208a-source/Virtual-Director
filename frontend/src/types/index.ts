export interface LogEntry {
  step: string;
  msg: string;
  ts: number;          // Date.now() when received
}

export interface Message {
  id: string;
  type: 'user' | 'ai' | 'log';
  text: string;
  entries?: LogEntry[];  // only for type === 'log'
}

export interface ActorKeyframe {
  time: number;
  position: { x: number; y: number; z: number };
  rotation?: { x: number; y: number; z: number };
}

export interface CameraKeyframe {
  time: number;
  position?: { x: number; y: number; z: number };
  lookat?: { x: number; y: number; z: number };
  mode?: string;
  target_id?: string;
}

export interface SceneSequence {
  meta: { total_duration: number };
  scene_setup: { background_color?: number[]; ground_color?: number[] };
  actors: Array<{ actor_id: string; shape: string; color: number[] }>;
  actor_tracks: Record<string, ActorKeyframe[]>;
  camera_track: CameraKeyframe[];
  asset_manifest?: Record<string, any>;
}

export interface ProjectMeta {
  id: string;
  prompt: string;
  model: string;
  created_at: string;
  status: string;
  has_video?: boolean;
  has_sequence?: boolean;
}

export interface ProjectDetail extends ProjectMeta {
  chat: LogEntry[];
  sequence?: SceneSequence;
}

export interface SSEEvent {
  step: string;
  msg: string;
  video_url?: string;
  sequence?: SceneSequence;
  review_sid?: string;
}
