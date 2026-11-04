"""Add a fourth H.265 tone choice without changing native enums.

Native N-Log tables and exposure rules remain. BT.2020 is the default;
the optional RWG research build adds a gated M1 matrix composition, and the
S-Log3 / S-Gamut3 build swaps the curve, matrix and names on the same paths.
The added choice routes only H.265 10-bit N-Log Lut1 jobs to a private LUT,
and the matching 12-bit NlgGamma row to a private copy of that curve.
HEVC VUI and MOV colr have no code for RWG or Log3G10, so such movies are
tagged primaries/transfer unspecified (native YCbCr matrix kept) and the
Nikon Picture Control name reads LOG3G10; manual interpretation remains
required. No claim about recorded pixels follows from offline verification.
"""
import hashlib
import struct
import zlib
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from z8prores.a64 import Block
from z8prores.menu import Image
from .curve import REC2020_TO_RWG, REC2020_TO_SGAMUT3, ROW_BYTES, lut_row, nlg_gamma_row, reference_summary
from .label import IMAGE_TABLE, tile_images

BASE = 0x40160000
STOCK_SHA = 'f85e0138e2f5e660ece8560de62e0d12cb795e0e14983e50f20b61dce906c46c'
STOCK_LUT = 0x4041010
STOCK_LUT_VA = BASE + STOCK_LUT
STOCK_LUT_CRC = 0xF4B99215
STOCK_NLG = 0x4042282  # four NlgGamma rows; row 1 is N-Log
STOCK_NLG_VA = BASE + STOCK_NLG
CODE = 0x40B00000
LUT = 0x40B02000
NLG = 0x40B02600  # between the private Lut1 rows and the RWG matrix
GUI = 0x40B03000
TEXT = 0x40B09000
# Unreferenced movie property in the tone's settings group, default 0. Whether
# it survives power-off needs a camera. Reads use the low byte of its backing word.
FLAG_PROPERTY = 0x03001229
FLAG = 0xA03D5C0A0
SETTINGS_TABLE = 0x44DC42D8  # {property, blob offset, size}, 0x431 rows
TABLES = 0x40B10000
END = 0x40B80000
ITEM = 0x35BF
H265_FILETYPE = 3
FILETYPE_RAM = 0xA03D5C014
TONE_PROPERTY = 0x0600124A
NATIVE_ENTRY = 0x4056D384
NATIVE_ACTION = 0x4056DA28
LUT_SITE = 0x4111A4FC
LUT_RESUME = 0x4111A50C
NLG_SITE = 0x4111A6C0  # w9 = selected row, after the INFO+0x43 override
NLG_RESUME = 0x4111A6D8
# File metadata. GUI_GET resolves a property through static descriptor
# tables; TONE_RAM is that table's backing word for TONE_PROPERTY.
PROPERTY_GROUPS = 0x440244C8
PROPERTY_ENTRIES = 0x4400A5C0
TONE_RAM = 0xA03D5C124
NLOG_GUI_TONE = 2
UNSPECIFIED = 2  # ITU-T H.273 primaries/transfer code
META = 0x40B02900
NCLC = META
NCLX = META + 0x10
PICTURE = META + 0x100
VUI_SITE = 0x402F72F8  # encoder config epilogue; +0x1C0.. = VUI fields
VUI_RESUME = 0x402F72FC
COLR_NCLC_SITE = 0x40349A70  # MOV writer veneers, w0 = native HLG
COLR_NCLX_SITE = 0x40349A78
NATIVE_NCLC = 0x40343D48
NATIVE_NCLX = 0x40343D94
NLOG_PICTURE = 0x440E1250  # N-LOG Picture Control definition
PICTURE_BYTES = 0x110
PICTURE_SITE = 0x410A8368
PICTURE_RESUME = 0x410A8378
PICTURE_GET = 0x410AA7B4
PROFILES = {
    'bt2020': dict(transfer='log3g10', menu='Log3G10 / BT.2020', picture=b'LOG3G10', tile='L3G10', target='BT.2020'),
    'rwg-research': dict(transfer='log3g10', menu='Log3G10 / RWG test', picture=b'LOG3G10', tile='L3G10',
                         target='REDWideGamutRGB', matrix=REC2020_TO_RWG),
    'sgamut3-slog3': dict(transfer='slog3', menu='S-Log3 / S-Gamut3', picture=b'S-LOG3', tile='SLOG3',
                          target='S-Gamut3', matrix=REC2020_TO_SGAMUT3),
    # Two rows in one build: switch value 1 selects the first, 2 the second.
    'rwg-slog3-dual': dict(modes=('rwg-research', 'sgamut3-slog3')),
    # Same two rows; the Log3G10 row drops the "test" suffix (04.21 on).
    'rwg-slog3': dict(modes=('rwg-research', 'sgamut3-slog3'), menus=('Log3G10 / RWG', 'S-Log3 / S-Gamut3')),
}
# Each further row keeps its own Lut1, NlgGamma, matrix and Picture Control
# copies at the first row's addresses plus this stride.
MODE_STRIDE = 0x4000
# Live-view tile: fill and outline images, resolved outside the stock table.
TILE_TABLE = META + 0x300  # two {u32 size, u64 data} rows
TILE_PNG = 0x40B0A000
TILE_ID = 0x1862  # first id past the stock image table
TILE_SITE = 0x4041A860
TILE_RESUME = 0x4041A954
NLOG_TILE = 0xA7D, 0xA7E
IMAGE_SITE = 0x4032DC64
IMAGE_RESUME = 0x4032DC68
IMAGE_FIRST = 0xD299AB09  # mov x9,#0xCD58, displaced by the hook
PAGE = 0x4BCC6C0
CALLBACK = 0x4BF3DF8
ROW_SOURCE = 0x3AA6E64
EVENT_SOURCE = 0x3AA6FF0
ENTRY_GET_PREVIOUS = 0x403DBCA8
FIND_ROW = 0x403AF870
HIDE_ROW = 0x403B1ED0
CURSOR = 0x403B0048
MARK = 0x403B00B8
GUARD = 0x403AE0F8
GUI_GET = 0x403EC398
GUI_SET = 0x403EC3C8


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read_item(b, state_reg, out=8):
    b.ldr_x(9, state_reg, 0x50)
    b.ldrh_w(10, state_reg, 0x58)
    b.ldrh_w(out, state_reg, 0x32)
    b.ldr_x(9, 9, 0x10)
    b.add_x(out, out, 10)
    b.mov_w(10, 44)
    b.madd_x(out, out, 10, 9)
    b.ldr_w(out, out, 0x18)


