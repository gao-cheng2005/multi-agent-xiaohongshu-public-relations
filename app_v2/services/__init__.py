"""
services 业务逻辑层。

这一层放着"具体业务怎么做"的代码：
- 怎么采集（collect_service）
- 怎么分析情感、生成预警和方案（data_access_service、alert_service 等）
- 怎么统计报表（analytics_service、report_service）
- 怎么维护关键词、系统配置等（keyword_service、system_config_service）

它向下依赖 repositories 去读写数据库，向上被 controllers 调用。
"""