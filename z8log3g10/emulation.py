"""Execute native C3.11 LUT/menu routines with modelled GUI services.

These tests model memory and service results, never sensor/ISP registers.
No emulator result here verifies pixels or camera installation safety.
"""
import struct
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X8, UC_ARM64_REG_X9, UC_ARM64_REG_X10, UC_ARM64_REG_X11, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21, UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X30, UC_ARM64_REG_SP, UC_ARM64_REG_PC
from . import patcher as p
from .curve import ROW_BYTES

STOP = 0x7000F000
STATE = 0x60000000
DESC = 0x60001000
PREV = 0x60002000
PREV_DESC = 0x60003000
PREV_ROW = 0x60004000
CONTEXT = 0x60005000
INFO = 0x60006000
OUTPUT = 0x60008000
STACK = 0x70008000


class Machine:
    def __init__(self, data, labels=None):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(p.BASE, (len(data) + 4095) & ~4095)
        self.uc.mem_write(p.BASE, bytes(data))
        self.uc.mem_map(STATE, 0x10000)
        self.uc.mem_map(0x70000000, 0x10000)
        self.uc.mem_map(p.FILETYPE_RAM & ~4095, 4096)
        self.labels = labels or {}
        self.services = {}
        self.hide = {}
        self.marks = {}
        self.cursor = None
        self.writes = []
        self.native_tone = 2
        self.filetype = p.H265_FILETYPE
        self.guard = 0
        self.uc.hook_add(UC_HOOK_CODE, self.step)

    def u64(self, at):
        return struct.unpack('<Q', self.uc.mem_read(at, 8))[0]

    def u32(self, at):
        return struct.unpack('<I', self.uc.mem_read(at, 4))[0]

    def w64(self, at, value):
        self.uc.mem_write(at, struct.pack('<Q', value))

    def w32(self, at, value):
        self.uc.mem_write(at, struct.pack('<I', value))

    def result(self, value=0):
        self.uc.reg_write(UC_ARM64_REG_X0, value & ((1 << 64) - 1))
        self.uc.reg_write(UC_ARM64_REG_PC, self.uc.reg_read(UC_ARM64_REG_X30))

    def step(self, uc, address, size, user):
        if address == self.stop:
            uc.emu_stop()
            return
        x0 = uc.reg_read(UC_ARM64_REG_X0)
        x1 = uc.reg_read(UC_ARM64_REG_X1)
        x2 = uc.reg_read(UC_ARM64_REG_X2)
        if address == 0x4127A900:
            uc.mem_write(x0, bytes(uc.mem_read(x1, x2)))
            self.result(x0)
        elif address == 0x4127AB40:
            uc.mem_write(x0, bytes([x1 & 255]) * x2)
            self.result(x0)
        elif address == p.ENTRY_GET_PREVIOUS:
            self.w64(x0, PREV)
            self.result()
        elif address == p.GUI_GET:
            if x0 == p.TONE_PROPERTY:
                self.result(self.native_tone)
            elif x0 == 0x06001206:
                self.result(self.filetype)
            elif x0 in (0x06001249, 0x04001258, 0x04001259):
                self.result(2)
            else:
                raise AssertionError('Unmodelled GUI property ' + hex(x0))
        elif address == p.GUI_SET:
            updates = []
            for i in range(x2):
                ident, value = self.u32(x0 + 4 * i), self.u32(x1 + 4 * i)
                updates.append((ident, value))
                if ident == p.TONE_PROPERTY:
                    if value not in (0, 1, 2):
                        raise AssertionError('Unsupported native tone value')
                    self.native_tone = value
                elif ident == 0x06001206:
                    self.filetype = value
                elif ident == p.FLAG_PROPERTY:
                    self.w32(p.FLAG, value)
                elif ident not in (0x06001249, 0x04001258, 0x04001259):
                    raise AssertionError('Unexpected GUI set property ' + hex(ident))
            self.writes.append(updates)
            self.result()
        elif address == 0x403EB6A8:
            value = uc.reg_read(UC_ARM64_REG_X3) & 0xFFFFFFFF
            for i in range(x1):
                if self.u32(x0 + i * 8) == x2:
                    value = i
                    break
            self.result(value)
        elif address == p.FIND_ROW:
            desc = self.u64(x0 + 0x50)
            rows = self.u64(desc + 0x10)
            matches = [i for i in range(11) if self.u32(rows + i * 44 + 24) == x1]
            if not matches:
                raise AssertionError('Menu row not found: ' + hex(x1))
            self.result(matches[0])
        elif address == p.HIDE_ROW:
            self.hide[x1] = x2
            self.result()
        elif address == p.CURSOR:
            self.cursor = x1
            self.result()
        elif address == p.MARK:
            self.marks[x1] = x2
            self.result()
        elif address == p.GUARD:
            self.result(self.guard)
        elif address in (0x4056D810, 0x403D3938, 0x403EFED8, 0x403E82BC, 0x403D4AD4):
            self.result()

    def start(self, address, stop=STOP):
        self.stop = stop
        self.uc.reg_write(UC_ARM64_REG_SP, STACK)
        self.uc.reg_write(UC_ARM64_REG_X30, STOP)
        self.uc.emu_start(address, STOP + 4, count=10000)
        if self.uc.reg_read(UC_ARM64_REG_PC) != stop:
            raise AssertionError('Execution did not reach expected return: ' + hex(self.uc.reg_read(UC_ARM64_REG_PC)))
        if self.uc.reg_read(UC_ARM64_REG_SP) != STACK:
            raise AssertionError('Stack was not restored')

    def setup_menu(self, index=9, parent=0x3059, flag=0):
        self.uc.mem_write(STATE, bytes(0x10000))
        self.w64(STATE + 0x50, DESC)
        self.w64(DESC + 0x10, p.GUI)
        self.uc.mem_write(STATE + 0x32, struct.pack('<H', index))
        self.w64(PREV + 0x50, PREV_DESC)
        self.w64(PREV_DESC + 0x10, PREV_ROW)
        self.w32(PREV_ROW + 0x18, parent)
        self.w64(CONTEXT, STATE)
        self.uc.mem_write(p.FLAG, bytes([flag]))
        self.hide.clear(); self.marks.clear(); self.writes.clear()
        self.cursor = None

    def lut(self, tone, filetype, flag):
        self.uc.mem_write(STATE, bytes(0x10000))
        self.w64(STATE + 0x98, INFO)
        self.w64(STATE + 0x50, OUTPUT)
        self.uc.mem_write(INFO + 0x31, bytes([tone]))
        self.w32(p.FILETYPE_RAM, filetype)
        self.uc.mem_write(p.FLAG, bytes([flag]))
        self.uc.reg_write(UC_ARM64_REG_X19, STATE)
        self.uc.reg_write(UC_ARM64_REG_X10, 0x123456789)
        self.uc.reg_write(UC_ARM64_REG_X11, 0x987654321)
        self.start(0x4111A4EC, 0x4111A6A0)
        return bytes(self.uc.mem_read(OUTPUT + 0xBE6, 6 * ROW_BYTES))

    def nlg(self, tone, filetype, flag, special):
        """Run on through the NlgGamma row copy; return (Lut1, NlgGamma)."""
        self.uc.mem_write(STATE, bytes(0x10000))
        self.w64(STATE + 0x98, INFO)
        self.w64(STATE + 0x50, OUTPUT)
        self.uc.mem_write(INFO + 0x31, bytes([tone]))
        self.uc.mem_write(INFO + 0x43, bytes([special]))
        self.w32(p.FILETYPE_RAM, filetype)
        self.uc.mem_write(p.FLAG, bytes([flag]))
        self.uc.reg_write(UC_ARM64_REG_X19, STATE)
        self.start(0x4111A4EC, 0x4111A6E4)
        return (bytes(self.uc.mem_read(OUTPUT + 0xBE6, 6 * ROW_BYTES)),
                bytes(self.uc.mem_read(OUTPUT + 0x16A2, ROW_BYTES)))