def property_ram(stock, ident):
    # Same lookup as the native getter: group = bits 8-15, index = low byte.
    group = stock[PROPERTY_GROUPS - BASE + 0x30 * (ident >> 8 & 255):][:0x30]
    first, count = struct.unpack_from('<2H', group, 0x18)
    need(any(group[:4]) and ident & 255 < count, 'Property descriptor missing')
    kind, size, ram = struct.unpack_from('<2IQ', stock, PROPERTY_ENTRIES - BASE + 0x18 * (first + (ident & 255)))
    need((kind, size) == (9, 4), 'Property is not a 32-bit word')
    return ram


def property_default(stock, ident):
    group = stock[PROPERTY_GROUPS - BASE + 0x30 * (ident >> 8 & 255):][:0x30]
    first = struct.unpack_from('<H', group, 0x18)[0]
    default = struct.unpack_from('<Q', stock, PROPERTY_ENTRIES - BASE + 0x18 * (first + (ident & 255)) + 16)[0]
    return struct.unpack_from('<I', stock, default - BASE)[0]


def modes(gamut):
    """Switch value -> that row's profile, menu item and private copies."""
    from .matrix import MATRIX_VA
    names = PROFILES[gamut].get('modes', (gamut,))
    menus = PROFILES[gamut].get('menus', [PROFILES[name]['menu'] for name in names])
    return {k + 1: dict(PROFILES[name], name=name, menu=menus[k], item=ITEM + k, string=k, lut=LUT + k * MODE_STRIDE,
                        nlg=NLG + k * MODE_STRIDE, picture_va=PICTURE + k * MODE_STRIDE,
                        matrix_va=MATRIX_VA + k * MODE_STRIDE, tile_ids=(TILE_ID + 2 * k, TILE_ID + 2 * k + 1))
            for k, name in enumerate(names)}


def log3g10_job(b, reg, fail, count=1):
    """Branch to fail unless switch 1..count, H.265 file type and GUI N-Log are set."""
    for address, load, value in ((FLAG, b.ldrb_w, 1), (FILETYPE_RAM, b.ldr_w, H265_FILETYPE),
                                 (TONE_RAM, b.ldr_w, NLOG_GUI_TONE)):
        b.mov_x64(reg, address)
        load(reg, reg)
        if address == FLAG and count > 1:
            b.cbz_w(reg, fail)
            b.cmp_wi(reg, count)
            b.b_cond('hi', fail)
            continue
        b.cmp_wi(reg, value)
        b.b_cond('ne', fail)


def choose(b, flag, moves, fail, name):
    """For switch value k in 1..len(moves), load moves[k-1] {register: constant}; other values go to fail."""
    for value, sets in enumerate(moves, 1):
        b.cmp_wi(flag, value)
        b.b_cond('ne', f'{name}_not{value}')
        for reg, constant in sets.items():
            b.mov_x64(reg, constant)
        b.b(f'{name}_chosen')
        b.label(f'{name}_not{value}')
    b.b(fail)
    b.label(f'{name}_chosen')


