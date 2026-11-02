"""Experimental composition of a BT.2020->target gamut matrix with R2Y M1.

The target is RED's RWG or Sony's S-Gamut3.
The native M1 field/format and multiplication code were traced in C3.11.
Pre-Lut1 hardware ordering and the incoming primaries still require pixel
validation. This is a separate, explicitly named research candidate.
"""
import math
import struct
from .curve import REC2020_TO_RWG

MATRIX_VA = 0x40B02800
MATRIX_SITE = 0x41116500  # native BL that computes fresh M1
NATIVE_MULTIPLY = 0x4112CF8C
Q = 16384
M1_OFFSET = 0x12


def coefficients(table=REC2020_TO_RWG):
    values = []
    for row in table:
        fixed = [math.floor(x * Q + .5) for x in row]
        # Preserve a neutral axis exactly in this transform's fixed-point
        # representation; published decimal coefficients have rounding.
        fixed[max(range(3), key=lambda i: row[i])] += Q - sum(fixed)
        if any(x < 0 or x > 32767 for x in fixed):
            raise ValueError('Unexpected fixed-point gamut coefficient')
        values.extend(fixed)
    return tuple(values)


def matrix_bytes(table=REC2020_TO_RWG):
    return struct.pack('<9h', *coefficients(table))


def compose_reference(existing, table=REC2020_TO_RWG):
    if len(existing) != 9 or any(not isinstance(x, int) or not -32768 <= x <= 32767 for x in existing):
        raise ValueError('Nine signed 16-bit native M1 coefficients required')
    transform = coefficients(table)
    out = []
    for r in range(3):
        for c in range(3):
            total = sum(transform[r*3+k] * existing[k*3+c] for k in range(3))
            value = (abs(total) + Q//2)//Q
            out.append(-value if total < 0 else value)
    return tuple(out)


def append_hook(b, *, flag, filetype_address, filetype_value, matrices=(MATRIX_VA,)):
    """matrices[k-1] is the transform for switch value k."""
    b.label('rwg_matrix')
    b.stp_pre(19, 30, -96)
    b.stp(20, 21, 16)
    b.str_x(2, 31, 32)  # native fresh-M1 output pointer
    # Preserve the original multiply, including its argument scaling and
    # return value. Applying T only after this recomputation prevents
    # accidental repeated T*T transforms on cached/serialized parameters.
    b.bl(NATIVE_MULTIPLY)
    b.str_x(0, 31, 40)
    b.ldr_x(8, 19, 0x40)
    b.ldr_w(9, 8, 0xBC)
    b.cmp_wi(9, 1)
    b.b_cond('ne', 'rwg_done')
    if len(matrices) > 1:
        from .patcher import choose
        b.mov_x64(8, filetype_address)
        b.ldr_w(8, 8)
        b.cmp_wi(8, filetype_value)
        b.b_cond('ne', 'rwg_done')
        b.mov_x64(8, flag)
        b.ldrb_w(8, 8)
        choose(b, 8, [{0: va} for va in matrices], 'rwg_done', 'matrix_pick')
        b.ldr_x(20, 31, 32)
    else:
        b.mov_x64(8, flag)
        b.ldrb_w(8, 8)
        b.cmp_wi(8, 1)
        b.b_cond('ne', 'rwg_done')
        b.mov_x64(8, filetype_address)
        b.ldr_w(8, 8)
        b.cmp_wi(8, filetype_value)
        b.b_cond('ne', 'rwg_done')
        b.ldr_x(20, 31, 32)
        b.mov_x64(0, matrices[0])
    # Column-vector convention: M_new = T_BT2020_to_RWG * M_native (x0 = T).
    b.mov_x(1, 20)
    b.add_xi(2, 31, 48)
    b.mov_w(3, Q)
    b.bl(NATIVE_MULTIPLY)
    b.mov_x(0, 20)
    b.add_xi(1, 31, 48)
    b.mov_w(2, 18)
    b.bl(0x4127A900)
    b.label('rwg_done')
    b.ldr_x(0, 31, 40)
    b.ldp(20, 21, 16)
    b.ldp_post(19, 30, 96)
    b.ret()
