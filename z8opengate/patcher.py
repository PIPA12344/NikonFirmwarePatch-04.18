"""Public source adapted from the pinned research implementation; regular files only."""
from z8prores.package import require
import struct, math, hashlib
from . import quality, sites
from z8prores.menu import Image
BASE, CAVE, END = (1075183616, 1083572224, 1083637760)
MENU, RATE, ROWS, EVENTS, TEXT, TABLES = (1082916864, 1082920960, 1082925056, 1082929152, 1082982400, 1083047936)
STOCK_STRINGS = 3137
Q3_STASH, Q3_CODE, Q3_DATA, Q3_GUI, Q3_GUI_END, OG_TIERS = (1083506688, 1083510784, 1083518976, 1083523072, 1083531264, 1083535360)
Q3_ALIAS = 43209719808 - 1075838976
FINE_ID, BASIC_ID = (3140, 3141)
RECORDS, RECORD_COUNT, HALF = (1118518416, 42, 21)
OG_BUDGETS = {(30000, 1): 3455, (25000, 1): 2885, (24000, 1): 2774, (30000, 0): 2089, (25000, 0): 1745, (24000, 0): 1681}
SESSION_END_SITES = (1077855636, 1077855688, 1091466828, 1091469032)
TIER_SITE, TIER_WORD = (1087497808, '2829089b')
sha = lambda b: hashlib.sha256(b).hexdigest()

def tier_names(q3, stock):
    """Q3's per-language Fine/Basic names and its glyph check, against the stock string pools."""
    img = q3.Image(stock)
    tables, blobs = q3.string_tables(img)
    names = []
    for k in range(q3.LANGUAGES):
        o = struct.unpack_from(f'<{STOCK_STRINGS}i', stock, tables[k])
        pool = set(stock[blobs[k] + o[0]:blobs[k] + o[-1]].decode('utf-16le'))
        fine, basic = q3.tier_names(img, tables, blobs, k)
        missing = sorted({c for c in fine + basic if c != ' ' and c not in pool})
        require(not missing, (k, missing))
        names.append((fine, basic))
    return names

def q3_feature(q3, stock):
    """Q3's edits (as its build(), minus strings and loader) against the stock image; tables for the join."""
    cs = q3.Cs(q3.CS_ARCH_ARM64, q3.CS_MODE_LITTLE_ENDIAN)
    img = q3.Image(stock)
    fine_table, basic_table, rate_rows = q3.rate_tables(img)
    blob, data = (bytearray(), {})

    def add(name, b, align=8):
        while len(blob) % align:
            blob.append(0)
        data[name] = Q3_DATA + len(blob)
        blob.extend(b)
    add('fine_table', fine_table)
    add('basic_table', basic_table)
    add('item_by_value', struct.pack('<4I', *q3.ITEM_BY_VALUE))
    add('list_fine', q3.LIST_TEXT[2].ljust(8, b'\x00'))
    add('list_basic', q3.LIST_TEXT[3].ljust(8, b'\x00'))
    add('display', b''.join((n.ljust(16, b'\x00') for n in q3.DISPLAY)), align=16)
    blk = q3.code(cs, data, ())
    code = blk.bytes()
    require(Q3_CODE + len(code) <= Q3_DATA and Q3_DATA + len(blob) <= Q3_GUI, 'Unexpected firmware structure')
    img.put(Q3_CODE - BASE, code, 'Q3 code: sub-page entry/OK, list text, selector, bit rate, label, PTP, GUI get, 1015h class, attribute tier, movie block stash, playback, derived value', expect_zero=True)
    img.put(Q3_DATA - BASE, bytes(blob), 'Q3 data: Fine/Basic bit-rate record tables, row items, texts', expect_zero=True)
    where = q3.menu(img, dict(fine_id=FINE_ID, basic_id=BASIC_ID), blk)
    hooked = q3.hooks(img, blk)
    listing = blk.listing(cs)
    facts = dict(menu=where, hooks=hooked, data={k: hex(v) for k, v in data.items()}, labels={k: hex(v) for k, v in blk.labels.items()}, rate_records=rate_rows, code_bytes=len(code), code=[dict(va=hex(x), word=w, text=t) for x, w, t in listing], stash=dict(va=hex(Q3_STASH), ram_alias=hex(Q3_STASH + Q3_ALIAS)), unnamed_class12_versions=[])
    return (img, facts, data, fine_table, basic_table)

