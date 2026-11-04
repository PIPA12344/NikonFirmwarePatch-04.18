"""Execute the patched and native selector code with modelled RAM. No pixels, no display hardware."""
import itertools
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                                 UC_ARM64_REG_X2, UC_ARM64_REG_X9, UC_ARM64_REG_X10, UC_ARM64_REG_X19,
                                 UC_ARM64_REG_X20, UC_ARM64_REG_X30)

from z8log3g10 import patcher as log
from . import patcher as p

STATE = 0xA02E70C98         # display state: +0x15a dev byte (a02e70df2), +0x314 alt byte (a02e70fac)
STACK = 0x70000000
STOP = 0x7000F000


class Machine:
    def __init__(self, eg):
        self.eg = eg
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(p.BASE, (len(eg) + 0xFFF) & ~0xFFF)
        self.uc.mem_write(p.BASE, bytes(eg))
        for page in {log.FLAG & ~0xFFF, log.FILETYPE_RAM & ~0xFFF, log.TONE_RAM & ~0xFFF,
                     p.SUB_INDEX & ~0xFFF, STATE & ~0xFFF, (STATE + 0x314) & ~0xFFF}:
            self.uc.mem_map(page, 0x1000)
        self.uc.mem_map(STACK, 0x10000)

    def run(self, start, until, regs):
        self.uc.reg_write(UC_ARM64_REG_SP, STACK + 0x8000)
        self.uc.reg_write(UC_ARM64_REG_X30, STOP)
        for r, v in regs.items():
            self.uc.reg_write(r, v)
        self.uc.emu_start(start, until, count=400)
        return self.uc.reg_read(UC_ARM64_REG_PC)

    def setup(self, flag=0, filetype=3, tone=2, dev=0, sub=0, alt=0):
        self.uc.mem_write(log.FLAG, bytes([flag]))
        self.uc.mem_write(log.FILETYPE_RAM, struct.pack('<I', filetype))
        self.uc.mem_write(log.TONE_RAM, struct.pack('<I', tone))
        self.uc.mem_write(p.SUB_INDEX, struct.pack('<I', sub))
        self.uc.mem_write(STATE + 0x15A, bytes([dev]))
        self.uc.mem_write(STATE + 0x314, bytes([alt]))

    def x(self, reg):
        return self.uc.reg_read(reg)


def deref(eg, entry):
    """Pointer-table entry -> bytes it points to (private rows in ROM, native rows in init RAM)."""
    target = p.ptr(eg, entry)
    n = p.CURVE_BYTES
    if p.CODE <= target < p.FREE_END:
        return target, p.rd(eg, target, n)
    return target, p.ram_alias(eg, target, n)


