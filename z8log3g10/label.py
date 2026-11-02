"""Live-view tile "L3G10" or "SLOG3": the two grey PNGs that replace the stock N-LOG tile.

The firmware draws the tile as two 8-bit grey PNGs: a 64x32 fill and a 68x36
outline ring around it. Five characters cannot use the stock 14-pixel glyph
width with clear gaps, so all of them are drawn here. They are 24 pixels high,
centred on the stock 26-pixel glyph band, so every curve ends inside its cell.
"""
import math
import struct
import zlib

IMAGE_TABLE = 0x431D96D0  # 0x18-byte rows: u32 at +4 size, u64 at +0x10 data
FILL_SIZE = (64, 32)
OUTLINE_SIZE = (68, 36)
GLYPH_TOP = 3
GLYPH_HEIGHT = 24
HALF_STROKE = 1.8


def encode_grey(rows):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    raw = b''.join(b'\0' + bytes(line) for line in rows)
    header = struct.pack('>2I5B', len(rows[0]), len(rows), 8, 0, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


def arc(cx, cy, rx, ry, first, last, steps=24):
    return [(cx + rx * math.cos(math.radians(first + (last - first) * i / steps)),
             cy + ry * math.sin(math.radians(first + (last - first) * i / steps))) for i in range(steps + 1)]


def stroke(width, paths):
    """Antialiased constant-width polylines; the cell edge cuts ends flat."""
    def distance(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy or 1)))
        return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)
    cell = []
    for y in range(GLYPH_HEIGHT):
        line = []
        for x in range(width):
            near = min(distance(x + .5, y + .5, a, b) for path in paths for a, b in zip(path, path[1:]))
            line.append(round(255 * max(0, min(1, HALF_STROKE + .5 - near))))
        cell.append(line)
    return cell


def letter_l(width=10):
    return stroke(width, [[(2, -4), (2, 22), (14, 22)]])


def letter_s():
    return stroke(11, [arc(5.5, 7, 3.5, 5, -15, -270) + arc(5.5, 17, 3.5, 5, -90, 165)])


def three():
    top = arc(5.5, 6, 3.5, 4, 180, 360) + arc(5.5, 8, 3.5, 4, 0, 90)
    bottom = arc(5.5, 16, 3.5, 4, -90, 0) + arc(5.5, 18, 3.5, 4, 0, 180)
    return stroke(11, [top + [(4, 12)], [(4, 12)] + bottom])


def letter_g():
    outer = [(10, 7.5)] + arc(6, 6, 4, 4, 360, 180) + arc(6, 18, 4, 4, 180, 0)
    return stroke(12, [outer + [(10, 12.5), (6.5, 12.5)]])


def one():
    return stroke(6, [[(4, -4), (4, 28)], [(-1, 7.5), (4, 2)]])


def zero():
    return stroke(12, [arc(6, 6, 4, 4, 180, 360) + arc(6, 18, 4, 4, 0, 180) + [(2, 6)]])


def tile_images(text='L3G10'):
    """Return the new (fill, outline) PNGs."""
    fill = [[0] * FILL_SIZE[0] for _ in range(FILL_SIZE[1])]
    layout = {'L3G10': ((letter_l(), 0), (three(), 13), (letter_g(), 27), (one(), 42), (zero(), 51)),
              'SLOG3': ((letter_s(), 0), (letter_l(9), 13), (zero(), 24), (letter_g(), 38), (three(), 53))}
    for glyph, left in layout[text]:
        for y, line in enumerate(glyph):
            fill[GLYPH_TOP + y][left:left + len(line)] = line
    # Stock ring: the glyph grown by two pixels, minus the glyph itself.
    width, height = OUTLINE_SIZE
    outline = [[0] * width for _ in range(height)]
    disc = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if dx * dx + dy * dy <= 5]
    for y in range(height):
        for x in range(width):
            grown = 0
            for dx, dy in disc:
                u, v = x - 2 + dx, y - 2 + dy
                if 0 <= u < FILL_SIZE[0] and 0 <= v < FILL_SIZE[1]:
                    grown = max(grown, fill[v][u])
            inner = fill[y - 2][x - 2] if 0 <= y - 2 < FILL_SIZE[1] and 0 <= x - 2 < FILL_SIZE[0] else 0
            outline[y][x] = max(0, grown - inner)
    return encode_grey(fill), encode_grey(outline)
