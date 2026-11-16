from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from script_video.launcher import launch


class LauncherTests(unittest.TestCase):
    def test_cancel_does_not_start_production(self):
        with patch('script_video.launcher.choose_source', return_value=None), patch('video.make_video') as make:
            self.assertEqual(launch(), 0)
            make.assert_not_called()

    def test_failed_production_does_not_open_an_old_video(self):
        with patch('video.make_video', side_effect=ValueError('文案为空')), \
                patch('script_video.launcher.message') as message, \
                patch('script_video.launcher.subprocess.run') as run:
            self.assertEqual(launch(Path('空文案.txt')), 1)
            message.assert_called_once()
            run.assert_not_called()

    def test_success_opens_the_exact_returned_path(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / '成片 含$()和\'引号.mp4'
            target.write_bytes(b'valid-result-placeholder')
            with patch('video.make_video', return_value={'video': str(target)}), \
                    patch('script_video.launcher.subprocess.run') as run:
                self.assertEqual(launch(Path('输入.txt')), 0)
                self.assertEqual(run.call_args_list[0].args[0], ['open', str(target)])
                self.assertEqual(run.call_args_list[1].args[0], ['open', '-R', str(target)])


if __name__ == '__main__':
    unittest.main()
