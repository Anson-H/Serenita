# Serenita 自部署版

Serenita 是 AI 健康工作区，提供健康会话、医疗报告、成员档案和长期记忆。

源码包含自部署所需的 Python 后端、React 前端和依赖锁文件。GitHub Release 提供 `Source code (zip)` 和 `Source code (tar.gz)` 两种压缩格式，内容相同，任选一种下载。

## 从源码启动

准备 Python 3.13 或更高版本、uv，以及 Node.js 和 npm。解压后进入源码根目录，构建网页并启动：

```bash
npm --prefix frontend ci
npm --prefix frontend run build
uv run --frozen python run.py
```

打开 `http://127.0.0.1:8000`。需要使用 Serenita 免费模型时，在启动前设置 `SERENITA_OFFICIAL_URL` 为实际官方 HTTPS 地址，再在提供方设置中点击“Serenita 授权登录”。官方服务地址由部署者提供；自配模型 API Key 与联网凭证保存在本地。

## 数据

每个自部署实例只有一个本地账号，打开网页直接进入工作区，所有浏览器使用同一份资料。一个工作区可以管理多位家庭成员。

资料默认保存在包根目录的 `serenita_self_hosted_data/`，可通过 `DATA_ROOT` 指定绝对路径。`all_users` 保存本部署的认证库和加密主密钥；`accounts` 下只有一个以本地账号标识命名的目录，保存配置与健康资料。Serenita 授权登录用于连接官方模型，本地资料仍归属同一个工作区。更新程序时保留整个数据目录及主密钥。

默认仅监听本机。`--host`、`--port` 可调整监听地址与端口；放到公网前应由部署者配置入口认证和 HTTPS。
