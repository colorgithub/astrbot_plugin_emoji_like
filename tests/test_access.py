"""AccessControl / 名单归一化单元测试（不依赖 AstrBot）。"""

from __future__ import annotations

import unittest

import _astrbot_stub as stubs

stubs.install()

from astrbot_plugin_emoji_like.core.access import (  # noqa: E402
    AccessControl,
    normalize_id,
    normalize_ids,
)

UMO = "aiocqhttp:GroupMessage:100"


class NormalizeIdTests(unittest.TestCase):
    def test_none_becomes_empty_string(self):
        self.assertEqual(normalize_id(None), "")

    def test_int_is_stringified(self):
        self.assertEqual(normalize_id(123), "123")

    def test_whitespace_is_stripped(self):
        self.assertEqual(normalize_id("  123  "), "123")
        self.assertEqual(normalize_id("  "), "")

    def test_empty_string_stays_empty(self):
        self.assertEqual(normalize_id(""), "")


class NormalizeIdsTests(unittest.TestCase):
    def test_none_and_empty_containers(self):
        self.assertEqual(normalize_ids(None), set())
        self.assertEqual(normalize_ids([]), set())
        self.assertEqual(normalize_ids(()), set())
        self.assertEqual(normalize_ids(set()), set())

    def test_scalar_string_and_int(self):
        self.assertEqual(normalize_ids("123"), {"123"})
        self.assertEqual(normalize_ids(123), {"123"})
        self.assertEqual(normalize_ids("  123  "), {"123"})
        self.assertEqual(normalize_ids(""), set())

    def test_list_mixed_types_and_blank_items(self):
        self.assertEqual(
            normalize_ids([123, " 456 ", None, "", "   ", 789]),
            {"123", "456", "789"},
        )

    def test_tuple_and_set_inputs(self):
        self.assertEqual(normalize_ids(("123", "456")), {"123", "456"})
        self.assertEqual(normalize_ids({1, 2}), {"1", "2"})

    def test_single_line_multi_value_with_commas(self):
        self.assertEqual(normalize_ids("123,456"), {"123", "456"})
        self.assertEqual(normalize_ids("123, 456 ,789"), {"123", "456", "789"})
        self.assertEqual(normalize_ids(["123,456"]), {"123", "456"})

    def test_single_line_multi_value_with_spaces(self):
        self.assertEqual(normalize_ids("123 456"), {"123", "456"})
        self.assertEqual(normalize_ids(["123  456"]), {"123", "456"})

    def test_full_width_and_cjk_separators(self):
        self.assertEqual(normalize_ids("123，456"), {"123", "456"})
        self.assertEqual(normalize_ids("123、456"), {"123", "456"})
        self.assertEqual(normalize_ids("123;456；789"), {"123", "456", "789"})

    def test_empty_result_is_a_new_set_each_time(self):
        first = normalize_ids(None)
        second = normalize_ids(None)
        self.assertIsNot(first, second)
        self.assertEqual(first, second)


