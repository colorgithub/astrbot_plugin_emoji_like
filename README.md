
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_emoji_like?name=astrbot_plugin_emoji_like&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_emoji_like

_✨ 智能贴表情 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 🤝 介绍

调用LLM判断消息的情感，智能地给消息贴上QQ表情（支持群聊/用户黑白名单）

## 📦 安装

在astrbot的插件市场搜索astrbot_plugin_emoji_like，点击安装即可


## ⌨️ 使用说明

### 命令表

|     命令      |        说明         |
|:-------------:|:----------------------------:|
| {一条消息}     | 概率触发贴表情，触发概率可在配置里设置  |
| 贴表情 <数量>  | 若不填数量，则默认贴5个    |

### 示例图

![download](https://github.com/user-attachments/assets/22d4a258-1d84-430e-9832-de2b12cdd9cf)

## 🚦 黑名单 / 白名单

支持按会话限制生效范围，配置只有两条列表，与 AstrBot 常见插件的白/黑名单用法一致。会话 ID 可用 AstrBot 内置的 `/sid` 指令查看。

| 配置项 | 说明 |
|:---|:---|
| `whitelist` | 贴表情白名单。**非空时只有名单内的会话会触发**，优先级高于黑名单 |
| `blacklist` | 贴表情黑名单。名单内的会话不会触发；白名单非空时以白名单为准 |

判定规则：

- **白名单优先**：白名单非空时，只有命中白名单的会话才会贴表情，黑名单不再参与判定；同一个会话同时出现在两个名单时也会放行。
- **白名单留空时黑名单生效**：命中黑名单的会话不触发；两者都留空表示不限制。
- 名单项支持四种写法：完整会话 ID（UMO，如 `aiocqhttp:GroupMessage:123456`）、UMO 前缀（如 `aiocqhttp:GroupMessage`，匹配该平台所有群）、群号（如 `123456`）、QQ号（如 `10001`，匹配该用户的消息与表情反应）。
- 名单同时作用于「自动贴表情」「跟随已有表情」「跟随群友表情反应」以及 `贴表情` 指令；被拦截时插件完全静默。
- 名单项支持整数或字符串，每项填一个；也兼容 `123,456`、`123 456` 这类一行多值的写法。

示例：只允许群 `123456` 和 `789012` 生效（群号或 UMO 都可以）：

```json
{
  "whitelist": ["123456", "aiocqhttp:GroupMessage:789012"],
  "blacklist": []
}
```

示例：除 QQ `10001` 外全部生效（黑名单模式，白名单留空）：

```json
{
  "whitelist": [],
  "blacklist": ["10001"]
}
```

## 🧪 开发与测试

仓库自带完全离线的测试套件（不安装、不连接 AstrBot，纯标准库 `unittest`）：

```bash
python -m unittest discover -s tests -v
```

测试通过 `tests/_astrbot_stub.py` 向 `sys.modules` 注入 AstrBot 桩模块，因此无需 `pip install astrbot`；覆盖黑白名单判定、配置热更新、各触发入口的拦截以及情感解析。

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）
