"""完全离线的 AstrBot 桩模块（stub）。

本测试套件不安装、也不连接真实的 AstrBot。导入插件前先调用 ``install()``：

    import _astrbot_stub
    _astrbot_stub.install()
    import astrbot_plugin_emoji_like.main

``install()`` 会做两件事：

1. 把仓库父目录（本文件向上三级，即包含 ``astrbot_plugin_emoji_like`` 的目录）
   加入 ``sys.path``，使仓库根目录（无 ``__init__.py``）作为 namespace package 可被导入；
2. 向 ``sys.modules`` 注入插件 import 所需的 astrbot 模块与对象。

重复调用是幂等的。所有网络 / 文件系统副作用均无。
"""

from __future__ import annotations

import logging
import sys
import tempfile
import types
from pathlib import Path

_STUB_MARKER = "__offline_astrbot_stub__"

# tests/ -> 仓库根目录 -> 仓库父目录（例如 D:\astrbot_plugins）
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPO_PARENT = _REPO_ROOT.parent


# ---------------------------------------------------------------------------
# 基础对象
# ---------------------------------------------------------------------------


class AstrBotConfig(dict):
    """AstrBotConfig 的最小替身：dict + save_config()。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved_count = 0

    def save_config(self) -> None:
        self.saved_count += 1


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("astrbot_plugin_emoji_like.tests.stub_logger")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


logger = _build_logger()


class Context:
    """AstrBot Context 的最小替身。"""

    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs

    def get_provider_by_id(self, provider_id=None, *args, **kwargs):
        return None

    def get_using_provider(self, umo=None, *args, **kwargs):
        return None


class Star:
    """AstrBot Star 基类的最小替身。"""

    def __init__(self, context):
        self.context = context


class Provider:
    """Provider 基类替身。

    必须保留为真实类：``PluginConfig.get_judge_provider`` 里有 isinstance 检查。
    """

    async def text_chat(self, **kwargs):  # pragma: no cover - 仅作为基类
        raise NotImplementedError


class StarTools:
    """StarTools 替身，返回临时目录，不落盘。"""

    _data_root = Path(tempfile.gettempdir()) / "astrbot_plugin_emoji_like_tests"

    @classmethod
    def get_data_dir(cls, plugin_name=None, *args, **kwargs) -> Path:
        return cls._data_root / str(plugin_name or "plugin")


def get_astrbot_plugin_path(*args, **kwargs) -> str:
    return str(StarTools._data_root / "plugins")


# ---------------------------------------------------------------------------
# 消息组件
# ---------------------------------------------------------------------------


class Face:
    def __init__(self, id=None, *args, **kwargs):
        self.id = id


class Image:
    def __init__(self, url="", *args, **kwargs):
        self.url = url


class Reply:
    def __init__(self, chain=None, text="", id=None, *args, **kwargs):
        self.chain = list(chain) if chain else []
        self.text = text
        self.id = id


# ---------------------------------------------------------------------------
# 事件类型
# ---------------------------------------------------------------------------


class AstrMessageEvent:
    """事件基类替身，仅用于类型注解。"""


class AiocqhttpMessageEvent(AstrMessageEvent):
    """aiocqhttp 事件替身，仅用于类型注解。"""


class EventMessageType:
    ALL = "all"
    GROUP_MESSAGE = "group_message"
    PRIVATE_MESSAGE = "private_message"


class PlatformAdapterType:
    AIOCQHTTP = "aiocqhttp"


class _Filter:
    """``astrbot.api.event.filter`` 替身：装饰器直接返回原函数。"""

    EventMessageType = EventMessageType
    PlatformAdapterType = PlatformAdapterType

    @staticmethod
    def command(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    @staticmethod
    def event_message_type(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    @staticmethod
    def platform_adapter_type(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


filter = _Filter()


# ---------------------------------------------------------------------------
# 模块注入
# ---------------------------------------------------------------------------


def _register(name: str, attrs: dict | None = None) -> types.ModuleType:
    """创建（或复用）一个 stub 模块并挂到 sys.modules / 父模块上。"""
    module = sys.modules.get(name)
    if module is None or not getattr(module, _STUB_MARKER, False):
        module = types.ModuleType(name)
        module.__package__ = name.rpartition(".")[0]
        # 让模块也能被当作 package 继续 import（即使所有子模块已预注入）
        module.__path__ = []
        setattr(module, _STUB_MARKER, True)
        sys.modules[name] = module

    for key, value in (attrs or {}).items():
        setattr(module, key, value)

    parent_name, _, child = name.rpartition(".")
    if parent_name:
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child, module)
    return module


def install() -> None:
    """注入全部 astrbot stub；幂等。"""
    if getattr(sys.modules.get("astrbot"), _STUB_MARKER, False):
        return

    parent = str(_REPO_PARENT)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    # 根与包
    _register("astrbot")
    _register(
        "astrbot.api",
        {
            "logger": logger,
            "AstrBotConfig": AstrBotConfig,
        },
    )
    _register(
        "astrbot.api.event",
        {
            "filter": filter,
            "EventMessageType": EventMessageType,
            "PlatformAdapterType": PlatformAdapterType,
            "AstrMessageEvent": AstrMessageEvent,
        },
    )
    _register(
        "astrbot.api.star",
        {
            "Context": Context,
            "Star": Star,
        },
    )

    # astrbot.core 及其子包
    _register("astrbot.core")
    _register("astrbot.core.config")
    _register(
        "astrbot.core.config.astrbot_config",
        {"AstrBotConfig": AstrBotConfig},
    )
    _register("astrbot.core.provider")
    _register("astrbot.core.provider.provider", {"Provider": Provider})
    _register("astrbot.core.star")
    _register("astrbot.core.star.context", {"Context": Context})
    _register("astrbot.core.star.star_tools", {"StarTools": StarTools})
    _register("astrbot.core.utils")
    _register(
        "astrbot.core.utils.astrbot_path",
        {"get_astrbot_plugin_path": get_astrbot_plugin_path},
    )
    _register("astrbot.core.message")
    _register(
        "astrbot.core.message.components",
        {"Face": Face, "Image": Image, "Reply": Reply},
    )
    _register("astrbot.core.platform")
    _register(
        "astrbot.core.platform.astr_message_event",
        {"AstrMessageEvent": AstrMessageEvent},
    )
    _register("astrbot.core.platform.sources")
    _register("astrbot.core.platform.sources.aiocqhttp")
    _register(
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event",
        {"AiocqhttpMessageEvent": AiocqhttpMessageEvent},
    )
