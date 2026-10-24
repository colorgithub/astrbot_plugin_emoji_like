"""会话 / 群聊 / 用户黑白名单访问控制。

该模块不依赖 AstrBot，方便脱离 AstrBot 运行环境进行单元测试。

名单项可以填写：

- 会话 ID（UMO），如 ``aiocqhttp:GroupMessage:123456``，可用 AstrBot 内置 ``/sid`` 查看；
- UMO 前缀，按 ``:`` 分段匹配，如 ``aiocqhttp:GroupMessage`` 匹配该平台所有群；
- 群号，如 ``123456``；
- QQ 号（消息发送者 / 表情操作者），如 ``10001``。

规则（与 AstrBot 常见插件的白/黑名单习惯一致）：

- 白名单非空：只有命中白名单才允许，黑名单不再参与（白名单优先）；
- 白名单为空：命中黑名单则拒绝，否则允许；
- 两者都为空：全部允许。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_ID_SEPARATOR = re.compile(r"[,，、;；\s]+")


def normalize_id(value: Any) -> str:
    """把单个 ID 规范化为去除首尾空白的字符串；无效值返回空串。"""
    if value is None:
        return ""
    return str(value).strip()


def normalize_ids(values: Any) -> set[str]:
    """把配置值规范化为 ID 集合。"""
    if values is None:
        return set()

    # 单个标量值（如误填 "123" 或 123）也按一个 ID 处理
    if isinstance(values, (str, int)):
        values = [values]

    try:
        iterator = iter(values)
    except TypeError:
        text = normalize_id(values)
        return {text} if text else set()

    result: set[str] = set()
    for item in iterator:
        text = normalize_id(item)
        if not text:
            continue
        result.update(part for part in _ID_SEPARATOR.split(text) if part)
    return result


class AccessControl:
    """按白名单 / 黑名单判断当前事件是否允许插件响应。"""

    __slots__ = ("whitelist", "blacklist")

    def __init__(self, whitelist: Any = None, blacklist: Any = None) -> None:
        self.whitelist = normalize_ids(whitelist)
        self.blacklist = normalize_ids(blacklist)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "AccessControl":
        """从插件配置（或任意 Mapping）构建访问控制器。"""
        config = config or {}
        return cls(
            whitelist=config.get("whitelist"),
            blacklist=config.get("blacklist"),
        )

    @property
    def has_rules(self) -> bool:
        return bool(self.whitelist or self.blacklist)

    def signature(self) -> tuple[frozenset[str], frozenset[str]]:
        """返回可用于缓存失效判断的稳定签名。"""
        return (frozenset(self.whitelist), frozenset(self.blacklist))

    @staticmethod
    def _matches(
        entries: set[str],
        *,
        umo: Any = "",
        group_id: Any = "",
        user_id: Any = "",
    ) -> bool:
        if not entries:
            return False

        umo_text = normalize_id(umo)
        identifiers = [
            text
            for text in (umo_text, normalize_id(group_id), normalize_id(user_id))
            if text
        ]
        if not identifiers:
            return False

        for entry in entries:
            if entry in identifiers:
                return True
            # 支持按 UMO 前缀匹配（例如 aiocqhttp:GroupMessage 匹配该平台所有群）
            if umo_text and umo_text.startswith(entry + ":"):
                return True
        return False

    def is_allowed(
        self,
        *,
        umo: Any = "",
        group_id: Any = "",
        user_id: Any = "",
    ) -> bool:
        if self.whitelist:
            return self._matches(
                self.whitelist, umo=umo, group_id=group_id, user_id=user_id
            )

        if self.blacklist:
            return not self._matches(
                self.blacklist, umo=umo, group_id=group_id, user_id=user_id
            )

        return True

    def __repr__(self) -> str:
        return (
            "AccessControl("
            f"whitelist={sorted(self.whitelist)}, "
            f"blacklist={sorted(self.blacklist)})"
        )
