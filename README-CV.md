# Qwen3-TTS CustomVoice llama.cpp fork 说明

> 本 fork 为 **Qwen3-TTS CustomVoice 支持** 的长期维护分支。
> 基于 llama.cpp 主线（上游 `ggml-org/llama.cpp`）添加：CustomVoice 预置音色 / 自然语言指示 / 长文本 EOS 修复。
> 中文详细记录（含量化流程、RTF 实测、踩坑）见本文件末尾。

> [!NOTE]
> 本 fork 中除 cherry-pick 的上游 PR #26603 外的所有改动代码，均由
> **DeepSeek-V4-Flash-0731 + QwenPaw** 编写（AI 辅助生成），仅供参考/自用。
> 使用前请自行审查代码，作者不对其正确性与安全性负责。

---

## 一、基线版本

- **基线 commit**：`030ebb558`（llama.cpp 主线 2026-08-10，"Address review comment of PR 25532 (#26852)"）
- **分支**：`cv-26603`（在基线上 cherry-pick 上游 PR #26603 后叠加本 fork 改动）
- **本地工作目录**：`D:\ai\llama.cpp-cv`（与用户定期重下的干净主线 `D:\ai\llama.cpp` 分离）

## 二、分支结构

```
master   —— 跟主线同步（可 fetch upstream 更新）
cv-26603 —— 本 fork 的功能分支：
  5 个 cherry-pick commit（上游 PR #26603：server POST /tts + 流式输出）
  + 1 个本 fork commit（CustomVoice 支持 + EOS 修复 + gen-audio mmproj 修复）
```

## 三、改动内容（相对基线共 +6 commit）

### 3.1 cherry-pick 上游 PR #26603（server TTS 端点）

| commit | 内容 |
|---|---|
| `499e2417a` | mtmd: add audio out stream api（流式输出）|
| `6ac1a33ad` | add /tts endpoint（server POST /tts）|
| `83880383c` | add docs |
| `ae5217d83` | wire up mtmd_helper_model_can_chat |
| `cf5d754e1` | upload speaker_ref via form-data |

- 接口：`POST /tts`，JSON body `input|prompt, lang, speaker_ref_b64, top_k, top_p, repeat_penalty, n_predict(默认512兜底), response_format(wav|pcm), stream`
- **不兼容 OpenAI 库**（非 `/v1/audio/speech`），直接 `requests` 调用
- cherry-pick 冲突处理：`server_output_limits` 保留主线新版 `return {params.n_batch, 1}` + 加 PR 的 mmproj 条件

### 3.2 本 fork commit `0a3706fbd`（CustomVoice 支持 + 修复）

#### CustomVoice 支持（9 文件 +133 行）

| 文件 | 改动 |
|---|---|
| `conversion/qwen3tts.py` | CustomVoice 无 `speaker_encoder_config` → mmproj 只写 GEN 不写 SPKENC；`get_audio_config` 返 talker_config |
| `tools/mtmd/clip.cpp` | `a.gen.code.proj_in` 改可选加载（0.6B 无 small_to_mtp_projection）|
| `tools/mtmd/mtmd-helper.h` | `mtmd_helper_gen_audio_inp` 加 `speaker_id`/`instruct` 字段 + setter |
| `tools/mtmd/mtmd-helper-gen.cpp` | speaker_id 查 `<|spk_xxx|>` embedding 行；instruct 前置插入 prompt |
| `common/arg.cpp` + `common/common.h` | `--tts-speaker-id` / `--tts-instruct` |
| `tools/tts/tts.cpp` | 传新参数 + 停止条件加 is_eos |
| `tools/server/server-context.cpp` | POST /tts JSON 支持 speaker_id/instruct |

#### 长文本 EOS 修复（核心 bug）

- **现象**：长文本生成时模型输出 end-of-speech 也不停，一直生成到 n_predict 上限
- **根因**：llama.cpp 只把文本 EOS（154086）加入 EOG 集合；Qwen3-TTS 停止 token 是 **codec_eos（2150）**（`<|codec_eos_token|>`）——不在 EOG 集合，`llama_vocab_is_eog(vocab, 2150)` 恒 false
- **修复**：新增 `mtmd_helper_gen_audio_is_eos(ctx, token)`（比较缓存的 codec_eos），server slot 循环 + CLI 生成循环都检查
- **验证**：修复前长文本撞上限不停；修复后 Q4 主干 258 帧 / bf16 主干 218 帧正常停

#### gen-audio-only mmproj 加载修复

- `tools/mtmd/mtmd.cpp`：`if (!ctx_v && !ctx_a)` 不认只有 GEN 的 mmproj → 加 `&& !ctx_gen_a`；n_embd 检查防空指针

