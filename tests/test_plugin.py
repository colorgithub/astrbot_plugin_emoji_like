"""插件入口集成测试：会话/群聊/用户黑白名单在各触发路径上的生效情况。

全部使用 fake Event / Bot / Provider，完全离线、确定性（概率置 1、间隔置 0）。
"""

from __future__ import annotations

import unittest

import _astrbot_stub as stubs

stubs.install()

from _fakes import (  # noqa: E402
    drain_tasks,
    make_message_event,
    make_notice_event,
    make_plugin,
)

HAPPY_EMOJI_POOL = {2, 74, 109}
GROUP_UMO = "aiocqhttp:GroupMessage:100"


class AutoLikeByMessageTests(unittest.IsolatedAsyncioTestCase):
    """on_message 里的「主动贴表情」路径（asyncio.create_task）。"""

    def _make(self, **overrides):
        options = {
            "emoji_like_prob": 1.0,
            "emoji_follow_prob": 0.0,
            "emoji_interval": 0.0,
        }
        options.update(overrides)
        return make_plugin(**options)

    async def test_triggers_in_whitelisted_group(self):
        plugin, _, _ = self._make(whitelist=["100"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)
        self.assertIn(event.bot.called_emoji_ids[0], HAPPY_EMOJI_POOL)
        self.assertEqual(event.bot.called_message_ids[0], "msg-1001")
        self.assertFalse(event.stopped)

    async def test_does_not_trigger_outside_whitelisted_group(self):
        plugin, _, _ = self._make(whitelist=["100"])
        event = make_message_event(group_id="999", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_blacklisted_group_blocks_when_no_whitelist(self):
        plugin, context, _ = self._make(blacklist=["100"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertEqual(context.by_id_provider.calls, [])  # 完全静默：连 LLM 都不调用

    async def test_whitelist_wins_over_blacklist_for_same_group(self):
        plugin, _, _ = self._make(whitelist=["100"], blacklist=["100"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_blacklisted_user_blocks(self):
        plugin, context, _ = self._make(blacklist=["200"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertEqual(context.by_id_provider.calls, [])

    async def test_user_outside_whitelist_blocks(self):
        plugin, context, _ = self._make(whitelist=["300"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertEqual(context.by_id_provider.calls, [])

    async def test_triggers_when_user_whitelisted(self):
        plugin, _, _ = self._make(whitelist=["200"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_whitelist_group_allows_even_if_user_blacklisted(self):
        plugin, _, _ = self._make(whitelist=["100"], blacklist=["200"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_umo_whitelist_matches(self):
        plugin, _, _ = self._make(whitelist=[GROUP_UMO])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_umo_prefix_whitelist_matches(self):
        plugin, _, _ = self._make(whitelist=["aiocqhttp:GroupMessage"])
        event = make_message_event(group_id="777", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_umo_mismatch_does_not_trigger(self):
        plugin, _, _ = self._make(whitelist=["aiocqhttp:GroupMessage:999"])
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_uses_group_fallback_when_raw_message_missing(self):
        plugin, _, _ = self._make(whitelist=["100"])
        event = make_message_event(group_id="100", user_id="200", with_raw=False)

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_uses_user_fallback_when_raw_message_missing(self):
        plugin, _, _ = self._make(whitelist=["200"])
        event = make_message_event(group_id="100", user_id="200", with_raw=False)

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(len(event.bot.emoji_like_calls), 1)

    async def test_wake_command_message_is_ignored(self):
        plugin, _, _ = self._make()
        event = make_message_event(group_id="100", user_id="200", is_at_or_wake_command=True)

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_empty_message_does_not_trigger(self):
        plugin, _, _ = self._make()
        event = make_message_event(group_id="100", user_id="200", message_str="")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])


class FollowExistingFaceTests(unittest.IsolatedAsyncioTestCase):
    """on_message 里的「跟随已有表情」路径。"""

    def _make(self, **overrides):
        options = {
            "emoji_follow_prob": 1.0,
            "emoji_like_prob": 0.0,
            "emoji_interval": 0.0,
        }
        options.update(overrides)
        return make_plugin(**options)

    async def test_follows_face_in_allowed_group(self):
        plugin, _, _ = self._make(whitelist=["100"])
        event = make_message_event(
            group_id="100", user_id="200", chain=[stubs.Face(7)], message_str=""
        )

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.called_emoji_ids, [7])
        self.assertEqual(event.bot.called_message_ids, ["msg-1001"])

    async def test_does_not_follow_face_in_blacklisted_group(self):
        plugin, _, _ = self._make(blacklist=["100"])
        event = make_message_event(
            group_id="100", user_id="200", chain=[stubs.Face(7)], message_str=""
        )

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_follows_face_when_umo_whitelisted(self):
        plugin, _, _ = self._make(whitelist=[GROUP_UMO])
        event = make_message_event(
            group_id="100", user_id="200", chain=[stubs.Face(7)], message_str=""
        )

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.called_emoji_ids, [7])


class CommandTests(unittest.IsolatedAsyncioTestCase):
    """``贴表情`` 指令路径。"""

    @staticmethod
    def _reply_chain(text="你好", reply_id="reply-9"):
        return [
            stubs.Reply(
                chain=[stubs.Image(url="https://example.invalid/a.png")],
                text=text,
                id=reply_id,
            )
        ]

    async def test_command_likes_reply_when_allowed(self):
        plugin, _, _ = make_plugin(emoji_interval=0.0)
        event = make_message_event(chain=self._reply_chain())

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(len(event.bot.emoji_like_calls), 3)
        self.assertEqual(set(event.bot.called_emoji_ids), HAPPY_EMOJI_POOL)
        self.assertTrue(all(mid == "reply-9" for mid in event.bot.called_message_ids))
        self.assertTrue(event.stopped)

    async def test_command_blocked_by_user_blacklist(self):
        plugin, _, _ = make_plugin(blacklist=["200"])
        event = make_message_event(chain=self._reply_chain())

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertFalse(event.stopped)

    async def test_command_blocked_by_group_blacklist(self):
        plugin, _, _ = make_plugin(blacklist=["100"])
        event = make_message_event(chain=self._reply_chain())

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_command_blocked_when_group_not_in_whitelist(self):
        plugin, _, _ = make_plugin(whitelist=["999"])
        event = make_message_event(chain=self._reply_chain())

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_command_allowed_by_umo_whitelist(self):
        plugin, _, _ = make_plugin(whitelist=[GROUP_UMO])
        event = make_message_event(chain=self._reply_chain())

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(len(event.bot.emoji_like_calls), 3)

    async def test_command_whitelist_wins_over_blacklist(self):
        plugin, _, _ = make_plugin(whitelist=["100"], blacklist=["200"])
        event = make_message_event(chain=self._reply_chain())

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(len(event.bot.emoji_like_calls), 3)

    async def test_command_without_reply_does_nothing(self):
        plugin, _, _ = make_plugin()
        event = make_message_event(chain=[])

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertFalse(event.stopped)

    async def test_command_reply_without_text_does_nothing(self):
        plugin, _, _ = make_plugin()
        event = make_message_event(chain=self._reply_chain(text=""))

        await plugin.on_command(event, emojiNum=3)

        self.assertEqual(event.bot.emoji_like_calls, [])


class ReactionFollowTests(unittest.IsolatedAsyncioTestCase):
    """on_group_emoji_reaction：跟随群友贴表情反应。"""

    def _make(self, **overrides):
        options = {
            "reaction_follow_enabled": True,
            "reaction_follow_prob": 1.0,
            "reaction_follow_dedupe_seconds": 0.0,
            "emoji_interval": 0.0,
        }
        options.update(overrides)
        return make_plugin(**options)

    async def test_follows_reaction_when_allowed(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="200", message_id="msg-42", emoji_ids=(5,))

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.called_emoji_ids, [5])
        self.assertEqual(event.bot.called_message_ids, ["msg-42"])
        self.assertTrue(event.stopped)

    async def test_follows_reaction_when_whitelisted(self):
        plugin, _, _ = self._make(whitelist=["100"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.called_emoji_ids, [5])

    async def test_blocked_by_blacklisted_group(self):
        plugin, _, _ = self._make(blacklist=["100"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertFalse(event.stopped)

    async def test_blocked_by_blacklisted_user(self):
        plugin, _, _ = self._make(blacklist=["200"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_blocked_when_user_outside_whitelist(self):
        plugin, _, _ = self._make(whitelist=["300"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_whitelist_wins_over_blacklist(self):
        plugin, _, _ = self._make(whitelist=["100"], blacklist=["200"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.called_emoji_ids, [5])

    async def test_bot_self_reaction_is_ignored(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="999999", self_id="999999")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_disabled_by_config(self):
        plugin, _, _ = self._make(reaction_follow_enabled=False)
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_ignores_emoji_removal(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="200", is_add=False)

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_ignores_non_reaction_notice(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="200", notice_type="group_recall")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_ignores_regular_message(self):
        plugin, _, _ = self._make()
        event = make_message_event(group_id="100", user_id="200")

        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_dedupe_prevents_second_follow(self):
        plugin, _, _ = self._make(reaction_follow_dedupe_seconds=10.0)
        event = make_notice_event(group_id="100", user_id="200", message_id="msg-42", emoji_ids=(5,))

        await plugin.on_group_emoji_reaction(event)
        await plugin.on_group_emoji_reaction(event)

        self.assertEqual(event.bot.called_emoji_ids, [5])

    async def test_probability_rejection_does_not_consume_dedupe(self):
        """概率未命中时不应写去重记录，否则会降低后续跟随成功率。"""
        plugin, _, config = self._make(
            reaction_follow_prob=0.0, reaction_follow_dedupe_seconds=10.0
        )
        event = make_notice_event(
            group_id="100", user_id="200", message_id="msg-42", emoji_ids=(5,)
        )

        await plugin.on_group_emoji_reaction(event)
        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertEqual(plugin._followed_reactions, {})

        config["reaction_follow_prob"] = 1.0
        await plugin.on_group_emoji_reaction(event)
        self.assertEqual(event.bot.called_emoji_ids, [5])


class FollowReactionNoticeTests(unittest.IsolatedAsyncioTestCase):
    """_follow_reaction_notice：on_message 内的 notice 分支。"""

    def _make(self, **overrides):
        options = {
            "emoji_reaction_follow_prob": 1.0,
            "reaction_follow_prob": 0.0,
            "emoji_like_prob": 0.0,
            "emoji_interval": 0.0,
        }
        options.update(overrides)
        return make_plugin(**options)

    async def test_follows_notice_via_on_message_when_allowed(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="200", message_id="msg-77", emoji_ids=(7,))

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.called_emoji_ids, [7])
        self.assertEqual(event.bot.called_message_ids, ["msg-77"])
        self.assertTrue(event.stopped)

    async def test_blocked_notice_via_on_message_for_blacklisted_user(self):
        plugin, _, _ = self._make(blacklist=["200"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])
        self.assertFalse(event.stopped)

    async def test_blocked_notice_via_on_message_for_blacklisted_group(self):
        plugin, _, _ = self._make(blacklist=["100"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_blocked_notice_via_on_message_when_user_outside_whitelist(self):
        plugin, _, _ = self._make(whitelist=["300"])
        event = make_notice_event(group_id="100", user_id="200")

        await plugin.on_message(event)
        await drain_tasks()

        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_direct_call_returns_true_when_allowed(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="200", emoji_ids=(7,))

        followed = await plugin._follow_reaction_notice(event)

        self.assertTrue(followed)
        self.assertEqual(event.bot.called_emoji_ids, [7])

    async def test_direct_call_returns_false_when_user_blacklisted(self):
        plugin, _, _ = self._make(blacklist=["200"])
        event = make_notice_event(group_id="100", user_id="200")

        followed = await plugin._follow_reaction_notice(event)

        self.assertFalse(followed)
        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_direct_call_returns_false_when_group_blacklisted(self):
        plugin, _, _ = self._make(blacklist=["100"])
        event = make_notice_event(group_id="100", user_id="200")

        followed = await plugin._follow_reaction_notice(event)

        self.assertFalse(followed)
        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_direct_call_ignores_bot_self(self):
        plugin, _, _ = self._make()
        event = make_notice_event(group_id="100", user_id="999999", self_id="999999")

        followed = await plugin._follow_reaction_notice(event)

        self.assertFalse(followed)
        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_direct_call_ignores_other_notice_types(self):
        plugin, _, _ = self._make()
        event = make_notice_event(
            group_id="100", user_id="200", notice_type="group_recall"
        )

        followed = await plugin._follow_reaction_notice(event)

        self.assertFalse(followed)
        self.assertEqual(event.bot.emoji_like_calls, [])

    async def test_probability_zero_disables_follow(self):
        plugin, _, _ = self._make(emoji_reaction_follow_prob=0.0)
        event = make_notice_event(group_id="100", user_id="200")

        followed = await plugin._follow_reaction_notice(event)

        self.assertFalse(followed)
        self.assertEqual(event.bot.emoji_like_calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