class AccessControlRuleTests(unittest.TestCase):
    def test_empty_lists_allow_everything(self):
        access = AccessControl()
        self.assertTrue(access.is_allowed())
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))
        self.assertFalse(access.has_rules)

    def test_whitelist_matches_umo_exactly(self):
        access = AccessControl(whitelist=["aiocqhttp:GroupMessage:100"])
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))
        self.assertFalse(
            access.is_allowed(
                umo="aiocqhttp:GroupMessage:101", group_id="101", user_id="200"
            )
        )

    def test_whitelist_matches_umo_prefix(self):
        access = AccessControl(whitelist=["aiocqhttp:GroupMessage"])
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100"))
        self.assertTrue(
            access.is_allowed(umo="aiocqhttp:GroupMessage:999", group_id="999")
        )
        self.assertFalse(
            access.is_allowed(umo="aiocqhttp:FriendMessage:200", user_id="200")
        )

    def test_whitelist_matches_platform_prefix(self):
        access = AccessControl(whitelist=["aiocqhttp"])
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100"))
        self.assertFalse(
            access.is_allowed(umo="telegram:GroupMessage:100", group_id="100")
        )

    def test_whitelist_matches_group_id(self):
        access = AccessControl(whitelist=["100"])
        self.assertTrue(access.is_allowed(umo=UMO, group_id=100, user_id="200"))
        self.assertFalse(
            access.is_allowed(
                umo="aiocqhttp:GroupMessage:999", group_id="999", user_id="200"
            )
        )

    def test_whitelist_matches_user_id(self):
        access = AccessControl(whitelist=["200"])
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id=200))
        self.assertFalse(access.is_allowed(umo=UMO, group_id="100", user_id="201"))

    def test_whitelist_allows_private_session_by_umo(self):
        access = AccessControl(whitelist=["aiocqhttp:FriendMessage:200"])
        self.assertTrue(
            access.is_allowed(umo="aiocqhttp:FriendMessage:200", user_id="200")
        )
        self.assertFalse(
            access.is_allowed(umo="aiocqhttp:FriendMessage:201", user_id="201")
        )

    def test_blacklist_blocks_matching_identifiers(self):
        access = AccessControl(blacklist=["100", "200"])
        self.assertFalse(access.is_allowed(umo=UMO, group_id="100", user_id="300"))
        self.assertFalse(
            access.is_allowed(
                umo="aiocqhttp:GroupMessage:999", group_id="999", user_id="200"
            )
        )
        self.assertTrue(
            access.is_allowed(
                umo="aiocqhttp:GroupMessage:999", group_id="999", user_id="300"
            )
        )

    def test_blacklist_supports_umo_prefix(self):
        access = AccessControl(blacklist=["aiocqhttp:GroupMessage"])
        self.assertFalse(access.is_allowed(umo=UMO, group_id="100"))
        self.assertTrue(
            access.is_allowed(umo="aiocqhttp:FriendMessage:200", user_id="200")
        )

    def test_whitelist_has_priority_over_blacklist(self):
        access = AccessControl(whitelist=["100"], blacklist=["100"])
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))

        # 白名单非空时，未命中白名单的会话即使不在黑名单也会被拒绝
        self.assertFalse(
            access.is_allowed(
                umo="aiocqhttp:GroupMessage:999", group_id="999", user_id="200"
            )
        )

    def test_blacklist_is_ignored_when_whitelist_non_empty(self):
        access = AccessControl(whitelist=["100"], blacklist=["200"])
        # 群 100 命中白名单 -> 放行，即使操作者 200 在黑名单
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))
        # 群 999 不命中白名单 -> 拒绝
        self.assertFalse(
            access.is_allowed(
                umo="aiocqhttp:GroupMessage:999", group_id="999", user_id="200"
            )
        )

    def test_empty_identifiers(self):
        self.assertTrue(AccessControl(blacklist=["100"]).is_allowed())
        self.assertFalse(AccessControl(whitelist=["100"]).is_allowed())

    def test_signature_reflects_both_lists(self):
        access = AccessControl(whitelist=["100"], blacklist=["200"])
        self.assertEqual(
            access.signature(),
            (frozenset({"100"}), frozenset({"200"})),
        )
        self.assertEqual(AccessControl().signature(), (frozenset(), frozenset()))

    def test_has_rules_flag(self):
        self.assertTrue(AccessControl(whitelist=["100"]).has_rules)
        self.assertTrue(AccessControl(blacklist=["100"]).has_rules)
        self.assertFalse(AccessControl().has_rules)


class AccessControlFromConfigTests(unittest.TestCase):
    def test_none_config_is_safe(self):
        access = AccessControl.from_config(None)
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))
        self.assertEqual(access.whitelist, set())

    def test_empty_mapping_is_safe(self):
        access = AccessControl.from_config({})
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))

    def test_missing_keys_are_treated_as_empty(self):
        access = AccessControl.from_config({"whitelist": ["100"]})
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100"))
        self.assertFalse(
            access.is_allowed(umo="aiocqhttp:GroupMessage:999", group_id="999")
        )
        self.assertEqual(access.blacklist, set())

    def test_none_values_are_treated_as_empty(self):
        access = AccessControl.from_config({"whitelist": None, "blacklist": None})
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100", user_id="200"))
        self.assertFalse(access.has_rules)

    def test_all_keys_are_read(self):
        access = AccessControl.from_config(
            {
                "whitelist": ["100", 101],
                "blacklist": "200,201",
            }
        )
        self.assertEqual(access.whitelist, {"100", "101"})
        self.assertEqual(access.blacklist, {"200", "201"})
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100"))
        self.assertFalse(access.is_allowed(umo=UMO, group_id="999"))

    def test_extra_keys_are_ignored(self):
        access = AccessControl.from_config(
            {"whitelist": ["100"], "unrelated": "x", "emoji_like_prob": 1.0}
        )
        self.assertTrue(access.is_allowed(umo=UMO, group_id="100"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
