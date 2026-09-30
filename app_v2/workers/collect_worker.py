"""
workers/collect_worker 采集后台任务（占位）。

以后这里会放一个能独立持续运行的任务：
专门负责按计划定时去小红书抓取数据，不依赖网页请求触发。
目前还没有实现，调用 main() 会直接报错提示。
"""


def main() -> None:
    """后台采集任务的入口（尚未实现）。

    本函数现在只是占位，保证项目结构完整。
    后续接入 MySQL 持久化任务队列时再填充具体逻辑。
    """
    raise NotImplementedError("MySQL persistent task worker will be wired in a later phase")