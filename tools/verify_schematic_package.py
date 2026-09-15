#!/usr/bin/env python3
"""Check a Rev A schematic package and local documentation links.

This checks file/record consistency, not electrical correctness or PDF layout.
Only the Python standard library is required.
"""

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('id', 'net', 'source', 'destination', 'wire', 'notes', 'status')
TABLE_FIELDS = FIELDS[:-1]
LINK = re.compile(r'!?\[[^\]\n]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+"[^"]*")?\s*\)')


def check_package(package, errors):
    """Compare the human wire schedule to all records in the JSON schedule."""
    json_path = package / 'connection-netlist.json'
    table_path = package / 'connection-list.md'
    try:
        netlist = json.loads(json_path.read_text(encoding='utf-8'))
        connections = netlist['connections']
        if netlist.get('revision') != 'A':
            errors.append('Expected revision A; this verifier intentionally checks the Rev A baseline.')
        if not isinstance(connections, list):
            raise ValueError('connections must be a list')
        if len(connections) != 142:
            errors.append(f'Rev A must contain 142 connection records; found {len(connections)}.')
        ids = set()
        for number, wire in enumerate(connections, 1):
            if not isinstance(wire, dict):
                errors.append(f'Connection {number} is not an object.')
                continue
            if any(not isinstance(wire.get(key), str) or not wire[key].strip() for key in FIELDS):
                errors.append(f'Connection {number} has missing or empty string fields.')
                continue
            if wire['id'] in ids:
                errors.append(f'Duplicate connection ID: {wire["id"]}')
            ids.add(wire['id'])
        expected = [
            [wire.get(key, '').replace('|', '/') for key in TABLE_FIELDS]
            for wire in connections if isinstance(wire, dict)
            and all(isinstance(wire.get(key), str) for key in TABLE_FIELDS)
        ]
        actual = []
        for line in table_path.read_text(encoding='utf-8').splitlines():
            if not line.startswith('| '):
                continue
            row = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if row[0] != 'ID':
                actual.append(row)
        if actual != expected:
            errors.append('connection-list.md table differs from connection-netlist.json (content or order).')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'Cannot validate connection schedules: {exc}')

    try:
        manifest = json.loads((package / 'render-manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, list) or [p.get('page') for p in manifest] != list(range(1, 30)):
            errors.append('Expected manifest entries for PDF pages 1 through 29.')
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        errors.append(f'Cannot validate page manifest: {exc}')

    pdf = package / 'PalmPilot_Full_Schematic_and_Build_Guide.pdf'
    try:
        with pdf.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                errors.append('The schematic PDF has an invalid file signature.')
    except OSError as exc:
        errors.append(f'Cannot read schematic PDF: {exc}')

    sheets = sorted((package / 'schematic-sheets').glob('*.svg'))
    if len(sheets) != 11:
        errors.append(f'Expected 11 SVG schematic sheets; found {len(sheets)}.')
    for sheet in sheets:
        try:
            if ET.parse(sheet).getroot().tag != '{http://www.w3.org/2000/svg}svg':
                errors.append(f'{sheet.name}: root is not SVG.')
        except (OSError, ET.ParseError) as exc:
            errors.append(f'{sheet.name}: {exc}')
    return len(sheets)


def check_links(paths, errors):
    """Check inline Markdown links; skip remote URLs, anchors and fenced code."""
    markdown_files = set()
    for item in paths:
        path = Path(item)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_dir():
            markdown_files.update(path.rglob('*.md'))
        elif path.is_file():
            markdown_files.add(path)
        else:
            errors.append(f'Documentation path does not exist: {item}')
    count = 0
    for path in sorted(markdown_files):
        in_fence = None
        for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            fence = re.match(r'^\s*(`{3,}|~{3,})', line)
            if fence:
                if in_fence is None:
                    in_fence = fence.group(1)[0]
                elif fence.group(1)[0] == in_fence:
                    in_fence = None
                continue
            if in_fence:
                continue
            # Inline code examples are not rendered as links by Markdown.
            line = re.sub(r'`[^`]*`', '', line)
            for match in LINK.finditer(line):
                target = match.group(1) or match.group(2)
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                count += 1
                target_path = Path(unquote(parsed.path))
                try:
                    label = path.relative_to(ROOT)
                except ValueError:
                    label = path
                if target_path.is_absolute():
                    errors.append(f'{label}:{line_number}: machine-specific absolute link: {target}')
                    continue
                if not (path.parent / target_path).resolve().exists():
                    errors.append(f'{label}:{line_number}: missing link target: {target}')
    return len(markdown_files), count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-dir', type=Path, default=Path('hardware/schematics/rev-a'),
                        help='Rev A package directory (relative to repository root; default: hardware/schematics/rev-a)')
    parser.add_argument('--paths', nargs='+', default=['hardware/schematics'],
                        help='Markdown files or directories to check (relative to repository root)')
    args = parser.parse_args()
    package = args.package_dir.expanduser()
    if not package.is_absolute():
        package = ROOT / package
    errors = []
    sheet_count = check_package(package, errors)
    document_count, link_count = check_links(args.paths, errors)
    if errors:
        print('\n'.join(f'ERROR: {error}' for error in errors), file=sys.stderr)
        return 1
    print(f'PASS: 142 connection records match; {sheet_count} SVG sheets parse; '
          f'{link_count} local links resolve across {document_count} Markdown files.')
    print('This is a documentation consistency check, not an electrical or hardware test.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
