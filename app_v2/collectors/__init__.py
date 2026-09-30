"""
collectors 抓取模块的入口。

这个模块负责挑选"用哪种方式去抓取小红书数据"。
目前只实现了 OpenCLI 这种抓取方式（复用 Chrome 浏览器的登录状态去抓）。
其他抓取方式以后可以继续往这里加，不影响别的地方调用。
"""
from .base import BaseCollector
from .opencli import OpencliCollector


def get_collector() -> BaseCollector:
    """返回当前要使用的抓取器。

    现在固定返回 OpenCLI 抓取器，以后想换成别的抓取方式，
    只需要改这里，其他调用方都不用动。
    """
    return OpencliCollector()