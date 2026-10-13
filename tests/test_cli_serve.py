"""CLI: ``megatool serve`` must announce a non-loopback bind.

The API has no authentication. On ``127.0.0.1`` the journal, portfolio and
transcribed PDF records are reachable only by the owner, which is the intended
deployment. ``--host 0.0.0.0`` (or ``MEGATOOL_HOST=``) changes that silently,
so the command is required to say so out loud.

``uvicorn`` is imported lazily *inside* ``_cmd_serve`` and only used to start
the blocking server, so these tests substitute a fake module: nothing listens
on a socket and no port is bound.
"""

from __future__ import annotations

import argparse
import sys
import types

import pytest

from megatool.cli import _cmd_serve


@pytest.fixture
def fake_uvicorn(monkeypatch):
    """Replace uvicorn so _cmd_serve records its call instead of serving."""
    started: dict[str, object] = {}
    mod = types.ModuleType("uvicorn")

    def _run(app, host=None, port=None, log_level=None):  # noqa: ANN001
        started.update(app=app, host=host, port=port, log_level=log_level)

    mod.run = _run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", mod)
    return started


def _ns(host: str | None) -> argparse.Namespace:
    return argparse.Namespace(host=host, port=8710, log_level="warning")


def test_serving_on_a_non_loopback_host_warns_about_no_auth(fake_uvicorn, capsys):
    """Binding past loopback exposes private records: say it, don't hide it.

    Journal entries, portfolio positions and transcribed records are served to
    whoever reaches the socket. This asserts the warning actually appears on
    stderr and names the problem, and that the server still starts (a warning,
    not a block: a firewall or SSH tunnel is a legitimate reason).
    """
    assert _cmd_serve(_ns("0.0.0.0")) == 0

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "NO authentication" in err
    assert "journal" in err and "portfolio" in err
    # It warns rather than refuses.
    assert fake_uvicorn["host"] == "0.0.0.0"


def test_serving_on_loopback_stays_quiet(fake_uvicorn, capsys):
    """The default bind is safe by construction and must not cry wolf."""
    assert _cmd_serve(_ns("127.0.0.1")) == 0

    captured = capsys.readouterr()
    assert "WARNING" not in captured.err
    assert "WARNING" not in captured.out
    assert fake_uvicorn["host"] == "127.0.0.1"


def test_an_unset_host_falls_back_to_the_config_default(fake_uvicorn, capsys):
    """``--host`` omitted means config.HOST, and the warning still applies."""
    from megatool.config import HOST

    assert _cmd_serve(_ns(None)) == 0
    assert fake_uvicorn["host"] == HOST

    warned = "WARNING" in capsys.readouterr().err
    assert warned == (HOST not in ("127.0.0.1", "localhost", "::1"))