def switch_values(m):
    """Every valid switch value plus 0 and one value past the last row."""
    return tuple(range(len(m) + 2))


def verify_routines(stock, candidate, labels, gamut='bt2020'):
    m = p.modes(gamut)
    flags = switch_values(m)
    baseline = Machine(stock)
    patched = Machine(candidate, labels)
    report = dict(lut_cases=0, nlg_cases=0, nlg_forced_row3_cases=0, menu_entry_cases=0, selection_cases=0,
                  native_tone_enum_preserved=True, camera_pixels_verified=False)
    for tone in (0, 1, 2):
        for filetype in range(1, 7):
            for flag in flags:
                before = baseline.lut(tone, filetype, flag)
                after = patched.lut(tone, filetype, flag)
                active = tone == 1 and filetype == p.H265_FILETYPE and flag in m
                if active:
                    expected = bytes(patched.uc.mem_read(m[flag]['lut'], 3 * ROW_BYTES))
                    if after != expected * 2 or after == before:
                        raise AssertionError('Private LUT not copied to both RGB paths')
                elif before != after:
                    raise AssertionError('A native SDR/HLG/N-Log path changed')
                report['lut_cases'] += 1
    # NlgGamma must pair with Lut1: private only for a Log3G10 job; SDR,
    # HLG, plain N-Log and the INFO+0x43 forced row 3 keep native rows.
    private = {k: (bytes(patched.uc.mem_read(r['lut'], ROW_BYTES)), bytes(patched.uc.mem_read(r['nlg'], ROW_BYTES)))
               for k, r in m.items()}
    if len({lut for lut, _ in private.values()}) != len(m):
        raise AssertionError('Rows do not have distinct private curves')
    for tone in (0, 1, 2):
        for filetype in range(1, 7):
            for flag in flags:
                for special in (0, 1, 255):
                    before_lut, before_nlg = baseline.nlg(tone, filetype, flag, special)
                    after_lut, after_nlg = patched.nlg(tone, filetype, flag, special)
                    row = 3 if special else tone
                    native = stock[p.STOCK_NLG + row * ROW_BYTES:p.STOCK_NLG + (row + 1) * ROW_BYTES]
                    if before_nlg != native:
                        raise AssertionError('Native NlgGamma model disagrees with stock selector')
                    job = tone == 1 and filetype == p.H265_FILETYPE and flag in m
                    if job != any(after_lut == lut * 6 for lut, _ in private.values()) or job and after_lut != private[flag][0] * 6:
                        raise AssertionError('Lut1 routing differs from Log3G10 job gate')
                    if job and not special:
                        if after_nlg != private[flag][1]:
                            raise AssertionError('Log3G10 job did not load private NlgGamma')
                    elif after_nlg != before_nlg:
                        raise AssertionError('A native SDR/HLG/N-Log/forced NlgGamma row changed')
                    report['nlg_cases'] += 1
                    report['nlg_forced_row3_cases'] += bool(special)
    for parent in (0x3058, 0x3059, 0x30E5, 0x30E6, 0x311C, 0x311D):
        for flag in flags[:-1]:
            for tone in (0, 1, 2):
                patched.setup_menu(parent=parent, flag=flag)
                patched.native_tone = tone
                patched.uc.reg_write(UC_ARM64_REG_X0, STATE)
                patched.start(labels['entry'])
                h265 = parent in (0x3059, 0x311D)
                if any(patched.hide.get(8 + k) != (0 if h265 else 1) for k in m):
                    raise AssertionError('Log3G10 row visibility is wrong')
                if h265 and flag in m and tone == 2:
                    if patched.marks.get(m[flag]['item']) != 1 or patched.marks.get(0x3060) != 0 \
                            or patched.cursor != m[flag]['item'] or any(patched.marks.get(r['item']) for k, r in m.items() if k != flag):
                        raise AssertionError('Log3G10/native N-Log marks disagree')
                elif any(r['item'] in patched.marks for r in m.values()):
                    raise AssertionError('A private row was marked outside its job')
                report['menu_entry_cases'] += 1
    # Run native OK through its actual lookup and GUI-set paths. Native
    # property services are modelled; the original ARM routine is executed.
    for row in range(9 + len(m)):
        for initial_flag in flags[:-1]:
            parent = 0x3059 if row >= 6 else (0x3058 if row >= 4 else 0x30E5)
            patched.setup_menu(index=row, parent=parent, flag=initial_flag)
            patched.native_tone = 2
            patched.filetype = p.H265_FILETYPE
            patched.uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
            patched.start(labels['action'])
            actual_flag = bytes(patched.uc.mem_read(p.FLAG, 1))[0]
            expected_flag = row - 8 if row >= 9 else 0 if row in (6, 7, 8) else initial_flag
            if actual_flag != expected_flag:
                raise AssertionError('Selecting tone row changed the wrong switch')
            if row >= 6:
                expected_tone = {6:0, 7:1}.get(row, 2)
                if patched.native_tone != expected_tone or patched.filetype != p.H265_FILETYPE:
                    raise AssertionError('Native H.265/tone properties are wrong')
                if patched.writes[0] != [(p.FLAG_PROPERTY, expected_flag), (p.TONE_PROPERTY, 0)]:
                    raise AssertionError('No real native tone transition requested')
            report['selection_cases'] += 1
    # The tile uses the job gate; the lookup serves only the new ids.
    report['tile_cases'] = 0
    for flag in flags:
        for filetype in range(1, 7):
            for tone in (0, 1, 2, 3):
                patched.w32(p.FLAG, flag)
                patched.w32(p.FILETYPE_RAM, filetype)
                patched.w32(p.TONE_RAM, tone)
                patched.start(labels['tile'], stop=p.TILE_RESUME)
                job = flag in m and filetype == p.H265_FILETYPE and tone == p.NLOG_GUI_TONE
                ids = m[flag]['tile_ids'] if job else p.NLOG_TILE
                if (patched.uc.reg_read(UC_ARM64_REG_X3), patched.uc.reg_read(UC_ARM64_REG_X4)) != ids:
                    raise AssertionError('Live-view tile differs from Log3G10 job gate')
                report['tile_cases'] += 1
    for index in range(2 * len(m)):
        patched.uc.mem_write(STATE, bytes(0x100))
        patched.w32(STATE, p.TILE_ID + index)
        patched.uc.reg_write(UC_ARM64_REG_X0, STATE)
        patched.uc.reg_write(UC_ARM64_REG_X1, STATE + 0x40)
        patched.start(labels['image'])
        size, address = patched.u32(STATE + 0x44), patched.u64(STATE + 0x50)
        if bytes(patched.uc.mem_read(address, 8)) != b'\x89PNG\r\n\x1a\n' or not 0 < size < 0x1000:
            raise AssertionError('Log3G10 tile image lookup is wrong')
    report['passed'] = True
    return report


