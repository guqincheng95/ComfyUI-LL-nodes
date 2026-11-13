"""ComfyUI-Manager installation hook; no setup runs during plugin import."""
import platform
import sys
from modules.dlss.runtime_setup import main

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    if platform.system() == 'Windows':
        # Manager invokes this using the active ComfyUI Python. Already-installed
        # bundles are reused; hardware failures are reported without breaking LL.
        code = main()
        if code:
            print('LL 其它节点仍可使用；DLSS5 尚未就绪，请运行 setup_dlss5.bat 查看报告。')
    else:
        print('LL DLSS5 需要 Windows，跳过其运行时部署；其它 LL 节点正常安装。')
