"""Select private View Assist tables for the 04.18 custom Log rows.

C3.11 View Assist (traced statically):
  40e9a1f4  display paths only: VA type 1 when cfg+0x310 (property 0x2303) is 1
            and cfg+0x3d8 is 2 (N-Log); written to driver parameter +0x3c.
  402cdfa0  re-applies tables whenever mode or VA type changes.
  402d197c  VA type -> matrix descriptor pointer table (N-Log: 0x4167a2a0).
  402d1ad0  VA type -> matrix/curve A/curve B pointer tables (N-Log: a2a0/a3a0/a3c0).

This patch makes 40e9a1f4 emit VA type 3 (switch 1, Log3G10/RWG) or 4
(switch 2, S-Log3/S-Gamut3) under the same gate 04.18 uses for its private
Lut1, and teaches both selectors those two values. Because the VA type
changes with the switch, the native change check in 402cdfa0 re-uploads the
tables. Types 0/1/2 keep their native paths byte-for-byte. Recording paths
never get a non-zero VA type natively, so recorded data is not affected.

From 04.21 the Video file type page also names the custom rows: 4056cd84
writes each row's tone text, and for the H.265 10-bit row (tone property
0x0600124A) value 2 writes "N-Log" inline at 4056cf50. That branch now
writes "Log3G10" for switch 1 and "S-Log3" for switch 2.
"""
import binascii
import hashlib
import json
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from z8prores.a64 import Block
from z8prores.menu import Image
from z8log3g10 import patcher as log

BASE = log.BASE
STOCK_SHA = log.STOCK_SHA
# 04.18 two-row payload (without CRC), rebuilt exactly from Z_8_0311.bin.
BASE_0418_SHA = '0488c9e94295199b62964d4c365fcd1bdc9e62b853307f9e5906eea39e043cbe'

CODE = 0x40B0C000   # zero in C3.11 and 04.18, no references (checked by need_free)
DATA = 0x40B0D000
FREE_END = 0x40B10000

SUB_INDEX = 0xA02810470     # u32 read by both native selectors
NLOG_M, NLOG_A, NLOG_B = 0x4167A2A0, 0x4167A3A0, 0x4167A3C0
DESC_BYTES, CURVE_BYTES = 0x18, 0x80

VA_SITE = 0x40E9A2EC        # mov w10,#1 (N-Log VA type); 40e9a2f0 b 40e9a568 follows
VA_RESUME = 0x40E9A2F0
M_SITE = 0x402D1A34         # cmp w1,#1 in 402d197c
M_NLOG = 0x402D1A80
M_REST = 0x402D1A3C
M_JOIN = 0x402D19E8         # x10=table, x9=sub, x8=dev
C_SITE = 0x402D1C34         # cmp w0,#1 in 402d1ad0
C_NLOG = 0x402D1CAC
C_REST = 0x402D1C3C
C_JOIN = 0x402D1B90         # x10/x11 already +dev*16, x12 raw, w13=sub, x8=dev

FT_SITE = 0x4056CF50        # H.265 10-bit row, tone 2: mov w9,#0x2d4e ("N-Lo" + "g" into [sp])
FT_RESUME = 0x4056CFAC      # mov w2,#0x46; mov x0,sp; then the row text call

SITES = {VA_SITE: bytes.fromhex('ea030032'), M_SITE: bytes.fromhex('3f040071'),
         C_SITE: bytes.fromhex('1f040071'), FT_SITE: bytes.fromhex('c9a98552')}
# Native code the hooks rely on, checked before patching.
CONTEXT = {VA_RESUME: bytes.fromhex('9e000014'), M_JOIN: bytes.fromhex('4811088b130d098b'),
           C_JOIN: bytes.fromhex('8811088b490d0d8b'),
           0x402D1A38: bytes.fromhex('40020054'), C_SITE + 4: bytes.fromhex('a0030054'),
           FT_SITE + 4: bytes.fromhex('e80c805289e9ad72e80b0079e90300b9'),
           FT_RESUME: bytes.fromhex('c2088052e0030091')}

MODES = (('log3g10_rwg', 3), ('slog3_sgamut3', 4))   # switch value k -> VA type k + 2
FT_TEXT = {1: b'Log3G10', 2: b'S-Log3'}               # switch value -> file type page tone text


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tables():
    data = json.loads((Path(__file__).with_name('tables.json')).read_text())
    for mode, _ in MODES:
        for row in data['modes'][mode]:
            m, y, k = row['matrix'], row['curve_a_y'], row['curve_a_knots']
            need(len(m) == 9 and all(-2048 <= v <= 2047 for v in m), f'{mode} matrix outside S12')
            need(all(sum(m[i:i + 3]) == 1024 for i in (0, 3, 6)), f'{mode} matrix row sum')
            need(len(y) == 33 and all(0 <= v <= 0x3FFF for v in y) and y == sorted(y), f'{mode} curve A values')
            # Every stock curve uses power-of-two segment widths; 04.19 with free knots
            # gave wildly wrong colours on camera, so curve A keeps the stock knots.
            need(k == list(range(32, 1024, 32)), f'{mode} curve A knots must be the stock 32..992')
    return data


