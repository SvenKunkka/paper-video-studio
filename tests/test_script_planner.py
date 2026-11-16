import copy
import tempfile
import unittest
from pathlib import Path

from script_video.planner import make_plan, validate_plan


def compact(text):
    return "".join(text.split())


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def document(self, text, name="文案.md", encoding="utf-8"):
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def narration(self, plan):
        return "".join(s["narration"] for s in plan["scenes"])

    def test_empty_file_has_readable_error(self):
        with self.assertRaisesRegex(ValueError, "文案为空"):
            make_plan(self.document(" \n\n"))

    def test_chinese_long_text_split_only_between_sentences(self):
        sentences = [("这是没有空格的中文正文" * 3) + ending for ending in ("。", "！", "？", "。", "。")]
        text = "".join(sentences)
        plan = make_plan(self.document(text, "长文.txt"))
        self.assertGreater(len(plan["scenes"]), 1)
        self.assertEqual(compact(self.narration(plan)), compact(text))
        self.assertTrue(all(s["narration"][-1] in "。！？" for s in plan["scenes"]))

    def test_very_long_single_sentence_is_not_truncated(self):
        text = "一段没有任何句号的中文" * 40
        plan = make_plan(self.document(text, "长句.txt"))
        self.assertEqual(self.narration(plan), text)
        self.assertTrue(plan["warnings"])

    def test_english_sentences_and_decimal_numbers_are_preserved(self):
        text = ("This sentence mentions version 3.14 without cutting the number. " * 5)
        plan = make_plan(self.document(text, "english.txt"))
        self.assertGreater(len(plan["scenes"]), 1)
        self.assertEqual(compact(self.narration(plan)), compact(text))
        self.assertTrue(all("3.14" in s["narration"] for s in plan["scenes"]))

    def test_an_incidental_last_word_is_not_a_step_list(self):
        plan = make_plan(self.document("先说明最后希望拿到什么结果。"))
        self.assertEqual(plan["scenes"][0]["kind"], "text")

    def test_decimal_at_start_of_paragraph_is_not_a_list_marker(self):
        text = "3.14 是这段文案提供的数值。"
        plan = make_plan(self.document(text))
        self.assertEqual(self.narration(plan), text)
        self.assertEqual(plan["scenes"][0]["kind"], "text")

    def test_utf8_bom_and_gb18030(self):
        for encoding in ("utf-8-sig", "gb18030"):
            with self.subTest(encoding=encoding):
                plan = make_plan(self.document("正文保持完整。", encoding=encoding))
                self.assertEqual(self.narration(plan), "正文保持完整。")

    def test_headings_and_metadata_are_not_spoken(self):
        text = "---\nauthor: 测试作者\n---\n# 视频总标题\n\n## 第一部分\n这是第一段。\n\n## 第二部分\n这是第二段。"
        plan = make_plan(self.document(text))
        self.assertEqual(plan["title"], "视频总标题")
        self.assertEqual([s["title"] for s in plan["scenes"]], ["第一部分", "第二部分"])
        self.assertEqual(self.narration(plan), "这是第一段。这是第二段。")
        self.assertNotIn("测试作者", plan["source"]["narration_text"])
        self.assertEqual(plan["source"]["text"], text)

    def test_txt_yaml_like_separators_are_literal_body(self):
        text = "---\n今天的第一段正文\n---\n\n今天的第二段正文。"
        plan = make_plan(self.document(text, "纯文本.txt"))
        self.assertEqual(compact(self.narration(plan)), compact(text))
        self.assertIn("今天的第一段正文", self.narration(plan))
        self.assertEqual(self.narration(plan).count("---"), 2)

    def test_txt_hash_stars_links_and_image_syntax_are_literal_body(self):
        text = "# 完整内容必须保留\n\n* 星号条目不能吞字。\n\n**强调符号也保留**\n\n[链接字面值](https://example.com/path)\n\n![图片字面值](不存在的图片.png)"
        plan = make_plan(self.document(text, "符号.txt"))
        self.assertEqual(compact(self.narration(plan)), compact(text))
        self.assertEqual(plan["title"], "符号")
        self.assertTrue(all(s["image"] is None for s in plan["scenes"]))
        self.assertEqual(compact(plan["source"]["narration_text"]), compact(text))

    def test_all_list_quote_and_table_body_is_preserved(self):
        text = "# 教程\n\n1. 第一步内容。\n2. 第二步内容。\n3. 第三步内容。\n4. 第四步内容。\n5. 第五步内容。\n\n> 引用正文也要保留。\n\n| 项目 | 特点 |\n|---|---|\n| 甲 | 稳定 |\n| 乙 | 轻巧 |"
        plan = make_plan(self.document(text))
        narration = self.narration(plan)
        for value in ("第一步内容。", "第五步内容。", "引用正文也要保留。", "项目", "特点", "甲", "稳定", "乙", "轻巧"):
            self.assertIn(value, narration)
        self.assertEqual(compact(narration), compact(plan["source"]["narration_text"]))
        self.assertIn("steps", {s["kind"] for s in plan["scenes"]})
        self.assertIn("compare", {s["kind"] for s in plan["scenes"]})

    def test_relative_image_with_chinese_spaces_and_parentheses(self):
        image = self.root / "图片 素材" / "开关 (示意).png"
        image.parent.mkdir()
        image.write_bytes(b"image fixture; decoding belongs to renderer")
        plan = make_plan(self.document("## 图示\n![不会读的说明](图片 素材/开关 (示意).png)\n\n这是图片旁的正文。"))
        scene = plan["scenes"][0]
        self.assertEqual(scene["image"], str(image.resolve()))
        self.assertEqual(scene["kind"], "image")
        self.assertEqual(scene["narration"], "这是图片旁的正文。")
        self.assertNotIn("不会读的说明", plan["source"]["narration_text"])

    def test_missing_image_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "找不到图片"):
            make_plan(self.document("正文。\n\n![图片](不存在.png)"))

    def test_network_images_are_not_downloaded(self):
        with self.assertRaisesRegex(ValueError, "仅支持本地"):
            make_plan(self.document("正文。\n\n![图片](https://example.com/image.png)"))

    def test_source_content_hash_changes_when_same_file_changes(self):
        path = self.document("第一版正文。")
        first = make_plan(path)
        path.write_text("第二版正文。", encoding="utf-8")
        second = make_plan(path)
        self.assertEqual(first["source"]["path"], second["source"]["path"])
        self.assertNotEqual(first["source"]["sha256"], second["source"]["sha256"])

    def test_validator_detects_narration_loss_or_reordering(self):
        plan = make_plan(self.document("第一段正文。\n\n第二段正文。"))
        bad = copy.deepcopy(plan)
        bad["scenes"][0]["narration"] = "被改写的文字。"
        with self.assertRaisesRegex(ValueError, "不一致"):
            validate_plan(bad)

    def test_image_only_scenes_keep_all_images(self):
        for name in ("一.png", "二.png"):
            (self.root / name).write_bytes(b"fixture")
        plan = make_plan(self.document("# 图片展示\n\n![一](一.png)\n\n![二](二.png)"))
        self.assertEqual(len(plan["scenes"]), 2)
        self.assertTrue(all(s["kind"] == "image" and s["narration"] == "" for s in plan["scenes"]))

    def test_invalid_rate_is_readable(self):
        for rate in (0, 451, True, "240"):
            with self.subTest(rate=rate), self.assertRaisesRegex(ValueError, "语速"):
                make_plan(self.document("正文。"), voice_rate=rate)


if __name__ == "__main__":
    unittest.main()
