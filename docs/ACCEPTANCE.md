# 目标环境验收

本文件是操作步骤，不代表已经在目标机器执行。

## 1. 安装并记录

在目标机器终端运行，安装路径已存在则使用更新命令，不重复克隆：

```bash
source /root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/activate
cd /root/autodl-tmp/AI_Workspace/ComfyUI
# 首次安装：
git clone https://github.com/guqincheng95/ComfyUI-ResolutionPreset.git custom_nodes/ComfyUI-ResolutionPreset
cd custom_nodes/ComfyUI-ResolutionPreset
mkdir -p acceptance-output
{
  date -Iseconds
  pwd
  git rev-parse HEAD
  python --version
  python -m unittest discover -s tests -v
} 2>&1 | tee acceptance-output/install.log
```

没有 pip 命令，不重装环境。已有服务占用 6006 时先在原管理终端正常停止或直接复用，不盲目杀进程。

## 2. 留存启动日志

插件目录运行：

```bash
bash scripts/capture_startup.sh
```

保持此终端运行。`acceptance-output/startup.log` 应包含本插件的 Custom Nodes 导入行；检查无本插件 IMPORT FAILED、ModuleNotFoundError 或相关 Traceback。其他插件错误应单独记录，不能删掉日志后声称整个环境无错误。

## 3. 真实服务与图像尺寸验收

另开终端，激活同一环境并进入插件目录：

```bash
python scripts/verify_server.py --url http://127.0.0.1:6006
```

脚本查询实际 `/object_info/ResolutionPreset` 注册信息、记录 `/system_stats`，提交十组真实工作流，读取执行历史并验证输出 PNG 的宽高。包含需求五例、第五种比例、另两类模型、强制横向和非 32 对齐 Custom。
失败退出非零，保留失败原因，**没有 mock 服务或跳过即成功的逻辑**。
会在 ComfyUI output/ResolutionPreset_acceptance 内保存十张纯色测试图；本地 acceptance-output 同时保存报告、图像、注册信息、系统信息和历史。大队列时可增加 `--timeout 600`。

## 4. UI 验收

浏览器刷新 ComfyUI，搜索 Resolution Preset。截图应显示节点菜单结果和节点本身。
导入 `examples/minimal_workflow.json`，确认宽、高两根连线，依次切换五种比例并执行。
将截图保存为 `acceptance-output/node-menu.png`。API 注册成功只能证明后端注册，不可替代菜单截图。

## 完成条件

安装日志、启动日志、菜单截图、`report.json` 全部齐备且目标环境版本核对通过后，才把 TEST_REPORT.md 的目标环境项标为通过。当前开发容器无法访问目标机器，不提供伪造的安装/启动成功日志。
