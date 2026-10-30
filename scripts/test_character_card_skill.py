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
        self.assertIn("version: 23", self.skill)
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

    def test_high_frequency_characters_use_deterministic_sparse_sampling(self):
        self.assertIn("高频主角的稀疏采样", self.skill)
        self.assertIn("matched_chapters / max(1, scanned_chapters) >= 0.4", self.skill)
        self.assertIn("每 50 章取该区间内第一个命中章节", self.skill)
        self.assertIn("`fast`：每个角色最多 6 章", self.skill)
        self.assertIn("`balanced`：每个角色最多 12 章", self.skill)
        self.assertIn("`deep`：每个角色最多 20 章", self.skill)
        self.assertIn("高频角色：第一页命中已经足够抽样", self.skill)

    def test_preview_and_apply_are_hard_gated(self):
        self.assertIn("预览与应用之间的硬门禁", self.skill)
        self.assertIn("扫描强度（快速/平衡/深入）只授权采样，不授权写入", self.skill)
        self.assertIn("不得在采样完成的同一轮、同一批工具调用中调用 `bookshelf_character_upsert`", self.skill)
        self.assertIn("没有展示过预览表格时，不得声称", self.skill)
        self.assertIn("用户只选择扫描范围或扫描强度，不构成应用确认", self.skill)


if __name__ == "__main__":
    unittest.main()
