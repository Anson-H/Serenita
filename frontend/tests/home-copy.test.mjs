import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const homeWorkspace = read("src/features/conversations/HomeWorkspace.tsx");
const workspaceTypes = read("src/features/conversations/workspaceTypes.ts");

assert(
  workspaceTypes.includes('title: "新对话"'),
  "home workspace title should read 新对话"
);

assert(
  homeWorkspace.includes("<strong>今天想先聊哪件健康小事？</strong>"),
  "home empty state should use the health-small-thing prompt as its primary line"
);

assert(
  !homeWorkspace.includes("可以先问一个具体问题") &&
    !homeWorkspace.includes("配置模型后，对话会写入后端时间线并可在刷新后恢复。") &&
    !workspaceTypes.includes("今天想先聊哪件健康小事？"),
  "home copy should remove the old prompt and backend timeline helper text"
);
