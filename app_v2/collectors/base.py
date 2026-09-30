"""抓取器的统一接口。

"抓取器"就是负责去平台（小红书）拿数据的东西。这个文件给所有抓取器定了一个统一要求：
不管以后用什么方式抓数据，都必须提供三个能力——搜索笔记、抓单篇笔记、抓评论。

这样上层业务代码不用关心具体用什么抓，只管调用这三个方法即可。
"""

from abc import ABC, abstractmethod


class BaseCollector(ABC):
    """所有抓取器的标准模板。

    它不实现功能，只规定"规矩"：谁想当抓取器，就必须实现下面三个方法。
    """

    @abstractmethod
    def search(self, keyword: str, limit: int = 10) -> list[dict]:
        """按关键词搜索笔记，返回笔记列表。"""

    @abstractmethod
    def note(self, url: str) -> dict:
        """抓取单篇笔记的详细信息。"""

    @abstractmethod
    def comments(self, note_url: str, limit: int = 20) -> list[dict]:
        """抓取某篇笔记下的评论。"""
