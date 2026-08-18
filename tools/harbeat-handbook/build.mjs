import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(toolRoot, '../..');
const src = path.join(toolRoot, 'src');
const output = path.join(repoRoot, 'docs/superpowers/specs/harbeat-mobile-product-handbook.html');

const read = (name) => readFile(path.join(src, name), 'utf8');
const [template, styles, content, model, handbook, prototypeView, annotations, app] = await Promise.all([
  read('template.html'), read('styles.css'), read('content.js'), read('model.js'),
  read('render-handbook.js'), read('render-prototype.js'), read('render-annotations.js'), read('app.js'),
]);

const replacements = {
  __HB_STYLES__: styles,
  __HB_CONTENT__: content,
  __HB_MODEL__: model,
  __HB_RENDERERS__: [handbook, prototypeView, annotations].join('\n'),
  __HB_APP__: app,
};

const html = Object.entries(replacements).reduce(
  (document, [marker, value]) => document.replace(marker, value),
  template,
);

if (/__HB_[A-Z_]+__/.test(html)) throw new Error('Unresolved build marker');
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, html, 'utf8');
console.log(`${output} ${Buffer.byteLength(html)} bytes`);
