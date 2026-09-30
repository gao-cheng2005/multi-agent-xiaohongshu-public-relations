import sys
from pathlib import Path

# 把项目根目录加到模块搜索路径，方便测试代码 import app_v2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
