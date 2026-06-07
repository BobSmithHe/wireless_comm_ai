"""
Code Executor — safe Python code execution via Docker sandbox (or local subprocess).
"""
import subprocess
import sys
import tempfile
import os
import re
import asyncio
import shutil

from ...core.config import get_settings
from ..observability import observe

settings = get_settings()

IMAGE_CAPTURE_SUFFIX = """
try:
    import base64 as _b64, io as _io
    import matplotlib.pyplot as _plt
    _img_payloads = []
    for _fn in _plt.get_fignums():
        _fig = _plt.figure(_fn)
        _buf = _io.BytesIO()
        _fig.savefig(_buf, format='png', dpi=80, bbox_inches='tight')
        _buf.seek(0)
        _img_payloads.append(_b64.b64encode(_buf.read()).decode())
        _plt.close(_fig)
    if _img_payloads:
        print('__IMAGES_B64__:' + '||'.join(_img_payloads))
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
            return self._parse_result(result.stdout, result.stderr, result.returncode)

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
            return self._parse_result(result.stdout, result.stderr, result.returncode)

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
            "import sys, os, warnings\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "sys.stderr.reconfigure(encoding='utf-8')\n"
            "warnings.filterwarnings('ignore', message='.*non-interactive.*')\n"
            "warnings.filterwarnings('ignore', message='.*cannot be shown.*')\n"
            "warnings.filterwarnings('ignore', category=UserWarning)\n"
            "os.environ.setdefault('MPLCONFIGDIR', '/tmp')\n"
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as _plt_setup\n"
            "import matplotlib.font_manager as _fm\n"
            "_avail = {f.name for f in _fm.fontManager.ttflist}\n"
            "_cjk_candidates = ['WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'SimHei', 'Microsoft YaHei', 'WenQuanYi Zen Hei', 'Noto Sans SC']\n"
            "_cjk_font = next((f for f in _cjk_candidates if f in _avail), None)\n"
            "if _cjk_font:\n"
            "    _plt_setup.rcParams['font.sans-serif'] = [_cjk_font, 'DejaVu Sans']\n"
            "else:\n"
            "    _plt_setup.rcParams['font.sans-serif'] = ['DejaVu Sans']\n"
            "_plt_setup.rcParams['axes.unicode_minus'] = False\n"
            "del _plt_setup, _fm, _cjk_candidates, _cjk_font, _avail\n"
            + code
            + "\n" + IMAGE_CAPTURE_SUFFIX
        )

    def _parse_result(self, stdout: bytes, stderr: bytes, returncode: int) -> dict:
        # Decode full stdout first — images get extracted before truncation
        stdout_full = _decode_output(stdout)
        stderr_str = _decode_output(stderr)[:10000]

        images = []
        clean_stdout = stdout_full
        m = re.search(r"__IMAGES_B64__:([A-Za-z0-9+/=|]+)", stdout_full)
        if m:
            images = [b64 for b64 in m.group(1).split("||") if b64]
            clean_stdout = stdout_full[: m.start()] + stdout_full[m.end():]

        # Truncate user-visible output only (images already extracted above)
        clean_stdout = clean_stdout[:20000]
        return {
            "stdout": clean_stdout.strip(),
            "stderr": stderr_str.strip(),
            "exit_code": returncode or 0,
            "images": images,
        }
