# -*- coding: utf-8 -*-
"""在 cv fork 目录下运行 convert_hf_to_gguf.py，确保加载 cv 版 conversion 包。
用法: python run_convert_cv.py <模型目录> [--mmproj] [--outtype bf16]
"""
import sys, os

CV_DIR = r"D:\ai\llama.cpp-cv"
os.chdir(CV_DIR)
sys.path.insert(0, CV_DIR)

from conversion import qwen3tts
print("conversion 来源:", qwen3tts.__file__)

# 解析参数
args = sys.argv[1:]
model_dir = args[0]
extra = args[1:]

sys.argv = ["convert_hf_to_gguf.py", model_dir] + extra
import runpy
runpy.run_path(os.path.join(CV_DIR, "convert_hf_to_gguf.py"), run_name="__main__")
