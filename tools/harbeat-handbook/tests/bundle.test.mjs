import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';

const testDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(testDir, '../../..');
const buildFile = path.join(repoRoot, 'tools/harbeat-handbook/build.mjs');
const outputFile = path.join(repoRoot, 'docs/superpowers/specs/harbeat-mobile-product-handbook.html');

test('builds a self-contained offline handbook', () => {
  execFileSync(process.execPath, [buildFile], { cwd: repoRoot });
  const html = readFileSync(outputFile, 'utf8');

  assert.match(html, /<!doctype html>/i);
  assert.match(html, /产品手册/);
  assert.match(html, /交互原型/);
  assert.match(html, /前端标注/);
  assert.match(html, /role="tablist"/);
  assert.match(html, /data-mode="handbook"/);
  assert.match(html, /data-mode="prototype"/);
  assert.match(html, /data-mode="annotations"/);
  assert.match(html, /data-action="reset"/);
  assert.match(html, /aria-label="场景导航"/);
  assert.match(html, /lang="zh-CN"/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /:focus-visible/);
  assert.match(html, /prefers-reduced-motion/);
  assert.match(html, /\.toast\s*\{[^}]*pointer-events:\s*none/);
  assert.doesNotMatch(html, /@import\s+url/);
  assert.doesNotMatch(html, /fetch\s*\(/);
  assert.doesNotMatch(html, /new\s+WebSocket/);
  assert.doesNotMatch(html, /__HB_[A-Z_]+__/);
  assert.doesNotMatch(html, /<(script|link)[^>]+(?:src|href)=["']https?:\/\//i);
});
