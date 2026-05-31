# Serenita v1.0.0 前端说明草案

> 文档状态：技术草案 / 前端实现参考
> 当前用途：记录 React + Vite 前端方案草案，后续可替换为正式前端开发文档
> 当前执行版本：`v0.1.0`
> ⚠️ 注意：本文档仅为早期 Vite 模板说明，不包含实质性前端架构内容。当前前端体验补充参考 `docs/shared/frontend-design.md`。

## React 与 Vite 模板说明

该模板用于用最小配置运行 React 和 Vite，并提供热更新能力和基础代码检查规则。

当前可用的官方插件包括：

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react)，使用 [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc)，使用 [SWC](https://swc.rs/)

## React Compiler 说明

当前模板未启用 React Compiler，因为它会影响开发和构建性能。若后续需要加入，请参考 [React Compiler 安装文档](https://react.dev/learn/react-compiler/installation)。

## ESLint 配置扩展

如果要开发生产级应用，建议为 TypeScript 启用类型感知的检查规则。可参考 [Vite React TypeScript 模板](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts)，了解如何集成 TypeScript 与 [`typescript-eslint`](https://typescript-eslint.io)。