## 四、编译方法

```bat
cd D:\ai\llama.cpp-cv
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build build --config Release --target llama-tts llama-server -j 8
```

- 环境：VS2022 + CMake + CUDA 13.0（3060 sm_86）
- 首次全量编译 20-40 分钟；之后只编 mtmd/llama-tts/llama-server 很快
- 产物：`build/bin/Release/llama-tts.exe` + `llama-server.exe` + `mtmd.dll`

## 五、使用方法

### CLI

```bat
llama-tts.exe ^
  -m Qwen3-TTS-1.7B-12Hz-CustomVoice-Q4_K_M.gguf ^
  -mm mmproj-Qwen3-TTS-12Hz-1.7b-CustomVoice-Q4_K_M.gguf ^
  -p "你好，我是赛琳娜。" --tts-lang zh --tts-speaker-id serena ^
  --tts-instruct "用特别热情的语气说话" -o out.wav -ngl 99
```

### Server

```bat
llama-server.exe -m ... -mm ... --port 9931 -ngl 99
```

```python
import requests
r = requests.post("http://127.0.0.1:9931/tts", json={
    "input": "你好，我是赛琳娜。",
    "lang": "zh",
    "speaker_id": "serena",
    "instruct": "用特别热情的语气说话",
})
open("out.wav", "wb").write(r.content)
```

### 参数

| 参数 | 说明 |
|---|---|
| `--tts-lang` / `"lang"` | 语言（zh/en/ja/ko/de/fr/ru 等）|
| `--tts-speaker-id` / `"speaker_id"` | CustomVoice 预置音色名（见下表）|
| `--tts-instruct` / `"instruct"` | 自然语言指示（**1.7B 效果最好**；0.6B 也可用但仅强情绪有效，见附录 A5）|
| `--tts-speaker-file` / `"speaker_ref"` | Base 模型参考音频克隆（原功能保留）|

## 六、CustomVoice 预置音色（9 个）

| 说话人 | 音色描述 | 母语 |
|---|---|---|
| Vivian | 明亮的年轻女声 | 中文 |
| Serena | 温暖柔和的年轻女声 | 中文 |
| Uncle_Fu | 成熟男声，音色醇厚 | 中文 |
| Dylan | 充满青春气息的北京男声 | 中文（北京）|
| Eric | 活泼的成都男声 | 中文（四川）|
| Ryan | 富有节奏感的活力男声 | 英文 |
| Aiden | 阳光的美式男声 | 英文 |
| Ono_Anna | 活泼的日语女声 | 日语 |
| Sohee | 温暖的韩语女声 | 韩语 |

## 七、性能实测（3060 Laptop 6GB，server 模式）

| 组合 | 模型大小 | RTF | 听感 |
|---|---|---|---|
| 0.6B 全Q4 | 564MB | 0.34 | 新手播音员（语速偶尔慢）|
| 1.7B 全Q4 | 1.23GB | 0.42 | **自信播音员（主力推荐）** |
| 1.7B Q4+Q8mm | 1.3GB | 0.49 | 同上 |
| 1.7B 双Q8 | 2.1GB | 0.58 | 显存峰值 5940MB 偏危险 |
| 1.7B 全bf16 | 3.9GB | 1.22 | 基准 |

- `-ngl 99` 全 GPU 只要不溢出就是最快；溢出到共享内存（DDR4 带宽）反而变慢
- server 推理后显存不降是正常的（CUDA 内存池复用）

## 八、模型转换与量化（可复用）

### 转换（torch → GGUF）

```bat
cd D:\ai\llama.cpp-cv
set PYTHONPATH=D:\ai\llama.cpp-cv\conversion;D:\ai\llama.cpp-cv\gguf-py
python convert_hf_to_gguf.py <模型目录> --outtype bf16            # 主干
python convert_hf_to_gguf.py <模型目录> --outtype bf16 --mmproj  # mmproj
```

### 主干量化

```bat
llama-quantize.exe in-bf16.gguf out-Q4_K_M.gguf Q4_K_M
```

### mmproj 量化（关键坑）

**code2wav 的 DAC/UP 卷积权重 ncols 不整除 32**（1~16），直接量化失败。必须先扫描生成 tensor-types 文件（36 条规则，这些张量保持 F16）：

```bat
llama-quantize.exe --tensor-type-file mmproj_tensor_types.txt in-mmproj-bf16.gguf out-mmproj-Q4_K_M.gguf Q4_K_M
```

生成 tensor-types 的脚本逻辑（Python）：

```python
from gguf import GGUFReader
r = GGUFReader("mmproj-bf16.gguf")
with open("mmproj_tensor_types.txt", "w") as f:
    for t in r.tensors:
        if int(t.shape[0]) % 32 != 0:
            f.write(f"{t.name}=f16\n")
```

