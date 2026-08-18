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
  assert.doesNotMatch(html, /__HB_[A-Z_]+__/);
  assert.doesNotMatch(html, /<(script|link)[^>]+(?:src|href)=["']https?:\/\//i);
});
