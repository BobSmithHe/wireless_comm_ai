"""
Code Executor — safe Python code execution via Docker sandbox (or local subprocess).
"""
import subprocess
import sys
import tempfile
import os
import re
import base64
import asyncio
import shutil

from ...config.settings import get_settings
from ..observability import observe

settings = get_settings()

IMAGE_CAPTURE_SUFFIX = """
try:
    import base64 as _b64, io as _io
    import matplotlib.pyplot as _plt
    _img_files = []
    for _fn in _plt.get_fignums():
        _fig = _plt.figure(_fn)
        _buf = _io.BytesIO()
        _fig.savefig(_buf, format='png', dpi=80, bbox_inches='tight')
        _buf.seek(0)
        with open('/tmp/__img_' + str(_fn) + '.png', 'wb') as _f:
            _f.write(_buf.read())
        _img_files.append('__img_' + str(_fn) + '.png')
        _plt.close(_fig)
    if _img_files:
        print('__IMGFILES__:' + '|'.join(_img_files))
except Exception:
    pass
"""

SANDBOX_IMAGE = "wcai-sandbox"

# Minimal safe env — no secrets, no user home, no network config
SANDBOX_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "PYTHONIOENCODING": "utf-8",
    "HOME": "/tmp",
    "MPLBACKEND": "Agg",
}


def _decode_output(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")


class CodeExecutor:
    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or settings.code_exec_timeout
        self.mode = settings.sandbox_mode  # "docker" | "subprocess"

    @observe(as_type="tool")
    async def execute(self, code: str, language: str = "python") -> dict:
        if language != "python":
            return {"stdout": "", "stderr": f"Language '{language}' not supported yet.", "exit_code": -1, "images": []}

        if self.mode == "docker":
            return await self._execute_in_docker(code)
        return await self._execute_local(code)

    # ------------------------------------------------------------------
    # Docker sandbox (production)
    # ------------------------------------------------------------------

    async def _execute_in_docker(self, code: str) -> dict:
        wrapped = self._wrap_code(code)

        try:
            def _run():
                return subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network=none",
                        f"--memory={settings.code_exec_max_memory}",
                        "--cpus=1",
                        "--read-only",
                        "--tmpfs=/tmp:size=128m",
                        "--user=65534",
                        SANDBOX_IMAGE,
                        "python", "-c", wrapped,
                    ],
                    capture_output=True,
                    timeout=self.timeout,
                )

            result = await asyncio.to_thread(_run)
            return self._parse_result(result.stdout, result.stderr, result.returncode, tempfile.gettempdir())

        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            return {"stdout": "", "stderr": f"Execution timed out after {self.timeout}s", "exit_code": -1, "images": []}
        except FileNotFoundError:
            return {"stdout": "", "stderr": "Docker not found. Build sandbox image first: docker build -t wcai-sandbox ./sandbox", "exit_code": -1, "images": []}

    # ------------------------------------------------------------------
    # Local subprocess (dev fallback)
    # ------------------------------------------------------------------

    async def _execute_local(self, code: str) -> dict:
        wrapped = self._wrap_code(code)
        tmpdir = tempfile.mkdtemp()
        script_path = os.path.join(tmpdir, "script.py")

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(wrapped)

        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["MPLBACKEND"] = "Agg"

            def _run():
                p = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    timeout=self.timeout,
                    cwd=tmpdir,
                    env=env,
                )
                return p.stdout, p.stderr, p.returncode

            result = await asyncio.to_thread(_run)
            return self._parse_result(result.stdout, result.stderr, result.returncode, tmpdir)

        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            return {"stdout": "", "stderr": f"Execution timed out after {self.timeout}s", "exit_code": -1, "images": []}
        except FileNotFoundError:
            return {"stdout": "", "stderr": "Python interpreter not found.", "exit_code": -1, "images": []}
        finally:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wrap_code(self, code: str) -> str:
        return (
            "import sys, warnings\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "sys.stderr.reconfigure(encoding='utf-8')\n"
            "warnings.filterwarnings('ignore', message='.*non-interactive.*')\n"
            "warnings.filterwarnings('ignore', message='.*cannot be shown.*')\n"
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as _plt_setup\n"
            "_plt_setup.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Noto Sans SC', 'DejaVu Sans']\n"
            "_plt_setup.rcParams['axes.unicode_minus'] = False\n"
            "del _plt_setup\n"
            + code
            + "\n" + IMAGE_CAPTURE_SUFFIX
        )

    def _parse_result(self, stdout: bytes, stderr: bytes, returncode: int, tmpdir: str) -> dict:
        stdout_str = _decode_output(stdout)[:20000]
        stderr_str = _decode_output(stderr)[:10000]

        images = []
        clean_stdout = stdout_str
        m = re.search(r"__IMGFILES__:([\w_.|]+)", stdout_str)
        if m:
            for fname in m.group(1).split("|"):
                fpath = os.path.join(tmpdir, fname)
                try:
                    with open(fpath, "rb") as imgf:
                        images.append(base64.b64encode(imgf.read()).decode())
                except Exception:
                    pass
            clean_stdout = stdout_str[: m.start()] + stdout_str[m.end():]

        return {
            "stdout": clean_stdout.strip(),
            "stderr": stderr_str.strip(),
            "exit_code": returncode or 0,
            "images": images,
        }
