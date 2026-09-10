"""Debounced rebuild opportunities inside an explicitly begun request."""
from pathlib import Path
import threading
import time

from .contracts import StudError
from .source import capture, read_source, source_identity


class SourceWatcher:
    def __init__(self,session,interval=.2,debounce=.35):
        self.session=session;self.interval=interval;self.debounce=debounce
        self.stop=threading.Event();self.thread=threading.Thread(target=self.run,name='stud-source-watch',daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set();self.thread.join(timeout=2)

    def run(self):
        previous=None;seen_at=0;submitted=None;reported=None
        while not self.stop.wait(self.interval):
            session=self.session
            try:
                with session.mutex:
                    active=session.state['active_request']
                    request=session._request(active) if active else None
                if not request or request['status']!='editing' or request.get('change_kind')=='records':
                    previous=submitted=reported=None;continue
                files=read_source(request['workspace']);source_id=source_identity(files);current=(active,source_id)
                if current!=previous:
                    previous=current;seen_at=time.monotonic();continue
                if current==submitted or time.monotonic()-seen_at<self.debounce:continue
                # Mid-edit syntax is visible as editing state. An explicit
                # evaluate/finish still records its failure when requested.
                for name,body in files.items():
                    if name.endswith('.py'):compile(body,name,'exec')
                source=capture(request['workspace'],session.local/'sources',source_id)
                with session.mutex:
                    latest=session._editable(active)
                    build=session.job(latest['latest_build']) if latest['latest_build'] else None
                    if not build or build['source_id']!=source_id:
                        session._schedule_build(latest,source,key=f'watch:{active}:{source_id}')
                    submitted=current;reported=None
            except (StudError,SyntaxError,OSError,UnicodeError) as error:
                signature=(str(error),previous)
                if reported!=signature:
                    with session.mutex:
                        if not session.closed:
                            session._emit('source_editing',request_id=session.state['active_request'],message=str(error))
                    reported=signature
            except Exception as error:
                with session.mutex:
                    session.state['watch_error']={'message':str(error)};session._save_state()
