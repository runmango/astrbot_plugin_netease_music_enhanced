# NetEase Cloud Music Enhanced · 网易云点歌增强版

[![Plugin Version](https://img.shields.io/badge/version-1.0.2-blue.svg)](#)
[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-ff69b4)](https://github.com/AstrBotDevs/AstrBot)
[![Platform](https://img.shields.io/badge/platform-QQ-NapCat)](https://napcat.napneko.icu/)
[![License](https://img.shields.io/badge/license-AGPL%203.0-green.svg)](LICENSE)

An enhanced NetEase Cloud Music plugin for [AstrBot](https://astrbot.app): natural-language song requests, “next song” without repeats, artist shuffle, and “user’s liked songs” feed (newest first). **QQ only** (NapCat / QQNT).

基于 [astrbot_plugin_neteasecloud_music](https://github.com/SatenShiroya/astrbot_plugin_neteasecloud_music) 扩展的网易云点歌插件，支持自然语言点歌、换一首不重复、按歌手随机、按用户喜欢列表顺序推送。**仅支持 QQ 平台**（NapCat / QQNT）。

---

## Table of Contents · 目录

- [Features · 功能特性](#features--功能特性)
- [Requirements · 环境要求](#requirements--环境要求)
- [Installation · 安装](#installation--安装)
- [Configuration · 配置](#configuration--配置)
- [Usage · 使用方式](#usage--使用方式)
- [LLM Tools Reference · LLM 工具说明](#llm-tools-reference--llm-工具说明)
- [Examples · 示例](#examples--示例)
- [Troubleshooting · 常见问题](#troubleshooting--常见问题)
- [License · 许可证](#license--许可证)

---

## Features · 功能特性

| Feature | Description |
|--------|-------------|
| **Natural-language play** | 说歌名或「歌手 + 歌名」，在 QQ 中发送网易云音乐卡片。 |
| **Next song without repeat** | 用户说「换一首」「再来一首」时，从上一轮搜索结果中换一首播放，尽量不重复；列表播完后会重新搜索再随机。 |
| **Artist-only shuffle** | 仅提歌手（如「放周杰伦的歌」）时，从该歌手歌曲中随机选一首，并避免与近期播放重复。 |
| **No “played” announcement** | 默认不发送「已为您播放《xxx》」；可在配置中自定义或留空。 |
| **User’s liked songs** | 支持按网易云用户（昵称或 ID）播放其「我喜欢的音乐」；推送顺序为**先新后旧**，同一会话内按顺序依次推送。 |
| **User’s liked music analysis** | 分析指定网易云用户的歌单（喜欢/公开歌单）：曲目总数、歌手分布（Top N）、偏好简述。 |

---

## Requirements · 环境要求

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)（支持 LLM 工具调用）
- QQ 协议端（如 [NapCat](https://napcat.napneko.icu/) / QQNT）
- Python 依赖：`aiohttp`；使用 SOCKS 代理时需安装 `aiohttp-socks`

```bash
pip install aiohttp
# 使用 SOCKS 代理时：
pip install aiohttp-socks
```

---

## Installation · 安装

**方式一：插件市场（推荐）**

在 AstrBot 管理后台的插件市场中搜索 **`astrbot_plugin_NetEase_Music_Enhanced`**，点击安装。

**方式二：本地安装**

1. 下载本仓库或发布包；
2. 在 AstrBot 管理界面中选择「从本地压缩包安装」，选择该插件目录或压缩包。

安装完成后在插件列表中启用「网易云点歌增强版」并保存配置。

---

## Configuration · 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `play_success_message_template` | string | `""` | 点歌/换一首/用户喜欢 成功后的回复模板。支持变量：`{title}`（歌名）、`{artist}`（歌手）。**留空则不发送任何成功提示**。 |
| `proxy_url` | string | `""` | 可选代理地址。海外部署建议配置国内 HTTP/HTTPS 或 SOCKS 代理以正常访问网易云接口。格式示例：`http://host:port`、`socks5://host:port`。使用 SOCKS 需安装 `aiohttp-socks`。 |

---

## Usage · 使用方式

用户在 QQ 中通过自然语言与机器人对话，由 AstrBot 的 LLM 理解意图并调用对应工具：

- 点歌：说歌名或「歌手 + 歌名」
- 换一首：说「换一首」「再来一首」「换一个」等
- 只播某歌手：说「放周杰伦的歌」「来首孙燕姿的」等（由 LLM 传 `only_artist=True`）
- 播某用户的喜欢：说「播放 xxx 喜欢的歌」（xxx 为网易云昵称或用户 ID）

仅 QQ 会发送音乐卡片；其他平台会返回文字说明，并提示在 QQ 中使用。

### 如何「搜索用户的歌」· How to play a user's liked songs

想播放**某个网易云用户**「我喜欢的音乐」里的歌时，在 QQ 里对机器人说类似：

- **用昵称**：`播放 张三 喜欢的歌`、`来首网易云用户 张三 的歌`、`搜一下用户 张三 的歌`
- **用用户 ID**：`播放 123456 喜欢的歌`（若 123456 是网易云用户 ID，会直接按 ID 取）

机器人会：先根据你给的名字或数字**搜索网易云用户** → 取该用户的**第一个歌单（即「我喜欢的音乐」）** → 按**先新后旧**的顺序每次推一首。同一会话里多次说「再播一首 xxx 的歌」会按顺序往后推。

若 LLM 没有正确识别，可在 AstrBot 的提示词或系统指令里说明：当用户提到「某人的歌」「某人喜欢的歌」「网易云用户 xxx」时，应调用工具 `play_netease_user_liked_song`，并传入用户昵称或用户 ID。

---

## LLM Tools Reference · LLM 工具说明

以下工具供 AstrBot 的 LLM 在对话中调用，无需用户记忆指令。

### 1. `play_netease_song_by_name(song_name, only_artist=False)`

按歌名或歌手播放网易云音乐。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `song_name` | string | 是 | 歌曲名、歌手名或「歌手 歌名」 |
| `only_artist` | boolean | 否 | 默认 `False`。当用户**只说了歌手**未说歌名时传 `True`，从该歌手歌曲中随机一首且尽量不重复。用户说「换一首」时应调用 `change_netease_song`，不要调用本工具。 |

---

### 2. `change_netease_song()`

无参数。用户说「换一首」「换一首歌」「再来一首」「换一个」等时调用。  
从上一轮搜索列表里换一首播放（不重复）；上一轮列表全部播过后会重新搜索再随机一首。

---

### 3. `play_netease_user_liked_song(user_identifier)`

根据网易云用户播放其「我喜欢的音乐」中的一首。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_identifier` | string | 是 | 网易云用户**昵称**或**用户 ID**（数字字符串）。昵称会先通过网易云用户搜索解析。 |

推送顺序：**先推送最新喜欢的，再推送较旧的**；同一会话多次调用按该顺序依次推送，播完一轮后从头循环。

---

### 4. `analyze_netease_user_liked_music(user_identifier)`

分析指定网易云用户的歌单（「我喜欢的音乐」或第一个有曲目的公开歌单），输出统计与偏好分析。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_identifier` | string | 是 | 网易云用户**昵称**或**用户 ID**（仅传昵称/ID，不要带「用户」等前缀）。 |

分析内容：**歌单概况**（曲目总数）、**歌手分布**（按出现次数 Top 15，含占比）、**偏好简述**（最常出现的歌手等）。用户说「分析一下 xxx 的歌单」「统计用户 xxx 的听歌喜好」时调用。

---

## Examples · 示例

| 用户说法 | 行为 |
|----------|------|
| 我想听七里香 | 按歌名搜索并发送第一首的音乐卡片 |
| 播放周杰伦的晴天 | 按「周杰伦 晴天」搜索并发送 |
| 放周杰伦的歌 / 来首孙燕姿的 | 仅按歌手搜索，随机一首并避免重复 |
| 换一首 / 再来一首 | 从上一轮列表换一首；列表播完则重新搜索再随机 |
| 播放 xxx 喜欢的歌 | 搜索网易云用户 xxx，从其「喜欢」列表按先新后旧推送一首 |
| 分析一下 xxx 的歌单 / 统计用户 xxx 的听歌喜好 | 获取该用户歌单并输出曲目数、歌手分布、偏好简述 |

---

## Troubleshooting · 常见问题

**Q: 海外服务器点歌失败或返回异常？**  
A: 网易云接口在国内，建议在插件配置中填写 `proxy_url`（国内 HTTP/HTTPS 或 SOCKS 代理）。使用 SOCKS 需安装：`pip install aiohttp-socks`。

**Q: 其他平台（如 Telegram）能播吗？**  
A: 仅 QQ 会发送网易云音乐卡片；其他平台会返回文字说明，建议在 QQ 中使用以获得完整体验。

**Q: 网易云接口稳定吗？**  
A: 本插件使用网易云网页端非官方接口，仅供学习与个人使用，请勿滥用；接口可能随官网变更而失效。

**Q: 为什么提示「该用户喜欢的音乐列表为空或无法获取」？**  
A: 网易云对未登录请求**不返回**「我喜欢的音乐」里的曲目（视为隐私），所以很多用户的「喜欢」列表会显示为空。插件已做** fallback**：若「我喜欢的音乐」无曲目，会自动尝试该用户的其他**公开歌单**并从中播放。若该用户所有歌单都不可用，才会报错。建议让该用户将「我喜欢的音乐」设为公开，或换一个有此歌单公开的网易云用户。

---

## License · 许可证

[AGPL-3.0](LICENSE)

---

## 中文简介

本插件在原有网易云点歌插件基础上增加：

1. **换一首不重复**：通过 `change_netease_song` 从上一轮列表中换歌，避免重复。
2. **仅提歌手时随机**：LLM 传 `only_artist=True` 时从该歌手歌曲中随机选曲并记录已播。
3. **默认不播报「已为您播放」**：成功提示模板默认留空，可按需在配置中自定义。
4. **按用户喜欢推送**：支持搜索网易云用户并按其「我喜欢的音乐」列表**先新后旧**顺序推送。  
5. **用户歌单分析**：分析指定用户的喜欢/歌单，输出曲目总数、歌手分布（Top 15）、偏好简述。

插件 ID：`astrbot_plugin_NetEase_Music_Enhanced`。安装后请在 AstrBot 中启用并配置代理（若在海外部署）。