def verify(stock_eg, patched_eg):
    t = p.tables()
    L = p.layout()
    native, patched = Machine(stock_eg), Machine(patched_eg)
    report = dict(va_type_cases=0, matrix_cases=0, curve_cases=0)

    # 1. VA type at 40e9a2ec..40e9a2f0 (w9 == 2 on entry: cfg+0x3d8 is N-Log).
    for flag, ft, tone in itertools.product(range(4), (3, 1), (2, 0)):
        want = flag + 2 if flag in (1, 2) and ft == 3 and tone == 2 else 1
        for m, expect in ((native, 1), (patched, want)):
            m.setup(flag, ft, tone)
            pc = m.run(p.VA_SITE, p.VA_RESUME, {UC_ARM64_REG_X9: 2, UC_ARM64_REG_X10: 0xDEAD})
            p.need(pc == p.VA_RESUME and m.x(UC_ARM64_REG_X10) == expect and m.x(UC_ARM64_REG_X9) == 2,
                   f'VA type flag={flag} ft={ft} tone={tone}')
        report['va_type_cases'] += 1

    def private(mode, kind, dev, sub):
        return L[f'{mode}_{kind}_table'] + dev * 16 + sub * 8

    # 2. 402d197c matrix entry; 3. 402d1ad0 matrix/A/B entries.
    for va, mode_arg, dev, sub, alt in itertools.product(range(5), range(4), (0, 1), (0, 1), (0, 1)):
        for m in (native, patched):
            m.setup(dev=dev, sub=sub, alt=alt)
        # 402d197c(mode, va, flag!=0) stops after x19 is chosen.
        got = []
        for m in (native, patched):
            pc = m.run(0x402D197C, 0x402D19FC, {UC_ARM64_REG_X0: mode_arg, UC_ARM64_REG_X1: va, UC_ARM64_REG_X2: 1})
            p.need(pc == 0x402D19FC, 'matrix selector did not reach upload')
            got.append(m.x(UC_ARM64_REG_X19))
        custom = va in (3, 4) and mode_arg | 1 != 3 and not alt
        if custom:
            mode = p.MODES[va - 3][0]
            p.need(got[1] == private(mode, 'm', dev, sub), f'matrix entry va={va}')
        else:  # native types, recording modes and the alternate set must be untouched
            p.need(got[0] == got[1], f'native matrix entry changed va={va} mode={mode_arg} alt={alt}')
        report['matrix_cases'] += 1
        # 402d1ad0(va, mode) stops at 402d1ba0 with x9/x20/x19 = matrix/A/B entries.
        got = []
        for m in (native, patched):
            pc = m.run(0x402D1AD0, 0x402D1BA0, {UC_ARM64_REG_X0: va, UC_ARM64_REG_X1: mode_arg})
            p.need(pc == 0x402D1BA0, 'curve selector did not reach upload')
            got.append((m.x(UC_ARM64_REG_X9), m.x(UC_ARM64_REG_X20), m.x(UC_ARM64_REG_X19)))
        if custom:
            mode = p.MODES[va - 3][0]
            want = (private(mode, 'm', dev, sub), private(mode, 'a', dev, sub), p.NLOG_B + dev * 16 + sub * 8)
            p.need(got[1] == want, f'curve entries va={va} dev={dev} sub={sub}')
            for entry, kind in zip(want, ('m', 'a', 'b')):
                target, data = deref(patched_eg, entry)
                if kind == 'b' or dev == 1:
                    native_entry = {'m': p.NLOG_M, 'a': p.NLOG_A, 'b': p.NLOG_B}[kind] + dev * 16 + sub * 8
                    p.need(target == p.ptr(stock_eg, native_entry), f'{kind} row should stay native')
                else:
                    row = t['modes'][mode][sub]
                    if kind == 'm':
                        p.need(struct.unpack('<9h', data[2:20]) == tuple(row['matrix']) and data[:2] == b'\1\1',
                               'matrix descriptor bytes')
                    else:
                        p.need(struct.unpack('<33H', data[:66]) == tuple(row['curve_a_y'])
                               and struct.unpack('<31H', data[66:128]) == tuple(row['curve_a_knots']), 'curve A bytes')
        else:
            p.need(got[0] == got[1], f'native curve entries changed va={va} mode={mode_arg} alt={alt}')
        report['curve_cases'] += 1
    # 4. Video file type page, H.265 10-bit row, tone 2: text left at [sp] for the row.
    report['file_type_text_cases'] = 0
    for flag in range(4):
        texts = []
        for m in (native, patched):
            m.setup(flag)
            m.uc.mem_write(STACK + 0x8000, b'\xAA' * 16)
            pc = m.run(p.FT_SITE, p.FT_RESUME, {})
            p.need(pc == p.FT_RESUME, 'file type text did not resume')
            texts.append(bytes(m.uc.mem_read(STACK + 0x8000, 16)).split(b'\0')[0])
        p.need(texts[0] == b'N-Log' and texts[1] == p.FT_TEXT.get(flag, b'N-Log'), f'file type text flag={flag}')
        report['file_type_text_cases'] += 1
    report['passed'] = True
    return report
