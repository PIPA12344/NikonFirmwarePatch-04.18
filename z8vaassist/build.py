"""Build an offline View Assist candidate: 04.18 two-row Log build + custom-Log VA tables.

Never touches a card or camera. Usage (from the workspace root):
    .venv\\Scripts\\python.exe -m z8vaassist.build Z_8_0311.bin build\\<new directory>
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from z8cardwav import stack  # noqa: E402
from z8prores.package import Package, require_official_input  # noqa: E402
from z8vaassist import patcher as p  # noqa: E402
from z8vaassist.verify import GAMUT, base_payload, module_name, verify  # noqa: E402

README = """EXPERIMENTAL CUSTOM-LOG VIEW ASSIST BUILD
Identity: {identity}.
Built from official Z8 C 3.11 using the four base features, two custom Log rows, card WAV,
and gated custom-Log View Assist tables. No camera or card is operated by this tool.
See docs/release-04.23.md for use, expected SHA256, limitations and hardware feedback scope.
The 04.23 tested card/file showed CUS on first selection and clean first-shot audio;
this does not qualify other WAVs, restore, shooting modes or display outputs.
"""


def build(stock_path, output, version='04.23', tag='', gamut=GAMUT):
    output = Path(output)
    p.need(not output.exists(), 'Output directory already exists')
    raw = Path(stock_path).read_bytes()
    require_official_input(raw)
    original = Package(raw)
    base, _, base_meta = base_payload(original.eg, version, tag, keep=output.with_name(output.name + '-card-wav-build'), gamut=gamut)
    payload, image, meta = p.apply(original.eg, base)
    name = module_name(version, tag)
    packet = stack.pack(original, payload, name)
    _, report = verify(raw, packet, version, tag, gamut)
    identity = version + ('.' + tag if tag else '')
    meta.update(status='EXPERIMENTAL_OFFLINE_ONLY', output_identity=identity, input_sha256=p.sha(raw),
                output_sha256=p.sha(packet), base=f'04.18 two-row recipe ({gamut}, card WAV)',
                card_wav=base_meta.get('card_wav'),
                created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(), verification=report)
    output.mkdir(parents=True)
    firmware = 'Z_8_' + version.replace('.', '') + '.bin'
    with (output / firmware).open('xb') as f:
        f.write(packet)
    p.need(p.sha((output / firmware).read_bytes()) == p.sha(packet), 'Firmware readback mismatch')
    (output / 'modified-main.bi').write_bytes(payload[:-2])
    (output / 'manifest.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    (output / 'SHA256SUMS.txt').write_text(p.sha(packet) + '  ' + firmware + '\n', encoding='ascii')
    readme = README.format(identity=identity)
    if (base_meta.get('card_wav', {}).get('confirmation_retry')
            and not base_meta.get('card_wav', {}).get('staged_confirmation')):
        readme += ('04.22: a consistency mismatch triggers one fresh complete two-import pair (maximum four imports).\n'
                   'Only a matching pair is published; read errors and persistent mismatches preserve the old selection.\n'
                   'This is an unverified workaround candidate for the camera-reported first-selection failure.\n')
    if base_meta.get('card_wav', {}).get('staged_confirmation'):
        readme += ('04.23 replaces content-cache confirmation with two independent unpublished PCM staging buffers.\n'
                   'All native WAV reads, including headers, use one dedicated aligned 4096-byte IO buffer,\n'
                   'with native cache clean/invalidate before and after each completed read.\n'
                   'Full PCM bytes and all metadata must agree before preparing an audio buffer.\n'
                   'The prepared audio buffer is read back after cache maintenance; only a successful bind\n'
                   'transfers it to the immutable content cache. Rejected imports do not consume cache slots.\n'
                   'WAV diff XX @XXXXXX identifies a persistent staging difference; WAV copy diff identifies\n'
                   'a copy/cache readback failure. These are diagnostic failures, never accepted as audio.\n'
                   'This changes the import implementation; real-card cache behavior and first-shot audio\n'
                   'are only qualified by the separate, limited user feedback recorded in docs/release-04.23.md.\n')
    (output / 'READ-ME-FIRST.txt').write_text(readme, encoding='utf8')
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('stock', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--version', default='04.23')
    parser.add_argument('--gamut', default=GAMUT, help='rwg-slog3 (04.21 on) or rwg-slog3-dual (04.18-04.20 row names)')
    parser.add_argument('--tag', default='')
    args = parser.parse_args()
    meta = build(args.stock, args.output, args.version, args.tag, args.gamut)
    print(json.dumps(dict(output=str(args.output.resolve()), identity=meta['output_identity'],
                          sha256=meta['output_sha256'], passed=meta['verification']['passed'],
                          changed_bytes=meta['verification']['changed_bytes'],
                          selectors=meta['verification']['va_selectors']), indent=2))


if __name__ == '__main__':
    main()
