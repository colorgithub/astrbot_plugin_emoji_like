"""EmotionJudger 单元测试：响应解析、LLM 调用成功/失败、event.extra 复用。"""

from __future__ import annotations

import unittest

import _astrbot_stub as stubs

stubs.install()

from _fakes import (  # noqa: E402
    FakeContext,
    FakeProvider,
    make_judger,
    make_plugin,
)


class ParseLlmResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        judger, _, _, _ = make_judger()
        cls.judger = judger

    def test_plain_json(self):
        self.assertEqual(self.judger._parse_llm_response('{"emotion": "开心"}'), "开心")

    def test_json_with_surrounding_whitespace(self):
        self.assertEqual(
            self.judger._parse_llm_response('  \n {"emotion": "难过"} \n '), "难过"
        )

    def test_json_code_block(self):
        text = '```json\n{"emotion": "生气"}\n```'
        self.assertEqual(self.judger._parse_llm_response(text), "生气")

    def test_json_code_block_without_language(self):
        text = '```\n{"emotion": "惊讶"}\n```'
        self.assertEqual(self.judger._parse_llm_response(text), "惊讶")

    def test_json_code_block_crlf(self):
        text = '```json\r\n{"emotion": "疑惑"}\r\n```'
        self.assertEqual(self.judger._parse_llm_response(text), "疑惑")

    def test_single_line_code_block(self):
        text = '```json{"emotion": "害羞"}```'
        self.assertEqual(self.judger._parse_llm_response(text), "害羞")

    def test_non_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.judger._parse_llm_response("我觉得他很开心")

    def test_empty_text_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.judger._parse_llm_response("")

    def test_json_without_emotion_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.judger._parse_llm_response('{"foo": "bar"}')

    def test_empty_emotion_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.judger._parse_llm_response('{"emotion": ""}')

    def test_non_string_emotion_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.judger._parse_llm_response('{"emotion": 123}')

    def test_null_emotion_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.judger._parse_llm_response('{"emotion": null}')

    def test_json_non_object_raises_value_error(self):
        # 合法 JSON 但不是对象时，应按契约抛 ValueError，而不是 AttributeError
        for text in ("[1, 2]", "null", '"abc"', "123", "true"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.judger._parse_llm_response(text)


class JudgeEmotionTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_returns_emotion_and_caches_it(self):
        provider = FakeProvider('{"emotion": "开心"}')
        judger, plugin, context, _ = make_judger(provider=provider)
        event = _make_event()

        emotion = await judger.judge_emotion(
            event,
            text="今天真开心",
            image_urls=["https://example.invalid/a.png"],
            labels=["开心", "生气"],
        )

        self.assertEqual(emotion, "开心")
        self.assertEqual(event.get_extra("emotion"), "开心")
        self.assertEqual(len(provider.calls), 1)
        call = provider.calls[0]
        self.assertIn("今天真开心", call.prompt)
        self.assertIn("开心", call.system_prompt)
        self.assertEqual(call.image_urls, ["https://example.invalid/a.png"])

    async def test_provider_exception_returns_none(self):
        provider = FakeProvider(error=RuntimeError("LLM 服务不可用"))
        judger, _, _, _ = make_judger(provider=provider)
        event = _make_event()

        emotion = await judger.judge_emotion(event, text="随便说点什么", labels=["开心"])

        self.assertIsNone(emotion)
        self.assertIsNone(event.get_extra("emotion"))
        self.assertEqual(len(provider.calls), 1)

    async def test_invalid_provider_response_returns_none(self):
        provider = FakeProvider("这不是 JSON")
        judger, _, _, _ = make_judger(provider=provider)
        event = _make_event()

        emotion = await judger.judge_emotion(event, text="文本", labels=["开心"])

        self.assertIsNone(emotion)
        self.assertIsNone(event.get_extra("emotion"))

    async def test_json_non_object_response_returns_none(self):
        # 合法 JSON 但不是对象（如数组）不是文档约定的返回值，judge_emotion 应吞掉异常返回 None
        provider = FakeProvider("[1, 2]")
        judger, _, _, _ = make_judger(provider=provider)
        event = _make_event()

        emotion = await judger.judge_emotion(event, text="文本", labels=["开心"])

        self.assertIsNone(emotion)

    async def test_cached_emotion_is_reused_without_calling_provider(self):
        provider = FakeProvider('{"emotion": "生气"}')
        judger, _, _, _ = make_judger(provider=provider)
        event = _make_event()
        event.set_extra("emotion", "开心")

        emotion = await judger.judge_emotion(event, text="文本", labels=["开心", "生气"])

        self.assertEqual(emotion, "开心")
        self.assertEqual(provider.calls, [])

    async def test_cached_emotion_reused_without_labels(self):
        provider = FakeProvider('{"emotion": "生气"}')
        judger, _, _, _ = make_judger(provider=provider)
        event = _make_event()
        event.set_extra("emotion", "开心")

        emotion = await judger.judge_emotion(event, text="文本")

        self.assertEqual(emotion, "开心")
        self.assertEqual(provider.calls, [])

    async def test_cached_emotion_outside_labels_is_recomputed(self):
        provider = FakeProvider('{"emotion": "生气"}')
        judger, _, _, _ = make_judger(provider=provider)
        event = _make_event()
        event.set_extra("emotion", "开心")

        emotion = await judger.judge_emotion(event, text="文本", labels=["生气"])

        self.assertEqual(emotion, "生气")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(event.get_extra("emotion"), "生气")

    async def test_no_usable_provider_returns_none(self):
        context = FakeContext()
        context.by_id_provider = object()
        context.using_provider = object()
        plugin, _, _ = make_plugin(context=context)
        judger = plugin.judger
        event = _make_event()

        emotion = await judger.judge_emotion(event, text="文本", labels=["开心"])

        self.assertIsNone(emotion)


def _make_event():
    from _fakes import FakeEvent

    return FakeEvent(message_str="今天真开心")


if __name__ == "__main__":
    unittest.main(verbosity=2)
