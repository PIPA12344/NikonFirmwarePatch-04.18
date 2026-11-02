"""RED's published Log3G10 and Sony's S-Log3 on the Nikon R2Y 229-node input grid.

The grid/grey placement is a research assumption corroborated by
ShiSheng233/NLoader-apps (mkcurve.py), not an on-camera Z8 calibration.
No upstream implementation or firmware table is redistributed here.
"""
import math
import struct

POINTS = 229
ROW_BYTES = POINTS * 2
RED_WHITE_PAPER = 'https://docs.red.com/955-0187/PDF/915-0187%20Rev-C%20%20%20RED%20OPS,%20White%20Paper%20on%20REDWideGamutRGB%20and%20Log3G10.pdf'
NIKON_NLOG_SPEC = 'https://download.nikonimglib.com/archive3/hDCmK00m9JDI03RPruD74xpoU905/N-Log_Specification_(En)01.pdf'
GRID_RESEARCH = 'https://github.com/ShiSheng233/NLoader-apps/blob/0912deac4aff767af56f3ebf9b3f093faff35744/log3g10/mkcurve.py'
# Sony's own ACES input transform, the source of the S-Log3 constants. Its
# S-Gamut3 matrix also confirms the primaries behind REC2020_TO_SGAMUT3.
SONY_SLOG3_IDT = 'https://github.com/ampas/aces-dev/blob/710ecbe52c87ce9f4a1e02c8ddf7ea0d6b611cc8/transforms/ctl/idt/vendorSupplied/sony/IDT.Sony.SLog3_SGamut3.ctl'

# Published reference. Only the optional RWG research build inserts it.
REC2020_TO_RWG = ((.853263, .079695, .067042),
                  (.029375, .809195, .161430),
                  (.051575, .208097, .740329))
# Sony publishes no direct table: derived from the S-Gamut3 and ITU-R BT.2020
# primaries, both D65. Every coefficient is positive, so BT.2020 cannot clip.
REC2020_TO_SGAMUT3 = ((.895573, .046511, .057916),
                      (.026021, .847553, .126426),
                      (.007812, .022505, .969682))


def log3g10(linear):
    value = float(linear)
    if not math.isfinite(value):
        raise ValueError('Finite linear value required')
    shifted = value + .01
    return shifted * 15.1927 if shifted < 0 else .224282 * math.log10(155.975327 * shifted + 1)


def slog3(linear):
    value = float(linear)
    if not math.isfinite(value):
        raise ValueError('Finite linear value required')
    if value >= .01125:
        return (420 + math.log10((value + .01) / (.18 + .01)) * 261.5) / 1023
    return (value * (171.2102946929 - 95) / .01125 + 95) / 1023


# Encoder and the multiplier that puts its output on the 15-bit job scale.
# S-Log3 is defined on 10-bit code values, so its scale is 1023 * 32.
TRANSFERS = dict(log3g10=(log3g10, 32768), slog3=(slog3, 1023 * 32))


def nlog(linear):
    value = float(linear)
    if not math.isfinite(value) or value < 0:
        raise ValueError('Nonnegative finite reflectance required')
    return 650 * (value + .0075) ** (1 / 3) if value < .328 else 150 * math.log(value) + 619


def input_grid():
    # Select hardware breakpoints by the spacing in each input interval.
    intervals = ((8, 1), (16, 2), (32, 4), (128, 8), (256, 16),
                 (1024, 32), (2048, 64), (4096, 128), (32768, 256),
                 (49152, 1024), (63488, 2048))
    grid = []
    lower = 0
    for upper, spacing in intervals:
        grid.extend(x for x in range(lower, upper + 1) if x % spacing == 0 and (not grid or x > grid[-1]))
        lower = upper + 1
    grid.append(65535)
    if len(grid) != POINTS or grid[40:42] != [384, 416]:
        raise ValueError('Unexpected R2Y grid')
    return grid


def lut_row(transfer='log3g10'):
    # One exposure placement only: grid 400 == linear reflectance .18.
    # 15-bit full scale is 32768; code values in the job use 5 fraction bits.
    encode, scale = TRANSFERS[transfer]
    values = [min(32767, max(0, math.floor(encode(x * .18 / 400) * scale + .5)))
              for x in input_grid()]
    if not all(a <= b for a, b in zip(values, values[1:])):
        raise ValueError('Curve is not monotonic')
    return struct.pack('<229H', *values)


def nlg_gamma_row(transfer='log3g10'):
    # C3.11's N-Log NlgGamma row is its Lut1 row rounded to 12 bits
    # (all 229 nodes); keep that pairing for the private Lut1 row.
    values = [min(4092, (v + 4) // 8) for v in struct.unpack('<229H', lut_row(transfer))]
    return struct.pack('<229H', *values)


def reference_summary(transfer='log3g10'):
    values = struct.unpack('<229H', lut_row(transfer))
    summary = dict(gamut='BT.2020', redwidegamut_applied=False,
                   grey_grid=400, black_code_10bit=values[0] / 32,
                   grey_code_10bit=(values[40] + values[41]) / 64,
                   top_grid_code_10bit=values[-1] / 32,
                   mathematical_grey=TRANSFERS[transfer][0](.18),
                   calibration='research grid; Z8 camera calibration outstanding',
                   grid_research=GRID_RESEARCH)
    if transfer == 'slog3':
        summary['sony_idt'] = SONY_SLOG3_IDT
    else:
        summary['red_white_paper'] = RED_WHITE_PAPER
    return summary
