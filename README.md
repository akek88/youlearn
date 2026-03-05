# YouLearn

将任意 YouTube 视频转化为结构化知识。

## 技术栈

- **前端**：React + Vite
- **后端**：Python Flask
- **AI**：Google Gemini 1.5 Flash
- **字幕**：youtube-transcript-api

## 项目结构

```
youlearn/
├── frontend/        # React Vite 前端
└── backend/         # Python Flask 后端
    ├── app.py
    ├── .env         # 存放 GEMINI_API_KEY（勿提交）
    ├── .env.example
    └── requirements.txt
```

## 环境配置

### 1. 配置后端 API Key

复制 `.env.example` 并填入你的 Gemini API Key：

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`：

```
GEMINI_API_KEY=your_actual_key_here
```

### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

## 启动项目

### 方式一：分别启动

打开两个终端窗口：

**终端 1 — 后端**
```bash
cd youlearn/backend
python app.py
# 运行在 http://localhost:5000
```

**终端 2 — 前端**
```bash
cd youlearn/frontend
npm run dev
# 运行在 http://localhost:5173
```

### 方式二：一键启动（Linux / macOS / Git Bash）

```bash
cd youlearn
bash start.sh
```

## 使用说明

1. 打开浏览器访问 `http://localhost:5173`
2. 粘贴任意 YouTube 视频链接
3. 点击「开始分析」
4. 等待分析完成后查看：
   - 左侧：视频播放器 + 双语字幕同步
   - 右侧：核心主题 / 关键知识点 / 洞察 / 延伸阅读
5. 点击「导出笔记」下载 Markdown 文件

## API 接口

### `POST /api/analyze`

**请求体**
```json
{ "url": "https://www.youtube.com/watch?v=xxx" }
```

**响应**
```json
{
  "videoId": "xxx",
  "subtitles": [
    { "start": 0.0, "duration": 4.0, "en": "...", "zh": "..." }
  ],
  "analysis": {
    "theme": "核心主题 / Core Theme",
    "keyPoints": ["知识点1", "知识点2"],
    "insights": ["洞察1", "洞察2"],
    "further": ["延伸阅读1", "延伸阅读2"]
  }
}
```
