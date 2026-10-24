"""测试用 fake 对象（Provider / Context / Bot / Event）与配置构造工具。

本模块导入时会自动安装离线 stub，因此测试文件可以直接::

    from _fakes import make_plugin

所有 fake 均为纯内存对象，不访问网络、不读写真实配置。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import _astrbot_stub as stubs

stubs.install()

from astrbot.core.config.astrbot_config import AstrBotConfig  # noqa: E402
from astrbot_plugin_emoji_like.core.config import PluginConfig  # noqa: E402
from astrbot_plugin_emoji_like.core.emotion import EmotionJudger  # noqa: E402
from astrbot_plugin_emoji_like.main import EmojiLikePlugin  # noqa: E402


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

#: 与 _conf_schema.json 字段一一对应；测试按需覆盖。
DEFAULT_CONFIG: dict = {
    "emoji_follow_prob": 0.0,
    "emoji_like_prob": 0.0,
    "emoji_reaction_follow_prob": 1.0,
    "judge_provider_id": "",
    "emoji_interval": 0.0,
    "emotions_mapping_list": [
        "开心：2 74 109",
        "生气：11 26",
    ],
    "reaction_follow_enabled": True,
    "reaction_follow_prob": 1.0,
    "reaction_follow_dedupe_seconds": 0.0,
    "whitelist": [],
    "blacklist": [],
}


def make_config(**overrides) -> AstrBotConfig:
    """构造包含 schema 全部字段的 AstrBotConfig。"""
    data = {key: (list(value) if isinstance(value, list) else value) for key, value in DEFAULT_CONFIG.items()}
    data.update(overrides)
    return AstrBotConfig(data)


# ---------------------------------------------------------------------------
# Provider / Context
# ---------------------------------------------------------------------------


class FakeProvider(stubs.Provider):
    """Fake LLM Provider：可配置返回文本或抛异常，并记录调用。"""

    def __init__(self, completion_text: str = '{"emotion": "开心"}', error: BaseException | None = None):
        self.completion_text = completion_text
        self.error = error
        self.calls: list[SimpleNamespace] = []

    async def text_chat(self, *, system_prompt="", prompt="", image_urls=None, **kwargs):
        self.calls.append(
            SimpleNamespace(
                system_prompt=system_prompt,
                prompt=prompt,
                image_urls=image_urls,
                kwargs=kwargs,
            )
        )
        if self.error is not None:
            raise self.error
        return SimpleNamespace(completion_text=self.completion_text)


class FakeContext(stubs.Context):
    """Fake AstrBot Context：按 id / 默认两种方式返回 provider。"""

    def __init__(self, provider: FakeProvider | None = None):
        super().__init__()
        default = provider if provider is not None else FakeProvider()
        self.by_id_provider = default
        self.using_provider = default

    def get_provider_by_id(self, provider_id=None, *args, **kwargs):
        return self.by_id_provider

    def get_using_provider(self, umo=None, *args, **kwargs):
        return self.using_provider


# ---------------------------------------------------------------------------
# Bot / Event
# ---------------------------------------------------------------------------


class FakeBot:
    """记录 set_msg_emoji_like 调用参数。"""

    def __init__(self):
        self.emoji_like_calls: list[dict] = []

    async def set_msg_emoji_like(self, message_id=None, emoji_id=None, set=True, **kwargs):
        self.emoji_like_calls.append(
            {"message_id": message_id, "emoji_id": emoji_id, "set": set, "kwargs": kwargs}
        )

    # 便于断言
    @property
    def called_emoji_ids(self) -> list:
        return [call["emoji_id"] for call in self.emoji_like_calls]

    @property
    def called_message_ids(self) -> list:
        return [call["message_id"] for call in self.emoji_like_calls]


class FakeMessageObj:
    def __init__(self, message_id="msg-1001", raw_message=None):
        self.message_id = message_id
        self.raw_message = raw_message


class FakeEvent:
    """最小可用的 AstrBot 事件替身（duck typing）。"""

    def __init__(
        self,
        *,
        group_id=None,
        user_id=None,
        self_id="999999",
        message_id="msg-1001",
        raw_message=None,
        chain=None,
        message_str="",
        is_at_or_wake_command=False,
        unified_msg_origin="aiocqhttp:GroupMessage:100",
    ):
        self._group_id = group_id
        self._user_id = user_id
        self._self_id = self_id
        self.message_obj = FakeMessageObj(message_id=message_id, raw_message=raw_message)
        self._chain = list(chain or [])
        self.message_str = message_str
        self.is_at_or_wake_command = is_at_or_wake_command
        self.unified_msg_origin = unified_msg_origin
        self._extra: dict = {}
        self.stopped = False
        self.bot = FakeBot()

    def get_messages(self):
        return list(self._chain)

    def get_group_id(self):
        return self._group_id

    def get_sender_id(self):
        return self._user_id

    def get_self_id(self):
        return self._self_id

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)

    def set_extra(self, key, value):
        self._extra[key] = value

    def stop_event(self):
        self.stopped = True


def make_message_event(
    *,
    group_id="100",
    user_id="200",
    message_id="msg-1001",
    chain=None,
    message_str="今天好开心",
    is_at_or_wake_command=False,
    with_raw=True,
    self_id="999999",
    umo=None,
):
    """普通群消息事件；with_raw=False 用于覆盖 get_group_id/get_sender_id 回退路径。"""
    raw_message = (
        {"group_id": group_id, "user_id": user_id, "message_id": message_id}
        if with_raw
        else None
    )
    return FakeEvent(
        group_id=group_id,
        user_id=user_id,
        self_id=self_id,
        message_id=message_id,
        raw_message=raw_message,
        chain=chain,
        message_str=message_str,
        is_at_or_wake_command=is_at_or_wake_command,
        unified_msg_origin=umo or f"aiocqhttp:GroupMessage:{group_id}",
    )


def make_notice_event(
    *,
    group_id="100",
    user_id="200",
    self_id="999999",
    message_id="msg-42",
    emoji_ids=(5,),
    is_add=True,
    notice_type="group_msg_emoji_like",
    post_type="notice",
    likes=None,
    umo=None,
):
    """群友贴表情 reaction notice 事件。"""
    if likes is None:
        likes = [{"emoji_id": emoji_id} for emoji_id in emoji_ids]
    raw_message = {
        "post_type": post_type,
        "notice_type": notice_type,
        "is_add": is_add,
        "group_id": group_id,
        "user_id": user_id,
        "self_id": self_id,
        "message_id": message_id,
        "likes": likes,
    }
    return FakeEvent(
        group_id=group_id,
        user_id=user_id,
        self_id=self_id,
        message_id=message_id,
        raw_message=raw_message,
        chain=[],
        message_str="",
        unified_msg_origin=umo or f"aiocqhttp:GroupMessage:{group_id}",
    )


# ---------------------------------------------------------------------------
# 插件构造 / 异步辅助
# ---------------------------------------------------------------------------


def make_plugin(context=None, provider=None, **overrides):
    """构造 (plugin, context, config)。

    ``overrides`` 覆盖 ``DEFAULT_CONFIG`` 中的字段。
    """
    if context is None:
        context = FakeContext(provider)
    config = make_config(**overrides)
    plugin = EmojiLikePlugin(context, config)
    return plugin, context, config


def make_judger(provider=None, **overrides):
    """构造 (judger, plugin, context, config)。"""
    plugin, context, config = make_plugin(provider=provider, **overrides)
    return EmotionJudger(plugin.cfg), plugin, context, config


async def drain_tasks(timeout: float = 2.0) -> None:
    """等待 on_message 里 ``asyncio.create_task`` 创建的后台任务跑完。

    若超时则断言失败，避免测试因漏掉任务而假通过。
    """
    current = asyncio.current_task()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        pending = [
            task
            for task in asyncio.all_tasks(loop)
            if task is not current and not task.done()
        ]
        if not pending:
            return
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AssertionError(f"后台任务在 {timeout}s 内未完成: {pending!r}")
        await asyncio.wait(pending, timeout=remaining)


__all__ = [
    "DEFAULT_CONFIG",
    "FakeBot",
    "FakeContext",
    "FakeEvent",
    "FakeMessageObj",
    "FakeProvider",
    "PluginConfig",
    "drain_tasks",
    "make_config",
    "make_judger",
    "make_message_event",
    "make_notice_event",
    "make_plugin",
]
