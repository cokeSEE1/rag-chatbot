"""Tests for cleaning pipeline steps."""

import pytest
from app.pipeline.cleaning import (
    BasicCleaningStep,
    DocxMetadataCleaningStep,
    QualityFilterStep,
    RAGChunkingStep,
    StructureCleaningStep,
)


class TestDocxMetadataCleaningStep:
    """Tests for DocxMetadataCleaningStep."""

    @pytest.fixture
    def step(self):
        return DocxMetadataCleaningStep()

    def test_removes_revision_history_table(self, step):
        """修订记录表格行应被移除."""
        text = (
            "需求分析说明书 第2.0版 2026年4月\n"
            "文档修订记录 *修订状态:C——创建,A——增加,M——修改,D——删除\n"
            "(备注:此文档中的图片示例均为原型示意图)\n"
            "一、更新提醒机制\n"
            "1、需求描述\n"
        )
        result = step.clean(text)
        assert "修订记录" not in result
        assert "修订状态" not in result
        assert "一、更新提醒机制" in result
        assert "1、需求描述" in result

    def test_removes_version_header(self, step):
        """版本号 + 日期行应被移除."""
        text = (
            "需求规格说明书 第1.0版 2025年12月\n"
            "实际正文内容开始。\n"
        )
        result = step.clean(text)
        assert "需求规格说明书" not in result
        assert "第1.0版" not in result
        assert "实际正文内容开始" in result

    def test_removes_remark_about_prototypes(self, step):
        """原型示意图备注行应被移除."""
        text = (
            "(备注:此文档中的图片示例均为原型示意图,前端实现时会遵守UI设计规范)\n"
            "正文内容。\n"
        )
        result = step.clean(text)
        assert "原型示意图" not in result
        assert "正文内容" in result

    def test_preserves_normal_content(self, step):
        """正文内容不应受影响."""
        text = (
            "一、更新提醒机制\n"
            "1、需求描述 实现方案 在设置下新增更新提醒配置菜单\n"
        )
        result = step.clean(text)
        assert "一、更新提醒机制" in result
        assert "更新提醒配置菜单" in result

    def test_handles_empty_text(self, step):
        """空文本应安全处理."""
        assert step.clean("") == ""

    def test_removes_multiple_metadata_lines(self, step):
        """多行元数据应全部移除."""
        text = (
            "需求分析说明书 第2.0版 2026年4月\n"
            "文档修订记录 *修订状态:C——创建,A——增加,M——修改,D——删除\n"
            "(备注:图片为原型示意图)\n"
            "\n"
            "一、功能介绍\n"
            "具体功能描述。\n"
        )
        result = step.clean(text)
        lines = result.strip().split("\n")
        assert lines[0] == "一、功能介绍"
        assert "具体功能描述" in result
