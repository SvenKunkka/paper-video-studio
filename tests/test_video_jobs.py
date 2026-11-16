from pathlib import Path
import tempfile
import unittest

from video import prepare_job


class JobIsolationTests(unittest.TestCase):
    def test_changed_copy_keeps_prior_source_and_uses_new_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / '含 空格与$()的文案.txt'
            source.write_text('第一版。')
            plan = {'title': '测试', 'source': {'path': str(source), 'text': '第一版。'},
                    'scenes': [{'id': 's001', 'kind': 'text', 'narration': '第一版。'}]}
            _, before = prepare_job(plan, root / 'jobs')
            source.write_text('第二版。')
            plan['source']['text'] = plan['scenes'][0]['narration'] = '第二版。'
            _, after = prepare_job(plan, root / 'jobs')
            self.assertNotEqual(before, after)
            self.assertEqual((before / 'source.txt').read_text(), '第一版。')

    def test_changed_image_bytes_at_same_path_use_new_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / '文案.md'
            source.write_text('图片讲解。')
            image = root / '含 空格 (测试).png'
            image.write_bytes(b'first-image-content')
            plan = {'title': '图像', 'source': {'path': str(source), 'text': '图片讲解。'},
                    'scenes': [{'id': 's001', 'kind': 'image', 'narration': '图片讲解。', 'image': str(image)}]}
            frozen, first = prepare_job(plan, root / 'jobs')
            image.write_bytes(b'updated-image-content')
            _, second = prepare_job(plan, root / 'jobs')
            self.assertNotEqual(first, second)
            self.assertEqual(Path(frozen['scenes'][0]['image']).read_bytes(), b'first-image-content')
            self.assertEqual(plan['scenes'][0]['image'], str(image))


if __name__ == '__main__':
    unittest.main()
