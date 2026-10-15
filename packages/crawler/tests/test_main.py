from p2pwatch.composition import __main__ as entry


def test_package_main_shim_reexports_main() -> None:
    # `python -m p2pwatch` runs the PACKAGE's __main__: it must expose the SAME
    # `main` function as composition.__main__ (otherwise DoD §9.4 is not met).
    from p2pwatch import __main__ as package_entry

    assert package_entry.main is entry.main
