import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const require = createRequire(import.meta.url);
const sourceRoot = fileURLToPath(new URL("../../src/", import.meta.url));

// Each call isolates module state. Dependencies share one cache within that call.
export function loadModule(path, globals = {}, overrides = {}) {
  const cache = new Map();
  function load(path) {
    const filename = [path, `${path}.ts`, `${path}.tsx`].find(existsSync);
    if (!filename) throw new Error(`Module not found: ${path}`);
    if (cache.has(filename)) return cache.get(filename).exports;
    const source = readFileSync(filename, "utf8").replaceAll("import.meta.env.VITE_API_BASE_URL", "undefined");
    const code = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX }
    }).outputText;
    const module = { exports: {} };
    cache.set(filename, module);
    const bindings = {
      window: { location: { origin: "http://test.local" }, dispatchEvent() {}, localStorage: { setItem() {} } },
      ...globals,
      exports: module.exports, module,
      require(id) {
        const replacement = typeof overrides === "function" ? overrides(id) : overrides[id];
        if (replacement !== undefined) return replacement;
        return id.startsWith(".") ? load(resolve(dirname(filename), id)) : require(id);
      }
    };
    new Function(...Object.keys(bindings), code + `\n//# sourceURL=${filename}`)(...Object.values(bindings));
    return module.exports;
  }
  return load(resolve(sourceRoot, path));
}
