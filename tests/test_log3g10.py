import itertools
import math
from pathlib import Path
import struct
import unittest
from z8log3g10.curve import input_grid, log3g10, lut_row, slog3
from z8log3g10 import patcher as p

ROOT = Path(__file__).resolve().parents[1]


class CurveTests(unittest.TestCase):
    def test_red_published_anchors(self):
        for x, y in [(-.01,0), (0,.091551), (.18,.333333), (1,.493449), (184.322,1)]:
            with self.subTest(x=x):
                self.assertAlmostEqual(log3g10(x), y, places=5)
        self.assertAlmostEqual(log3g10(-.02), -.151927)

    def test_nonfinite_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                log3g10(value)

    def test_grid_precision_and_monotonicity(self):
        grid = input_grid()
        values = struct.unpack('<229H', lut_row())
        self.assertEqual(len(grid), 229)
        self.assertEqual(grid[:9], list(range(9)))
        self.assertEqual(grid[40:42], [384,416])
        self.assertEqual(grid[-1], 65535)
        self.assertEqual(values[0], 3000)
        self.assertTrue(all(a < b for a,b in zip(grid,grid[1:])))
        self.assertTrue(all(a <= b for a,b in zip(values,values[1:])))
        # Independent scalar equation at every grid input bounds the table
        # error to half of a 15-bit code, with no N-Log decoding step.
        for x, value in zip(grid,values):
            exact = .224282 * math.log10(1 + 155.975327 * (.01 + x * .00045)) * 32768
            self.assertLessEqual(abs(value-exact), .500001)


class SLog3Tests(unittest.TestCase):
    def test_sony_code_values(self):
        for x, code in [(0,95), (.18,420), (.9,598)]:
            with self.subTest(x=x):
                self.assertEqual(round(slog3(x)*1023), code)
        self.assertAlmostEqual(slog3(.01125)*1023, 171.2102946929, places=6)
        self.assertAlmostEqual(slog3(.18)*1023, 420, places=9)

    def test_inverse_of_sony_idt(self):
        # SLog3_to_linear, as Sony supplies it to ACES.
        def decode(y):
            if y >= 171.2102946929/1023:
                return 10**((y*1023-420)/261.5)*(.18+.01)-.01
            return (y*1023-95)*.01125/(171.2102946929-95)
        for x in (0,.001,.01125,.05,.18,.9,5,29):
            with self.subTest(x=x):
                self.assertAlmostEqual(decode(slog3(x)), x, places=9)

    def test_nonfinite_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                slog3(value)

    def test_table_scale_and_monotonicity(self):
        from z8log3g10.curve import nlg_gamma_row
        grid = input_grid()
        values = struct.unpack('<229H', lut_row('slog3'))
        self.assertEqual(values[0], 95*32)
        self.assertTrue(all(a < b for a,b in zip(values,values[1:])))
        self.assertLess(values[-1], 32767)
        self.assertLess(max(struct.unpack('<229H', nlg_gamma_row('slog3'))), 4092)
        for x, value in zip(grid,values):
            exact = slog3(x*.00045)*1023*32
            self.assertLessEqual(abs(value-exact), .500001)

    def test_log3g10_table_unchanged(self):
        self.assertEqual(lut_row(), lut_row('log3g10'))
        self.assertEqual(struct.unpack('<229H', lut_row())[0], 3000)


