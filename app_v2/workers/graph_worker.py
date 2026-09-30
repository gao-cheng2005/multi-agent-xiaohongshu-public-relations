"""
workers/graph_worker 图计算后台任务（占位）。

以后这里会放一个独立运行的任务：
把采集到的内容送入知识图谱（例如带记忆的多步分析流程）。
目前还没有实现，调用 main() 会直接报错提示。
"""


def main() -> None:
    """图计算后台任务的入口（尚未实现）。

    本函数现在只是占位，保证项目结构完整。
    后续接入 MySQL 持久化任务队列时再填充具体逻辑。
    """
    raise NotImplementedError("MySQL persistent task worker will be wired in a later phase")