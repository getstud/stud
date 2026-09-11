"""Bounded PNG validation for project captures."""
import base64
import binascii
import struct
import zlib

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

