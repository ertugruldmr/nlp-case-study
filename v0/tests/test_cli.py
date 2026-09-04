import ftlink.cli as cli


def test_locate_failure_exits_clean(monkeypatch, capsys):
    # a misconfigured footnote number must fail loudly but WITHOUT a raw traceback
    def boom(settings):
        raise RuntimeError("footnote 99 not found (toc and scan both failed)")

    monkeypatch.setattr(cli, "run", boom)
    rc = cli.main(["run", "--config", "configs/default.yaml"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "error: footnote 99 not found" in err
