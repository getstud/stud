"""Project-local image-generation inputs, separate from design/review records."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from comments import decode_screenshot
from .contracts import confined


def save_render_reference(root, payload):
    """Save only bounded PNG/JSON data under a server-chosen immutable name."""
    if not isinstance(payload, dict) or set(payload) != {'image', 'brief'}:
        raise ValueError('Expected image and brief.')
    brief = payload['brief']
    if (not isinstance(brief, dict) or brief.get('schema_version') != 1
            or brief.get('kind') != 'stud-render-reference'
            or not isinstance(brief.get('revision'), str) or not brief['revision']
            or not isinstance(brief.get('prompt'), str) or not brief['prompt']):
        raise ValueError('A versioned render brief with revision and prompt is required.')
    # Browser context is descriptive evidence, never executable design input.
    encoded = json.dumps(brief, allow_nan=False)
    if len(encoded.encode()) > 1024 * 1024:
        raise ValueError('Render brief exceeds 1 MB.')
    image, width, height = decode_screenshot(payload['image'])
    reference_id = uuid.uuid4().hex
    directory = confined(Path(root).resolve(), f'exports/render-references/{reference_id}')
    directory.mkdir(parents=True, exist_ok=False)
    reference = directory / 'geometry.png'
    metadata = directory / 'brief.json'
    record = {**brief, 'reference_id': reference_id, 'created_at': datetime.now(timezone.utc).isoformat(),
              'image': {'width': width, 'height': height, 'mime_type': 'image/png',
                        'sha256': hashlib.sha256(image).hexdigest()}}
    try:
        reference.write_bytes(image)
        metadata.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
    except OSError:
        reference.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return dict(reference_id=reference_id, reference_path=str(reference), brief_path=str(metadata),
                image=record['image'], revision=brief['revision'])
