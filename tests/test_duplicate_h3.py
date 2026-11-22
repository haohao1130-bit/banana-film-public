import unittest

from banana_mv import film
from banana_mv.direction_contract import last_complete_h3, validate_h3_sections


def six(tag):
    return (f'subject_definitions:\n<Subject 1> is 小巫 from <Picture 1>. {tag}\n\n'
            f'summary:\n小巫 greets a guest. {tag}\n\n'
            f'retention_analysis:\n<Subject 1>: fully_preserved. {tag}\n\n'
            f'detailed_description:\n[Shot 1] <Subject 1> bows at the izakaya door. {tag}\n\n'
            f'overall_soundscape:\nQuiet night street. {tag}\n\n'
            f'non_diegetic_music:\nNone. {tag}')


class DuplicateH3Tests(unittest.TestCase):
    def test_single_prompt_is_unchanged(self):
        self.assertEqual(last_complete_h3(six('A')), six('A'))

    def test_repeated_prompt_keeps_only_last_complete_copy(self):
        # 實測 7a634f08：正式稿 32227 字，同一份六欄寫了兩遍以上。
        text = six('FIRST') + '\n\nLet me revise.\n\n' + six('SECOND')
        kept = last_complete_h3(text)
        self.assertEqual(kept, six('SECOND'))
        validate_h3_sections(kept)

    def test_trailing_partial_copy_falls_back_to_last_complete_one(self):
        text = six('FIRST') + '\n\nsubject_definitions:\n<Subject 1> half\n\ndetailed_description:\n[Shot 1] cut off'
        self.assertEqual(last_complete_h3(text), six('FIRST'))

    def test_film_normalize_sends_one_copy_to_h3(self):
        text = film.normalize_prompt(six('FIRST') + '\n\n' + six('SECOND'), 1)
        self.assertEqual(text.count('detailed_description:'), 1)
        self.assertIn('SECOND', text)
        self.assertNotIn('FIRST', text)


if __name__ == '__main__':
    unittest.main()
