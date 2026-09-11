import base64
import random
import struct
import unittest
import zlib

from stud.screenshots import decode_screenshot


def png(width=3, height=2):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    rng=random.Random(7)
    pixels=b''.join(b'\0'+rng.randbytes(width*4) for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b''))


def data_url(image):
    return 'data:image/png;base64,'+base64.b64encode(image).decode()


class ScreenshotTests(unittest.TestCase):
    def test_preserves_capture_bytes_and_dimensions(self):
        image=png(100,100)
        self.assertGreater(len(image),32768)
        self.assertEqual(decode_screenshot(data_url(image)),(image,100,100))

    def test_rejects_non_png_corrupt_truncated_and_oversized_captures(self):
        damaged=bytearray(png());damaged[-5]^=1
        for value in ('data:text/html;base64,AAAA','data:image/png;base64,%%%',
                      data_url(png()[:-4]),data_url(damaged),data_url(png(4097,1)),
                      'data:image/png;base64,'+'A'*(7*1024*1024)):
            with self.subTest(prefix=value[:40]):
                with self.assertRaises(ValueError):decode_screenshot(value)