def code(gamut='bt2020'):
    m = modes(gamut)
    rows = list(m.values())
    dual = len(m) > 1
    b = Block(CODE)
    b.label('lut')
    b.stp_pre(10, 11, -16)
    b.mov_x64(8, STOCK_LUT_VA)
    b.cmp_wi(9, 1)  # pipeline tone 1=N-Log, 2=HLG (GUI enum differs)
    b.b_cond('ne', 'lut_done')
    if dual:
        b.mov_x64(10, FILETYPE_RAM)
        b.ldr_w(10, 10)
        b.cmp_wi(10, H265_FILETYPE)
        b.b_cond('ne', 'lut_done')
        b.mov_x64(10, FLAG)
        b.ldrb_w(10, 10)
        choose(b, 10, [{8: r['lut']} for r in rows], 'lut_done', 'lut_pick')
    else:
        b.mov_x64(10, FLAG)
        b.ldrb_w(10, 10)
        b.cmp_wi(10, 1)
        b.b_cond('ne', 'lut_done')
        b.mov_x64(10, FILETYPE_RAM)
        b.ldr_w(10, 10)
        b.cmp_wi(10, H265_FILETYPE)
        b.b_cond('ne', 'lut_done')
        b.mov_x64(8, LUT)
    b.label('lut_done')
    b.ldp_post(10, 11, 16)
    b.b(LUT_RESUME)

    # NlgGamma is the 12-bit copy of Lut1, so it follows the same gate.
    # Test the row already selected (forced row 3 stays native) and use
    # only the registers the replaced native sequence writes.
    b.label('nlg')
    b.mov_x64(10, STOCK_NLG_VA)
    b.mov_w(2, ROW_BYTES)
    b.cmp_wi(9, 1)
    b.b_cond('ne', 'nlg_done')
    if dual:
        # w9 must stay 1 on every exit to nlg_done, so only x1 is scratch.
        b.mov_x64(1, FILETYPE_RAM)
        b.ldr_w(1, 1)
        b.cmp_wi(1, H265_FILETYPE)
        b.b_cond('ne', 'nlg_done')
        b.mov_x64(1, FLAG)
        b.ldrb_w(1, 1)
        choose(b, 1, [{10: r['nlg']} for r in rows], 'nlg_done', 'nlg_pick')
    else:
        b.mov_x64(1, FLAG)
        b.ldrb_w(1, 1)
        b.cmp_wi(1, 1)
        b.b_cond('ne', 'nlg_done')
        b.mov_x64(1, FILETYPE_RAM)
        b.ldr_w(1, 1)
        b.cmp_wi(1, H265_FILETYPE)
        b.b_cond('ne', 'nlg_done')
        b.mov_x64(10, NLG)
    b.mov_w(9, 0)
    b.label('nlg_done')
    b.madd_x(1, 9, 2, 10)
    b.b(NLG_RESUME)

    # File metadata. HEVC VUI: label primaries and transfer unspecified;
    # the YCbCr matrix still describes the native encoding, so keep it.
    b.label('vui')
    b.cbnz_w(21, 'vui_done')  # native HLG request
    log3g10_job(b, 8, 'vui_done', len(m))
    b.mov_w(8, UNSPECIFIED)
    b.str_w(8, 19, 0x1C8)
    b.str_w(8, 19, 0x1CC)
    b.label('vui_done')
    b.ldp(19, 30, 0x80)
    b.b(VUI_RESUME)

    # MOV colr template getters: (w0 HLG, x1 &template, x2 &length).
    for name, native, template, size in (('nclc', NATIVE_NCLC, NCLC, 10), ('nclx', NATIVE_NCLX, NCLX, 11)):
        b.label(name)
        b.cbnz_w(0, name + '_native')
        log3g10_job(b, 8, name + '_native', len(m))
        b.mov_x64(8, template)
        b.mov_w(9, size)
        b.str_x(8, 1)
        b.str_w(9, 2)
        b.ret()
        b.label(name + '_native')
        b.b(native)

    # The N-LOG Picture Control definition, as copied into the clip's
    # Picture Control state and as returned by the definition getter.
    def pick(name, fail, moves):
        # After the job gate the switch is 1..n; reload it and take that row's values.
        b.mov_x64(8, FLAG)
        b.ldrb_w(8, 8)
        choose(b, 8, moves, fail, name)

    b.label('picture')
    b.mov_x64(23, NLOG_PICTURE)
    log3g10_job(b, 8, 'picture_done', len(m))
    if dual:
        pick('picture_pick', 'picture_done', [{23: r['picture_va']} for r in rows])
    else:
        b.mov_x64(23, PICTURE)
    b.label('picture_done')
    b.b(PICTURE_RESUME)
    b.label('picture_get')
    b.mov_x64(0, NLOG_PICTURE)
    log3g10_job(b, 8, 'picture_get_done', len(m))
    if dual:
        pick('picture_get_pick', 'picture_get_done', [{0: r['picture_va']} for r in rows])
    else:
        b.mov_x64(0, PICTURE)
    b.label('picture_get_done')
    b.ret()

    # The tile is drawn from the same gate as the recorded job.
    b.label('tile')
    b.mov_w(3, NLOG_TILE[0])
    b.mov_w(4, NLOG_TILE[1])
    log3g10_job(b, 8, 'tile_done', len(m))
    if dual:
        pick('tile_pick', 'tile_done', [{3: r['tile_ids'][0], 4: r['tile_ids'][1]} for r in rows])
    else:
        b.mov_w(3, TILE_ID)
        b.mov_w(4, TILE_ID + 1)
    b.label('tile_done')
    b.b(TILE_RESUME)

    # Image lookup: (x0 &id, x1 out) with out u16 +0, size +4, data +0x10.
    b.label('image')
    b.ldr_w(8, 0)
    b.mov_w(9, TILE_ID)
    b.sub_w(9, 8, 9)
    b.cmp_wi(9, 2 * len(m) - 1)
    b.b_cond('hi', 'image_native')
    b.mov_x64(10, TILE_TABLE)
    b.lsl_wi(9, 9, 4)
    b.add_x(10, 10, 9)
    b.mov_w(9, 0x100)
    b.strh_w(9, 1)
    b.ldr_w(9, 10)
    b.str_w(9, 1, 4)
    b.ldr_x(9, 10, 8)
    b.str_x(9, 1, 0x10)
    b.ret()
    b.label('image_native')
    b._w(IMAGE_FIRST)
    b.b(IMAGE_RESUME)

    # Original entry handles every native row and the original mark.
    # After it, hide the new rows unless the parent is H.265 10-bit.
    b.label('entry')
    b.stp_pre(19, 30, -64)
    b.stp(20, 21, 16)
    b.mov_x(19, 0)
    b.bl(NATIVE_ENTRY)
    b.mov_x(21, 0)
    b.add_xi(0, 31, 32)
    b.mov_w(1, 1)
    b.bl(ENTRY_GET_PREVIOUS)
    b.mov_w(20, 1)
    b.ldr_x(8, 31, 32)
    b.cbz_x(8, 'visibility')
    read_item(b, 8)
    b.mov_w(9, 0x3059)
    b.cmp_w(8, 9)
    b.b_cond('eq', 'show')
    b.mov_w(9, 0x311D)
    b.cmp_w(8, 9)
    b.b_cond('ne', 'visibility')
    b.label('show')
    b.mov_w(20, 0)
    b.label('visibility')
    for r in rows:
        b.mov_x(0, 19)
        b.mov_w(1, r['item'])
        b.bl(FIND_ROW)
        b.mov_wr(1, 0)
        b.mov_wr(2, 20)
        b.mov_x(0, 19)
        b.bl(HIDE_ROW)
    b.cbnz_w(20, 'entry_done')
    b.mov_x64(8, FLAG)
    b.ldrb_w(8, 8)
    if dual:
        # w20 (callee-saved, now free) holds the marked row's item id.
        b.cbz_w(8, 'entry_done')
        b.cmp_wi(8, len(m))
        b.b_cond('hi', 'entry_done')
        b.mov_w(20, ITEM - 1)
        b.add_w(20, 20, 8)
    else:
        b.cmp_wi(8, 1)
        b.b_cond('ne', 'entry_done')
    b.mov_w(0, TONE_PROPERTY & 65535)
    b.movk_w16(0, TONE_PROPERTY >> 16)
    b.bl(GUI_GET)
    b.cmp_wi(0, 2)  # native GUI enum 2=N-Log
    b.b_cond('ne', 'entry_done')
    b.mov_x(0, 19)
    b.mov_w(1, 0x3060)
    b.mov_w(2, 0)
    b.bl(MARK)
    b.mov_x(0, 19)
    b.mov_wr(1, 20) if dual else b.mov_w(1, ITEM)
    b.mov_w(2, 1)
    b.bl(MARK)
    b.bl(GUARD)
    b.cmp_wi(0, 1)
    b.b_cond('eq', 'entry_done')
    b.mov_x(0, 19)
    b.mov_wr(1, 20) if dual else b.mov_w(1, ITEM)
    b.bl(CURSOR)
    b.label('entry_done')
    b.mov_x(0, 21)
    b.ldp(20, 21, 16)
    b.ldp_post(19, 30, 64)
    b.ret()

    # The extra rows map to native tone 2, never to an unsupported value 3.
    # GUI_SET also updates the native settings copy of the flag.
    b.label('action')
    b.stp_pre(19, 30, -48)
    b.mov_x(19, 0)
    b.ldr_x(8, 0)
    read_item(b, 8)
    b.mov_w(9, ITEM)
    b.cmp_w(8, 9)
    b.b_cond('eq', 'action_log')
    for r in rows[1:]:
        b.mov_w(9, r['item'])
        b.cmp_w(8, 9)
        b.b_cond('eq', f"action_log{r['string'] + 1}")
    b.mov_w(9, 0x305E)
    b.cmp_w(8, 9)
    b.b_cond('lo', 'action_native')
    b.mov_w(9, 0x3060)
    b.cmp_w(8, 9)
    b.b_cond('hi', 'action_native')
    b.mov_w(10, 0)
    b.b('action_store')
    for r in rows[1:]:
        b.label(f"action_log{r['string'] + 1}")
        b.mov_w(10, r['string'] + 1)
        b.b('action_store')
    b.label('action_log')
    b.mov_w(10, 1)
    b.label('action_store')
    # Force a real tone transition before native OK installs the final
    # value. Otherwise switching N-Log <-> Log3G10 leaves native enum 2
    # unchanged and the live-view job may retain its old LUT.
    b.mov_w(8, FLAG_PROPERTY & 65535)
    b.movk_w16(8, FLAG_PROPERTY >> 16)
    b.str_w(8, 31, 16)
    b.mov_w(8, TONE_PROPERTY & 65535)
    b.movk_w16(8, TONE_PROPERTY >> 16)
    b.str_w(8, 31, 20)
    b.str_w(10, 31, 24)
    b.str_w(31, 31, 28)
    b.add_xi(0, 31, 16)
    b.add_xi(1, 31, 24)
    b.mov_w(2, 2)
    b.bl(GUI_SET)
    b.label('action_native')
    b.mov_x(0, 19)
    b.bl(NATIVE_ACTION)
    b.ldp_post(19, 30, 48)
    b.ret()
    need(len({'matrix' in r for r in rows}) == 1, 'Either every row or no row composes a matrix')
    if 'matrix' in rows[0]:
        from .matrix import append_hook
        append_hook(b, flag=FLAG, filetype_address=FILETYPE_RAM, filetype_value=H265_FILETYPE,
                    matrices=[r['matrix_va'] for r in rows])
    listing = b.listing(Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN))
    need(len(b.bytes()) < 0x2000, 'Code cave overflow')
    return b.bytes(), b.labels, listing