def og_tier_tables(fine_table, basic_table):
    """Open-gate copies of Q3's Fine (High half) and Basic (Normal half) tables: the 8.3K 24..30p records get the
    full-height size and a rate from the same rule Q3 uses (overhead of the D6 full-height High/Normal pair +
    bit/px x 8268 x 5512 x frame rate)."""
    out = []
    rows = []
    for table, half, bpp, name in ((fine_table, 0, 2.0, 'fine'), (basic_table, 1, 1.0, 'basic')):
        t = bytearray(table)
        for i in range(half * HALF, (half + 1) * HALF):
            w, ht, n, d, res, bps = struct.unpack_from('<HHIIIQ', t, 24 * i)
            if (w, ht) != (8268, 4652) or (n, 1) not in OG_BUDGETS:
                continue
            pr = 8268 * 5512 * n / d
            hi, no = (OG_BUDGETS[n, 1] * 1000000.0, OG_BUDGETS[n, 0] * 1000000.0)
            over = max(hi - 2.5 * pr, no - 1.5 * pr)
            require(0 < over < 0.05 * hi, (i, over))
            new = math.ceil((bpp * pr + over) / 1000000.0) * 1000000
            require(no > new if bpp == 1.0 else no < new < hi, 'Unexpected firmware structure')
            struct.pack_into('<H', t, 24 * i + 2, 5512)
            struct.pack_into('<Q', t, 24 * i + 16, new)
            rows.append(dict(table=name, index=i, numerator=n, denominator=d, stock_16x9_bps=bps, og_bps=new, overhead=round(over)))
        out.append(bytes(t))
    require(len([r for r in rows if r['table'] == 'fine']) == 3 and len([r for r in rows if r['table'] == 'basic']) == 3, 'Unexpected firmware structure')
    return (out[0], out[1], rows)

