# AI Interactive Video

**把文字概念或上传的视频转成有分支、可选择路径的交互式视频。**

[English](README.md) · [配置](docs/CONFIGURATION.md) · [架构/API](docs/ARCHITECTURE.md) · [GitHub 发布步骤](docs/PUBLISH_TO_GITHUB.md)

![本地交互视频演示](docs/images/local-demo.png)

项目由 React 前端、FastAPI 后端和 FFmpeg 视频处理组成。后端生成故事图和各节点的视频片段，前端在播放结束后显示选择按钮，支持回看历史路径与恢复任务。

当前版本：`0.2.0`。默认是无需 API key 的本地演示模式；截图使用占位视频，不代表付费模型生成效果。

## 本地运行

需要 **Python 3.12**、**Node.js 22.12+**、npm 和可通过命令行调用的 **FFmpeg**。

在项目根目录启动后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

另开终端，在项目根目录启动前端：

```bash
cd frontend
npm ci
npm run dev
```

打开 **http://localhost:5173**，保留 **Local demo**，输入文字概念并创建任务。视频结束后会出现分支选项。API 文档在 **http://localhost:8000/docs**。

Windows 用 `.venv\Scripts\Activate.ps1` 激活环境、用 `Copy-Item .env.example .env` 复制配置。macOS/Linux 安装完成后，也可以运行 `./scripts/start-demo.sh` 同时启动两个服务。

## 真实 AI 生成

修改本地 `backend/.env`，填入自己的 key，重启后端，并在前端选择对应 provider：

| Provider | 所需配置 | 处理方式 |
| --- | --- | --- |
| `mock` | 无需 key | 本地故事模板及带音频的占位视频 |
| `veo_lite / veo_fast / veo_standard` | `GEMINI_API_KEY` | Gemini 规划故事；Veo 根据文字生成视频 |
| `fal` | `FAL_KEY`；Gemini key 可选 | 通过 fal 生成视频，可给首段上传视频参考 |

`mock` 模式不会调用外部 AI，包括已经配置了 Gemini key 的情况。缺少真实 provider 所需 key 时，API 会提前提示。模型名称可配置，请核对自己的账户权限和服务商当前模型目录。

默认 5 个节点、每段 8 秒。15 秒选项向上取整为约 16 秒，60 秒为约 64 秒，分别生成 10 或 40 段视频；服务商重试可能增加请求。系统会生成所有分支，不仅生成用户最后选择的路径。

## 已保留的能力

- 视频/文字输入和多种故事风格。
- 分支、合流与循环的故事图。
- 全局风格和角色记忆写入提示词。
- Gemini/Veo 和 fal 的 provider 接口。
- FFmpeg 拼接、任务日志、历史记录、断点式重试。
- 播放器选项按钮、历史路径回看、恢复已有任务。

## 开发检查

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest -q
npm --prefix frontend run build
python3 scripts/check_release.py
```

当前是本地单用户 MVP，后台任务尚未使用持久化队列，服务重启后不会自动恢复正在执行的任务；没有登录和任务访问控制。真实视频的跨片段角色一致性由提示词约束，尚不保证。

作者：**Ziyang Ye**。采用 [MIT](LICENSE) 许可证，包含 CI、Issue/PR 模板及[发布说明](docs/PUBLISH_TO_GITHUB.md)。实际 key、上传视频、任务结果和依赖目录未包含在公开源码中。