def rd(eg, va, n):
    return eg[va - BASE:va - BASE + n]


def ptr(eg, va):
    return struct.unpack('<Q', rd(eg, va, 8))[0]


def ram_alias(eg, va, n):
    """Initialised RAM bytes live in the EG at the boot-descriptor copy offset."""
    return eg[va - 0xA02808000 + 0x4B1BE30 - (0xA02810E30 - 0xA02808000):][:n]


def layout():
    """Data block: four pointer tables (dev0 sub0, dev0 sub1, dev1 sub0, dev1 sub1), then rows."""
    at, out = DATA, {}
    for mode, _ in MODES:
        for kind in ('m', 'a'):
            out[f'{mode}_{kind}_table'] = at
            at += 32
    for mode, _ in MODES:
        for sub in (0, 1):
            out[f'{mode}_m{sub}'] = at
            at += DESC_BYTES
    at = (at + 15) & ~15
    for mode, _ in MODES:
        for sub in (0, 1):
            out[f'{mode}_a{sub}'] = at
            at += CURVE_BYTES
    out['end'] = at
    need(at <= FREE_END, 'data overflow')
    return out


def data_block(eg, t):
    L = layout()
    blob = bytearray(L['end'] - DATA)

    def put(va, b):
        blob[va - DATA:va - DATA + len(b)] = b

    for mode, _ in MODES:
        for sub, row in enumerate(t['modes'][mode]):
            native = ram_alias(eg, ptr(eg, NLOG_M + 8 * sub), DESC_BYTES)
            need(native[:2] == b'\1\1', 'native N-Log VA enables differ')
            put(L[f'{mode}_m{sub}'], native[:2] + struct.pack('<9h', *row['matrix']) + native[20:])
            put(L[f'{mode}_a{sub}'], struct.pack('<33H', *row['curve_a_y']) + struct.pack('<31H', *row['curve_a_knots']))
        # dev1 keeps the native N-Log rows: its descriptor format is not understood.
        mt = [L[f'{mode}_m0'], L[f'{mode}_m1'], ptr(eg, NLOG_M + 16), ptr(eg, NLOG_M + 24)]
        at = [L[f'{mode}_a0'], L[f'{mode}_a1'], ptr(eg, NLOG_A + 16), ptr(eg, NLOG_A + 24)]
        put(L[f'{mode}_m_table'], struct.pack('<4Q', *mt))
        put(L[f'{mode}_a_table'], struct.pack('<4Q', *at))
    return bytes(blob), L


def code_block(L):
    b = Block(CODE)
    # 40e9a2ec: w9 == 2 (N-Log) here and is read again at 40e9a2fc; x10 is the result.
    b.label('va_type')
    b.mov_x64(10, log.FLAG)
    b.ldrb_w(10, 10)
    b.cbz_w(10, 'va_native')
    b.cmp_wi(10, 2)
    b.b_cond('hi', 'va_native')
    b.mov_x64(9, log.FILETYPE_RAM)
    b.ldr_w(9, 9)
    b.cmp_wi(9, log.H265_FILETYPE)
    b.b_cond('ne', 'va_native')
    b.mov_x64(9, log.TONE_RAM)
    b.ldr_w(9, 9)
    b.cmp_wi(9, log.NLOG_GUI_TONE)
    b.b_cond('ne', 'va_native')
    b.add_xi(10, 10, 2)
    b.b('va_done')
    b.label('va_native')
    b.mov_w(10, 1)
    b.label('va_done')
    b.mov_w(9, 2)
    b.b(VA_RESUME)

    # 402d1a34 in 402d197c: w1 = VA type, x8 = dev byte.
    b.label('matrix_pick')
    for mode, value in MODES:
        b.cmp_wi(1, value)
        b.b_cond('eq', f'matrix_{mode}')
    b.cmp_wi(1, 1)
    b.b_cond('ne', 'matrix_rest')
    b.b(M_NLOG)
    b.label('matrix_rest')
    b.b(M_REST)
    for mode, _ in MODES:
        b.label(f'matrix_{mode}')
        b.mov_x64(10, L[f'{mode}_m_table'])
        b.b('matrix_join')
    b.label('matrix_join')
    b.mov_x64(9, SUB_INDEX)
    b.ldr_w(9, 9)
    b.b(M_JOIN)

    # 402d1c34 in 402d1ad0: w0 = VA type, x8 = dev byte.
    b.label('curve_pick')
    for mode, value in MODES:
        b.cmp_wi(0, value)
        b.b_cond('eq', f'curve_{mode}')
    b.cmp_wi(0, 1)
    b.b_cond('ne', 'curve_rest')
    b.b(C_NLOG)
    b.label('curve_rest')
    b.b(C_REST)
    for mode, _ in MODES:
        b.label(f'curve_{mode}')
        b.mov_x64(10, L[f'{mode}_m_table'])
        b.mov_x64(11, L[f'{mode}_a_table'])
        b.b('curve_join')
    b.label('curve_join')
    b.mov_x64(12, NLOG_B)          # curve B stays native N-Log
    b.mov_x64(9, SUB_INDEX)
    b.ldr_w(13, 9)
    b.add_x(10, 10, 8, 4)
    b.add_x(11, 11, 8, 4)
    b.b(C_JOIN)

    # 4056cf50: the H.265 10-bit row shows N-Log; name the custom row instead.
    # Eight bytes at [sp], NUL padded; the native text was six. w8/w9 are scratch here.
    def text(name):
        return int.from_bytes(name.ljust(8, b'\0'), 'little')
    b.label('ftype_text')
    b.mov_x64(9, log.FLAG)
    b.ldrb_w(9, 9)
    b.mov_x64(8, text(b'N-Log'))
    for value, name in FT_TEXT.items():
        b.cmp_wi(9, value)
        b.b_cond('ne', f'ftype_not{value}')
        b.mov_x64(8, text(name))
        b.label(f'ftype_not{value}')
    b.str_x(8, 31)
    b.b(FT_RESUME)
    need(b.here <= DATA, 'code overflow')
    return b


