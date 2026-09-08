"""Persistent part and area-screenshot comments, separate from geometry."""
import base64, binascii, json, os, struct, threading, uuid, zlib
from datetime import datetime, timezone
from pathlib import Path

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def decode_screenshot(value):
    """Accept bounded PNG captures without trusting a client filename or MIME type."""
    prefix = 'data:image/png;base64,'
    if not isinstance(value, str) or not value.startswith(prefix) or len(value) > MAX_IMAGE_BYTES * 4 // 3 + 64:
        raise ValueError('Attach a PNG screenshot of at most 5 MB.')
    try:
        image = base64.b64decode(value[len(prefix):], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Invalid screenshot encoding.') from None
    if len(image) > MAX_IMAGE_BYTES or image[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid PNG screenshot.')
    offset = 8
    width = height = None
    has_data = False
    while offset + 12 <= len(image):
        length = struct.unpack('>I', image[offset:offset+4])[0]
        kind = image[offset+4:offset+8]
        end = offset + 12 + length
        if end > len(image):
            raise ValueError('Incomplete PNG screenshot.')
        chunk = image[offset+8:end-4]
        crc = struct.unpack('>I', image[end-4:end])[0]
        if zlib.crc32(kind + chunk) != crc:
            raise ValueError('Damaged PNG screenshot.')
        if offset == 8:
            if kind != b'IHDR' or length != 13:
                raise ValueError('Invalid PNG header.')
            width, height = struct.unpack('>II', chunk[:8])
            if not 1 <= width <= 4096 or not 1 <= height <= 4096:
                raise ValueError('Screenshot dimensions must be between 1 and 4096 pixels.')
        if kind == b'IDAT':
            has_data = True
        if kind == b'IEND':
            if length or end != len(image) or not has_data:
                raise ValueError('Invalid PNG screenshot.')
            return image, width, height
        offset = end
    raise ValueError('Incomplete PNG screenshot.')


class CommentStore:
    def __init__(self, path):
        self.path=Path(path); self.lock=threading.Lock()
    def read(self):
        if not self.path.exists(): return []
        return json.loads(self.path.read_text())['comments']
    def image(self, comment_id):
        row = next((r for r in self.read() if r['id'] == comment_id and r.get('kind') == 'area'), None)
        if row is None:
            raise FileNotFoundError('Screenshot not found.')
        # Derive the path from the validated ID, never from a request path.
        return (self.path.parent / 'screenshots' / f'{uuid.UUID(row["id"])}.png').read_bytes()
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
                kind = payload.get('kind', 'part')
                if kind == 'area':
                    revision = payload.get('revision')
                    if not isinstance(revision, str) or not 1 <= len(revision) <= 128:
                        raise ValueError('A screenshot needs its captured model revision.')
                    image, width, height = decode_screenshot(payload.get('image'))
                    relative = f'screenshots/{uuid.UUID(request_id)}.png'
                    target = self.path.parent / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix('.tmp')
                    temporary.write_bytes(image)
                    os.replace(temporary, target)
                    rows.append(dict(id=request_id,kind='area',text=text.strip(),
                                     created_at=datetime.now(timezone.utc).isoformat(),resolved=False,
                                     revision=revision,image=dict(path=relative,width=width,height=height,mime_type='image/png')))
                elif kind == 'part':
                    part=next((p for p in model['parts'] if p['id']==part_id),None)
                    if not part: raise ValueError('Part no longer exists. Select a current part.')
                    rows.append(dict(id=request_id,part_id=part_id,text=text.strip(),created_at=datetime.now(timezone.utc).isoformat(),resolved=False,revision=model['revision'],part_snapshot={k:part[k] for k in ('assembly','stock','size','origin','rotation')}))
                else:
                    raise ValueError('Unknown comment kind.')
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
