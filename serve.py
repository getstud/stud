"""Local read-only viewer with automatic rebuilds. python3 serve.py --port 8765"""
import argparse, csv, io, json, mimetypes, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from comments import CommentStore
from pricing import PriceStore
ROOT=Path(__file__).resolve().parent
PROJECT=Path.cwd()
comments=CommentStore(PROJECT / "annotations/comments.json")
prices=PriceStore(PROJECT / "annotations/prices.json")
lock=threading.Lock(); stamp=None; data=None

def model():
    global stamp,data
    with lock:
        sources = set(PROJECT.glob('*.py')) | set((PROJECT/'src').rglob('*.py'))
        sources.update(ROOT/f for f in ('clubhouse/__init__.py','stud/__init__.py','build.py','validate.py','solid_geometry.py','validation_rules.py'))
        sources.update((ROOT/'stud').rglob('*.py'))
        current=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(sources))
        if current!=stamp:
            result=subprocess.run([sys.executable,'-B',str(ROOT/'build.py'),'--project',str(PROJECT)],cwd=PROJECT,capture_output=True,text=True,timeout=20)
            if result.returncode: raise ValueError((result.stdout + result.stderr)[-3000:])
            data=json.loads((PROJECT/'output/model/model.json').read_text());stamp=current
        return data

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        try:
            if path=='/api/pricing':
                return self.send(json.dumps(prices.estimate(model())).encode(),'application/json')
            if path=='/api/costs.csv':
                estimate=prices.estimate(model());stream=io.StringIO();w=csv.writer(stream)
                w.writerow(['material','unit','quantity','unit_price_usd','line_total_usd','source','date','url','quantity_basis','price_kind','category'])
                for row in estimate['rows']:
                    q=row['quote'] or {};w.writerow([row['name'],row['unit'],row['quantity'],q.get('unit_price'),row['total'],q.get('source'),q.get('observed_on'),q.get('url'),row['basis'],row['quote_kind'],row['category']])
                w.writerow(['ITEM SUBTOTAL USD',estimate['subtotal']]);w.writerow(['UNPRICED LINES',estimate['unpriced_lines']])
                if estimate.get('budget'):
                    for key in ('sales_tax','contingency','grand_total','target','over_target'): w.writerow([key,estimate['budget'][key]])
                    w.writerow(['EXCLUDES','; '.join(estimate['budget']['excluded'])])
                return self.send(stream.getvalue().encode(),'text/csv','stud-costs.csv')
            if path=='/api/comments':
                return self.send(json.dumps({'comments':comments.read()}).encode(),'application/json')
            if path.startswith('/api/comment-images/'):
                try:
                    image = comments.image(path.removeprefix('/api/comment-images/'))
                except (FileNotFoundError, ValueError):
                    return self.send(b'Not found', 'text/plain', status=404)
                return self.send(image, 'image/png')
            if path=='/api/validation':
                error=None
                try: model()
                except Exception as exc: error=str(exc)
                report_path=PROJECT/'output/model/validation.json'
                report=json.loads(report_path.read_text()) if report_path.exists() else {}
                if error: report['build_error']=error
                return self.send(json.dumps(report).encode(),'application/json')
            if path=='/api/model':
                return self.send(json.dumps(model()).encode(),'application/json')
            if path=='/api/parts.csv':
                model();return self.send((PROJECT/'output/model/parts.csv').read_bytes(),'text/csv','stud-parts.csv')
            if path=='/api/materials.csv':
                d=model();s=io.StringIO();w=csv.writer(s);w.writerow(['material','modeled_parts','stock_allowance','basis','status','product_url'])
                for r in d['materials']: w.writerow([r['name'],r['parts'],r['purchase'],r['basis'],r['status'],r['url']])
                return self.send(s.getvalue().encode(),'text/csv','stud-materials.csv')
            routes={'/':'web/index.html','/app.js':'web/app.js','/show.js':'web/show.js','/area-capture.js':'web/area-capture.js','/style.css':'web/style.css', '/vendor/three.js':'node_modules/three/build/three.module.js','/vendor/three.core.js':'node_modules/three/build/three.core.js','/vendor/OrbitControls.js':'node_modules/three/examples/jsm/controls/OrbitControls.js'}
            if path not in routes: return self.send(b'Not found','text/plain',status=404)
            file=ROOT/routes[path]
            return self.send(file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        except Exception as e: return self.send(json.dumps({'error':str(e)}).encode(),'application/json',status=500)
    def do_POST(self):
        if urlsplit(self.path).path not in ('/api/comments','/api/pricing'):
            return self.send(b'Not found','text/plain',status=404)
        # JSON and same-origin checks prevent unrelated websites writing local notes.
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        host=self.headers.get('Host','')
        if host not in allowed or self.headers.get('Origin') not in (None,f'http://{host}'):
            return self.send(b'Forbidden','text/plain',status=403)
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.send(b'Expected JSON','text/plain',status=415)
        try:
            length=int(self.headers.get('Content-Length','0'))
            limit = 8 * 1024 * 1024 if urlsplit(self.path).path == '/api/comments' else 32768
            if not 0 < length <= limit: raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError('Expected an object')
            if urlsplit(self.path).path=='/api/pricing':
                return self.send(json.dumps(prices.update(payload,model())).encode(),'application/json')
            needs_model = payload.get('action','add') == 'add' and payload.get('kind','part') == 'part'
            rows=comments.update(payload,model() if needs_model else None)
            return self.send(json.dumps({'comments':rows}).encode(),'application/json')
        except (ValueError,TypeError) as e:
            return self.send(json.dumps({'error':str(e)}).encode(),'application/json',status=400)
        except Exception:
            return self.send(b'{"error":"Could not save comments. Please retry."}','application/json',status=500)
    def send(self,body,kind,filename=None,status=200):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

def serve(project_dir=None, port=8765):
    global PROJECT, comments, prices, stamp, data
    PROJECT=Path(project_dir or Path.cwd()).resolve()
    if not (PROJECT/'design.py').is_file():
        raise ValueError(f'No design.py in {PROJECT}')
    comments=CommentStore(PROJECT/'annotations/comments.json')
    prices=PriceStore(PROJECT/'annotations/prices.json')
    stamp=data=None
    model()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'stud · {PROJECT.name}: http://127.0.0.1:{server.server_port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--project',type=Path,default=Path.cwd())
    args=parser.parse_args()
    serve(args.project,args.port)