class SGamut3Tests(unittest.TestCase):
    @staticmethod
    def to_xyz(primaries):
        import numpy as np
        point = lambda x, y: np.array([x/y, 1, (1-x-y)/y])
        white = point(.3127, .3290)
        matrix = np.column_stack([point(*c) for c in primaries])
        return matrix*np.linalg.solve(matrix, white)

    def test_primaries_match_sony_matrix(self):
        import numpy as np
        sony = np.array(((.7064827132,.1288010498,.1151721641),
                         (.2709796708,.7866064112,-.0575860820),
                         (-.0096778454,.0046000375,1.0941355587)))
        derived = self.to_xyz(((.73,.28),(.14,.855),(.1,-.05)))
        self.assertLess(abs(derived-sony).max(), 1e-9)

    def test_matrix_from_primaries(self):
        import numpy as np
        from z8log3g10.curve import REC2020_TO_SGAMUT3
        wanted = np.linalg.solve(self.to_xyz(((.73,.28),(.14,.855),(.1,-.05))),
                                 self.to_xyz(((.708,.292),(.17,.797),(.131,.046))))
        self.assertLess(abs(wanted-np.array(REC2020_TO_SGAMUT3)).max(), 6e-7)
        self.assertGreater(wanted.min(), 0)

    def test_fixed_point_white_and_precision(self):
        from z8log3g10.matrix import coefficients,Q,compose_reference
        from z8log3g10.curve import REC2020_TO_SGAMUT3
        fixed = coefficients(REC2020_TO_SGAMUT3)
        for r in range(3):
            self.assertEqual(sum(fixed[r*3:r*3+3]),Q)
            for c in range(3):
                self.assertLess(abs(fixed[r*3+c]/Q-REC2020_TO_SGAMUT3[r][c]),.00006)
        # The three terms round separately on M1's own scale, so the neutral
        # row may sit one M1 step off even though T sums exactly to Q.
        result = compose_reference((512,0,0,0,512,0,0,0,512),REC2020_TO_SGAMUT3)
        for r in range(3):
            self.assertLessEqual(abs(sum(result[r*3:r*3+3])-512),1)


class TileTests(unittest.TestCase):
    def test_both_tiles_fit(self):
        from z8log3g10.label import FILL_SIZE, OUTLINE_SIZE, tile_images
        for text in ('L3G10','SLOG3'):
            with self.subTest(text=text):
                fill, outline = tile_images(text)
                self.assertEqual(struct.unpack_from('>2I',fill,16),FILL_SIZE)
                self.assertEqual(struct.unpack_from('>2I',outline,16),OUTLINE_SIZE)
                self.assertLess(len(fill),0x1000)
                self.assertLess(len(outline),0x1000)
        self.assertNotEqual(tile_images('L3G10'),tile_images('SLOG3'))


class RWGReferenceTests(unittest.TestCase):
    def test_fixed_point_white_and_precision(self):
        from z8log3g10.matrix import coefficients,Q,compose_reference
        from z8log3g10.curve import REC2020_TO_RWG
        fixed = coefficients()
        for r in range(3):
            self.assertEqual(sum(fixed[r*3:r*3+3]),Q)
            for c in range(3):
                self.assertLess(abs(fixed[r*3+c]/Q-REC2020_TO_RWG[r][c]),.00005)
        result = compose_reference((512,0,0,0,512,0,0,0,512))
        for r in range(3):
            self.assertEqual(sum(result[r*3:r*3+3]),512)

    def test_transform_precedes_log_in_reference(self):
        from z8log3g10.curve import REC2020_TO_RWG
        correct = [log3g10(row[0]) for row in REC2020_TO_RWG]
        wrong = [sum(row[k]*log3g10(1 if k==0 else 0) for k in range(3)) for row in REC2020_TO_RWG]
        self.assertGreater(max(abs(a-b) for a,b in zip(correct,wrong)),.05)

