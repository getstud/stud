"""Inspect Mach-O deployment targets without loading or executing native code.

Example: python3 scripts/verify-macos-floor.py --minimum 12.0 src-tauri/resources
Exit 1 means an advertised deployment floor is too low; exit 2 means scan failure.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

THIN = {b'\xce\xfa\xed\xfe': ('<', False), b'\xfe\xed\xfa\xce': ('>', False),
        b'\xcf\xfa\xed\xfe': ('<', True), b'\xfe\xed\xfa\xcf': ('>', True)}
FAT = {b'\xca\xfe\xba\xbe': ('>', False), b'\xbe\xba\xfe\xca': ('<', False),
       b'\xca\xfe\xba\xbf': ('>', True), b'\xbf\xba\xfe\xca': ('<', True)}
CPU = {0x1000007: 'x86_64', 0x100000c: 'arm64', 7: 'x86', 12: 'arm'}


def unpack(stream, fmt):
    size = struct.calcsize(fmt)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('Truncated Mach-O header/load command')
    return struct.unpack(fmt, data)


def inspect(stream, offset=0, depth=0):
    if depth > 1:
        raise ValueError('Nested universal Mach-O header')
    stream.seek(offset)
    magic = stream.read(4)
    if magic in FAT:
        endian, wide = FAT[magic]
        count, = unpack(stream, endian + 'I')
        if not 0 < count <= 32:
            raise ValueError('Invalid universal architecture count')
        fmt = endian + ('IIQQII' if wide else 'IIIII')
        arches = [unpack(stream, fmt) for _ in range(count)]
        result = []
        for arch in arches:
            rows = inspect(stream, arch[2], depth + 1)
            if not rows:
                raise ValueError('Universal slice has no macOS deployment target')
            result.extend(rows)
        return result
    if magic not in THIN:
        return []
    endian, wide = THIN[magic]
    header = unpack(stream, endian + ('IIIIIII' if wide else 'IIIIII'))
    cpu, subtype, filetype, count, command_bytes, flags = header[:6]
    if count > 10000 or command_bytes > 16 * 1024 * 1024:
        raise ValueError('Invalid Mach-O command inventory')
    end = stream.tell() + command_bytes
    result = []
    for _ in range(count):
        start = stream.tell()
        command, size = unpack(stream, endian + 'II')
        if size < 8 or start + size > end:
            raise ValueError('Invalid Mach-O command size')
        version = None
        if command == 0x32:  # LC_BUILD_VERSION
            if size < 24:
                raise ValueError('Truncated LC_BUILD_VERSION')
            platform, version = unpack(stream, endian + 'II')
            if platform != 1:  # PLATFORM_MACOS
                raise ValueError('A non-macOS native slice is bundled')
        elif command == 0x24:  # LC_VERSION_MIN_MACOSX
            if size < 16:
                raise ValueError('Truncated LC_VERSION_MIN_MACOSX')
            version, = unpack(stream, endian + 'I')
        if version is not None:
            result.append({'architecture': CPU.get(cpu, hex(cpu)),
                           'minimum': [version >> 16, (version >> 8) & 255, version & 255]})
        stream.seek(start + size)
    if not result:
        raise ValueError('Mach-O has no macOS deployment target')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minimum', required=True, help='Advertised minimumSystemVersion, e.g. 12.0')
    parser.add_argument('--json', type=Path, help='Optional full machine-readable report')
    parser.add_argument('directories', nargs='+', type=Path)
    args = parser.parse_args()
    floor = tuple(map(int, args.minimum.split('.')))
    if not 1 <= len(floor) <= 3:
        parser.error('--minimum needs one to three integer components')
    floor += (0,) * (3 - len(floor))
    files, errors = [], []
    for directory in args.directories:
        if not directory.is_dir():
            errors.append({'path': str(directory), 'error': 'Scan root is not a directory'})
            continue
        for path in sorted(directory.rglob('*')):
            # Symlink targets are encountered at their actual paths in the bundle.
            if path.is_symlink() or not path.is_file():
                continue
            try:
                with path.open('rb') as stream:
                    slices = inspect(stream)
                if slices:
                    files.append({'path': str(path), 'slices': slices})
            except (OSError, ValueError, struct.error) as error:
                errors.append({'path': str(path), 'error': str(error)})
    violations = [{'path': row['path'], **slice_} for row in files for slice_ in row['slices']
                  if tuple(slice_['minimum']) > floor]
    report = {'minimum': list(floor), 'files': files, 'violations': violations, 'errors': errors}
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Inspected {len(files)} Mach-O files; {len(violations)} deployment violations; {len(errors)} scan errors.')
    for row in violations + errors:
        print(json.dumps(row))
    return 2 if errors or not files else 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())
