"""Separate verification entry: exact input, envelopes, edits and ARM paths.

Byte reconstruction shares the patch implementation; native-routine
emulation and the semantic/table assertions are additional checks.
"""
import binascii
import struct
from features import build as feature_build
from z8prores.package import Package, require_official_input
from . import patcher as p
from .emulation import verify_routines, verify_metadata_routines
from z8cardwav import stack


def expected_payload(stock, features, version, tag, gamut='bt2020', card_wav=False, keep=None,
                     compiler='clang', code_source='prebuilt', card_wav_source='prebuilt'):
    base, _ = feature_build(stock, version, tag, features, compiler, code_source)
    image, meta = p.apply(stock, base, gamut)
    result = bytearray(image.new)
    result[-2:] = binascii.crc_hqx(result[:-2], 0).to_bytes(2, 'big')
    if card_wav:
        result, meta['card_wav'] = stack.stack(stock, bytes(result), keep=keep, code_source=card_wav_source)
    return bytes(result), image, meta


def verify_candidate(original, candidate, features, version, tag, arm=True, gamut='bt2020', card_wav=False,
                     compiler='clang', code_source='prebuilt', card_wav_source='prebuilt'):
    require_official_input(original)
    before = Package(original)
    wanted_name = 'eg2070_' + version.replace('.', '') + tag + '.bi'
    if card_wav:
        after_eg = stack.unpack(before, candidate, wanted_name)
    else:
        after = Package(candidate)
        after_eg = after.eg
        p.need(after.modules[2]['name'] == wanted_name, 'Experimental module identity differs')
        p.need(before.body[:112] == after.body[:112] and before.body[128:581844] == after.body[128:581844], 'Unselected package headers changed')
        end = 581844 + len(before.eg)
        p.need(before.body[end:-16] == after.body[end:-16] and before.body[-14:] == after.body[-14:], 'Unselected package modules/trailer changed')
    expected, image, meta = expected_payload(before.eg, features, version, tag, gamut, card_wav,
                                             compiler=compiler, code_source=code_source, card_wav_source=card_wav_source)
    p.need(after_eg == expected, 'Candidate differs from bounded experimental recipe')
    p.need(after_eg[p.STOCK_LUT:p.STOCK_LUT + 3 * 458] == before.eg[p.STOCK_LUT:p.STOCK_LUT + 3 * 458], 'Original N-Log table changed')
    p.need(after_eg[0x4040AB2:p.STOCK_LUT] == before.eg[0x4040AB2:p.STOCK_LUT], 'Original SDR rows changed')
    p.need(after_eg[0x404156E:0x4041ACC] == before.eg[0x404156E:0x4041ACC], 'Original HLG rows changed')
    p.need(after_eg[0x4042282:0x4042BAE] == before.eg[0x4042282:0x4042BAE], 'Original gamma/gain rows changed')
    p.need(p.property_default(after_eg, p.FLAG_PROPERTY) == 0, 'Startup switch must be off')
    modes = p.modes(gamut)
    for r in modes.values():
        private_lut = struct.unpack_from('<229H', after_eg, r['lut'] - p.BASE)
        private_nlg = struct.unpack_from('<229H', after_eg, r['nlg'] - p.BASE)
        p.need(private_nlg == tuple(min(4092, (v + 4) // 8) for v in private_lut), 'Private NlgGamma is not the 12-bit private Lut1')
    profile = modes[1]
    targets = ' / '.join(r['target'] for r in modes.values())
    pictures = ' / '.join(r['picture'].decode() for r in modes.values())
    report = dict(passed=True, input_sha256=p.sha(original), candidate_sha256=p.sha(candidate),
                  original_curves_preserved=True, private_nlg_gamma_paired=True, package_integrity=True,
                  exact_reconstruction=True, camera_verified=False,
                  limitations=[(targets + ' matrix inserted; hardware ordering/primaries unverified' if 'matrix' in profile else 'BT.2020 only; RWG not implemented'),
                               'File tags: primaries/transfer unspecified, Picture Control ' + pictures + '; no standard code, manual interpretation needed',
                               'Switch stored in unreferenced native property 0x03001229; reload after power-off not camera verified',
                               'Selector gates on current file type, not historical clip identity',
                               'No Z8 sensor/ISP pixel or thermal validation'])
    if arm:
        report['arm'] = verify_routines(before.eg, after_eg, {k:int(v,16) for k,v in meta['labels'].items()}, gamut)
        report['metadata_arm'] = verify_metadata_routines(before.eg, after_eg, gamut)
        if 'matrix' in profile:
            from .emulation import verify_matrix_routines
            report['rwg_matrix_arm' if gamut == 'rwg-research' else 'gamut_matrix_arm'] = verify_matrix_routines(before.eg, after_eg, gamut)
    report['gamut_option'] = gamut
    report['camera_gamut_verified'] = False
    return report
