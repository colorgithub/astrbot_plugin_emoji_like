"""PluginConfig / AccessControl 配置集成测试（实时生效、provider 选择）。"""

from __future__ import annotations

import unittest

import _astrbot_stub as stubs

stubs.install()

from astrbot_plugin_emoji_like.core.access import AccessControl  # noqa: E402
from _fakes import (  # noqa: E402
    FakeContext,
    FakeProvider,
    make_plugin,
)


class PluginConfigFieldsTests(unittest.TestCase):
    def test_two_lists_exist(self):
        plugin, _, _ = make_plugin()
        config = plugin.cfg
        self.assertEqual(config.whitelist, [])
        self.assertEqual(config.blacklist, [])

    def test_lists_read_from_underlying_config(self):
        plugin, _, _ = make_plugin(whitelist=["100"], blacklist=["200"])
        config = plugin.cfg
        self.assertEqual(config.whitelist, ["100"])
        self.assertEqual(config.blacklist, ["200"])

    def test_access_returns_access_control_instance(self):
        plugin, _, _ = make_plugin()
        self.assertIsInstance(plugin.cfg.access, AccessControl)

    def test_other_config_fields_are_loaded(self):
        plugin, _, _ = make_plugin(
            emoji_like_prob=0.5,
            emoji_interval=0.25,
            reaction_follow_enabled=False,
            reaction_follow_prob=0.75,
            reaction_follow_dedupe_seconds=5,
            emoji_reaction_follow_prob=0.5,
            judge_provider_id="provider-x",
        )
        config = plugin.cfg
        self.assertEqual(config.emoji_like_prob, 0.5)
        self.assertEqual(config.emoji_interval, 0.25)
        self.assertFalse(config.reaction_follow_enabled)
        self.assertEqual(config.reaction_follow_prob, 0.75)
        self.assertEqual(config.reaction_follow_dedupe_seconds, 5)
        self.assertEqual(config.emoji_reaction_follow_prob, 0.5)
        self.assertEqual(config.judge_provider_id, "provider-x")

    def test_emotion_mapping_is_parsed(self):
        plugin, _, _ = make_plugin()
        self.assertEqual(plugin.cfg.emotion_mapping, {"开心": [2, 74, 109], "生气": [11, 26]})
        self.assertEqual(plugin.cfg.emotion_labels, ["开心", "生气"])


