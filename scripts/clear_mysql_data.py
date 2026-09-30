# -*- coding: utf-8 -*-
"""
scripts/clear_mysql_data 清空 MySQL 业务库（yuqing_pr）全部数据。

安全边界：
- 清空 10 张业务表的全部行：contents/comments/analyses/alerts/response_plans/
  issue_tags/product_reports/brands/keywords/system_configs；
- 保留 alembic_version（数据库结构版本标记，删了会导致下次启动迁移报错）；
- 只清数据，保留表结构（不 DROP 表）；
- 不可逆，如需备份请先执行 mysqldump。

清空后应用可自行恢复的部分：
- brands：首次写数据时自动重建默认品牌；
- system_configs：大模型回退 .env 默认模型；
- keywords：下次按关键词采集时自动重建。

用法（code 目录下，用项目 conda 环境）：
    python scripts/clear_mysql_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 保证能 import 到 app_v2（从此处自动读取 .env 连接配置）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql

from app_v2.core.settings import settings

# 待清空表（alembic_version 不在此列，必须保留）
TABLES = (
    "product_reports",
    "issue_tags",
    "response_plans",
    "alerts",
    "analyses",
    "comments",
    "contents",
    "keywords",
    "system_configs",
    "brands",
)


def main() -> None:
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
    )
    try:
        # --- 第一步：预告将清空的表与行数 ---
        with conn.cursor() as cur:
            print(f"数据库：{settings.mysql_database}（alembic_version 保留）")
            for t in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                print(f"  待清空 {t}: {cur.fetchone()[0]} 行")

        # --- 第二步：关闭外键检查，按序清空 ---
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for t in TABLES:
                cur.execute(f"TRUNCATE TABLE `{t}`")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()

        # --- 第三步：清空后验证 ---
        with conn.cursor() as cur:
            bad = []
            print("\n清空后验证：")
            for t in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                n = cur.fetchone()[0]
                print(f"  {t}: {n} 行")
                if n:
                    bad.append(t)
            cur.execute("SELECT COUNT(*) FROM `alembic_version`")
            print(f"  alembic_version: {cur.fetchone()[0]} 行（保留）")
        if bad:
            print(f"\n[警告] 以下表未清空：{bad}")
        else:
            print("\n完成：业务数据已清空，表结构保留。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()