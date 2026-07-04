import http from 'node:http';
import { createReadStream, existsSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
const port = Number(process.env.PORT || 5173);
const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/geo+json'};
http.createServer((req,res)=>{
  let p = decodeURIComponent((req.url || '/').split('?')[0]);
  if (p === '/' || p === '/jinke/') p = '/index.html';
  p = p.replace(/^\/jinke\//, '/');
  const file = normalize(join(process.cwd(), p === '/index.html' ? 'index.html' : p.slice(1)));
  if (!file.startsWith(process.cwd()) || !existsSync(file)) { res.writeHead(404); res.end('Not found'); return; }
  res.writeHead(200, {'content-type': types[extname(file)] || 'application/octet-stream'});
  createReadStream(file).pipe(res);
}).listen(port, '0.0.0.0', ()=>console.log(`Serving http://localhost:${port}/jinke/`));