class PluginConfigAccessRealtimeTests(unittest.TestCase):
    """README 承诺「保存后即时生效」，这里验证缓存自动失效。"""

    def test_empty_lists_allow_everything(self):
        plugin, _, _ = make_plugin()
        access = plugin.cfg.access
        self.assertTrue(access.is_allowed(umo="aiocqhttp:GroupMessage:100", group_id="100", user_id="200"))
        self.assertFalse(access.has_rules)

    def test_access_object_is_cached_while_config_unchanged(self):
        plugin, _, _ = make_plugin(whitelist=["100"])
        first = plugin.cfg.access
        second = plugin.cfg.access
        self.assertIs(first, second)

    def test_whitelist_change_takes_effect_immediately(self):
        plugin, _, config = make_plugin(whitelist=[])
        self.assertTrue(plugin.cfg.access.is_allowed(group_id="111"))

        config["whitelist"] = ["222"]
        access = plugin.cfg.access
        self.assertTrue(access.is_allowed(group_id="222"))
        self.assertFalse(access.is_allowed(group_id="111"))

        config["whitelist"] = []
        self.assertTrue(plugin.cfg.access.is_allowed(group_id="111"))

    def test_blacklist_change_takes_effect_immediately(self):
        plugin, _, config = make_plugin()
        self.assertTrue(plugin.cfg.access.is_allowed(group_id="100"))

        config["blacklist"] = ["100"]
        self.assertFalse(plugin.cfg.access.is_allowed(group_id="100"))

        config["blacklist"] = []
        self.assertTrue(plugin.cfg.access.is_allowed(group_id="100"))

    def test_whitelist_priority_takes_effect_immediately(self):
        plugin, _, config = make_plugin(whitelist=["100"], blacklist=["100"])
        self.assertTrue(plugin.cfg.access.is_allowed(group_id="100"))

        # 清空白名单后黑名单立即接管
        config["whitelist"] = []
        self.assertFalse(plugin.cfg.access.is_allowed(group_id="100"))

    def test_in_place_list_mutation_takes_effect_immediately(self):
        plugin, _, config = make_plugin(whitelist=[])
        self.assertTrue(plugin.cfg.access.is_allowed(group_id="333"))

        config["whitelist"].append("333")  # 原地修改，不替换列表对象

        self.assertTrue(plugin.cfg.access.is_allowed(group_id="333"))
        self.assertFalse(plugin.cfg.access.is_allowed(group_id="444"))

    def test_multi_value_string_in_config_is_supported(self):
        plugin, _, _ = make_plugin(whitelist=["100,101"])
        access = plugin.cfg.access
        self.assertTrue(access.is_allowed(group_id="100"))
        self.assertTrue(access.is_allowed(group_id="101"))
        self.assertFalse(access.is_allowed(group_id="102"))

        plugin, _, _ = make_plugin(blacklist=["200 201"])
        access = plugin.cfg.access
        self.assertFalse(access.is_allowed(user_id="200"))
        self.assertFalse(access.is_allowed(user_id="201"))
        self.assertTrue(access.is_allowed(user_id="202"))

    def test_none_lists_do_not_break_access(self):
        plugin, _, _ = make_plugin(whitelist=None, blacklist=None)
        access = plugin.cfg.access
        self.assertTrue(access.is_allowed(umo="aiocqhttp:GroupMessage:100", group_id="100", user_id="200"))
        self.assertFalse(access.has_rules)

    def test_scalar_whitelist_id_is_supported(self):
        """配置误填为标量（如 whitelist: 123）时不应在 tuple() 处抛 TypeError。"""
        plugin, _, config = make_plugin(whitelist=123, blacklist="456")
        access = plugin.cfg.access
        self.assertTrue(access.is_allowed(user_id=123))
        self.assertFalse(access.is_allowed(user_id=789))

        # 标量变化后签名缓存也应失效
        config["whitelist"] = 999
        self.assertTrue(plugin.cfg.access.is_allowed(user_id=999))
        self.assertFalse(plugin.cfg.access.is_allowed(user_id=123))

    def test_scalar_string_with_separators_is_supported(self):
        plugin, _, _ = make_plugin(whitelist="100,101")
        access = plugin.cfg.access
        self.assertTrue(access.is_allowed(group_id="100"))
        self.assertTrue(access.is_allowed(group_id="101"))
        self.assertFalse(access.is_allowed(group_id="102"))

    def test_scalar_blacklist_id_is_supported(self):
        plugin, _, _ = make_plugin(blacklist=456)
        access = plugin.cfg.access
        self.assertFalse(access.is_allowed(user_id="456"))
        self.assertTrue(access.is_allowed(user_id="789"))

    def test_umo_prefix_in_config(self):
        plugin, _, _ = make_plugin(whitelist=["aiocqhttp:GroupMessage"])
        self.assertTrue(
            plugin.cfg.access.is_allowed(
                umo="aiocqhttp:GroupMessage:100", group_id="100", user_id="200"
            )
        )
        self.assertFalse(
            plugin.cfg.access.is_allowed(
                umo="telegram:GroupMessage:100", group_id="100", user_id="200"
            )
        )


class JudgeProviderTests(unittest.TestCase):
    def test_uses_provider_by_id_first(self):
        configured = FakeProvider('{"emotion": "开心"}')
        fallback = FakeProvider('{"emotion": "生气"}')
        context = FakeContext()
        context.by_id_provider = configured
        context.using_provider = fallback
        plugin, _, _ = make_plugin(
            context=context, judge_provider_id="my-provider"
        )

        provider = plugin.cfg.get_judge_provider()

        self.assertIs(provider, configured)
        self.assertIsNot(provider, fallback)

    def test_falls_back_to_using_provider(self):
        fallback = FakeProvider()
        context = FakeContext()
        context.by_id_provider = None
        context.using_provider = fallback
        plugin, _, _ = make_plugin(
            context=context, judge_provider_id="missing-provider"
        )
        self.assertIs(plugin.cfg.get_judge_provider("umo"), fallback)

    def test_rejects_non_provider_object(self):
        context = FakeContext()
        context.by_id_provider = object()
        context.using_provider = object()
        plugin, _, _ = make_plugin(context=context)
        with self.assertRaises(RuntimeError):
            plugin.cfg.get_judge_provider()

    def test_judge_provider_id_is_passed_through(self):
        configured = FakeProvider()
        fallback = FakeProvider()
        seen = []
        context = FakeContext()
        context.by_id_provider = configured
        context.using_provider = fallback
        original = context.get_provider_by_id

        def spy(provider_id=None, *args, **kwargs):
            seen.append(provider_id)
            return original(provider_id, *args, **kwargs)

        context.get_provider_by_id = spy
        plugin, _, _ = make_plugin(context=context, judge_provider_id="my-provider")
        self.assertIs(plugin.cfg.get_judge_provider(), configured)
        self.assertEqual(seen, ["my-provider"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