def verify_metadata_routines(stock, candidate, gamut='bt2020'):
    """Run native encoder-config, MOV colr and Picture Control code paths.

    Checks the tags handed to the encoder/muxer, not a recorded file.
    """
    m = p.modes(gamut)
    baseline = Machine(stock)
    patched = Machine(candidate)
    report = dict(vui_cases=0, colr_cases=0, picture_cases=0, recorded_file_verified=False)
    stock_picture = bytes(baseline.uc.mem_read(p.NLOG_PICTURE, p.PICTURE_BYTES))
    for r in m.values():
        private_picture = bytes(patched.uc.mem_read(r['picture_va'], p.PICTURE_BYTES))
        if private_picture[:8] != stock_picture[:8] or private_picture[28:] != stock_picture[28:]:
            raise AssertionError('Private Picture Control differs beyond its name')

    def gate(m, tone, filetype, flag):
        m.uc.mem_write(STATE, bytes(0x10000))
        m.w32(p.FILETYPE_RAM, filetype)
        m.w32(p.TONE_RAM, tone)
        m.uc.mem_write(p.FLAG, bytes([flag]))

    def vui(m, hlg, first):
        m.w32(STATE, first)
        m.uc.reg_write(UC_ARM64_REG_X0, STATE)
        m.uc.reg_write(UC_ARM64_REG_X1, hlg)
        m.uc.reg_write(UC_ARM64_REG_X2, 0)
        m.uc.reg_write(UC_ARM64_REG_X3, OUTPUT)
        m.uc.reg_write(UC_ARM64_REG_X19, 0x1919)
        m.uc.reg_write(UC_ARM64_REG_X21, 0x2121)
        m.start(0x402F6C10)
        if m.uc.reg_read(UC_ARM64_REG_X19) != 0x1919 or m.uc.reg_read(UC_ARM64_REG_X21) != 0x2121:
            raise AssertionError('Encoder config hook changed a callee-saved register')
        return bytes(m.uc.mem_read(OUTPUT, 0x200)), struct.unpack('<5I', m.uc.mem_read(OUTPUT + 0x1C0, 20))

    def colr(m, site, hlg):
        m.uc.reg_write(UC_ARM64_REG_X0, hlg)
        m.uc.reg_write(UC_ARM64_REG_X1, OUTPUT)
        m.uc.reg_write(UC_ARM64_REG_X2, OUTPUT + 8)
        m.start(site)
        at, size = m.u64(OUTPUT), m.u32(OUTPUT + 8)
        return bytes(m.uc.mem_read(at, size))

    def picture(m):
        m.uc.reg_write(UC_ARM64_REG_X19, OUTPUT)
        m.start(p.PICTURE_SITE, 0x410A8388)
        state = m.uc.reg_read(UC_ARM64_REG_X23)
        m.start(p.PICTURE_GET)
        return state, m.uc.reg_read(UC_ARM64_REG_X0), bytes(m.uc.mem_read(OUTPUT, 20))

    gate(baseline, 0, 1, 0)
    native = {(s, h): colr(baseline, s, h) for s in (p.COLR_NCLC_SITE, p.COLR_NCLX_SITE) for h in (0, 1)}
    if native[p.COLR_NCLC_SITE, 0] != b'nclc\0\1\0\1\0\1' or native[p.COLR_NCLX_SITE, 1] != b'nclx\0\x09\0\x12\0\x09\x80':
        raise AssertionError('Native MOV colr model disagrees with stock templates')
    for tone in (0, 1, 2):
        for filetype in range(1, 7):
            for flag in switch_values(m):
                job = tone == p.NLOG_GUI_TONE and filetype == p.H265_FILETYPE and flag in m
                for hlg in (0, 1):
                    for first in (0, 1):
                        gate(baseline, tone, filetype, flag)
                        gate(patched, tone, filetype, flag)
                        before, before_vui = vui(baseline, hlg, first)
                        after, after_vui = vui(patched, hlg, first)
                        if before_vui != ((5, 1, 9, 18, 9) if hlg else (5, 1, 1, 1, 1)):
                            raise AssertionError('Native VUI model disagrees with stock encoder config')
                        if job and not hlg:
                            if after_vui != (5, 1, p.UNSPECIFIED, p.UNSPECIFIED, 1):
                                raise AssertionError('Log3G10 VUI not unspecified')
                            if after[:0x1C8] != before[:0x1C8] or after[0x1D0:] != before[0x1D0:]:
                                raise AssertionError('VUI hook changed other encoder fields')
                        elif after != before:
                            raise AssertionError('A native VUI colour description changed')
                        report['vui_cases'] += 1
                    for site in (p.COLR_NCLC_SITE, p.COLR_NCLX_SITE):
                        tag = colr(patched, site, hlg)
                        if job and not hlg:
                            if tag != native[site, 0][:5] + b'\2\0\2' + native[site, 0][8:]:
                                raise AssertionError('Log3G10 MOV colr not unspecified')
                        elif tag != native[site, hlg]:
                            raise AssertionError('A native MOV colr tag changed')
                        report['colr_cases'] += 1
                gate(patched, tone, filetype, flag)
                state, getter, name = picture(patched)
                wanted = m[flag]['picture_va'] if job else p.NLOG_PICTURE
                if (state, getter) != (wanted, wanted):
                    raise AssertionError('Picture Control routing differs from Log3G10 job gate')
                if name != (m[flag]['picture'] if job else b'N-LOG').ljust(20, b'\0'):
                    raise AssertionError('Picture Control name copied incorrectly')
                report['picture_cases'] += 1
    report['passed'] = True
    return report


