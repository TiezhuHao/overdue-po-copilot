"""The same release cases run in pytest and the standalone summary runner."""
import pytest
from tests.release_evaluation import CASES, check_case


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_release_evaluation(case):
    check_case(case)