def build_main(stock, code, entries, strings_context):
    with_q3 = True
    image = Image(stock)
    changes = []

    def put(a, new, why):
        o = a - BASE
        image.put(o, new, why)
        changes.append(dict(file_offset=o, bytes=len(new)))
    q3 = quality
    extra = tier_names(q3, stock) if with_q3 else None
    NEW_IDS = sites.NEW_IDS
    menu = bytearray(stock[43776736:43776736 + 80 * 24])
    rows = bytearray(stock[61501836:61501836 + 80 * 44])
    ev = bytearray(stock[61505360:61505360 + 80 * 8])
    require(len(set(NEW_IDS) & {struct.unpack_from('<I', rows, i * 44 + 24)[0] for i in range(80)}) == 0, 'Unexpected firmware structure')
    for j, rate in enumerate([4, 5, 6]):
        menu += struct.pack('<6I', NEW_IDS[j], 6, rate, 6, 1, 2147483648 + j)
        row = list(struct.unpack_from('<11I', rows, (53 + j) * 44))
        require(row[6] == 12531 + j, 'Unexpected firmware structure')
        row[0] = 3137 + j
        row[6] = NEW_IDS[j]
        rows += struct.pack('<11I', *row)
        ev += stock[61505360 + (53 + j) * 8:61505360 + (54 + j) * 8]
    menu = menu[-72:] + menu[:-72]
    rows = rows[-132:] + rows[:-132]
    ev = ev[-24:] + ev[:-24]
    put(MENU, menu, 'three independent full-height rows first, then all 80 factory mappings')
    put(ROWS, rows, '83 menu rows, OG first; original 80 row bytes retained')
    put(EVENTS, ev, '83 row event pointers; three rows share the original corresponding-rate events')
    page = 79480592
    require(struct.unpack_from('<H', stock, page + 32)[0] == 80, 'Unexpected firmware structure')
    put(BASE + page + 16, struct.pack('<QQ', ROWS, EVENTS), 'frame-size page row and event pointer relocation')
    put(BASE + page + 32, struct.pack('<H', 83), 'frame-size page 83 rows')
    localized_labels = []
    blob = bytearray()
    tables = []
    count = STOCK_STRINGS + 3 + (2 if with_q3 else 0) + 1
    for lang in range(36):
        t = struct.unpack_from('<Q', stock, 51496352 + lang * 8)[0]
        b = struct.unpack_from('<Q', stock, 59223896 + lang * 8)[0]
        offsets = list(struct.unpack_from(f'<{STOCK_STRINGS}i', stock, t - BASE))
        labels = []
        for idx in (2034, 2035, 2036):
            x, y = struct.unpack_from('<2i', stock, t - BASE + 4 * idx)
            native = stock[b + x - BASE:b + y - BASE].decode('utf-16le')
            require(native.count('[FX]') == 1, 'Unexpected firmware structure')
            label = native.replace('[FX]', '[FX 3:2]')
            hits = 0
            for before, after in [('4644', '5504'), ('4.644', '5.504'), ('4,644', '5,504'), ('4 644', '5 504')]:
                hits += label.count(before)
                label = label.replace(before, after)
            require(hits == 1, (lang, native))
            labels.append(label)
        localized_labels.append(labels)
        for label in labels + (list(extra[lang]) if with_q3 else []):
            offsets.append(TEXT + len(blob) - b)
            blob += label.encode('utf-16le')
        offsets.append(TEXT + len(blob) - b)
        require(len(offsets) == count, 'Unexpected firmware structure')
        tables.append(struct.pack(f'<{count}i', *offsets))
    require(TEXT + len(blob) < TABLES and TABLES + sum(map(len, tables)) < (Q3_STASH if with_q3 else CAVE), 'Unexpected firmware structure')
    strings_context.add('opengate-nraw', [localized_labels[k] + list(extra[k]) for k in range(36)])
    rates = bytearray(stock[43334800:43334800 + 42 * 24])
    rate_edits = []
    for i in range(42):
        w, hz, n, d, reserved, bps = struct.unpack_from('<HH3IQ', rates, i * 24)
        q = int(i < 21)
        if w == 8268 and hz == 4652 and ((n, q) in OG_BUDGETS):
            new = OG_BUDGETS[n, q] * 1000000
            struct.pack_into('<H', rates, i * 24 + 2, 5512)
            struct.pack_into('<Q', rates, i * 24 + 16, new)
            rate_edits.append(dict(index=i, numerator=n, denominator=d, quality=q, old_bps=bps, new_bps=new))
    require(len(rate_edits) == 6, 'Unexpected firmware structure')
    put(RATE, rates, 'private remaining-time records, six low-rate full-height budgets')
    from .imenu import extend
    imenu = extend(stock, put)
    q3facts = None
    defs = ['-DWITH_Q3=0']
    if with_q3:
        img, q3facts, data, fine_table, basic_table = q3_feature(q3, stock)
        og_fine, og_basic, tier_rows = og_tier_tables(fine_table, basic_table)
        require(data['basic_table'] - data['fine_table'] == len(fine_table) == 1008, 'Unexpected firmware structure')
        put(OG_TIERS, og_fine + og_basic, 'open-gate copies of the Q3 Fine/Basic record tables (8.3K 30/25/24p: 8268x5512, full-height rates)')
        defs = ['-DWITH_Q3=1', f'-DQ3_STASH_RAM={Q3_STASH + Q3_ALIAS:#x}', f"-DQ3_FINE_TABLE={data['fine_table']:#x}", f"-DQ3_BASIC_TABLE={data['basic_table']:#x}", f"-DOG_TIER_DELTA={OG_TIERS - data['fine_table']:#x}"]
        q3facts['og_tier_records'] = tier_rows
    put(CAVE, code, 'D3 core, D4 policy/menu/time/icon, D5/D6 display, D7 cancel and Q3 joins')
    for a, old, name, call in [*sites.SITES, *sites.NAV_SITES]:
        if name == 'boot_reset_hook':
            name = 'boot_reset_d8_hook'
        require(stock[a - BASE:a - BASE + len(bytes.fromhex(old))] == bytes.fromhex(old), 'Unexpected firmware structure')
        delta = entries[name] - a
        new = struct.pack('<I', (2483027968 if call else 335544320) | delta // 4 & 67108863)
        if len(old) == 16:
            new += bytes.fromhex('1f2003d5')
        put(a, new, name)
    bl = lambda a, t, call: struct.pack('<I', (2483027968 if call else 335544320) | (t - a) // 4 & 67108863)
    for a, name, call in sites.EXTRA:
        if a == 1090609900:
            continue
        delta = entries[name] - a
        require(delta % 4 == 0 and -(1 << 27) <= delta < 1 << 27, 'Unexpected firmware structure')
        put(a, bl(a, entries[name], call), name)
    for a, w, why in [(1079428924, 4043309087 | 2008 << 10 | 23 << 5, 'list bound = 16 + 83*24'), (1079444276, 1384120321 | 83 << 5, 'selection table count 83'), (1079455300, 2457862165 | 82 << 5, 'summary counter starts -83')]:
        put(a, struct.pack('<I', w), why)
    for a in SESSION_END_SITES:
        require(stock[a - BASE:a - BASE + 4] == bl(a, 1091404800, True), 'Unexpected firmware structure')
        put(a, bl(a, entries['ds_session_end_d8_hook'], True), 'data-store session end -> ds_session_end_hook')
    if with_q3:
        require(stock[TIER_SITE - BASE:TIER_SITE - BASE + 4] == bytes.fromhex(TIER_WORD), 'Unexpected firmware structure')
        put(TIER_SITE, bl(TIER_SITE, entries['tier_table_hook'], False), 'RAW bit-rate record join -> tier_table_hook')
        mine = [(int(c['file_offset']), int(c['file_offset']) + c['bytes']) for c in changes]
        for e in sorted(img.edits, key=lambda e: e['offset']):
            require(not any((a < e['end'] and e['offset'] < b for a, b in mine)), ('Q3 edit overlaps a D7 edit', hex(e['offset']), e['purpose']))
            put(BASE + e['offset'], e['new'], 'Q3: ' + e['purpose'])
    for a, name in [(1090000372, 'og_compare_exit_hook'), (1089978268, 'og_apply_hook'), (1089981448, 'og_apply_hook'), (1081663824, 'og_aspect_class_hook'), (1081663964, 'og_aspect_class_thumb_hook')]:
        put(a, bl(a, entries[name], name == 'og_apply_hook'), name)
    return (image, dict(code_bytes=len(code), entries={k: hex(v) for k, v in entries.items()}, q3=q3facts, rate_edits=rate_edits))
