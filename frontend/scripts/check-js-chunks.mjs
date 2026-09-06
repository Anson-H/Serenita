import { readdir, stat } from "node:fs/promises";
import { join, relative, resolve } from "node:path";

const limitBytes = 500_000;
const outputRoot = resolve("dist");

async function collectJavaScriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await collectJavaScriptFiles(path));
    else if (entry.isFile() && entry.name.endsWith(".js")) files.push(path);
  }
  return files;
}

const files = await collectJavaScriptFiles(outputRoot);
const oversized = [];
for (const file of files) {
  const { size } = await stat(file);
  if (size > limitBytes) oversized.push({ file: relative(outputRoot, file), size });
}

if (oversized.length) {
  console.error(`JavaScript chunk budget exceeded (${limitBytes} bytes):`);
  for (const { file, size } of oversized) console.error(`- ${file}: ${size} bytes`);
  process.exitCode = 1;
} else {
  console.log(`JavaScript chunk budget passed: ${files.length} chunks at or below ${limitBytes} bytes.`);
}
