# Serenita

Serenita 是面向患者的本地优先 AI 健康工作台，支持健康会话、医疗报告管理与解读、成员健康档案和收藏。智能体根据用户目标与已有证据，自主选择 Skill 和工具完成任务。

项目使用 Python + FastAPI 构建后端，React + TypeScript + Vite 构建前端。

项目地址：[GitHub - Anson-H/Serenita](https://github.com/Anson-H/Serenita)

## 本地运行

准备 Python 3.13 或更高版本、uv，以及 Node.js 和 npm。

在仓库根目录启动后端：

```bash
uv sync
uv run uvicorn backend.app.main:create_app --factory --reload
```

另开终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

打开终端显示的前端地址，默认是 `http://127.0.0.1:5173`。开发服务器将 `/api` 请求代理到后端。

登录后，在设置中配置模型服务和默认模型；需要联网时，再配置并开启联网服务。本地开发数据默认保存在仓库下的 `serenita_files/` 目录。

## 远端服务器 SSH 登录

服务器已配置本机的 Ed25519 公钥，使用 `lighthouse` 用户登录：

```bash
ssh lighthouse@43.138.247.24
```

如果 SSH 未自动使用默认密钥，可以显式指定：

```bash
ssh -i ~/.ssh/id_ed25519 lighthouse@43.138.247.24
```

本机私钥只保存在本机，项目根目录的 `serenita.pem` 已加入 `.gitignore`。

## 文档

- [文档中心](docs/README.md)：当前执行文档与未来愿景。
- [后端开发](backend/README.md)：后端结构、运行与测试。
- [前端开发](frontend/README.md)：前端结构、运行与测试。
- [设计规范](DESIGN.md)：界面视觉规范。
- [智能体开发规则](AGENTS.md)：项目开发约束。