def string_extension(img, stock, gamut='bt2020'):
    """Append a label after an unused bridge entry; preserve old offsets.

    The bridge spans the gap between old and private text, as the existing
    release's dummy string does. It is never referenced by any menu.
    """
    shared = struct.unpack_from('<Q', img.old, 0x311C5A0)[0] == 0x408E0000
    old_count = 3154 if shared else 3137
    ident = old_count
    labels = [r['menu'].encode('utf-16le') for r in modes(gamut).values()]
    text = b''.join(labels)
    ends = [sum(map(len, labels[:k + 1])) for k in range(len(labels))]
    blob = bytearray()
    for lang in range(36):
        old_va = struct.unpack_from('<Q', img.old, 0x311C5A0 + 8 * lang)[0]
        origin = struct.unpack_from('<Q', stock, 0x387AF58 + 8 * lang)[0]
        old = img.old[old_va - BASE:old_va - BASE + old_count * 4]
        need(len(old) == old_count * 4, 'String table is out of bounds')
        offsets = struct.unpack('<' + str(old_count) + 'i', old)
        new_begin = TEXT - origin
        need(-(1 << 31) <= new_begin and new_begin + len(text) < (1 << 31), 'String extension offsets overflow')
        row = old + struct.pack('<' + str(1 + len(ends)) + 'i', new_begin, *(new_begin + e for e in ends))
        va = TABLES + len(blob)
        blob.extend(row)
        img.put(0x311C5A0 + 8 * lang, struct.pack('<Q', va), 'Log3G10 private language directory')
    need(TABLES + len(blob) <= END, 'String tables overflow')
    img.put(TEXT - BASE, text, 'Log3G10 BT.2020 label', expect_zero=True)
    img.put(TABLES - BASE, blob, 'Log3G10 extended language tables', expect_zero=True)
    return ident, old_count, len(blob)


