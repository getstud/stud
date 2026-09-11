"""Static viewer assets and the CadQuery project server entry point."""
import argparse, json, mimetypes, os, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from updates import UpdateNotice
ROOT=Path(__file__).resolve().parent
update_notice=UpdateNotice(ROOT)

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

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        try:
            if path=='/appearance.js':
                return self.send(('window.studAppearance=' + json.dumps(viewer_appearance()) + ';').encode(), 'text/javascript')
            if path=='/api/update':
                return self.send(json.dumps(update_notice.check()).encode(),'application/json')
            routes={'/build-camera.js':'web/build-camera.js','/assembly-instructions.js':'web/assembly-instructions.js','/annotation-layout.js':'web/annotation-layout.js','/camera-transition.js':'web/camera-transition.js','/fly-controls.js':'web/fly-controls.js','/theme.js':'web/theme.js','/build-animation.js':'web/build-animation.js','/environment.js':'web/environment.js','/':'web/index.html','/app.js':'web/app.js','/updates.js':'web/updates.js','/show.js':'web/show.js','/area-capture.js':'web/area-capture.js','/style.css':'web/style.css', '/vendor/three.js':'node_modules/three/build/three.module.js','/vendor/three.core.js':'node_modules/three/build/three.core.js','/vendor/OrbitControls.js':'node_modules/three/examples/jsm/controls/OrbitControls.js'}
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
        return self.send(b'Not found', 'text/plain', status=404)
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
    from stud.source import manifest_at
    from stud.session_http import serve_project
    root = Path(project_dir or Path.cwd()).resolve()
    manifest_at(root)
    return serve_project(root, port, open_browser=open_browser)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--project',type=Path,default=Path.cwd())
    parser.add_argument('--no-open', action='store_true')
    args=parser.parse_args()
    try:
        serve(args.project,args.port,open_browser=not args.no_open)
    except (ValueError, OSError) as error:
        print(f'stud: {error}', file=sys.stderr)
        raise SystemExit(1)
