from server.game_logic.mashup import evaluate_mashup_card, is_mashup_guess_correct, is_mashup_guess_exact


def test_correct_guess_within_tolerance():
    result = evaluate_mashup_card(guessed_year=2005, actual_year=2000)
    assert result.correct is True


def test_incorrect_guess_outside_tolerance():
    result = evaluate_mashup_card(guessed_year=1900, actual_year=2000)
    assert result.correct is False


def test_boundary_exactly_ten_years_off_is_inclusive_correct():
    assert is_mashup_guess_correct(guessed_year=2000, actual_year=1990) is True
    assert is_mashup_guess_correct(guessed_year=1990, actual_year=2000) is True


def test_boundary_eleven_years_off_is_incorrect():
    assert is_mashup_guess_correct(guessed_year=2001, actual_year=1990) is False
    assert is_mashup_guess_correct(guessed_year=1990, actual_year=2001) is False


def test_exact_match_is_correct():
    assert is_mashup_guess_correct(guessed_year=2005, actual_year=2005) is True


def test_metadata_present_in_result_regardless_of_correctness():
    result = evaluate_mashup_card(guessed_year=1950, actual_year=1970)
    # Wrong guess, but actual/guessed years are still surfaced, not gated
    # behind `correct` — display layer decides what to reveal.
    assert result.actual_year == 1970
    assert result.guessed_year == 1950
    assert result.correct is False


def test_exact_guess_is_both_correct_and_exact():
    assert is_mashup_guess_exact(guessed_year=2005, actual_year=2005) is True
    result = evaluate_mashup_card(guessed_year=2005, actual_year=2005)
    assert result.correct is True
    assert result.exact is True


def test_within_tolerance_but_not_exact_is_correct_but_not_exact():
    assert is_mashup_guess_exact(guessed_year=2000, actual_year=1995) is False
    result = evaluate_mashup_card(guessed_year=2000, actual_year=1995)
    assert result.correct is True
    assert result.exact is False


def test_wrong_guess_is_neither_correct_nor_exact():
    result = evaluate_mashup_card(guessed_year=1950, actual_year=1970)
    assert result.correct is False
    assert result.exact is False
