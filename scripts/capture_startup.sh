#!/usr/bin/env bash
# Run on the specified target host. Does not install or alter dependencies.
set -euo pipefail
plugin_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$plugin_dir/acceptance-output"
source /root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/activate
cd /root/autodl-tmp/AI_Workspace/ComfyUI
python -u main.py --listen 0.0.0.0 --port 6006 2>&1 | tee "$plugin_dir/acceptance-output/startup.log"
