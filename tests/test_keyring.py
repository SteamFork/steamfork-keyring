from contextlib import nullcontext as does_not_raise
from copy import deepcopy
from pathlib import Path
from typing import ContextManager

from pytest import mark
from pytest import raises

from libkeyringctl import keyring
from libkeyringctl.types import Fingerprint
from libkeyringctl.types import Uid
from libkeyringctl.types import Username

from .conftest import create_certificate
from .conftest import create_key_revocation
from .conftest import test_all_fingerprints
from .conftest import test_certificates
from .conftest import test_keys
from .conftest import test_main_fingerprints


def test_is_pgp_fingerprint(
    valid_fingerprint: str,
    invalid_fingerprint: str,
) -> None:
    assert keyring.is_pgp_fingerprint(string=valid_fingerprint) is True
    assert keyring.is_pgp_fingerprint(string=invalid_fingerprint) is False


@mark.parametrize(
    "create_paths, create_paths_in_keyring_dir",
    [
        (True, False),
        (True, True),
        (False, True),
        (False, False),
    ],
)
def test_transform_username_to_keyring_path(
    create_paths: bool,
    create_paths_in_keyring_dir: bool,
    working_dir: Path,
    keyring_dir: Path,
) -> None:
    paths = [Path("test")]
    input_paths = deepcopy(paths)

    for index, path in enumerate(paths):
        path_in_working_dir = working_dir / path
        if create_paths:
            path_in_working_dir.mkdir()

        if create_paths_in_keyring_dir:
            (keyring_dir / path).mkdir(parents=True)

        paths[index] = path_in_working_dir

    modified_paths = deepcopy(paths)

    keyring.transform_username_to_keyring_path(keyring_dir=keyring_dir, paths=paths)

    for index, path in enumerate(paths):
        if create_paths or (not create_paths and not create_paths_in_keyring_dir):
            assert path == modified_paths[index]
        if not create_paths and create_paths_in_keyring_dir:
            assert path == keyring_dir / input_paths[index]


@mark.parametrize(
    "fingerprint_path, create_paths, create_paths_in_keyring_dir",
    [
        (True, True, False),
        (True, True, True),
        (True, False, True),
        (True, False, False),
        (False, True, False),
        (False, True, True),
        (False, False, True),
        (False, False, False),
    ],
)
def test_transform_fingerprint_to_keyring_path(
    fingerprint_path: bool,
    create_paths: bool,
    create_paths_in_keyring_dir: bool,
    working_dir: Path,
    keyring_dir: Path,
    valid_fingerprint: str,
) -> None:
    paths = [Path(valid_fingerprint) if fingerprint_path else Path("test")]
    input_paths = deepcopy(paths)

    keyring_subdir = keyring_dir / "type" / "username"

    for index, path in enumerate(paths):
        path_in_working_dir = working_dir / path
        if create_paths:
            path_in_working_dir.mkdir()

        if create_paths_in_keyring_dir:
            (keyring_subdir / path).mkdir(parents=True)

        paths[index] = path_in_working_dir

    modified_paths = deepcopy(paths)

    keyring.transform_fingerprint_to_keyring_path(keyring_root=keyring_dir, paths=paths)

    for index, path in enumerate(paths):
        if create_paths or (not fingerprint_path and not create_paths):
            assert path == modified_paths[index]
        if not create_paths and fingerprint_path and create_paths_in_keyring_dir:
            assert path == keyring_subdir / input_paths[index]


@create_certificate(username=Username("foobar"), uids=[Uid("foobar <foo@bar.xyz>")])
def test_convert(working_dir: Path, keyring_dir: Path) -> None:
    keyring.convert(
        working_dir=working_dir,
        keyring_root=keyring_dir,
        sources=test_certificates[Username("foobar")],
        target_dir=keyring_dir,
    )

    with raises(Exception):
        keyring.convert(
            working_dir=working_dir,
            keyring_root=keyring_dir,
            sources=test_keys[Username("foobar")],
            target_dir=keyring_dir,
        )


@create_certificate(username=Username("main"), uids=[Uid("main <foo@bar.xyz>")], keyring_type="main")
@create_certificate(username=Username("other_main"), uids=[Uid("other main <foo@bar.xyz>")], keyring_type="main")
@create_certificate(username=Username("foobar"), uids=[Uid("foobar <foo@bar.xyz>")])
def test_export_ownertrust(working_dir: Path, keyring_dir: Path) -> None:
    output = working_dir / "build"

    keyring.export_ownertrust(
        certs=[keyring_dir / "main"],
        keyring_root=keyring_dir,
        output=output,
    )

    with open(file=output, mode="r") as output_file:
        for line in output_file.readlines():
            assert line.split(":")[0] in test_main_fingerprints


@create_certificate(username=Username("main"), uids=[Uid("main <foo@bar.xyz>")], keyring_type="main")
@create_certificate(username=Username("foobar"), uids=[Uid("foobar <foo@bar.xyz>")])
@create_key_revocation(username=Username("foobar"))
def test_export_revoked(working_dir: Path, keyring_dir: Path) -> None:
    output = working_dir / "build"

    keyring.export_revoked(
        certs=[keyring_dir / "packager"],
        keyring_root=keyring_dir,
        main_keys=test_main_fingerprints,
        output=output,
    )

    revoked_fingerprints = test_all_fingerprints - test_main_fingerprints
    with open(file=output, mode="r") as output_file:
        for line in output_file.readlines():
            assert line.strip() in revoked_fingerprints


@mark.parametrize(
    "create_dir, duplicate_fingerprints, expectation",
    [
        (True, False, does_not_raise()),
        (True, True, raises(Exception)),
        (False, False, does_not_raise()),
        (False, True, does_not_raise()),
    ],
)
def test_derive_username_from_fingerprint(
    create_dir: bool,
    duplicate_fingerprints: bool,
    expectation: ContextManager[str],
    keyring_dir: Path,
    valid_fingerprint: str,
) -> None:

    username = "username"
    other_username = "other_user"

    typed_keyring_dir = keyring_dir / "type"

    if create_dir:
        (typed_keyring_dir / username / valid_fingerprint).mkdir(parents=True)
        if duplicate_fingerprints:
            (typed_keyring_dir / other_username / valid_fingerprint).mkdir(parents=True)

    with expectation:
        returned_username = keyring.derive_username_from_fingerprint(
            keyring_dir=typed_keyring_dir,
            certificate_fingerprint=Fingerprint(valid_fingerprint),
        )
        if create_dir and not duplicate_fingerprints:
            assert returned_username == username
        else:
            assert returned_username is None


def test_get_fingerprints_from_paths(keyring_dir: Path, valid_fingerprint: str, valid_subkey_fingerprint: str) -> None:

    fingerprint_dir = keyring_dir / "type" / "username" / valid_fingerprint
    fingerprint_dir.mkdir(parents=True)
    (fingerprint_dir / (fingerprint_dir.name + ".asc")).touch()

    fingerprint_subkey_dir = fingerprint_dir / "subkey" / valid_subkey_fingerprint
    fingerprint_subkey_dir.mkdir(parents=True)
    fingerprint_subkey_asc = fingerprint_subkey_dir / (fingerprint_subkey_dir.name + ".asc")
    fingerprint_subkey_asc.touch()

    assert keyring.get_fingerprints_from_paths(sources=[fingerprint_subkey_dir]) == set(
        [Fingerprint(valid_subkey_fingerprint)]
    )
    assert keyring.get_fingerprints_from_paths(sources=[fingerprint_dir]) == set([Fingerprint(valid_fingerprint)])