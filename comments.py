"""Persistent part comments, kept separately from regenerated geometry."""
import json, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path

class CommentStore:
    def __init__(self, path):
        self.path=Path(path); self.lock=threading.Lock()
    def read(self):
        if not self.path.exists(): return []
        return json.loads(self.path.read_text())['comments']
    def update(self, payload, model):
        with self.lock:
            rows=self.read()
            action=payload.get('action','add')
            if action=='add':
                text=payload.get('text');part_id=payload.get('part_id');request_id=payload.get('id')
                if not isinstance(text,str) or not 1<=len(text.strip())<=5000: raise ValueError('Enter a comment of 1–5000 characters.')
                try: uuid.UUID(request_id)
                except (ValueError,TypeError,AttributeError): raise ValueError('Invalid comment ID.')
                if any(r['id']==request_id for r in rows): return rows
                part=next((p for p in model['parts'] if p['id']==part_id),None)
                if not part: raise ValueError('Part no longer exists. Select a current part.')
                rows.append(dict(id=request_id,part_id=part_id,text=text.strip(),created_at=datetime.now(timezone.utc).isoformat(),resolved=False,revision=model['revision'],part_snapshot={k:part[k] for k in ('assembly','stock','size','origin','rotation')}))
            elif action=='resolve':
                if not isinstance(payload.get('resolved'),bool): raise ValueError('resolved must be boolean')
                row=next((r for r in rows if r['id']==payload.get('id')),None)
                if not row: raise ValueError('Comment not found.')
                row['resolved']=payload['resolved']
            else: raise ValueError('Unknown action.')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'schema_version':1,'comments':rows},indent=2)+'\n')
            os.replace(temp,self.path)
            return rows
