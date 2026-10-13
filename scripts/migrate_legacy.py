"""Move recognized legacy installations out of custom_nodes; never delete them."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil

LEGACY = {
    'ComfyUI-ResolutionPreset': 'ResolutionPreset',
    'ComfyUI-ResolutionPreset-main': 'ResolutionPreset',
    'ComfyUI-PhotoFinish': 'AIVisualPhotoFinish',
    'ComfyUI-PhotoFinish-main': 'AIVisualPhotoFinish',
}


def migrate(root, apply=False):
    root = Path(root).resolve()
    custom_nodes = root.parent
    if custom_nodes.name != 'custom_nodes':
        raise ValueError('请将节点库安装在 ComfyUI/custom_nodes 下再运行迁移。')
    pending = []
    for name, marker in LEGACY.items():
        source = custom_nodes / name
        if source == root or not source.exists():
            continue
        init = source / '__init__.py'
        if source.is_symlink() or not init.is_file() or marker not in init.read_text(encoding='utf-8'):
            raise ValueError(f'无法确认旧插件身份，请手动检查：{source}')
        pending.append(source)
    if not apply:
        return [str(source) for source in pending]
    if not pending:
        return []
    backup = custom_nodes.parent / 'll-nodes-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    results = []
    for source in pending:
        destination = backup / source.name
        shutil.move(str(source), str(destination))
        results.append(str(destination))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='将已确认的旧目录移到 ComfyUI/ll-nodes-backups')
    args = parser.parse_args()
    try:
        results = migrate(Path(__file__).resolve().parents[1], args.apply)
        print('旧版已备份（重启后生效）：' if args.apply else '仅预览；加 --apply 才执行：')
        print('\n'.join(results) if results else '无须迁移。')
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
