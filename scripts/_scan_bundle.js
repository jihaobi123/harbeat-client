const fs = require('fs');
const js = fs.readFileSync(process.argv[2], 'utf8');
const routes = [...new Set([...js.matchAll(/path:"([^"]+)"/g)].map(m=>m[1]))];
const tabs = [...new Set([...js.matchAll(/"([A-Z][A-Z][A-Z\s]{2,20})"/g)].map(m=>m[1]))];
const labels = [...new Set([...js.matchAll(/"([A-Za-z][^"]{4,28})"/g)].map(m=>m[1]))]
  .filter(s => /[A-Z]/.test(s) && !/^\d|http|https|application|text\/|image\/|audio\//.test(s));
console.log('=== ROUTES ===');
routes.forEach(r=>console.log(r));
console.log('=== UPPERCASE TABS ===');
tabs.forEach(r=>console.log(r));
console.log('=== INTERESTING LABELS ===');
labels.slice(0,200).forEach(l=>console.log(l));
