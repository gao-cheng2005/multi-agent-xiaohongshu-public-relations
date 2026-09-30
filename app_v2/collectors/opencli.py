"""用 OpenCLI 抓取小红书数据。

OpenCLI 是一个命令行工具，它能驱动"已登录小红书的 Chrome 浏览器"去页面里抓数据。
这个文件负责：找到并调用 OpenCLI 命令、把返回结果整理成统一格式、失败时重试或给出提示。

抓不到数据的常见原因：Chrome 没登录小红书、链接里的签名过期等。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from ..core.settings import settings
from .base import BaseCollector


def _path_exists(path: str | Path) -> bool:
    """判断文件/目录是否存在；权限异常时当存在放行，避免误判。"""
    try:
        return Path(path).exists()
    except OSError:
        return True


def _resolve_command(bin_name: str) -> list[str]:
    """找到 opencli 命令的完整调用方式。

    Windows 上安装的全局命令通常是个 .cmd 小脚本，直接用偶尔出问题，
    所以优先找到它真正的主程序（main.js），用 node 直接运行更稳定。
    """
    # 先在系统 PATH 里找命令
    path = shutil.which(bin_name)
    # Windows 上没找到，再去 npm 全局安装目录找
    if not path and os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            npm_dir = Path(appdata) / "npm"
            for suffix in (".cmd", ".exe", ""):
                candidate = npm_dir / f"{bin_name}{suffix}"
                if _path_exists(candidate):
                    path = str(candidate)
                    break
    path = path or bin_name

    # 如果是 .cmd/.bat 小脚本，改成用 node 直接运行主程序
    if os.name == "nt" and path.lower().endswith((".cmd", ".bat")):
        npm_prefix = os.path.dirname(path)
        main_js = os.path.join(
            npm_prefix, "node_modules", "@jackwener", "opencli", "dist", "src", "main.js"
        )
        node = shutil.which("node") or shutil.which("node.exe")
        if node and _path_exists(main_js):
            return [node, main_js]
        return ["cmd", "/c", path]
    return [path]


class OpencliCollector(BaseCollector):
    """用 OpenCLI 抓取小红书的具体实现。"""

    # 认定为"瞬时/竞态"的失败特征：重试大概率能成功
    _TRANSIENT_FAILURE_MARKERS = (
        "Navigation rejected",
        "navigation was rejected",
        "session busy",
        "BROWSER_CONNECT",
        "Browser Bridge extension not connected",
        "code: UNKNOWN",
    )
    _RETRY_TIMES = 2          # 瞬时失败最多整体重试 2 次
    _RETRY_DELAY_SECONDS = 2  # 重试间隔

    @staticmethod
    def _extract_id(url: str) -> str:
        """从笔记链接里取出笔记编号（取路径最后一段）。"""
        try:
            path = urlparse(url).path
        except ValueError:
            path = url
        return path.rstrip("/").split("/")[-1]

    @staticmethod
    def _field_value(rows: list[dict], field: str) -> str:
        """从 [{field, value}, ...] 结构里按名字取值。"""
        for row in rows:
            if row.get("field") == field:
                return str(row.get("value") or "")
        return ""

    @staticmethod
    def _num(value) -> int:
        """把各种写法的数字（如"1.2万"）统一转成整数。"""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return int(digits) if digits else 0

    @staticmethod
    def _decode_output(blob: bytes) -> str:
        """把 opencli 的原始字节解码成文本，选乱码更少的解码结果。"""
        candidates: list[str] = []
        for enc in ("utf-8", "gbk"):
            try:
                candidates.append(blob.decode(enc))
            except UnicodeDecodeError:
                continue
        if not candidates:
            candidates.append(blob.decode("utf-8", errors="replace"))
        return min(candidates, key=lambda t: t.count("\ufffd"))

    def _run(self, args: list[str]) -> list[dict]:
        """执行 OpenCLI 命令并解析 JSON；瞬时失败自动重试几次。"""
        cmd = [*_resolve_command(settings.opencli_bin), *args, "-f", "json"]
        env = {**os.environ, "OPENCLI_BROWSER_COMMAND_TIMEOUT": "180"}
        proc = None
        last_reason = ""

        for attempt in range(self._RETRY_TIMES + 1):
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=240, env=env)
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"未找到 OpenCLI 命令 '{settings.opencli_bin}'。"
                    "请先安装：npm install -g @jackwener/opencli。"
                ) from exc

            # 失败时的错误信息，优先取 stderr
            last_reason = (
                (proc.stderr or b"").decode("utf-8", errors="replace").strip()
                or self._decode_output(proc.stdout or b"").strip()
            )
            if proc.returncode == 0:
                break
            # 瞬时/竞态类失败：隔几秒重试同一条命令
            if attempt < self._RETRY_TIMES and any(
                m in last_reason for m in self._TRANSIENT_FAILURE_MARKERS
            ):
                time.sleep(self._RETRY_DELAY_SECONDS)
                continue
            # 最常见失败：浏览器桥接扩展未连接
            if "BROWSER_CONNECT" in last_reason or "Browser Bridge extension not connected" in last_reason:
                raise RuntimeError(
                    "OpenCLI 未连接到浏览器：请先打开 Chrome，并确认已启用 OpenCLI 扩展、"
                    "该 Chrome 已登录小红书。底层信息：" + last_reason[:160]
                ) from None
            raise RuntimeError(f"OpenCLI 执行失败：{last_reason}")

        if proc is None or proc.returncode != 0:
            raise RuntimeError(f"OpenCLI 执行失败：{last_reason or '无输出'}")

        text = self._decode_output(proc.stdout or b"").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenCLI 返回的不是 JSON：{text[:200]}") from exc
        # 如果外层是字典，尝试取出里面真正的数据列表
        if isinstance(data, dict):
            data = data.get("data", data.get("items", []))
        if not isinstance(data, list):
            data = [data]
        return data

    def search(self, keyword: str, limit: int = 10) -> list[dict]:
        """按关键词搜索笔记，整理成统一结构返回。"""
        rows = self._run(["xiaohongshu", "search", keyword, "--limit", str(limit)])
        records = []
        for row in rows:
            url = row.get("url") or ""
            content_id = self._extract_id(url) if url else str(row.get("id", ""))
            records.append(
                {
                    "content_id": content_id,
                    "url": url,
                    "author": row.get("author") or (row.get("user") or {}).get("name", ""),
                    "title": row.get("title", ""),
                    "body": row.get("desc") or row.get("title", ""),
                    "like_count": self._num(row.get("likes") or row.get("like_count")),
                    "collect_count": self._num(row.get("collect_count") or row.get("collects")),
                    "comment_count": self._num(row.get("comment_count") or row.get("comments")),
                    "share_count": self._num(row.get("share_count")),
                    "published_at": row.get("published_at") or row.get("time", ""),
                    "media_type": "note",
                }
            )
        return records

    def note(self, url: str) -> dict:
        """抓取单篇笔记详情，整理成统一结构返回。"""
        from ..core.timeutil import published_at_from_xhs_url

        rows = self._run(["xiaohongshu", "note", url])
        # 发布时间：优先取返回的时间，否则用链接里的笔记编号推导
        published_at = self._field_value(rows, "time") or self._field_value(rows, "published_at")
        if not published_at:
            published_at = published_at_from_xhs_url(url)
        return {
            "content_id": self._extract_id(url),
            "url": url,
            "author": self._field_value(rows, "author"),
            "title": self._field_value(rows, "title"),
            "body": self._field_value(rows, "content"),
            "like_count": self._num(self._field_value(rows, "likes")),
            "collect_count": self._num(
                self._field_value(rows, "collects") or self._field_value(rows, "collect_count")
            ),
            "comment_count": self._num(
                self._field_value(rows, "comments") or self._field_value(rows, "comment_count")
            ),
            "share_count": 0,
            "published_at": published_at,
            "media_type": "note",
        }

    def comments(self, note_url: str, limit: int = 20, with_replies: bool = True) -> list[dict]:
        """抓取一篇笔记下的评论（可包含楼中楼回复）。

        返回的每条评论都会生成一个自己的编号：顶层评论是"笔记编号_序号"，
        回复是"笔记编号_序号_r序号"，并尽量通过 parent_id 指向它回复的那条。
        """
        note_id = self._extract_id(note_url)
        args = ["xiaohongshu", "comments", note_url, "--limit", str(limit)]
        if with_replies:
            args += ["--with-replies", "true"]
        rows = self._run(args)

        records: list[dict] = []
        top_index = 0    # 顶层评论计数
        reply_index = 0  # 回复计数
        last_id_by_author: dict[str, str] = {}  # 记录每个作者最近一条评论的编号，用于回复挂接

        for row in rows:
            is_reply = str(row.get("is_reply", "")).lower() in ("true", "1")
            reply_to = row.get("reply_to") or ""
            if not is_reply:
                top_index += 1
                comment_id = f"{note_id}_{top_index}"
                parent_id = None
            else:
                reply_index += 1
                comment_id = f"{note_id}_{top_index}_r{reply_index}"
                parent_id = last_id_by_author.get(reply_to)

            author = row.get("author") or (row.get("user") or {}).get("name", "")
            last_id_by_author[author] = comment_id
            records.append(
                {
                    "note_id": note_id,
                    "comment_id": comment_id,
                    "parent_id": parent_id,
                    "author": author,
                    "content": row.get("content") or row.get("text", ""),
                    "like_count": self._num(row.get("like_count") or row.get("likes")),
                    "published_at": row.get("published_at") or row.get("time", ""),
                }
            )
        return records
