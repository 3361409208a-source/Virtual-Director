# Virtual Director 🎬

**Virtual Director** 是一个基于多智能体 AI 协作的 3D 视频生成系统。它能够将用户的自然语言描述（提示词）转化为结构化的 3D 场景数据，并通过 Godot 4 引擎实时渲染成高质量的视频。

## ✨ 核心特性

- **多智能体协作**：采用“总导演 + 专项专家”架构。
  - **总导演 (Director)**：分析剧本，拆解任务。
  - **场景美术 (Scene Agent)**：规划天空、光影、地面与静态环境。
  - **动画导演 (Actor Agent)**：定义角色并规划复杂的 3D 移动轨迹。
  - **摄影指导 (Camera Agent)**：实现电影级的运镜控制（追踪、环绕、俯瞰等）。
  - **资产策划 (Asset Agent)**：利用 **AI 积木拼装技术**，根据描述自动构建 3D 模型。
- **Procedural AI Modeling**：当找不到对应 3D 模型时，AI 会利用基础几何体（盒、球、圆柱）拼装出逼真的物体造型。
- **DeepSeek 驱动**：深度集成 DeepSeek-V3/R1 模型，具备极强的指令遵循与逻辑规划能力。
- **实时预览与渲染**：前后端分离架构，Godot 引擎后端执行，FFmpeg 母带压制。

## 🚀 快速启动

### 1. 环境依赖
- **Python 3.10+**
- **Node.js 18+**
- **Godot 4.x** (需在 `backend/config.py` 中配置执行程序路径)
- **FFmpeg** (需添加到系统环境变量)

### 2. 安装与运行
```bash
# 克隆仓库
git clone https://github.com/3361409208a-source/Virtual-Director.git
cd Virtual-Director

# 启动后端 (根目录下)
pip install -r requirements.txt  # 请根据需要创建
uvicorn backend.main:app --reload

# 启动前端 (另一个终端)
cd frontend
npm install
npm run dev
```

## 🛠️ 技术架构

- **Frontend**: React + Vite + Tailwind CSS
- **Backend**: FastAPI + OpenAI SDK (DeepSeek API)
- **Engine**: Godot 4 (GDScript 运行时驱动)
- **Streaming**: SSE (Server-Sent Events) 实现生成过程的实时反馈

## 📂 目录结构

```text
├── godot/              # Godot 项目文件，包含核心渲染逻辑 (DirectorEngine.gd)
├── backend/            # FastAPI 后端，包含 AI Agents 与 渲染服务
├── frontend/           # React 前端界面
└── projects/           # 历史生成记录与成片存储
```

---
*Created by [Antigravity](https://github.com/google-deepmind) for procedural AI filmmaking.*