@unittest.skipUnless((ROOT/'Z_8_0311.bin').is_file(), 'Local official firmware required')
class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from z8prores.package import Package, require_official_input
        from features import build, FEATURES
        cls.original = (ROOT/'Z_8_0311.bin').read_bytes()
        require_official_input(cls.original)
        cls.package = Package(cls.original)
        cls.stock = cls.package.eg
        cls.baseline, _ = build(cls.stock, '04.13', 'e0', FEATURES)
        cls.image, cls.meta = p.apply(cls.stock, cls.baseline)

    def test_fifteen_base_feature_combinations(self):
        from features import FEATURES, build
        for n in range(1,5):
            for choices in itertools.combinations(FEATURES,n):
                with self.subTest(features=choices):
                    baseline, _ = build(self.stock, '04.13', 'e0', choices)
                    image, meta = p.apply(self.stock, baseline)
                    self.assertEqual(image.new[p.STOCK_LUT:p.STOCK_LUT+1374], self.stock[p.STOCK_LUT:p.STOCK_LUT+1374])
                    self.assertEqual(image.new[p.LUT-p.BASE:p.LUT-p.BASE+1374], lut_row()*3)
                    # Every original string boundary remains byte-identical.
                    count = meta['prior_string_entries']
                    for lang in range(36):
                        old = struct.unpack_from('<Q',baseline,0x311C5A0+8*lang)[0]-p.BASE
                        new = struct.unpack_from('<Q',image.new,0x311C5A0+8*lang)[0]-p.BASE
                        self.assertEqual(image.new[new:new+count*4],baseline[old:old+count*4])

    def test_native_arm_routines(self):
        from z8log3g10.emulation import verify_routines
        result = verify_routines(self.stock, self.image.new, {k:int(v,16) for k,v in self.meta['labels'].items()})
        self.assertTrue(result['passed'])
        self.assertEqual((result['lut_cases'],result['menu_entry_cases'],result['selection_cases']),(54,36,20))
        self.assertEqual((result['nlg_cases'],result['nlg_forced_row3_cases']),(162,108))

    def test_private_nlg_gamma_pairs_private_lut(self):
        from z8log3g10.curve import nlg_gamma_row
        lut = struct.unpack('<229H', lut_row())
        nlg = struct.unpack('<229H', nlg_gamma_row())
        self.assertEqual(nlg, tuple(min(4092,(v+4)//8) for v in lut))
        self.assertEqual(self.image.new[p.NLG-p.BASE:p.NLG-p.BASE+458], nlg_gamma_row())
        self.assertEqual(self.image.new[p.STOCK_NLG:p.STOCK_NLG+4*458], self.stock[p.STOCK_NLG:p.STOCK_NLG+4*458])
        self.assertLessEqual(p.NLG+458, 0x40B02800)

    def test_file_metadata_routing(self):
        from z8log3g10.emulation import verify_metadata_routines
        for gamut in p.PROFILES:
            with self.subTest(gamut=gamut):
                image, _ = p.apply(self.stock, self.baseline, gamut)
                result = verify_metadata_routines(self.stock, image.new, gamut)
                self.assertTrue(result['passed'])
                flags = len(p.modes(gamut)) + 2
                self.assertEqual((result['vui_cases'],result['colr_cases'],result['picture_cases']),(72*flags,72*flags,18*flags))
                self.assertFalse(result['recorded_file_verified'])


    def test_rwg_matrix_native_hook(self):
        from z8log3g10.emulation import verify_matrix_routines
        image, meta = p.apply(self.stock,self.baseline,'rwg-research')
        result = verify_matrix_routines(self.stock,image.new)
        self.assertEqual(result['cases'],632)
        self.assertTrue(result['no_repeated_matrix_compounding'])
        self.assertTrue(result['passed'])
        self.assertFalse(result['hardware_stage_order_verified'])
        self.assertTrue(meta['rwg_matrix_inserted'])

    def test_slog3_build_payload(self):
        from z8log3g10.curve import nlg_gamma_row, REC2020_TO_SGAMUT3
        from z8log3g10.emulation import verify_matrix_routines, verify_routines
        from z8log3g10.matrix import MATRIX_VA, matrix_bytes
        from z8log3g10.label import tile_images
        image, meta = p.apply(self.stock, self.baseline, 'sgamut3-slog3')
        at = lambda va, size: image.new[va-p.BASE:va-p.BASE+size]
        self.assertEqual(at(p.LUT,1374), lut_row('slog3')*3)
        self.assertEqual(at(p.NLG,458), nlg_gamma_row('slog3'))
        self.assertEqual(at(MATRIX_VA,18), matrix_bytes(REC2020_TO_SGAMUT3))
        self.assertEqual(at(p.PICTURE+8,20), b'S-LOG3'.ljust(20,b'\0'))
        self.assertEqual(at(p.TEXT,34), 'S-Log3 / S-Gamut3'.encode('utf-16le'))
        fill, outline = tile_images('SLOG3')
        self.assertEqual(at(p.TILE_PNG,len(fill)+len(outline)), fill+outline)
        self.assertEqual(image.new[p.STOCK_LUT:p.STOCK_LUT+1374], self.stock[p.STOCK_LUT:p.STOCK_LUT+1374])
        routines = verify_routines(self.stock, image.new, {k:int(v,16) for k,v in meta['labels'].items()})
        self.assertEqual((routines['lut_cases'],routines['nlg_cases'],routines['tile_cases']),(54,162,72))
        self.assertEqual(verify_matrix_routines(self.stock,image.new,'sgamut3-slog3')['cases'],632)

    def test_dual_build_keeps_each_row(self):
        from z8log3g10.curve import nlg_gamma_row, REC2020_TO_RWG, REC2020_TO_SGAMUT3
        from z8log3g10.emulation import verify_matrix_routines, verify_routines
        from z8log3g10.matrix import matrix_bytes
        from z8log3g10.label import tile_images
        image, meta = p.apply(self.stock, self.baseline, 'rwg-slog3-dual')
        at = lambda va, size: image.new[va-p.BASE:va-p.BASE+size]
        rwg, slog3 = p.modes('rwg-slog3-dual').values()
        for row, transfer, table, name in ((rwg,'log3g10',REC2020_TO_RWG,b'LOG3G10'), (slog3,'slog3',REC2020_TO_SGAMUT3,b'S-LOG3')):
            self.assertEqual(at(row['lut'],1374), lut_row(transfer)*3)
            self.assertEqual(at(row['nlg'],458), nlg_gamma_row(transfer))
            self.assertEqual(at(row['matrix_va'],18), matrix_bytes(table))
            self.assertEqual(at(row['picture_va']+8,20), name.ljust(20,b'\0'))
        text = 'Log3G10 / RWG test'.encode('utf-16le') + 'S-Log3 / S-Gamut3'.encode('utf-16le')
        self.assertEqual(at(p.TEXT,len(text)), text)
        tiles = b''.join(tile_images('L3G10') + tile_images('SLOG3'))
        self.assertEqual(at(p.TILE_PNG,len(tiles)), tiles)
        # Every 04.16 row asset sits where the 04.16 build put it.
        single, _ = p.apply(self.stock, self.baseline, 'rwg-research')
        for va, size in ((p.LUT,1374),(p.NLG,458),(rwg['matrix_va'],18),(p.PICTURE,p.PICTURE_BYTES)):
            self.assertEqual(at(va,size), single.new[va-p.BASE:va-p.BASE+size])
        self.assertEqual(struct.unpack_from('<H',image.new,p.PAGE+32)[0], 11)
        self.assertEqual(meta['menu_label'], ['Log3G10 / RWG test','S-Log3 / S-Gamut3'])
        routines = verify_routines(self.stock, image.new, {k:int(v,16) for k,v in meta['labels'].items()}, 'rwg-slog3-dual')
        self.assertEqual((routines['lut_cases'],routines['nlg_cases'],routines['menu_entry_cases'],
                          routines['selection_cases'],routines['tile_cases']),(72,216,54,33,96))
        self.assertEqual(verify_matrix_routines(self.stock,image.new,'rwg-slog3-dual')['cases'],976)

    def test_rwg_fifteen_feature_combinations(self):
        from features import FEATURES,build
        from z8log3g10.matrix import MATRIX_SITE,MATRIX_VA,matrix_bytes
        for n in range(1,5):
            for choices in itertools.combinations(FEATURES,n):
                with self.subTest(features=choices):
                    baseline,_ = build(self.stock,'04.14','e0',choices)
                    image,meta = p.apply(self.stock,baseline,'rwg-research')
                    self.assertEqual(image.new[MATRIX_VA-p.BASE:MATRIX_VA-p.BASE+18],matrix_bytes())
                    self.assertEqual(image.new[p.STOCK_LUT:p.STOCK_LUT+1374],self.stock[p.STOCK_LUT:p.STOCK_LUT+1374])
                    count=meta['prior_string_entries']
                    for lang in range(36):
                        old=struct.unpack_from('<Q',baseline,0x311C5A0+8*lang)[0]-p.BASE
                        new=struct.unpack_from('<Q',image.new,0x311C5A0+8*lang)[0]-p.BASE
                        self.assertEqual(image.new[new:new+count*4],baseline[old:old+count*4])

    def test_plain_0414_identity_and_package_roundtrip(self):
        from features import FEATURES
        from z8prores.patcher import public_words
        from z8prores.package import Package
        from z8log3g10.verify import expected_payload, verify_candidate
        tagged, _, _ = expected_payload(self.stock, FEATURES, '04.14', 'e1', 'rwg-research')
        plain, _, _ = expected_payload(self.stock, FEATURES, '04.14', '', 'rwg-research')
        fixed = b'04.14\0\0\0'
        self.assertEqual(plain[0x14EAA90:0x14EAA98], fixed)
        self.assertEqual(plain[-11:-3], fixed)
        self.assertEqual(plain[0xEB29FC:0xEB29FC+12], public_words('04.14'))
        # Executable feature bytes and all curve/matrix/menu data must be
        # exactly the previously tested e1 candidate; only identities/CRC differ.
        normalized = bytearray(plain)
        for at, count in ((0x14EAA90,8),(len(plain)-11,8),(len(plain)-2,2)):
            normalized[at:at+count] = tagged[at:at+count]
        self.assertEqual(bytes(normalized), tagged)
        packet, checked = self.package.replace_eg(plain,'eg2070_0414.bi')
        self.assertEqual(len(packet), len(self.original))
        self.assertEqual(checked.modules[2]['name'],'eg2070_0414.bi')
        self.assertEqual(Package(packet).eg,plain)
        result = verify_candidate(self.original,packet,FEATURES,'04.14','',arm=False,gamut='rwg-research')
        self.assertTrue(result['passed'])

    def test_live_view_tile_routing(self):
        from z8log3g10.emulation import verify_routines
        from z8log3g10.label import FILL_SIZE, OUTLINE_SIZE
        result = verify_routines(self.stock, self.image.new, {k:int(v,16) for k,v in self.meta['labels'].items()})
        self.assertEqual(result['tile_cases'], 72)
        size, address = struct.unpack_from('<IxxxxQ', self.image.new, p.TILE_TABLE-p.BASE)
        self.assertEqual(struct.unpack_from('>2I', self.image.new, address-p.BASE+16), FILL_SIZE)
        size, address = struct.unpack_from('<IxxxxQ', self.image.new, p.TILE_TABLE-p.BASE+16)
        self.assertEqual(struct.unpack_from('>2I', self.image.new, address-p.BASE+16), OUTLINE_SIZE)

    def test_switch_is_a_native_setting(self):
        self.assertEqual(p.property_ram(self.stock, p.FLAG_PROPERTY), p.FLAG)
        self.assertEqual(p.property_default(self.image.new, p.FLAG_PROPERTY), 0)
        self.assertEqual(struct.unpack_from('<3I', self.stock, p.SETTINGS_TABLE-p.BASE), (0x06000000, 8, 2))

    def test_card_wav_stack_and_longer_package(self):
        from features import FEATURES
        from z8cardwav import stack
        from z8log3g10.verify import expected_payload, verify_candidate
        from z8log3g10.matrix import MATRIX_VA, matrix_bytes
        if not Path(stack.LLVM).is_dir():
            self.skipTest('LLVM required')
        payload, _, _ = expected_payload(self.stock, FEATURES, '04.16', '', 'rwg-research', card_wav=True)
        self.assertGreater(len(payload), len(self.stock))
        self.assertEqual(payload[-15:-2], b'Ver.04.16\0\0\0\0')
        self.assertEqual(payload[MATRIX_VA-p.BASE:MATRIX_VA-p.BASE+18], matrix_bytes())
        packet = stack.pack(self.package, payload, 'eg2070_0416.bi')
        self.assertEqual(stack.unpack(self.package, packet, 'eg2070_0416.bi'), payload)
        self.assertTrue(verify_candidate(self.original, packet, FEATURES, '04.16', '', arm=False,
                                         gamut='rwg-research', card_wav=True)['passed'])

    def test_occupied_region_rejected(self):
        data = bytearray(self.baseline)
        data[p.CODE-p.BASE] = 1
        with self.assertRaisesRegex(ValueError, 'occupied'):
            p.apply(self.stock,data)

    def test_modified_original_or_curve_rejected(self):
        data = bytearray(self.stock); data[123456] ^= 1
        with self.assertRaisesRegex(ValueError, 'Exact official'):
            p.apply(data,self.baseline)
        data = bytearray(self.baseline); data[p.STOCK_LUT] ^= 1
        with self.assertRaisesRegex(ValueError, 'already changes'):
            p.apply(self.stock,data)

    def test_valid_envelope_extra_edit_rejected(self):
        from features import FEATURES
        from z8log3g10.verify import expected_payload, verify_candidate
        import binascii
        result, _, _ = expected_payload(self.stock, FEATURES, '04.13', 'e0')
        tampered = bytearray(result)
        tampered[0xA90000] ^= 1  # outside the declared experimental region
        tampered[-2:] = binascii.crc_hqx(tampered[:-2],0).to_bytes(2,'big')
        packet, _ = self.package.replace_eg(tampered,'eg2070_0413e0.bi')
        with self.assertRaisesRegex(ValueError, 'bounded experimental recipe'):
            verify_candidate(self.original,packet,FEATURES,'04.13','e0',arm=False)


if __name__ == '__main__':
    unittest.main()
