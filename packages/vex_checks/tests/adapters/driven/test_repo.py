from vex_checks.adapters.driven import repo


def test_repo_root_contains_the_packages_dir() -> None:
    assert (repo.repo_root() / "packages").is_dir()


def test_source_dirs_are_the_shipped_packages_only() -> None:
    names = {p.parent.name for p in repo.source_dirs()}
    assert names == {"crawler", "matching", "amule"}


def test_vex_files_point_at_security_dir() -> None:
    files = repo.vex_files()
    assert set(files) == {"crawler", "amule"}
    for image, path in files.items():
        assert path.name == f"{image}.vex.openvex.json"
        assert path.is_file()