def hook(site, target):
    b = Block(site)
    b.b(target)
    return b.bytes()


def need_free(eg, lo, hi):
    need(not any(eg[lo - BASE:hi - BASE]), 'patch area is not zero')


def apply(stock_eg, base_payload):
    """base_payload: finished EG of the two-row build, CRC included. Returns (payload, image, meta)."""
    need(sha(stock_eg) == STOCK_SHA, 'stock C3.11 MAIN required')
    eg = base_payload[:-2]
    need(binascii.crc_hqx(base_payload, 0) == 0, 'base EG CRC invalid')
    for va, b in {**SITES, **CONTEXT}.items():
        need(rd(eg, va, len(b)) == b == rd(stock_eg, va, len(b)), f'unexpected bytes at {va:#x}')
    need_free(eg, CODE, FREE_END)
    need_free(stock_eg, CODE, FREE_END)
    for va in (NLOG_M, NLOG_A, NLOG_B):
        need(rd(eg, va, 32) == rd(stock_eg, va, 32), 'native N-Log VA pointer table differs')
    t = tables()
    blob, L = data_block(stock_eg, t)
    code = code_block(L)
    img = Image(base_payload)
    img.put(CODE - BASE, code.bytes(), 'VA type and table selectors for custom Log rows', expect_zero=True)
    img.put(DATA - BASE, blob, 'Custom Log View Assist pointer tables, matrices and curve A rows', expect_zero=True)
    labels = code.labels
    img.put(VA_SITE - BASE, hook(VA_SITE, labels['va_type']), 'VA type 3/4 for switch 1/2', expect=SITES[VA_SITE])
    img.put(M_SITE - BASE, hook(M_SITE, labels['matrix_pick']), 'Matrix selector: VA types 3/4', expect=SITES[M_SITE])
    img.put(C_SITE - BASE, hook(C_SITE, labels['curve_pick']), 'Curve selector: VA types 3/4', expect=SITES[C_SITE])
    img.put(FT_SITE - BASE, hook(FT_SITE, labels['ftype_text']), 'Video file type page: custom Log tone text',
            expect=SITES[FT_SITE])
    out = bytearray(img.new)
    out[-2:] = binascii.crc_hqx(out[:-2], 0).to_bytes(2, 'big')
    cs = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    meta = dict(code_va=hex(CODE), data_va=hex(DATA),
                labels={k: hex(v) for k, v in {**labels, **L}.items()},
                listing=code.listing(cs),
                hooks={hex(k): next(cs.disasm(rd(out, k, 4), k)).op_str for k in SITES},
                tables_source=t['source'], tables_json_sha256=t['source_json_sha256'],
                va_types={'1': 'native N-Log', '3': 'Log3G10/RWG (switch 1)', '4': 'S-Log3/S-Gamut3 (switch 2)'},
                gate='switch 1 or 2, file type 3 (H.265), GUI tone 2 (N-Log); otherwise native N-Log VA',
                dev1='native N-Log rows kept', curve_b='native N-Log row of the same sub',
                file_type_text={str(k): v.decode() for k, v in FT_TEXT.items()})
    return bytes(out), img, meta
