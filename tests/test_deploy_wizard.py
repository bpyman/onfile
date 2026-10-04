"""The go-live wizard's non-interactive paths (ticket 10, ADR 0006 "Hosting").

The interactive stages open dashboards and wait on a person, so only the parts a
machine can drive are run here: ``--help``, and ``--check``, which re-verifies a
saved deploy. In-process APIs stand in for the hosts: one with the proxy token
plays Render, and one without it plays the Vercel proxy, which adds the token
before the call reaches Python.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from api_server import serve
from financial_analyst_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]
WIZARD = ROOT / "scripts" / "deploy_wizard.sh"
DEPLOY_NOTES = ROOT / "docs" / "deploy.md"
TOKEN = "wizard-secret"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("curl") is None,
    reason="the wizard needs bash and curl",
)


def _api(tmp_path: Path, name: str, *, token: str, public_demo: bool) -> Iterator[str]:
    from financial_analyst_agent.api import create_app

    settings = Settings(
        app_mode="recorded",
        public_demo=public_demo,
        api_proxy_token=token,
        _env_file=None,  # type: ignore[call-arg]
    )
    yield from serve(create_app(settings, store_root=tmp_path / name))


@pytest.fixture
def render_api(tmp_path: Path) -> Iterator[str]:
    """The API as Render runs it: public demo, refuses calls without the token."""
    yield from _api(tmp_path, "render", token=TOKEN, public_demo=True)


@pytest.fixture
def open_api(tmp_path: Path) -> Iterator[str]:
    """An API with no token: what the Vercel proxy looks like from outside."""
    yield from _api(tmp_path, "open", token="", public_demo=False)


def _run(
    *args: str, env_file: Path | None = None, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"API_PROXY_TOKEN", "RENDER_API_URL", "VERCEL_URL", "SMOKE_PROXY_TOKEN"}
    }
    env["WAKE_SECONDS"] = "5"
    env.update(extra_env or {})
    if env_file is not None:
        env["DEPLOY_ENV_FILE"] = str(env_file)
    return subprocess.run(
        ["bash", str(WIZARD), *args],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        timeout=240,
        check=False,
    )


def _saved(tmp_path: Path, **values: str) -> Path:
    env_file = tmp_path / ".env.deploy"
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    return env_file


def test_wizard_is_checked_in_executable_and_linked_from_the_deploy_notes() -> None:
    assert WIZARD.is_file()
    assert os.access(WIZARD, os.X_OK)
    assert "scripts/deploy_wizard.sh" in DEPLOY_NOTES.read_text(encoding="utf-8")
    syntax = subprocess.run(["bash", "-n", str(WIZARD)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr


def test_help_names_every_stage_and_where_values_are_kept() -> None:
    result = _run("--help")

    assert result.returncode == 0, result.stderr
    for stage in (
        "proxy token",
        "Render",
        "Auto-Deploy",
        "Root Directory",
        "Deploy Hook",
        "API_ORIGIN",
        "health",
        "browser check",
    ):
        assert stage in result.stdout, stage
    assert ".env.deploy" in result.stdout
    assert "--check" in result.stdout


def test_saved_values_stay_out_of_the_env_file_the_api_reads() -> None:
    """A proxy token in ``.env`` would make the local API refuse the local window."""
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", ".env.deploy"], cwd=ROOT, check=False
    )
    assert ignored.returncode == 0, ".env.deploy must be gitignored"
    text = WIZARD.read_text(encoding="utf-8")
    stages = text.split("# STAGES", 1)[1]
    assert 'ENV_FILE="${DEPLOY_ENV_FILE:-.env.deploy}"' in stages


def test_unknown_option_is_refused() -> None:
    result = _run("--bogus")

    assert result.returncode == 2
    assert "Usage" in result.stderr


def test_check_without_a_saved_deploy_says_to_run_the_wizard(tmp_path: Path) -> None:
    result = _run("--check", env_file=tmp_path / ".env.deploy")

    assert result.returncode == 1
    assert "run scripts/deploy_wizard.sh first" in result.stdout


def test_check_passes_when_only_the_proxy_reaches_the_api(
    tmp_path: Path, render_api: str, open_api: str
) -> None:
    env_file = _saved(
        tmp_path, RENDER_API_URL=render_api, VERCEL_URL=f"{open_api}/", API_PROXY_TOKEN=TOKEN
    )

    result = _run("--check", env_file=env_file)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Render refuses a call without the token (401)" in result.stdout
    assert "guided story through the Vercel proxy" in result.stdout
    assert "✗" not in result.stdout


def test_check_fails_when_render_answers_without_the_token(tmp_path: Path, open_api: str) -> None:
    env_file = _saved(tmp_path, RENDER_API_URL=open_api, VERCEL_URL=open_api, API_PROXY_TOKEN=TOKEN)

    result = _run("--check", env_file=env_file)

    assert result.returncode == 1
    assert "✗ Render refuses a call without the token" in result.stdout
    assert "answered 200" in result.stdout


def test_check_fails_when_the_saved_token_is_not_renders(
    tmp_path: Path, render_api: str, open_api: str
) -> None:
    env_file = _saved(
        tmp_path, RENDER_API_URL=render_api, VERCEL_URL=open_api, API_PROXY_TOKEN="stale"
    )

    result = _run("--check", env_file=env_file)

    assert result.returncode == 1
    assert "✗ guided story on Render with the saved token" in result.stdout


def test_check_fails_when_the_window_cannot_reach_the_api(tmp_path: Path, render_api: str) -> None:
    env_file = _saved(
        tmp_path,
        RENDER_API_URL=render_api,
        VERCEL_URL="http://127.0.0.1:9",
        API_PROXY_TOKEN=TOKEN,
    )

    result = _run("--check", env_file=env_file)

    assert result.returncode == 1
    assert "✗ health check through the Vercel proxy" in result.stdout


def test_check_passes_the_token_to_the_smoke_script_in_the_environment() -> None:
    """On the command line, the token would show in ``ps`` while the story runs."""
    stages = WIZARD.read_text(encoding="utf-8").split("# STAGES", 1)[1]

    assert "--proxy-token" not in stages
    assert 'SMOKE_PROXY_TOKEN="${2:-}"' in stages


def test_check_sends_no_token_through_the_proxy_even_if_one_is_exported(
    tmp_path: Path, render_api: str
) -> None:
    """A token in the shell must not stand in for the one the Vercel proxy adds."""
    env_file = _saved(
        tmp_path, RENDER_API_URL=render_api, VERCEL_URL=render_api, API_PROXY_TOKEN=TOKEN
    )

    result = _run("--check", env_file=env_file, extra_env={"SMOKE_PROXY_TOKEN": TOKEN})

    assert result.returncode == 1
    assert "✓ guided story on Render with the saved token" in result.stdout
    assert "✗ guided story through the Vercel proxy" in result.stdout
    assert "401" in result.stdout


def test_every_stage_runs_and_the_count_matches_the_help() -> None:
    text = WIZARD.read_text(encoding="utf-8")
    stages = text.split("# STAGES", 1)[1]
    defined = re.findall(r"^(stage_\w+)\(\) \{", stages, flags=re.MULTILINE)
    called = re.findall(r"^(stage_\w+)$", stages, flags=re.MULTILINE)
    total = re.search(r"^TOTAL_STAGES=(\d+)$", stages, flags=re.MULTILINE)

    assert called == defined
    assert total is not None and int(total.group(1)) == len(called)
    assert f"in {len(called)} stages" in _run("--help").stdout
    assert called.index("stage_vercel_hook") == called.index("stage_vercel_import") + 1


def _functions(*names: str) -> str:
    """The named shell functions, cut out of the wizard to run on their own."""
    text = WIZARD.read_text(encoding="utf-8")
    bodies = []
    for name in names:
        match = re.search(rf"^{name}\(\) \{{.*?^\}}$", text, flags=re.MULTILINE | re.DOTALL)
        if match is None:  # a one-line function
            match = re.search(rf"^{name}\(\) \{{.*\}}$", text, flags=re.MULTILINE)
        assert match is not None, name
        bodies.append(match.group(0))
    return "\n".join(bodies)


def _bash(script: str, *, path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = f"{path}{os.pathsep}{env['PATH']}"
    prelude = "\n".join(
        [
            "set -euo pipefail",
            'GREEN=""; RESET=""; DIM=""; YELLOW=""',
            "SKIPPED=(); WRITTEN_SECRET=()",
            "",
        ]
    )
    return subprocess.run(
        ["bash", "-c", prelude + script],
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def _fake_gh(tmp_path: Path, *, signed_in: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    record = tmp_path / "gh.log"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'if [[ "$1 $2" == "auth status" ]]; then exit {0 if signed_in else 1}; fi\n'
        f'printf \'%s|%s\\n\' "$*" "$(cat)" >> {shlex.quote(record.as_posix())}\n'
    )
    gh.chmod(0o755)
    return bin_dir


def test_hook_secret_is_set_with_gh_from_stdin(tmp_path: Path) -> None:
    bin_dir = _fake_gh(tmp_path, signed_in=True)
    script = _functions("note", "warn", "set_secret", "store_secret")
    script += '\nstore_secret VERCEL_DEPLOY_HOOK_URL "https://hook.example/abc"'

    result = _bash(script, path=str(bin_dir))

    assert result.returncode == 0, result.stderr
    assert "set GitHub secret VERCEL_DEPLOY_HOOK_URL" in result.stdout
    record = (tmp_path / "gh.log").read_text()
    assert record == "secret set VERCEL_DEPLOY_HOOK_URL|https://hook.example/abc\n"


def test_hook_secret_without_gh_says_where_to_paste_it_on_github(tmp_path: Path) -> None:
    bin_dir = _fake_gh(tmp_path, signed_in=False)
    script = _functions("note", "warn", "set_secret", "store_secret")
    script += (
        '\nREPO_SLUG=owner/repo\nstore_secret VERCEL_DEPLOY_HOOK_URL "https://hook.example/abc"'
    )
    script += '\nprintf "skipped: %s\\n" "${SKIPPED[@]}"'

    result = _bash(script, path=str(bin_dir))

    assert result.returncode == 0, result.stderr
    assert "owner/repo → Settings → Secrets and variables → Actions" in result.stdout
    assert "name VERCEL_DEPLOY_HOOK_URL" in result.stdout
    assert "skipped: GitHub secret VERCEL_DEPLOY_HOOK_URL" in result.stdout
    assert "https://hook.example/abc" not in result.stdout


@pytest.fixture
def hook_server() -> Iterator[tuple[str, list[tuple[str, str]]]]:
    calls: list[tuple[str, str]] = []

    class Hook(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the http.server hook name
            calls.append(("POST", self.path))
            body = b'{"job":{"id":"j1","state":"PENDING"}}'
            self.send_response(201)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Hook)
    runner = threading.Thread(target=server.serve_forever, daemon=True)
    runner.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        runner.join(timeout=10)


def test_hook_call_posts_without_putting_the_url_on_the_command_line(
    hook_server: tuple[str, list[tuple[str, str]]],
) -> None:
    base, calls = hook_server
    post_hook = _functions("post_hook")

    result = _bash(post_hook + f'\npost_hook "{base}/v1/integrations/deploy/prj_1/k3y"')

    assert result.returncode == 0, result.stderr
    assert calls == [("POST", "/v1/integrations/deploy/prj_1/k3y")]
    assert '"job"' in result.stdout
    assert "--config -" in post_hook
    assert '"$1"' not in post_hook.split("| curl", 1)[1]
