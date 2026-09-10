"""Local read-only viewer with automatic rebuilds. python3 serve.py --port 8765"""
import argparse, csv, io, json, mimetypes, os, re, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from comments import CommentStore
from pricing import PriceStore
from updates import UpdateNotice
from stud.environment import environment_stamp
ROOT=Path(__file__).resolve().parent
PROJECT=Path.cwd()
update_notice=UpdateNotice(ROOT)
comments=CommentStore(PROJECT / "annotations/comments.json")
prices=PriceStore(PROJECT / "annotations/prices.json")
lock=threading.Lock(); stamp=None; data=None

def viewer_appearance():
    """Expose only validated appearance settings, never the rest of Codex config."""
    try:
        import tomllib
        config = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'
        desktop = tomllib.loads(config.read_text()).get('desktop', {})
        mode = desktop.get('appearanceTheme', 'system')
        result = {'mode': mode if mode in ('light', 'dark', 'system') else 'system', 'colors': {}}
        for theme in ('light', 'dark'):
            source = desktop.get(f'appearance{theme.title()}ChromeTheme', {})
            result['colors'][theme] = {key: value for key, value in source.items()
                if key in ('surface', 'ink', 'accent') and isinstance(value, str)
                and re.fullmatch(r'#[0-9a-fA-F]{6}', value)}
        return result
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        return {'mode': 'system', 'colors': {}}

def model():
    global stamp,data
    with lock:
        sources = set(PROJECT.glob('*.py')) | set((PROJECT/'src').rglob('*.py'))
        sources.update(ROOT/f for f in ('clubhouse/__init__.py','stud/__init__.py','build.py','validate.py','solid_geometry.py','validation_rules.py'))
        sources.update((ROOT/'stud').rglob('*.py'))
        current=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(sources)) + environment_stamp(PROJECT)
        if current!=stamp:
            result=subprocess.run([sys.executable,'-B',str(ROOT/'build.py'),'--project',str(PROJECT)],cwd=PROJECT,capture_output=True,text=True,timeout=20)
            if result.returncode: raise ValueError((result.stdout + result.stderr)[-3000:])
            data=json.loads((PROJECT/'output/model/model.json').read_text());stamp=current
        return data

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        try:
            if path=='/appearance.js':
                return self.send(('window.studAppearance=' + json.dumps(viewer_appearance()) + ';').encode(), 'text/javascript')
            if path=='/api/update':
                return self.send(json.dumps(update_notice.check()).encode(),'application/json')
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
            if path.startswith('/environment/'):
                relative = Path(unquote(path.removeprefix('/environment/')))
                base = (PROJECT / 'output/environment').resolve()
                file = (base / relative).resolve()
                if relative.is_absolute() or '..' in relative.parts or not file.is_relative_to(base) or not file.is_file():
                    return self.send(b'Not found', 'text/plain', status=404)
                kind = 'text/javascript' if file.suffix in ('.js', '.mjs') else mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                return self.send(file.read_bytes(), kind)
            routes={'/build-camera.js':'web/build-camera.js','/assembly-instructions.js':'web/assembly-instructions.js','/annotation-layout.js':'web/annotation-layout.js','/camera-transition.js':'web/camera-transition.js','/fly-controls.js':'web/fly-controls.js','/profile-geometry.js':'web/profile-geometry.js','/theme.js':'web/theme.js','/build-animation.js':'web/build-animation.js','/environment.js':'web/environment.js','/':'web/index.html','/app.js':'web/app.js','/updates.js':'web/updates.js','/show.js':'web/show.js','/area-capture.js':'web/area-capture.js','/style.css':'web/style.css', '/vendor/three.js':'node_modules/three/build/three.module.js','/vendor/three.core.js':'node_modules/three/build/three.core.js','/vendor/OrbitControls.js':'node_modules/three/examples/jsm/controls/OrbitControls.js'}
            routes.update({'/sequence-player.js':'web/sequence-player.js','/viewer-tools.js':'web/viewer-tools.js','/viewer-operations.js':'web/viewer-operations.js','/project-operations.js':'web/project-operations.js','/cad-scene.js':'web/cad-scene.js','/project-events.js':'web/project-events.js',
                           '/render-reference.js':'web/render-reference.js',
                           '/option-comparison.js':'web/option-comparison.js','/option-tabs.js':'web/option-tabs.js',
                           '/versions.js':'web/versions.js','/versions.css':'web/versions.css',
                           '/comparison-scene.js':'web/comparison-scene.js'})
            if path not in routes: return self.send(b'Not found','text/plain',status=404)
            file=ROOT/routes[path]
            return self.send(file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        except Exception as e: return self.send(json.dumps({'error':str(e)}).encode(),'application/json',status=500)
    def do_POST(self):
        if urlsplit(self.path).path not in ('/api/comments','/api/pricing','/api/render-references'):
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
            limit = 32768 if urlsplit(self.path).path == '/api/pricing' else 8 * 1024 * 1024
            if not 0 < length <= limit: raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError('Expected an object')
            if urlsplit(self.path).path=='/api/render-references':
                from stud.render_references import save_render_reference
                return self.send(json.dumps(save_render_reference(PROJECT,payload)).encode(),'application/json')
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

class ViewerServer(ThreadingHTTPServer):
    def server_bind(self):
        # A loopback-only viewer has no need for HTTPServer's reverse DNS lookup.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(project_dir=None, port=8765, open_browser=True):
    candidate=Path(project_dir or Path.cwd()).resolve()
    if (candidate/'stud.json').is_file():
        from stud.session_http import serve_project
        return serve_project(candidate,port,open_browser=open_browser)
    global PROJECT, comments, prices, stamp, data
    PROJECT=Path(project_dir or Path.cwd()).resolve()
    if not (PROJECT/'design.py').is_file():
        raise ValueError(f'No design.py in {PROJECT}')
    comments=CommentStore(PROJECT/'annotations/comments.json')
    prices=PriceStore(PROJECT/'annotations/prices.json')
    stamp=data=None
    server=ViewerServer(('127.0.0.1',port),Handler)
    print(f'stud · {PROJECT.name}: http://127.0.0.1:{server.server_port}',flush=True)
    try:
        if open_browser:
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--project',type=Path,default=Path.cwd())
    parser.add_argument('--no-open', action='store_true')
    args=parser.parse_args()
    serve(args.project,args.port,open_browser=not args.no_open)
