import pytest

from nostr_sdk_wrapper.cli import main
from nostr_sdk_wrapper.identity import load_identity


def test_init_then_whoami(home, capsys):
    main(["init", "--name", "alice", "--role", "client"])
    keys = load_identity(home / "alice" / "identity.json")
    assert keys.public_key().to_bech32() in capsys.readouterr().out

    main(["--name", "alice", "whoami"])
    out = capsys.readouterr().out
    assert keys.public_key().to_bech32() in out
    assert keys.public_key().to_hex() in out
    assert "nsec" not in out

    main(["whoami", "--name", "alice", "--show-secret"])
    assert keys.secret_key().to_bech32() in capsys.readouterr().out


def test_global_home_flag(tmp_path, home, capsys):
    main(["--home", str(tmp_path / "other"), "init", "--name", "bob", "--role", "merchant"])
    assert (tmp_path / "other" / "bob" / "identity.json").exists()


@pytest.mark.parametrize("argv", [["whoami", "--name", "ghost"], ["register", "--name", "ghost"], ["whoami"]])
def test_config_errors_exit_cleanly(home, capsys, argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code.startswith("kuberbolt: ")
    assert "\n" not in exc.value.code


def test_register_with_placeholder_config_names_missing_field(home):
    main(["init", "--name", "alice", "--role", "client"])
    with pytest.raises(SystemExit) as exc:
        main(["register", "--name", "alice"])
    assert "is required" in exc.value.code