### 产物尺寸

| 模型 | bf16 | Q8_0 | Q4_K_M |
|---|---|---|---|
| 0.6B 主干 | 1155MB | — | 339MB |
| 0.6B mmproj | 545MB | 315MB | 225MB |
| 1.7B 主干 | 3312MB | 1756MB | 988MB |
| 1.7B mmproj | 615MB | 352MB | 245MB |

## 九、兼容性说明

- 所有改动**增量**：`--tts-speaker-file`（Base 克隆）完全保留；转换脚本对 Base 行为不变
- 0.6B 无 `small_to_mtp_projection` → mmproj 缺 proj_in，clip.cpp 已改可选加载
- CustomVoice 无 speaker encoder → mmproj 只含 GEN，mtmd.cpp 已修复加载

## 十、待办

- [ ] 方言支持（Eric 四川话 / Dylan 北京话，torch 有 `spk_is_dialect` 逻辑）暂缓
- [ ] 批量生成脚本（读文本列表 → POST /tts → 收集音频）
- [ ] 主线更新时 rebase（`git fetch upstream && git rebase upstream/master`）

---

## 附录：完整修改记录（中文详细版）

（以下为 2026-08-11 开发全过程的关键决策与踩坑，供日后维护参考）

### A1. 为什么做这个 fork

用户需要 llama.cpp 跑 Qwen3-TTS **CustomVoice** 模型（9 个预置音色 + 语言 + 自然语言指示），
主线只有 Base 模型的 `--tts-speaker-file`（参考音频克隆），不支持预置音色选择。
上游 PR #26603（server TTS）也未合并，故在 fork 中一并 cherry-pick。

### A2. 关键决策

1. **server 优先，CLI 备用**：批量生成 + 接机器人场景
2. **改动全增量**：主线可能长期不合并，fork 当长期工具用
3. **量化方案**：主干 Q4_K_M + mmproj Q4_K_M（conv 保持 F16）为最优平衡
4. **EOS 修复**：识别 codec_eos（2150）而非依赖 llama.cpp 的文本 EOG 集合

### A3. 踩坑记录

- **Python sys.path**：Qwen3 python 环境把旧 `D:\ai\Qwen3\llama.cpp` 注入 sys.path，转换脚本加载到旧版 qwen3tts.py → 用启动脚本在 import 前 `sys.path.insert(0, cv_dir)`
- **MSVC C2059**：`SRV_WRN("...")` 单参数导致宏展开参数不匹配（原作者 gcc/clang 没暴露）→ 加 `"%s"` 格式符
- **mmproj Q8/Q4 量化失败**：conv 权重 ncols 不整除 32 → tensor-types 保护
- **EOS 不停**：根因是 codec_eos 不在 EOG 集合，非量化问题（bf16 长文本也不停）

### A5. 0.6B instruct 实测（2026-08-11 晚）

- **官方 torch API 在 0.6B 上禁用 instruct**（`qwen_tts/inference/qwen3_tts_model.py` L799-800：`if self.model.tts_model_size in "0b6": instruct = None`）
- **但 modeling 层的 instruct 处理是通用的**（无模型大小判断）——架构上支持，官方只是保守禁用
- **本 fork 没模仿 API 层拦截** → 0.6B 上 `--tts-instruct` 照常生效
- **实测（0.6B 全 Q4 + serena）**：happy/angry **正常响应**（真的开心/愤怒）；sad 偏成"小声/麻木"（更像 whisper）；whisper 只让整体变小且集中在开头
- **结论**：0.6B instruct **强情绪有效、微妙情绪弱**；需要细腻情绪控制（悲伤/耳语）用 1.7B

### A4. 音色试听结论（用户反馈，2026-08-11 修正版）

- **初始 4 个组合（A/B/C/D）听感差异很小**
- E（0.6B Q4+Q8mm）那次"助眠主播"（反常的慢和轻柔）是**个例/采样特殊情况**，不是 0.6B Q4 的普遍特征
- **真实规律：听感随规模 + 量化走**：
  - **1.7B 双 F16 = 经验丰富的播音员 + 优质的录音设备**（语速快且清晰）
  - **0.6B 双 Q4 = 新手播音员 + 普通录音设备**（语速偶尔慢、音质稍差）
  - 差异是"扬声器音质对比"级别的细微差别（能听出但小到难描述）
  - **最小的（0.6B 双 Q4）也可接受**
- 结论：**主力用两个规模的 Q4**（1.7B 全 Q4 综合最优 + 0.6B 全 Q4 最省）；torch 模型不大、量化简单，随时可重建
