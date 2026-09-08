import base64
import random
import struct
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path

from comments import CommentStore


def png(width=3, height=2):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rng = random.Random(7)
    pixels = b''.join(b'\0' + rng.randbytes(width*4) for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


def area_payload(image=None):
    return dict(id=str(uuid.uuid4()), kind='area', text='This gap looks too wide.',
                revision='captured-revision',
                image='data:image/png;base64,' + base64.b64encode(image or png()).decode())


class AreaCommentsTests(unittest.TestCase):
    def test_image_persists_without_model_or_part_and_can_be_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CommentStore(Path(directory)/'annotations/comments.json')
            payload = area_payload()
            store.update(payload, None)
            # Retrying an uncertain save must not create a second record or image.
            store.update(payload, None)
            reopened = CommentStore(store.path)
            row, = reopened.read()
            self.assertEqual(row['kind'], 'area')
            self.assertEqual(row['revision'], 'captured-revision')
            self.assertNotIn('part_id', row)
            self.assertNotIn('part_snapshot', row)
            self.assertEqual((row['image']['width'], row['image']['height']), (3, 2))
            self.assertEqual(reopened.image(row['id']), png())
            self.assertEqual(len(list((store.path.parent/'screenshots').glob('*.png'))), 1)
            reopened.update(dict(action='resolve', id=row['id'], resolved=True), None)
            self.assertTrue(reopened.read()[0]['resolved'])
            self.assertEqual(reopened.image(row['id']), png())
            with self.assertRaises(FileNotFoundError):
                reopened.image('../comments.json')

    def test_invalid_capture_does_not_create_comment_or_image(self):
        for change in [dict(image='data:text/html;base64,AAAA'), dict(image='data:image/png;base64,%%%'),
                       dict(image='data:image/png;base64,'+base64.b64encode(png()[:-4]).decode()),
                       dict(revision=None), dict(text=' '), dict(id='../bad'), dict(kind='unknown')]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                store = CommentStore(Path(directory)/'comments.json')
                with self.assertRaises(ValueError):
                    store.update(dict(area_payload(), **change), None)
                self.assertEqual(store.read(), [])
                self.assertFalse((Path(directory)/'screenshots').exists())

    def test_regular_screenshot_larger_than_old_comment_request_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            image = png(100, 100)
            self.assertGreater(len(image), 32768)
            store = CommentStore(Path(directory)/'comments.json')
            payload = area_payload(image)
            store.update(payload, None)
            self.assertEqual(store.image(payload['id']), image)
