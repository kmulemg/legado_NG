import unittest
from pathlib import Path


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "src"
    / "main"
    / "assets"
    / "skills"
    / "character_card_generate.md"
)


class CharacterCardSkillPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")

    def test_apply_batches_all_character_writes_before_results(self):
        self.assertIn("version: 21", self.skill)
        self.assertIn("同一次助手工具调用批次中一次性发出", self.skill)
        self.assertIn("只进行一次写操作确认", self.skill)

    def test_apply_state_is_persisted_after_the_business_batch(self):
        self.assertIn("使用一次 `agent_memory_batch_upsert`", self.skill)
        self.assertIn("batch 顶层 `source_receipt_ids`", self.skill)
        self.assertNotIn("记忆更新成功后才继续下一个角色", self.skill)
        self.assertNotIn("每个结果后立即更新预览记忆", self.skill)

    def test_preview_uses_text_search_to_locate_character_chapters(self):
        self.assertIn("bookshelf.search_content", self.skill)
        self.assertIn("bookshelf_text_search", self.skill)
        self.assertIn("只对选中的章节调用", self.skill)
        self.assertIn("不要读取没有命中的章节", self.skill)


if __name__ == "__main__":
    unittest.main()
