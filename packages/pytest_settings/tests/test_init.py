import pytest


def _run_pytest(pytester: pytest.Pytester) -> pytest.RunResult:
    # pytest-asyncio, installed for the crawler, warns in any run that leaves its loop scope unset.
    return pytester.runpytest("-p", "no:asyncio")


def test_a_misspelled_marker_is_a_collection_error(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.misspeled
        def test_marked() -> None:
            pass
        """
    )

    outcome = _run_pytest(pytester)

    outcome.assert_outcomes(errors=1)
    outcome.stdout.fnmatch_lines(["*Unknown pytest.mark.misspeled*"])


def test_a_resource_warning_fails_its_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import warnings

        def test_leaking() -> None:
            warnings.warn("unclosed resource", ResourceWarning)
        """
    )

    _run_pytest(pytester).assert_outcomes(failed=1)


def test_an_unraisable_exception_fails_its_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        class RaisingOnDelete:
            def __del__(self) -> None:
                raise RuntimeError("raised in __del__")

        def test_dropping() -> None:
            RaisingOnDelete()
        """
    )

    _run_pytest(pytester).assert_outcomes(failed=1)


def test_a_package_filter_does_not_lift_a_shared_one(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\nfilterwarnings = ignore::ResourceWarning\n")
    pytester.makepyfile(
        """
        import warnings

        def test_leaking() -> None:
            warnings.warn("unclosed resource", ResourceWarning)
        """
    )

    _run_pytest(pytester).assert_outcomes(failed=1)
