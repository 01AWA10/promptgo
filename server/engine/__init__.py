"""提示词增强引擎（零依赖、纯规则、可解释）。"""

from .pipeline import MAX_CHARS, META, EnhanceError, enhance, normalize, stream
from .scorer import compare, score

__all__ = ["META", "MAX_CHARS", "EnhanceError", "enhance", "normalize",
           "stream", "compare", "score"]
# 版本唯一来源：HTTP 层直接引用本常量；前端组件是静态单文件，无法 import，
# 由 tests/test_packaging.py 的版本一致性用例守护，防止发版漏改。
__version__ = "1.1.0"
