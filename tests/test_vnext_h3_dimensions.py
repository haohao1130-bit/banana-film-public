"""Regression: VNext H3 sampling uses the legacy one-click film padded size.

The final export still uses the requested output dimensions.
"""
import unittest

from banana_mv.film_vnext.local_adapter import _h3_render_size
from banana_mv.film_vnext.pipeline import ProductionError


class VNextH3DimensionsTests(unittest.TestCase):
    def test_portrait_720p_aligns_width_before_sampling(self):
        self.assertEqual(_h3_render_size((720, 1280)), (736, 1280))

    def test_portrait_480p_aligns_height_before_sampling(self):
        self.assertEqual(_h3_render_size((480, 854)), (480, 864))

    def test_all_original_output_presets_keep_existing_contract(self):
        from banana_mv.core import OUTPUT_SIZE_PRESETS, dimensions
        for preset in OUTPUT_SIZE_PRESETS.values():
            for aspect, output in preset.items():
                with self.subTest(aspect=aspect, output=output):
                    self.assertEqual(_h3_render_size(output), dimensions(aspect, output[0]))
                    self.assertTrue(all(dim % 32 == 0 for dim in _h3_render_size(output)))

    def test_unknown_size_is_not_silently_changed(self):
        with self.assertRaises(ProductionError):
            _h3_render_size((721, 1280))


if __name__ == "__main__":
    unittest.main()
