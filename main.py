"""
网易云点歌增强版：换一首不重复、按歌手随机、不播报、按用户喜欢推送（先新后旧）
"""
import json
import random
import aiohttp
from astrbot.api.event import filter
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.api.star import Star, register, Context
from astrbot.api import logger, AstrBotConfig


def _chat_key(event) -> str:
    """会话唯一键：群聊用 group_id，私聊用 user_id"""
    if not isinstance(event, AiocqhttpMessageEvent):
        return ""
    if event.is_private_chat():
        return f"p_{event.get_sender_id()}"
    return f"g_{event.get_group_id()}"


@register(
    "astrbot_plugin_NetEase_Music_Enhanced",
    "YourName",
    "网易云点歌增强：换一首不重复、歌手随机、用户喜欢推送（先新后旧）",
    "1.0.0",
)
class MusicPluginEnhanced(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.session = None
        self.play_success_message_template = config.get("play_success_message_template", "")
        self.proxy_url = config.get("proxy_url", "")

        # 当前会话的「上一首」上下文：换一首 / 同歌手随机用
        # key: _chat_key(event), value: { "keyword": str, "song_ids": [id,...], "played_ids": set(id,...) }
        self._play_context: dict[str, dict] = {}

        # 网易云用户「喜欢」歌单推送进度：先新后旧
        # key: (chat_key, netease_uid), value: next_index
        self._user_liked_index: dict[tuple[str, str], int] = {}

    async def initialize(self):
        connector = None
        if self.proxy_url.startswith(("socks4://", "socks5://")):
            try:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(self.proxy_url)
                logger.info("[NetEaseMusicEnhanced] 已启用 SOCKS 代理")
            except ImportError:
                logger.error(
                    "[NetEaseMusicEnhanced] 需 SOCKS 代理但未安装 aiohttp-socks，回退无代理。"
                    " pip install aiohttp-socks"
                )
                self.proxy_url = ""
        self.session = aiohttp.ClientSession(connector=connector, trust_env=False)

    async def _netease_request(self, url: str, data: dict = None, method: str = "GET"):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://music.163.com/",
            "Origin": "https://music.163.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        cookies = {"appver": "2.9.11", "os": "pc"}
        proxy = (
            self.proxy_url
            if self.proxy_url and self.proxy_url.startswith(("http://", "https://"))
            else None
        )
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            if method.upper() == "POST":
                async with self.session.post(
                    url, headers=headers, cookies=cookies, data=data or {},
                    proxy=proxy, timeout=timeout,
                ) as resp:
                    return json.loads(await resp.text())
            async with self.session.get(
                url, headers=headers, cookies=cookies,
                proxy=proxy, timeout=timeout,
            ) as resp:
                return json.loads(await resp.text())
        except Exception as e:
            logger.error(f"[NetEaseMusicEnhanced] 请求失败 {url}: {e}")
            raise

    async def netease_search_songs(self, keyword: str, limit: int = 30) -> list[dict]:
        """搜索歌曲，返回 [{id, name, artists}, ...]"""
        url = "http://music.163.com/api/search/get/web"
        data = {"s": keyword.strip(), "type": 1, "limit": limit, "offset": 0}
        for attempt in range(3):
            try:
                result = await self._netease_request(url, data=data, method="POST")
                if not isinstance(result, dict):
                    raise ValueError(f"响应类型错误: {type(result)}")
                songs = result.get("result", {}).get("songs", [])
                if not isinstance(songs, list):
                    raise ValueError("歌曲列表不是 list")
                out = []
                for s in songs[:limit]:
                    if not isinstance(s, dict):
                        continue
                    out.append({
                        "id": s["id"],
                        "name": s["name"],
                        "artists": "、".join(
                            a["name"] for a in s.get("artists", [])
                            if isinstance(a, dict) and "name" in a
                        ),
                    })
                return out
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                logger.warning(f"网易云搜索解析失败 第{attempt + 1}次: {e}")
            except Exception as e:
                logger.warning(f"网易云搜索请求异常 第{attempt + 1}次: {e}")
        logger.error(f"网易云搜索失败 keyword={keyword}")
        return []

    def _pick_song_from_context(self, chat_k: str, keyword: str, songs: list[dict], avoid_repeat: bool) -> dict | None:
        """从本次搜索结果中选一首：可排除已播，用于换一首/同歌手随机。"""
        if not songs:
            return None
        ctx = self._play_context.get(chat_k)
        played = set(ctx["played_ids"]) if ctx else set()
        song_ids = [s["id"] for s in songs]
        # 更新或创建上下文
        if chat_k not in self._play_context:
            self._play_context[chat_k] = {"keyword": keyword, "song_ids": song_ids, "played_ids": set()}
        else:
            self._play_context[chat_k]["keyword"] = keyword
            self._play_context[chat_k]["song_ids"] = song_ids
            self._play_context[chat_k]["played_ids"] = played

        candidates = [s for s in songs if not (avoid_repeat and s["id"] in played)]
        if not candidates:
            # 全部播过则重置已播，再随机
            self._play_context[chat_k]["played_ids"] = set()
            candidates = songs
        chosen = random.choice(candidates)
        self._play_context[chat_k]["played_ids"].add(chosen["id"])
        return chosen

    def _pick_first_or_random(self, chat_k: str, keyword: str, songs: list[dict], prefer_random: bool) -> dict | None:
        """点歌：若 prefer_random（仅歌手/换一首）则随机且不重复；否则取第一首并记录上下文。"""
        if not songs:
            return None
        if prefer_random:
            return self._pick_song_from_context(chat_k, keyword, songs, avoid_repeat=True)
        # 明确歌名：仍记录上下文供「换一首」用，本次取第一首
        if chat_k not in self._play_context:
            self._play_context[chat_k] = {"keyword": keyword, "song_ids": [s["id"] for s in songs], "played_ids": set()}
        self._play_context[chat_k]["played_ids"].add(songs[0]["id"])
        return songs[0]

    async def _send_qq_music_card(self, event: AiocqhttpMessageEvent, song_id: str) -> bool:
        """在 QQ 发送网易云音乐卡片。"""
        payload = {
            "message": [{"type": "music", "data": {"type": "163", "id": str(song_id)}}]
        }
        if event.is_private_chat():
            payload["user_id"] = event.get_sender_id()
            await event.bot.call_action("send_private_msg", **payload)
        else:
            payload["group_id"] = event.get_group_id()
            await event.bot.call_action("send_group_msg", **payload)
        return True

    # ---------- 网易云用户搜索与「喜欢」歌单 ----------
    async def netease_search_user(self, keyword: str, limit: int = 5) -> list[dict]:
        """搜索网易云用户。返回 [{userId, nickname, ...}, ...]"""
        url = "http://music.163.com/api/search/get/web"
        data = {"s": keyword.strip(), "type": 1002, "limit": limit, "offset": 0}
        for attempt in range(3):
            try:
                result = await self._netease_request(url, data=data, method="POST")
                if not isinstance(result, dict):
                    raise ValueError(f"响应类型错误: {type(result)}")
                users = (
                    result.get("result", {}).get("userprofiles")
                    or result.get("result", {}).get("users")
                    or []
                )
                if not isinstance(users, list):
                    users = []
                out = []
                for u in users[:limit]:
                    if not isinstance(u, dict):
                        continue
                    uid = u.get("userId") or u.get("id")
                    if uid is None:
                        continue
                    out.append({
                        "userId": str(uid),
                        "nickname": (u.get("nickname") or u.get("name") or "").strip() or str(uid),
                    })
                return out
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                logger.warning(f"网易云用户搜索解析失败 第{attempt + 1}次: {e}")
            except Exception as e:
                logger.warning(f"网易云用户搜索请求异常 第{attempt + 1}次: {e}")
        return []

    async def netease_user_playlists(self, uid: str, limit: int = 15) -> list[dict]:
        """获取用户歌单列表。第一个通常为「我喜欢的音乐」，后面为创建的歌单。"""
        url = "http://music.163.com/api/user/playlist"
        try:
            result = await self._netease_request(
                f"{url}?uid={uid}&limit={limit}&offset=0",
                method="GET",
            )
            if not isinstance(result, dict):
                return []
            playlists = result.get("playlist", [])
            if not isinstance(playlists, list):
                return []
            return playlists
        except Exception as e:
            logger.warning(f"获取用户歌单失败 uid={uid}: {e}")
            return []

    async def netease_playlist_detail(self, playlist_id: str) -> list[dict]:
        """获取歌单详情。返回按添加时间倒序的歌曲列表 [{id, name, artists}, ...]。"""
        url = "http://music.163.com/api/playlist/detail"
        try:
            result = await self._netease_request(
                f"{url}?id={playlist_id}",
                method="GET",
            )
            if not isinstance(result, dict):
                return []
            pl = result.get("result", result)
            if not isinstance(pl, dict):
                return []
            # trackIds: [ { id, t (添加时间 ms) }, ... ]，按 t 倒序=先新后旧
            track_ids = pl.get("trackIds", [])
            tracks = pl.get("tracks", [])
            if not isinstance(track_ids, list):
                track_ids = []
            if not isinstance(tracks, list):
                tracks = []

            # 有 trackIds 时按 t 排序（新在前）
            if track_ids and isinstance(track_ids[0], dict):
                track_ids_sorted = sorted(
                    track_ids,
                    key=lambda x: (x.get("t") or 0),
                    reverse=True,
                )
                id_order = [str(t["id"]) for t in track_ids_sorted]
            else:
                id_order = [str(t.get("id", t) if isinstance(t, dict) else t) for t in track_ids]

            # 用 tracks 拼信息，不足时只保留 id 列表，播时用 id 即可
            track_map = {}
            for t in tracks:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("id", ""))
                track_map[tid] = {
                    "id": t.get("id"),
                    "name": t.get("name", "未知"),
                    "artists": "、".join(
                        a.get("name", "") for a in (t.get("artists") or [])
                        if isinstance(a, dict)
                    ) or "未知",
                }
            out = []
            for tid in id_order:
                if tid in track_map:
                    out.append(track_map[tid])
                else:
                    out.append({"id": int(tid) if tid.isdigit() else tid, "name": "未知", "artists": ""})
            return out
        except Exception as e:
            logger.warning(f"获取歌单详情失败 id={playlist_id}: {e}")
            return []

    def _get_user_liked_track(self, chat_k: str, netease_uid: str, tracks: list[dict]) -> dict | None:
        """按「先新后旧」取当前该聊天、该用户喜欢列表中的下一首；无则返回 None。"""
        if not tracks:
            return None
        key = (chat_k, netease_uid)
        idx = self._user_liked_index.get(key, 0)
        if idx >= len(tracks):
            idx = 0
            self._user_liked_index[key] = 0
        track = tracks[idx]
        self._user_liked_index[key] = idx + 1
        return track

    # ---------- LLM 工具 ----------
    @filter.llm_tool(name="play_netease_song_by_name")
    async def play_netease_song_by_name(
        self, event: AiocqhttpMessageEvent, song_name: str, only_artist: bool = False
    ) -> MessageEventResult:
        """
        根据歌名或歌手播放网易云音乐。
        - 若用户只说了歌手名（如「放周杰伦的歌」「来首孙燕姿的」）未说具体歌名，请传 only_artist=True，会从该歌手歌曲中随机一首且尽量不重复。
        - 若用户说「换一首」「换一首歌」「再来一首」等，请调用 change_netease_song，不要调用本工具。
        Args:
            song_name(string): 歌曲名或歌手名或「歌手 歌名」
            only_artist(bool): 是否仅为「歌手名」未指定歌名，True 时随机选歌不重复
        """
        if not song_name or not song_name.strip():
            yield event.plain_result("歌名或歌手不能为空哦~")
            return

        keyword = song_name.strip()
        chat_k = _chat_key(event)
        songs = await self.netease_search_songs(keyword, limit=25)
        if not songs:
            yield event.plain_result(f"没找到「{keyword}」相关的歌曲")
            return

        chosen = self._pick_first_or_random(chat_k, keyword, songs, prefer_random=only_artist)
        if not chosen:
            yield event.plain_result("选歌失败，请稍后再试")
            return

        song_id = str(chosen["id"])
        title = chosen["name"]
        artist = chosen["artists"]

        if not isinstance(event, AiocqhttpMessageEvent):
            yield event.plain_result(
                f"🎵 《{title}》- {artist}\n"
                "当前平台不支持直接播放，建议在 QQ 中使用。"
            )
            return

        try:
            await self._send_qq_music_card(event, song_id)
            logger.info(f"[NetEaseMusicEnhanced] 已发送: {title} - {artist} ({song_id})")
            if self.play_success_message_template and self.play_success_message_template.strip():
                yield event.plain_result(
                    self.play_success_message_template.format(title=title, artist=artist)
                )
            return
        except Exception as e:
            logger.error(f"发送音乐卡片失败: {e}")
            yield event.plain_result("抱歉，发送音乐卡片失败了")
            return

    @filter.llm_tool(name="change_netease_song")
    async def change_netease_song(self, event: AiocqhttpMessageEvent) -> MessageEventResult:
        """
        用户说「换一首」「换一首歌」「再来一首」「换一个」等时调用。
        从上一轮的搜索列表里换一首播放，不重复；若上一轮列表已播完则重新搜索再随机一首。
        无需参数。
        """
        chat_k = _chat_key(event)
        if not chat_k:
            yield event.plain_result("当前环境无法换歌哦")
            return

        ctx = self._play_context.get(chat_k)
        if not ctx or not ctx.get("song_ids"):
            yield event.plain_result("没有上一首可以换哦，先点一首歌吧~")
            return

        keyword = ctx["keyword"]
        # 先尝试从当前列表选未播过的
        songs_raw = await self.netease_search_songs(keyword, limit=25)
        if not songs_raw:
            yield event.plain_result("重新搜索失败，请稍后再试")
            return

        chosen = self._pick_song_from_context(chat_k, keyword, songs_raw, avoid_repeat=True)
        if not chosen:
            yield event.plain_result("换歌失败，请稍后再试")
            return

        song_id = str(chosen["id"])
        title = chosen["name"]
        artist = chosen["artists"]

        if not isinstance(event, AiocqhttpMessageEvent):
            yield event.plain_result(f"🎵 《{title}》- {artist}\n请在 QQ 中使用以直接播放。")
            return

        try:
            await self._send_qq_music_card(event, song_id)
            logger.info(f"[NetEaseMusicEnhanced] 换一首已发送: {title} - {artist} ({song_id})")
            if self.play_success_message_template and self.play_success_message_template.strip():
                yield event.plain_result(
                    self.play_success_message_template.format(title=title, artist=artist)
                )
            return
        except Exception as e:
            logger.error(f"发送音乐卡片失败: {e}")
            yield event.plain_result("抱歉，发送失败了")
            return

    @filter.llm_tool(name="play_netease_user_liked_song")
    async def play_netease_user_liked_song(
        self, event: AiocqhttpMessageEvent, user_identifier: str
    ) -> MessageEventResult:
        """
        当用户想听「某个网易云用户的歌」「某人喜欢的歌」「某人歌单」时调用此工具。
        会先根据 user_identifier 搜索网易云用户（昵称或用户ID），再播放该用户「我喜欢的音乐」中的一首；
        推送顺序为先新后旧，同一会话多次调用会按顺序往后推。
        示例：用户说「播放 张三 喜欢的歌」「来首网易云用户 acane麦外敷 的歌」→ 传入「张三」或「acane麦外敷」（不要带「用户」二字）。
        Args:
            user_identifier(string): 网易云用户昵称或用户ID（纯数字）。仅传昵称/ID，不要包含「用户」「网易云用户」等前缀。
        """
        if not user_identifier or not user_identifier.strip():
            yield event.plain_result("请提供网易云用户昵称或用户ID哦~")
            return

        # 规范参数：去掉句首「用户」字样，避免 LLM 传入「用户acane麦外敷」导致搜索不一致
        raw = user_identifier.strip()
        for prefix in ("用户", "网易云用户", "网易云 "):
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
                break
        if not raw:
            yield event.plain_result("请提供网易云用户昵称或用户ID哦~")
            return

        chat_k = _chat_key(event)

        # 若为纯数字视为 uid
        if raw.isdigit():
            uid = raw
            nickname = raw
        else:
            users = await self.netease_search_user(raw, limit=5)
            if not users:
                yield event.plain_result(f"未找到网易云用户「{raw}」")
                return
            uid = users[0]["userId"]
            nickname = users[0]["nickname"]

        playlists = await self.netease_user_playlists(uid)
        if not playlists:
            yield event.plain_result("该用户暂无公开歌单或「喜欢」列表不可用")
            return

        # 依次尝试歌单：优先「我喜欢的音乐」（第一个），若为空则尝试后续公开歌单（网易云未登录时常不返回「喜欢」曲目）
        tracks = []
        for pl in playlists:
            pl_id = str(pl.get("id", ""))
            pl_name = (pl.get("name") or "歌单").strip()
            if not pl_id:
                continue
            detail_tracks = await self.netease_playlist_detail(pl_id)
            if detail_tracks:
                tracks = detail_tracks
                if pl is playlists[0]:
                    logger.info(f"[NetEaseMusicEnhanced] 用户 {nickname}({uid}) 使用「我喜欢的音乐」")
                else:
                    logger.info(f"[NetEaseMusicEnhanced] 用户 {nickname}「我喜欢的音乐」无曲目，改用歌单「{pl_name}」")
                break
            if pl is playlists[0]:
                logger.warning(
                    f"[NetEaseMusicEnhanced] 用户 {nickname}({uid}) 歌单「{pl_name}」返回 0 首，"
                    "可能为隐私或未登录无法获取，将尝试其他歌单"
                )

        if not tracks:
            yield event.plain_result(
                "该用户的歌单暂时无法获取（网易云「我喜欢的音乐」多为隐私，未登录时无法读取）。"
                "可尝试提供其他网易云用户，或请该用户将「我喜欢的音乐」设为公开。"
            )
            return

        track = self._get_user_liked_track(chat_k, uid, tracks)
        if not track:
            yield event.plain_result("没有可推送的歌曲了")
            return

        song_id = str(track["id"])
        title = track.get("name", "未知")
        artist = track.get("artists", "")

        if not isinstance(event, AiocqhttpMessageEvent):
            yield event.plain_result(
                f"🎵 《{title}》- {artist}（来自用户 {nickname} 的喜欢）\n请在 QQ 中使用以直接播放。"
            )
            return

        try:
            await self._send_qq_music_card(event, song_id)
            logger.info(f"[NetEaseMusicEnhanced] 用户喜欢已发送: {title} - {artist} (用户 {nickname})")
            if self.play_success_message_template and self.play_success_message_template.strip():
                yield event.plain_result(
                    self.play_success_message_template.format(title=title, artist=artist)
                )
            return
        except Exception as e:
            logger.error(f"发送音乐卡片失败: {e}")
            yield event.plain_result("抱歉，发送失败了")
            return

    async def terminate(self):
        if self.session:
            await self.session.close()