def apply(stock, baseline, gamut='bt2020'):
    need(gamut in PROFILES, 'Unsupported experimental gamut')
    m = modes(gamut)
    dual = len(m) > 1
    profile = m[1]
    transfer = profile['transfer']
    need(sha(stock) == STOCK_SHA, 'Exact official Z8 C3.11 EG required')
    need(len(baseline) == len(stock), 'Baseline length mismatch')
    rows = stock[STOCK_LUT:STOCK_LUT + 3 * ROW_BYTES]
    need(zlib.crc32(rows) == STOCK_LUT_CRC, 'Stock N-Log LUT identity mismatch')
    need(rows[:ROW_BYTES] == rows[ROW_BYTES:2 * ROW_BYTES] == rows[2 * ROW_BYTES:], 'N-Log lanes differ')
    need(baseline[STOCK_LUT:STOCK_LUT + 3 * ROW_BYTES] == rows, 'Baseline already changes N-Log')
    nlog_gamma = stock[STOCK_NLG + ROW_BYTES:STOCK_NLG + 2 * ROW_BYTES]
    need(struct.unpack('<229H', nlog_gamma) == tuple((v + 4) // 8 for v in struct.unpack('<229H', rows[:ROW_BYTES])),
         'Stock NlgGamma is not the 12-bit N-Log Lut1')
    need(baseline[STOCK_NLG:STOCK_NLG + 4 * ROW_BYTES] == stock[STOCK_NLG:STOCK_NLG + 4 * ROW_BYTES], 'Baseline already changes NlgGamma')
    need(not any(baseline[CODE - BASE:END - BASE]), 'Experimental region is occupied')
    for r in m.values():
        need(struct.pack('<I', r['item']) not in stock[0x3AA0000:0x3C00000], 'Menu item id is in use')
    img = Image(baseline)
    machine, labels, listing = code(gamut)
    label_id, old_entries, table_bytes = string_extension(img, stock, gamut)
    img.put(CODE - BASE, machine, 'Log3G10 selector and menu wrappers', expect_zero=True)
    need(NLG + ROW_BYTES <= 0x40B02800, 'Private NlgGamma overlaps matrix area')
    # Further rows' copies must clear the GUI rows/events and the label text.
    need(not dual or GUI + 0x2000 <= LUT + MODE_STRIDE and PICTURE + PICTURE_BYTES + MODE_STRIDE * (len(m) - 1) <= TEXT,
         'Second-row private copies overlap')
    for k, r in m.items():
        suffix = '' if k == 1 else f" (row {k}, {r['transfer']})"
        img.put(r['lut'] - BASE, lut_row(r['transfer']) * 3, 'Private Log3G10 three-lane Lut1' + suffix, expect_zero=True)
        if k == 1:
            lut_expect = bytes.fromhex('080282d24883a8f20800c0f20800e0f2')
            branch = Block(LUT_SITE); branch.b(labels['lut']); branch.nop(); branch.nop(); branch.nop()
            img.put(LUT_SITE - BASE, branch.bytes(), 'Route H.265 10-bit N-Log job to selected LUT', expect=lut_expect)
        img.put(r['nlg'] - BASE, nlg_gamma_row(r['transfer']), 'Private Log3G10 NlgGamma row' + suffix, expect_zero=True)
    branch = Block(NLG_SITE); branch.b(labels['nlg'])
    for _ in range(5):
        branch.nop()
    img.put(NLG_SITE - BASE, branch.bytes(), 'Route Log3G10 job NlgGamma row',
            expect=bytes.fromhex('4a5084d24a83a8f2423980520a00c0f20a00e0f22129029b'))

    need(property_ram(stock, 0x06001206) == FILETYPE_RAM and property_ram(stock, TONE_PROPERTY) == TONE_RAM,
         'Movie file type/tone property storage differs')
    need(property_ram(stock, FLAG_PROPERTY) == FLAG and property_default(stock, FLAG_PROPERTY) == 0,
         'Flag property storage differs')
    need(struct.pack('<3I', FLAG_PROPERTY, 800, 2) in stock[SETTINGS_TABLE - BASE:SETTINGS_TABLE - BASE + 0x431 * 12],
         'Flag property is not in the native settings table')
    need(stock[0x42AB2310 - BASE:0x42AB232F - BASE] == b'nclc\0\1\0\1\0\1nclc\0\x09\0\x12\0\x09nclx\0\1\0\1\0\1\x80',
         'Native MOV colr templates differ')
    img.put(NCLC - BASE, b'nclc\0\2\0\2\0\1', 'Log3G10 MOV colr nclc: unspecified primaries/transfer', expect_zero=True)
    img.put(NCLX - BASE, b'nclx\0\2\0\2\0\1\x80', 'Log3G10 MOV colr nclx: unspecified primaries/transfer', expect_zero=True)
    picture = bytearray(stock[NLOG_PICTURE - BASE:NLOG_PICTURE - BASE + PICTURE_BYTES])
    need(picture[8:28] == b'N-LOG'.ljust(20, b'\0'), 'N-LOG Picture Control definition differs')
    for k, r in m.items():
        picture[8:28] = r['picture'].ljust(20, b'\0')
        img.put(r['picture_va'] - BASE, picture,
                'Log3G10 Picture Control definition (renamed N-LOG copy)' + ('' if k == 1 else f' (row {k})'), expect_zero=True)
    for site, label, nops, expect, purpose in (
            (VUI_SITE, 'vui', 0, 'f37b48a9', 'Log3G10 HEVC VUI colour description'),
            (COLR_NCLC_SITE, 'nclc', 0, 'b6e8ff17', 'Log3G10 MOV colr nclc selection'),
            (COLR_NCLX_SITE, 'nclx', 0, 'c7e8ff17', 'Log3G10 MOV colr nclx selection'),
            (PICTURE_SITE, 'picture', 3, '174a82d2d781a8f21700c0f21700e0f2', 'Log3G10 Picture Control state'),
            (PICTURE_GET, 'picture_get', 4, '004a82d2c081a8f20000c0f20000e0f2c0035fd6', 'Log3G10 Picture Control getter')):
        branch = Block(site); branch.b(labels[label])
        for _ in range(nops):
            branch.nop()
        img.put(site - BASE, branch.bytes(), purpose, expect=bytes.fromhex(expect))

    # Fill/outline PNG pairs, one per row, in tile id order.
    tiles = [image for r in m.values() for image in tile_images(r['tile'])]
    need(stock[struct.unpack_from('<Q', stock, IMAGE_TABLE - BASE + 0x18 * (TILE_ID - 1) + 0x10)[0] - BASE:][:4] == b'\x89PNG'
         and not struct.unpack_from('<I', stock, IMAGE_TABLE - BASE + 0x18 * TILE_ID + 4)[0], 'Stock image table end differs')
    need(TILE_PNG + sum(map(len, tiles)) <= TABLES and TILE_TABLE + 16 * len(tiles) <= GUI, 'Tile images overflow')
    img.put(TILE_PNG - BASE, b''.join(tiles), 'Log3G10 live-view tile PNGs', expect_zero=True)
    starts = [TILE_PNG + sum(map(len, tiles[:i])) for i in range(len(tiles))]
    img.put(TILE_TABLE - BASE, b''.join(struct.pack('<IIQ', len(t), 0, at) for t, at in zip(tiles, starts)),
            'Log3G10 tile image rows', expect_zero=True)
    branch = Block(TILE_SITE); branch.b(labels['tile'])
    img.put(TILE_SITE - BASE, branch.bytes(), 'Log3G10 live-view tile selection', expect=bytes.fromhex('a34f8152'))
    branch = Block(IMAGE_SITE); branch.b(labels['image'])
    img.put(IMAGE_SITE - BASE, branch.bytes(), 'Log3G10 tile image lookup', expect=struct.pack('<I', IMAGE_FIRST))

    # Copy every original tone row and event pointer verbatim, append one per mode.
    original_rows = stock[ROW_SOURCE:ROW_SOURCE + 9 * 44]
    template = list(struct.unpack_from('<11I', original_rows, 8 * 44))
    need(template[0] == 0x70A and template[6] == 0x3060, 'H.265 N-Log template differs')
    row_data = original_rows
    for r in m.values():
        row = list(template)
        row[0], row[6] = label_id + r['string'], r['item']
        row_data += struct.pack('<11I', *row)
    count = 9 + len(m)
    pointers = list(struct.unpack_from('<9Q', stock, EVENT_SOURCE))
    event_va = GUI + 0x400
    new_events = bytearray()
    translated = {}
    for original in sorted(set(pointers)):
        start = original - BASE
        records = bytearray()
        for i in range(32):
            e, a, g, t = struct.unpack_from('<4Q', stock, start + 32 * i)
            records.extend(struct.pack('<4Q', e, labels['action'] if a == NATIVE_ACTION else a, g, t))
            if e == 0x3BB:
                break
        else:
            raise ValueError('Tone events have no terminator')
        translated[original] = event_va + len(new_events)
        new_events.extend(records)
    pointers = [translated[p] for p in pointers] + [translated[pointers[8]]] * len(m)
    pointer_va = GUI + 0x200
    map_va = GUI + 0x1800
    mapping = stock[0x29C044C:0x29C044C + 9 * 8] + b''.join(struct.pack('<2I', r['item'], 2) for r in m.values())
    need(len(row_data) <= pointer_va - GUI and 8 * count <= event_va - pointer_va, 'Tone row region overflow')
    img.put(GUI - BASE, row_data, 'Ten tone rows; ninth native row preserved' if not dual else f'{count} tone rows; ninth native row preserved',
            expect_zero=True)
    img.put(pointer_va - BASE, struct.pack(f'<{count}Q', *pointers), 'Tone event directory with Log3G10 row', expect_zero=True)
    img.put(event_va - BASE, new_events, 'Tone events with isolated choice wrapper', expect_zero=True)
    need(event_va + len(new_events) < map_va, 'Tone event region overflow')
    img.put(map_va - BASE, mapping, 'Tone item-to-native-value map, Log3G10 maps to 2', expect_zero=True)
    need(struct.unpack_from('<3Q', stock, PAGE + 8) == (0x43C06C88, BASE + ROW_SOURCE, BASE + EVENT_SOURCE), 'Tone page layout differs')
    need(struct.unpack_from('<H', stock, PAGE + 32)[0] == 9, 'Tone row count differs')
    img.put(PAGE + 16, struct.pack('<2Q', GUI, pointer_va), 'Tone page private rows/events')
    img.put(PAGE + 32, struct.pack('<H', count), 'Tone page ten physical rows' if not dual else f'Tone page {count} physical rows')
    img.put(CALLBACK, struct.pack('<Q', labels['entry']), 'Tone page entry wrapper', expect=struct.pack('<Q', NATIVE_ENTRY))
    map_code = Block(0x4056DA5C); map_code.mov_x64(21, map_va)
    # Two non-contiguous native instructions between the constant pieces
    # must be retained: x9 load at +0x0c and the later 48-bit MOVK.
    img.put(0x4056DA5C - BASE, map_code.bytes()[:12], 'Native tone map private pointer low/16/32 bits', expect=bytes.fromhex('958980d25556a8f21500c0f2'))
    img.put(0x4056DA6C - BASE, map_code.bytes()[12:], 'Native tone map pointer high bits', expect=bytes.fromhex('1500e0f2'))
    c = Block(0x4056DA7C); c.mov_w(1, count)
    img.put(0x4056DA7C - BASE, c.bytes(), 'Native tone map count ten' if not dual else f'Native tone map count {count}',
            expect=bytes.fromhex('21018052'))
    # Extend the existing text mapping to cover private code, tables and
    # the zero-initialised flag, preserving the original mapped room.
    loader = Block(0x41184D8C)
    loader.mov_x64(8, END)
    need(struct.unpack_from('<2I', baseline, 0x1024D8C)[0] & 0xFFE0001F == 0xD2800008, 'Unexpected text-copy boundary code')
    img.put(0x1024D8C, loader.bytes()[:8], 'Experimental text copy boundary')
    if 'matrix' in profile:
        from .matrix import MATRIX_VA, MATRIX_SITE, matrix_bytes, coefficients
        for k, r in m.items():
            img.put(r['matrix_va'] - BASE, matrix_bytes(r['matrix']),
                    'Research BT.2020 to RWG fixed-point matrix' if k == 1 else f"BT.2020 to {r['target']} fixed-point matrix (row {k})",
                    expect_zero=True)
        hook = Block(MATRIX_SITE); hook.bl(labels['rwg_matrix'])
        img.put(MATRIX_SITE - BASE, hook.bytes(), 'Research fresh native M1 composition hook', expect=bytes.fromhex('a35a0094'))
    meta = dict(status='EXPERIMENTAL_OFFLINE_ONLY', labels={k:hex(v) for k,v in labels.items()},
                item_id=hex(ITEM), flag_property=hex(FLAG_PROPERTY), flag_ram=hex(FLAG),
                flag_persistence='native settings property; reload after power-off not verified',
                native_h265_filetype=H265_FILETYPE, native_gui_tone_value=2,
                stock_nlog_preserved=True, stock_lut_offset=hex(STOCK_LUT), stock_lut_crc32=hex(STOCK_LUT_CRC),
                private_lut_va=hex(LUT), private_nlg_gamma_va=hex(NLG), stock_nlg_gamma_preserved=True,
                nlg_gamma_gate='selected row 1 (INFO+0x43 forced row 3 unchanged), flag 1, file type 3',
                menu_label=profile['menu'], new_string_id=label_id,
                prior_string_entries=old_entries, private_string_bytes=table_bytes,
                native_metadata='Private-curve movies only: HEVC VUI and MOV colr primaries/transfer 2 (unspecified), '
                                f"matrix kept native; Picture Control name {profile['picture'].decode()}. No standard "
                                f"code exists for {profile['target']} or {transfer}, so manual interpretation remains required.",
                file_metadata=dict(vui_site=hex(VUI_SITE), colr_sites=[hex(COLR_NCLC_SITE), hex(COLR_NCLX_SITE)],
                                   picture_sites=[hex(PICTURE_SITE), hex(PICTURE_GET)], tone_ram=hex(TONE_RAM),
                                   gate='switch 1, file type 3, GUI tone 2 (N-Log), native HLG request 0',
                                   primaries=UNSPECIFIED, transfer=UNSPECIFIED, matrix='native',
                                   picture_control_name=profile['picture'].decode(), camera_file_verified=False),
                live_view_tile=dict(site=hex(TILE_SITE), image_ids=[hex(TILE_ID), hex(TILE_ID + 1)], text=profile['tile'],
                                    gate='switch 1, file type 3, GUI tone 2 (N-Log)'),
                camera_verified=False, full_rwg_implemented=False, transfer=transfer,
                curve=reference_summary(transfer), code_listing=listing,
                gamut_option=gamut, rwg_matrix_inserted=gamut == 'rwg-research',
                target_gamut=profile['target'],
                camera_gamut_verified=False)
    if gamut == 'rwg-research':
        meta['rwg_research'] = dict(matrix_va=hex(MATRIX_VA), hook_site=hex(MATRIX_SITE),
                                    matrix_q14=coefficients(),
                                    operation='T_BT2020_to_RWG * M_native',
                                    pipeline_order_verified=False, incoming_primaries_verified=False)
        meta['curve']['gamut'] = 'RWG candidate (unverified hardware stage/primaries)'
        meta['curve']['redwidegamut_applied'] = False  # claim awaits pixel validation
        meta['curve']['rwg_matrix_inserted'] = True
    if gamut == 'sgamut3-slog3':
        meta['sgamut3'] = dict(matrix_va=hex(MATRIX_VA), hook_site=hex(MATRIX_SITE),
                               matrix_q14=coefficients(profile['matrix']),
                               operation='T_BT2020_to_SGamut3 * M_native',
                               pipeline_order_verified=False, incoming_primaries_verified=False)
        meta['curve']['gamut'] = 'S-Gamut3 candidate (unverified hardware stage/primaries)'
    if dual:
        switch = ' or '.join(f"switch {k} ({r['tile']})" for k, r in m.items())
        meta.update(menu_label=[r['menu'] for r in m.values()], transfer=[r['transfer'] for r in m.values()],
                    target_gamut=[r['target'] for r in m.values()], rwg_matrix_inserted=True,
                    item_id=[hex(r['item']) for r in m.values()],
                    curve={r['transfer']: reference_summary(r['transfer']) for r in m.values()},
                    nlg_gamma_gate=f'selected row 1 (INFO+0x43 forced row 3 unchanged), {switch}, file type 3',
                    native_metadata='Private-curve movies only: HEVC VUI and MOV colr primaries/transfer 2 (unspecified), '
                                    'matrix kept native; Picture Control name per row. No standard code exists, '
                                    'so manual interpretation remains required.')
        meta['file_metadata'].update(gate=f'{switch}, file type 3, GUI tone 2 (N-Log), native HLG request 0',
                                     picture_control_name=[r['picture'].decode() for r in m.values()])
        meta['live_view_tile'].update(image_ids=[hex(i) for r in m.values() for i in r['tile_ids']],
                                      text=[r['tile'] for r in m.values()], gate=f'{switch}, file type 3, GUI tone 2 (N-Log)')
        meta['modes'] = [dict(switch_value=k, profile=r['name'], menu_label=r['menu'], item_id=hex(r['item']),
                              string_id=label_id + r['string'], transfer=r['transfer'], target_gamut=r['target'],
                              picture_control_name=r['picture'].decode(), tile=r['tile'], tile_ids=[hex(i) for i in r['tile_ids']],
                              private_lut_va=hex(r['lut']), private_nlg_gamma_va=hex(r['nlg']),
                              picture_va=hex(r['picture_va']), matrix_va=hex(r['matrix_va']),
                              matrix_q14=coefficients(r['matrix']), operation=f"T_BT2020_to_{r['target']} * M_native",
                              pipeline_order_verified=False, incoming_primaries_verified=False)
                         for k, r in m.items()]
        del meta['private_lut_va'], meta['private_nlg_gamma_va']
    return img, meta
