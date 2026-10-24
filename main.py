import asyncio
import random
import time

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Face, Image, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .core.config import PluginConfig
from .core.emotion import EmotionJudger


def _raw_get(raw, key, default=None):
    """安全读取 raw_message 中的字段，兼容 dict 和对象两种类型"""
    if isinstance(raw, dict):
        return raw.get(key, default)
    try:
        return raw.get(key, default)
    except Exception:
        return getattr(raw, key, default)


def _to_id(value) -> str:
    """把消息中的 ID 规范化为去除首尾空白的字符串"""
    if value is None:
        return ""
    return str(value).strip()


class EmojiLikePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.judger = EmotionJudger(self.cfg)
        self._followed_reactions: dict[tuple[str, str], float] = {}

    def _group_id_of(self, event: AiocqhttpMessageEvent) -> str:
        """读取事件所属群号，优先取 raw_message，兼容通知事件"""
        raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
        group_id = _raw_get(raw, "group_id") if raw is not None else None
        if group_id:
            return _to_id(group_id)
        try:
            return _to_id(event.get_group_id())
        except Exception:
            return ""

    def _user_id_of(self, event: AiocqhttpMessageEvent) -> str:
        """读取事件的操作者 QQ 号，优先取 raw_message（通知事件中为贴表情的人）"""
        raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
        user_id = _raw_get(raw, "user_id") if raw is not None else None
        if user_id:
            return _to_id(user_id)
        try:
            return _to_id(event.get_sender_id())
        except Exception:
            return ""

    def _umo_of(self, event: AiocqhttpMessageEvent) -> str:
        """读取事件所属会话 ID（UMO），如 aiocqhttp:GroupMessage:123456"""
        try:
            return _to_id(event.unified_msg_origin)
        except Exception:
            return ""

    def _is_allowed(
        self,
        event: AiocqhttpMessageEvent,
        *,
        group_id=None,
        user_id=None,
    ) -> bool:
        """会话 / 群聊 / 用户黑白名单校验，未通过则插件不响应"""
        gid = self._group_id_of(event) if group_id is None else _to_id(group_id)
        uid = self._user_id_of(event) if user_id is None else _to_id(user_id)
        return self.cfg.access.is_allowed(
            umo=self._umo_of(event), group_id=gid, user_id=uid
        )

    async def _emoji_like(
        self,
        event: AiocqhttpMessageEvent,
        emoji_ids: list[int],
        message_id: int | str | None = None,
    ):
        logger.info(f"贴表情: {emoji_ids}")
        message_id = message_id or event.message_obj.message_id
        emoji_ids = emoji_ids[: self.cfg.max_emoji_count]
        for emoji_id in set(emoji_ids):
            try:
                await event.bot.set_msg_emoji_like(
                    message_id=message_id,
                    emoji_id=emoji_id,
                    set=True,
                )
            except Exception as e:
                logger.warning(f"贴表情失败: {e}")

            await asyncio.sleep(self.cfg.emoji_interval)

    async def _follow_reaction_notice(self, event: AiocqhttpMessageEvent) -> bool:
        raw = getattr(event.message_obj, "raw_message", None)
        if not raw or _raw_get(raw, "post_type") != "notice":
            return False
        if _raw_get(raw, "notice_type") not in ("group_msg_emoji_like", "reaction"):
            return False
        if not self._is_allowed(
            event,
            group_id=_raw_get(raw, "group_id"),
            user_id=_raw_get(raw, "user_id"),
        ):
            return False
        if _raw_get(raw, "is_add") is False:
            return False
        if str(_raw_get(raw, "user_id")) == str(event.get_self_id()):
            return False
        if random.random() >= self.cfg.emoji_reaction_follow_prob:
            return False

        message_id = _raw_get(raw, "message_id")
        if not message_id:
            return False

        for item in _raw_get(raw, "likes") or []:
            emoji_id = item.get("emoji_id") if isinstance(item, dict) else None
            if str(emoji_id).isdigit():
                await self._emoji_like(event, [int(emoji_id)], message_id=message_id)
                return True
        return False

    @filter.command("贴表情")
    async def on_command(self, event: AiocqhttpMessageEvent, emojiNum: int = 5):
        """贴表情 <数量>"""
        if not self._is_allowed(event):
            return

        chain = event.get_messages()
        if not chain:
            return
        reply = chain[0] if isinstance(chain[0], Reply) else None
        if not reply or not reply.chain or not reply.text or not reply.id:
            return

        images = [seg.url for seg in reply.chain if isinstance(seg, Image) and seg.url]

        emotion = await self.judger.judge_emotion(
            event,
            text=reply.text,
            image_urls=images,
            labels=self.cfg.emotion_labels,
        )
        emoji_ids = self.cfg.get_emoji_ids(emotion, need_count=int(emojiNum))
        await self._emoji_like(event, emoji_ids, message_id=reply.id)
        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_message(self, event: AiocqhttpMessageEvent):
        """群消息监听"""
        if not self._is_allowed(event):
            return

        if await self._follow_reaction_notice(event):
            event.stop_event()
            return

        if event.is_at_or_wake_command:
            return

        # 跟随已有表情
        chain = event.get_messages()
        emoji_ids = [seg.id for seg in chain if isinstance(seg, Face)]
        if emoji_ids and random.random() < self.cfg.emoji_follow_prob:
            await self._emoji_like(event, emoji_ids)

        # 主动表情
        msg = event.message_str
        if msg and random.random() < self.cfg.emoji_like_prob:
            asyncio.create_task(self.async_emoji_like_by_emotion(event, msg))

    async def async_emoji_like_by_emotion(
        self,
        event: AiocqhttpMessageEvent,
        text: str,
        image_urls: list[str] | None = None,
        message_id: int | str | None = None,
    ):
        emotion = await self.judger.judge_emotion(
            event,
            text=text,
            image_urls=image_urls,
            labels=self.cfg.emotion_labels,
        )
        emoji_ids = self.cfg.get_emoji_ids(emotion, need_count=1)
        await self._emoji_like(event, emoji_ids, message_id=message_id)

    def _recently_followed(self, message_id: str, emoji_id: str, ttl: float = 10.0) -> bool:
        """检查同一消息同一表情是否在去重时间窗口内已被跟随"""
        now = time.time()
        key = (str(message_id), str(emoji_id))
        last = self._followed_reactions.get(key, 0)
        if now - last < ttl:
            return True
        self._followed_reactions[key] = now

        # 缓存超过 500 条时清理过期条目
        if len(self._followed_reactions) > 500:
            self._followed_reactions = {
                k: v for k, v in self._followed_reactions.items() if now - v < ttl
            }

        return False

    @filter.event_message_type(filter.EventMessageType.ALL)
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def on_group_emoji_reaction(self, event: AiocqhttpMessageEvent):
        """跟随群友给某条消息贴表情反应"""
        reaction_follow_enabled = getattr(self.cfg, "reaction_follow_enabled", True)
        if not reaction_follow_enabled:
            return

        raw = getattr(event.message_obj, "raw_message", None)
        if raw is None:
            return

        if _raw_get(raw, "post_type") != "notice":
            return

        if _raw_get(raw, "notice_type") != "group_msg_emoji_like":
            return

        # 只跟随"添加表情"，不跟随取消
        if _raw_get(raw, "is_add") is False:
            return

        group_id = _raw_get(raw, "group_id")
        reactor_id = _raw_get(raw, "user_id")
        self_id = _raw_get(raw, "self_id")
        message_id = _raw_get(raw, "message_id")
        likes = _raw_get(raw, "likes", [])

        # 防止 Bot 自己贴表情后再次触发循环
        if str(reactor_id) == str(self_id):
            return

        # 会话 / 群聊 / 用户黑白名单
        if not self._is_allowed(event, group_id=group_id, user_id=reactor_id):
            return

        if not message_id or not likes:
            return

        # 按概率决定是否跟随（先判定概率，避免未跟随也消耗去重窗口）
        reaction_follow_prob = getattr(self.cfg, "reaction_follow_prob", 0.3)
        if random.random() >= reaction_follow_prob:
            return

        # 从 likes 中提取 emoji_id，并过滤去重
        dedupe_seconds = getattr(self.cfg, "reaction_follow_dedupe_seconds", 10.0)
        emoji_ids = []
        for item in likes:
            try:
                emoji_id = int(item.get("emoji_id") if isinstance(item, dict) else item)
                if not self._recently_followed(str(message_id), str(emoji_id), dedupe_seconds):
                    emoji_ids.append(emoji_id)
            except Exception:
                continue

        if not emoji_ids:
            return

        logger.info(
            f"跟随群友贴表情: group={group_id}, reactor={reactor_id}, "
            f"message={message_id}, emoji_ids={emoji_ids}"
        )

        await self._emoji_like(event, emoji_ids, message_id=message_id)
        event.stop_event()