def verify_matrix_routines(stock, candidate, gamut='rwg-research'):
    """Execute the inserted hook and C3.11 native signed matrix multiply.

    This checks arithmetic and isolation, not the hardware's stage order.
    """
    import random
    from .matrix import MATRIX_SITE, M1_OFFSET, compose_reference
    m = p.modes(gamut)
    machine = Machine(candidate)
    control = Machine(stock)
    report = dict(cases=0, native_matrix_multiply_executed=True, no_repeated_matrix_compounding=True,
                  hardware_stage_order_verified=False, pixels_verified=False)
    matrices = [(512,0,0,0,512,0,0,0,512),
                (700,-120,-68,-30,600,-58,20,-200,692),
                (0,512,0,0,0,512,512,0,0),
                (-2048,1024,1536,1536,-2048,1024,1024,1536,-2048)]
    rng = random.Random(311)
    matrices += [tuple(rng.randint(-2048,2047) for _ in range(9)) for _ in range(4)]
    def one(existing, tone, filetype, flag):
        for target in (machine,control):
            target.uc.mem_write(STATE, bytes(0x10000))
            target.w64(STATE + 0x40, INFO)
            target.w64(STATE + 0xA0, OUTPUT)
            target.w32(INFO + 0xBC, tone)
            target.w32(p.FILETYPE_RAM, filetype)
            target.uc.mem_write(p.FLAG, bytes([flag]))
            target.uc.mem_write(OUTPUT, b'Z' * 80)
            # Actual call-site scaling is 32768. A*I_16384/32768
            # reproduces each seeded native M1 when A=2*M1.
            target.uc.mem_write(INFO+0x100,struct.pack('<9h',*(2*x for x in existing)))
            target.uc.mem_write(INFO+0x140,struct.pack('<9h',16384,0,0,0,16384,0,0,0,16384))
            target.uc.reg_write(UC_ARM64_REG_X0,INFO+0x100)
            target.uc.reg_write(UC_ARM64_REG_X1,INFO+0x140)
            target.uc.reg_write(UC_ARM64_REG_X2,OUTPUT+M1_OFFSET)
            target.uc.reg_write(UC_ARM64_REG_X3,32768)
            target.uc.reg_write(UC_ARM64_REG_X19,STATE)
            target.uc.reg_write(UC_ARM64_REG_X20,0x12320)
            target.uc.reg_write(UC_ARM64_REG_X21,0x12321)
            target.start(MATRIX_SITE,MATRIX_SITE+4)
        actual = struct.unpack('<9h', machine.uc.mem_read(OUTPUT + M1_OFFSET,18))
        expected = compose_reference(existing, m[flag]['matrix']) if tone == 1 and filetype == 3 and flag in m else existing
        if actual != expected:
            raise AssertionError('Native matrix multiply differs from independent integer reference')
        if machine.uc.reg_read(UC_ARM64_REG_X0) != control.uc.reg_read(UC_ARM64_REG_X0):
            raise AssertionError('M1 hook changed the native return value')
        for register,value in [(UC_ARM64_REG_X19,STATE),(UC_ARM64_REG_X20,0x12320),(UC_ARM64_REG_X21,0x12321)]:
            if machine.uc.reg_read(register) != value:
                raise AssertionError('M1 hook changed a callee-saved register')
        if bytes(machine.uc.mem_read(OUTPUT,M1_OFFSET)) != b'Z'*M1_OFFSET or bytes(machine.uc.mem_read(OUTPUT+M1_OFFSET+18,44)) != b'Z'*44:
            raise AssertionError('Matrix hook wrote outside M1')
        # Recompute with the same source inputs while the target already
        # contains transformed coefficients: output must not compound T.
        machine.uc.reg_write(UC_ARM64_REG_X0,INFO+0x100)
        machine.uc.reg_write(UC_ARM64_REG_X1,INFO+0x140)
        machine.uc.reg_write(UC_ARM64_REG_X2,OUTPUT+M1_OFFSET)
        machine.uc.reg_write(UC_ARM64_REG_X3,32768)
        machine.start(MATRIX_SITE,MATRIX_SITE+4)
        if struct.unpack('<9h',machine.uc.mem_read(OUTPUT+M1_OFFSET,18)) != actual:
            raise AssertionError('RWG conversion compounded on repeated task construction')
        report['cases'] += 1
    for existing in matrices:
        for tone in (0,1,2):
            for filetype in range(1,7):
                for flag in switch_values(m):
                    one(existing,tone,filetype,flag)
    for flag in m:
        for _ in range(200):
            one(tuple(rng.randint(-2048,2047) for _ in range(9)),1,3,flag)
    report['passed'] = True
    return report
