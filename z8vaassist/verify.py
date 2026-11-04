"""Independent check of a View Assist candidate: rebuild, bounded diff, emulation."""
import binascii

from features import FEATURES
from z8cardwav import stack
from z8log3g10.emulation import verify_matrix_routines, verify_metadata_routines, verify_routines
from z8log3g10.verify import expected_payload
from z8prores.package import Package, require_official_input
from . import emulation
from . import patcher as p

GAMUT = 'rwg-slog3'           # 04.21 on: Log3G10 row without "test"
GAMUT_0418 = 'rwg-slog3-dual'  # 04.18 .. 04.20


def module_name(version, tag):
    return 'eg2070_' + version.replace('.', '') + tag + '.bi'


def base_payload(stock_eg, version, tag, keep=None, gamut=GAMUT):
    """The 04.18 two-row recipe (four features, card WAV) under the requested identity and row names."""
    reference, _, _ = expected_payload(stock_eg, FEATURES, '04.18', '', GAMUT_0418, True)
    p.need(p.sha(reference[:-2]) == p.BASE_0418_SHA, '04.18 recipe no longer reproduces the released MAIN')
    return expected_payload(stock_eg, FEATURES, version, tag, gamut, True, keep)


def verify(original, packet, version, tag, gamut=GAMUT):
    require_official_input(original)
    before = Package(original)
    eg = stack.unpack(before, packet, module_name(version, tag))
    base, _, base_meta = base_payload(before.eg, version, tag, gamut=gamut)
    expected, image, meta = p.apply(before.eg, base)
    p.need(eg == expected, 'Candidate differs from the bounded recipe')
    p.need(binascii.crc_hqx(eg, 0) == 0, 'EG CRC invalid')
    allowed = [(e['offset'], e['end']) for e in image.edits] + [(len(eg) - 2, len(eg))]
    changed = [i for i in range(len(eg)) if eg[i] != base[i]] if len(eg) == len(base) else None
    p.need(changed is not None, 'EG length changed')
    p.need(all(any(a <= i < b for a, b in allowed) for i in changed), 'Bytes changed outside declared edits')
    report = dict(passed=True, packet_sha256=p.sha(packet), eg_sha256=p.sha(eg), base_eg_sha256=p.sha(base),
                  base_0418_reproduced=True, changed_bytes=len(changed),
                  edits=[dict(va=hex(e['offset'] + p.BASE), bytes=e['end'] - e['offset'], purpose=e['purpose'])
                         for e in image.edits],
                  va_selectors=emulation.verify(before.eg, eg[:-2]))
    labels = {k: int(v, 16) for k, v in base_meta['labels'].items()}
    report['log_rows_arm'] = verify_routines(before.eg, eg, labels, gamut)
    report['log_metadata_arm'] = verify_metadata_routines(before.eg, eg, gamut)
    report['log_matrix_arm'] = verify_matrix_routines(before.eg, eg, gamut)
    report['card_wav'] = base_meta.get('card_wav')
    report['base_gamut'] = gamut
    report['camera_verified'] = False
    report['limitations'] = [
        'Card WAV confirmation is a workaround candidate; cache/DMA and audible output need real-camera validation',
        'Static trace + emulation of selector code only; no display hardware, pixels or panel colour checked',
        'Assumes the live-view display input is the 04.18 private Lut1 code (Log3G10 /1024, S-Log3 /1023)',
        'dev1 rows stay native N-Log; dev/sub meaning (LCD/EVF/HDMI) not established',
        'Switch change relies on the 04.18 forced tone transition to rebuild the display parameters',
        'Tables target the stock N-Log View Assist look; very bright saturated blues differ (S12 limit)',
    ]
    return meta, report


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--version', default='04.23')
    parser.add_argument('--tag', default='')
    parser.add_argument('--gamut', default=GAMUT)
    args = parser.parse_args()
    _, report = verify(args.stock.read_bytes(), args.candidate.read_bytes(), args.version, args.tag, args.gamut)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
