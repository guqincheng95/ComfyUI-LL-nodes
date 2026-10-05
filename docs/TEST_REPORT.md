# v0.1.0 测试报告

日期：2026-10-06（Asia/Shanghai）。开发执行环境：Python 3.12.14。

## 已执行

`python -m unittest discover -s tests -v`：8 个测试方法全部通过，详见 [原始日志](unit-tests.log)。

| 需求案例 | 输出 | 结果 |
|---|---|---|
| Z-Image / 9:16 / Quality / Portrait | 864 × 1536 | 通过 |
| Z-Image / 16:9 / Quality / Landscape | 1536 × 864 | 通过 |
| Z-Image / 3:4 / Max / Portrait | 1536 × 2048 | 通过 |
| Z-Image / 4:3 / Fast / Landscape | 1024 × 768 | 通过 |
| Custom / 1376 × 768 / Portrait | 1376 × 768 | 通过，忽略方向 |

- 全部 3 模型 × 5 比例 × 3 档 × 3 方向，共 135 组输出与独立尺寸计算基准一致，且均为 32 的倍数。
- Custom 非对齐值 1377 × 769、极小正整数及大于常见下游限制的值均原样返回；非法类型与非正整数明确报错。
- 模型表独立；损坏预设能被发现；节点包可通过 importlib 导入；注册名、控件默认值和输出类型符合要求。
- 示例 JSON 可解析，宽高连线结构检查通过。尚未在真实前端打开。
- Python 编译检查、启动脚本 Bash 语法检查、验收工具 CLI 加载通过。

## 未执行，不得视为通过

| 验收项 | 状态与原因 |
|---|---|
| 安装到指定 ComfyUI 路径 | 待目标机；本环境不存在 /root/autodl-tmp/AI_Workspace/ComfyUI |
| ComfyUI 0.38.0 启动及 Custom Nodes 导入日志 | 待目标机 |
| Python 3.12.3 / Torch 2.9.1+cu130 / RTX 4090 48GB 兼容实测 | 待目标机；本环境不同 |
| 节点菜单显示截图 | 待真实 UI |
| 示例工作流执行及 PNG 输出尺寸 | 待运行 scripts/verify_server.py |

**结论：本期全部节点功能实现且单元测试通过；目标环境的最终验收尚未完成。**
没有安装或改动 Torch/CUDA/Triton/SageAttention，未安装 xformers、flash-attn 或任何大型依赖。
