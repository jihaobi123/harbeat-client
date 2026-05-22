const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.resolve(process.argv[2] || '.');
const PORT = parseInt(process.argv[3] || '8765', 10);
const MIME = {'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.wav':'audio/wav','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon','.woff':'font/woff','.woff2':'font/woff2'};
http.createServer((req,res) => {
  let p = req.url.split('?')[0];
  if (p === '/') p = '/index.html';
  const fp = path.resolve(path.join(ROOT, p));
  if (!fp.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  fs.readFile(fp, (e,d) => {
    if (e) {
      // SPA fallback
      fs.readFile(path.join(ROOT,'index.html'),(e2,d2)=>{ if(e2){res.writeHead(404);res.end();}else{res.writeHead(200,{'Content-Type':'text/html'});res.end(d2);} });
    } else {
      res.writeHead(200, {'Content-Type': MIME[path.extname(fp)] || 'application/octet-stream'});
      res.end(d);
    }
  });
}).listen(PORT, '127.0.0.1', () => console.log('serving', ROOT, 'on', PORT));
