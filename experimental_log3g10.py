"""Build an offline-only H.265 Log3G10 prototype with optional RWG research matrix for exact Z8 C3.11.

Does not copy to cards, install firmware, alter camera settings or publish.
"""
import argparse
import csv
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import struct
from features import FEATURES, selected_features
from z8prores.package import Package, require_official_input
from z8log3g10 import patcher as p
from z8cardwav import stack
from z8log3g10.curve import input_grid, lut_row, nlog, REC2020_TO_RWG, REC2020_TO_SGAMUT3
from z8log3g10.verify import expected_payload, verify_candidate


def build_experiment(stock_path, output, features=FEATURES, version='04.13', tag='e0', gamut='bt2020', card_wav=False,
                     compiler='clang', code_source='prebuilt', card_wav_source='prebuilt'):
    output = Path(output)
    p.need(not output.exists(), 'Output directory already exists')
    features = selected_features(features)
    p.need(tag == '' or re.fullmatch(r'[a-z][0-9]', tag), 'Invalid experiment tag')
    raw = Path(stock_path).read_bytes()
    require_official_input(raw)
    original = Package(raw)
    keep = output.with_name(output.name + '-card-wav-build') if card_wav else None
    payload, image, meta = expected_payload(original.eg, features, version, tag, gamut, card_wav, keep, compiler, code_source,
                                            card_wav_source)
    module_name = 'eg2070_' + version.replace('.', '') + tag + '.bi'
    packet = stack.pack(original, payload, module_name) if card_wav else original.replace_eg(payload, module_name)[0]
    checked = verify_candidate(raw, packet, features, version, tag, gamut=gamut, card_wav=card_wav,
                               compiler=compiler, code_source=code_source, card_wav_source=card_wav_source)
    rows = [dict(offset=hex(e['offset']), bytes=len(e['new']), purpose=e['purpose'],
                 before_sha256=p.sha(e['old']), after_sha256=p.sha(e['new'])) for e in image.edits]
    meta.update(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                output_identity=version+('.'+tag if tag else ''), base_features=features,
                input_sha256=p.sha(raw), output_sha256=p.sha(packet),
                edits=rows, verification=checked)
    output.mkdir(parents=True, exist_ok=False)
    name = 'Z_8_' + version.replace('.', '') + '.bin'
    with (output/name).open('xb') as f:
        f.write(packet)
    p.need(p.sha((output/name).read_bytes()) == p.sha(packet), 'Firmware readback mismatch')
    (output/'modified-main.bi').write_bytes(payload[:-2])
    (output/'manifest.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False)+'\n', encoding='utf8')
    (output/'verification.json').write_text(json.dumps(checked, indent=2)+'\n', encoding='utf8')
    (output/'SHA256SUMS.txt').write_text(p.sha(packet)+'  '+name+'\n', encoding='ascii')
    transfers = [r['transfer'] for r in p.modes(gamut).values()]
    old = struct.unpack_from('<229H', original.eg, p.STOCK_LUT)
    new = [struct.unpack('<229H', lut_row(t)) for t in transfers]
    with (output/'curve-comparison.csv').open('w', newline='', encoding='utf8') as f:
        writer = csv.writer(f)
        writer.writerow(['grid','linear_reflectance','stock_nlog_15bit',*(t+'_15bit' for t in transfers),
                         'stock_10bit',*(t+'_10bit' for t in transfers),'published_nlog_10bit'])
        for grid, a, *b in zip(input_grid(), old, *new):
            writer.writerow([grid,grid*.18/400,a,*b,a/32,*(v/32 for v in b),nlog(grid*.18/400)])
    if gamut == 'rwg-slog3-dual':
        (output/'gamut-matrix-status.json').write_text(json.dumps(dict(applied_to_firmware=True, pixel_verified=False,
            switch_1_rec2020_to_rwg_linear=REC2020_TO_RWG, switch_2_rec2020_to_sgamut3_linear=REC2020_TO_SGAMUT3),indent=2)+'\n')
    elif gamut == 'sgamut3-slog3':
        (output/'sgamut3-matrix-status.json').write_text(json.dumps(dict(applied_to_firmware=True, pixel_verified=False, rec2020_to_sgamut3_linear=REC2020_TO_SGAMUT3),indent=2)+'\n')
    else:
        (output/'rwg-matrix-status.json').write_text(json.dumps(dict(applied_to_firmware=gamut == 'rwg-research', pixel_verified=False, rec2020_to_rwg_linear=REC2020_TO_RWG),indent=2)+'\n')
    (output/'READ-ME-FIRST.txt').write_text(
        'OFFLINE EXPERIMENTAL PROTOTYPE - NOT CAMERA VERIFIED\n'
        'Tone mode: H.265 10-bit -> Log3G10 / BT.2020.\n'
        'Scene-linear curve change is before H.265 encoding, not a monitor/post LUT.\n'
        'Original N-Log and HLG choices/tables are preserved.\n'
        'Colour remains BT.2020. REDWideGamutRGB is NOT implemented.\n'
        'File tags: HEVC VUI/MOV colr primaries+transfer unspecified, matrix BT.709;\n'
        'Picture Control LOG3G10. No standard code exists; interpret manually as BT.2020 / Log3G10.\n'
        'The switch is stored in native settings; reload after power-off is not camera verified.\n'
        'The live-view tile reads L3G10; native menu summaries/help may still say N-Log.\n'
        'Private 12-bit NlgGamma row pairs with the private Lut1 for Log3G10 jobs.\n'
        '758 ARM routine cases passed; these do not emulate sensor/ISP pixels.\n'
        'Boot/menu/render and camera pixel validation remain required.\n', encoding='utf8')
    if gamut == 'rwg-research':
        (output/'READ-ME-FIRST.txt').write_text(
            'OFFLINE RWG RESEARCH CANDIDATE - NOT CAMERA VERIFIED\n'
            'Menu: H.265 10-bit -> Log3G10 / RWG test.\n'
            'A BT.2020->RWG fixed-point matrix is composed after each fresh native R2Y M1 computation.\n'
            'Matrix arithmetic is ARM-emulated; physical stage ordering and\n'
            'incoming primaries are NOT established by a pixel recording.\n'
            'The target is RWG/Log3G10, not yet a verified colour profile.\n'
            'Private 12-bit NlgGamma row pairs with the private Lut1 for Log3G10 jobs.\n'
            'Original N-Log, HLG and SDR rows/tables are preserved.\n'
            'File tags: HEVC VUI/MOV colr primaries+transfer unspecified (no RWG/Log3G10 code exists),\n'
            'matrix BT.709 kept; Picture Control name LOG3G10. Interpret manually as RWG / Log3G10.\n'
            'Tag routing is ARM-emulated only; check a recorded clip with ffprobe/ExifTool.\n'
            'The switch is stored in a native settings property; reload after power-off is not camera verified.\n'
            'The live-view tile reads L3G10.\n'
            'This is a development candidate; offline checks do not establish camera safety.\n', encoding='utf8')
    if gamut == 'sgamut3-slog3':
        (output/'READ-ME-FIRST.txt').write_text(
            'OFFLINE S-LOG3 CANDIDATE - NOT CAMERA VERIFIED\n'
            'Menu: H.265 10-bit -> S-Log3 / S-Gamut3. This build has no Log3G10 row.\n'
            'Curve: Sony S-Log3 written as 10-bit code values. Black 95, 18% grey 420, 90% white 598.\n'
            'A BT.2020->S-Gamut3 fixed-point matrix is composed after each fresh native R2Y M1 computation.\n'
            'Physical stage ordering, incoming primaries and grid 400 = 18% grey are not established by pixels.\n'
            'Private 12-bit NlgGamma row pairs with the private Lut1.\n'
            'Original N-Log, HLG and SDR rows/tables are preserved.\n'
            'File tags: HEVC VUI/MOV colr primaries+transfer unspecified, matrix BT.709 kept;\n'
            'Picture Control name S-LOG3. Interpret manually as S-Gamut3 / S-Log3, full range.\n'
            'The switch is stored in a native settings property; reload after power-off is not camera verified.\n'
            'The live-view tile reads SLOG3. Not a Sony or Nikon product.\n'
            'This is a development candidate; offline checks do not establish camera safety.\n', encoding='utf8')
    if gamut == 'rwg-slog3-dual':
        (output/'READ-ME-FIRST.txt').write_text(
            'TWO-ROW BUILD 04.18 - CAMERA-VERIFIED ON Z8 BY THE MAINTAINER\n'
            'Menu: H.265 10-bit -> Log3G10 / RWG test (switch 1) or S-Log3 / S-Gamut3 (switch 2).\n'
            'Each row has its own private Lut1, NlgGamma, gamut matrix, Picture Control name and tile.\n'
            'Log3G10 / RWG test: same tables and matrix as 04.16; tile L3G10, Picture Control LOG3G10.\n'
            'S-Log3 / S-Gamut3: same tables and matrix as 04.17; tile SLOG3, Picture Control S-LOG3.\n'
            'Matrices are composed after each fresh native R2Y M1 computation.\n'
            'Original N-Log, HLG and SDR rows/tables are preserved.\n'
            'File tags: HEVC VUI/MOV colr primaries+transfer unspecified, matrix BT.709 kept.\n'
            'Interpret manually from the tile / Picture Control name; S-Log3 clips are full range.\n'
            'The switch is stored in a native settings property and survives power-off.\n'
            'Not a Sony, RED or Nikon product. Unofficial experimental firmware; use at your own risk.\n', encoding='utf8')
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('stock', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--features', nargs='+', choices=FEATURES, default=list(FEATURES))
    parser.add_argument('--gamut', choices=tuple(p.PROFILES), default='bt2020')
    parser.add_argument('--card-wav', action='store_true', help='Add the GPL-3.0-or-later card WAV shutter sound port')
    parser.add_argument('--card-wav-source', choices=('prebuilt', 'source'), default='prebuilt',
                        help='prebuilt fills resources/cardwav.bin from the input; source compiles with LLVM (Z8_LLVM_BIN)')
    parser.add_argument('--code-source', choices=('prebuilt', 'source'), default='prebuilt',
                        help='prebuilt reads resources/*.bin from the v0.3.0-r1 toolkit; source compiles them with --compiler')
    parser.add_argument('--compiler', default='clang', help='Clang executable for --code-source source')
    parser.add_argument('--version', default='04.13')
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument('--tag', default='e0')
    identity.add_argument('--no-tag', action='store_const', dest='tag', const='', help='Use plain version NN.NN with zero-padded fixed identity slots')
    args = parser.parse_args()
    result = build_experiment(args.stock, args.output, args.features, args.version, args.tag, args.gamut, args.card_wav,
                              args.compiler, args.code_source, args.card_wav_source)
    print(json.dumps(dict(output=str(args.output.resolve()), status=result['status'],
                          identity=result['output_identity'], verification=result['verification']), indent=2))


if __name__ == '__main__':
    main()
