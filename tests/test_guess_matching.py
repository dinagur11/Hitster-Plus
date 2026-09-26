from server.game_logic.guess_matching import (
    is_artist_guess_correct,
    is_guess_bonus_earned,
    is_title_guess_correct,
    normalize_guess_text,
)


def test_normalize_strips_case_punctuation_and_parenthetical():
    assert normalize_guess_text("The Beatles!") == "beatles"
    assert normalize_guess_text("Hey Jude (Remastered 2011)") == "hey jude"
    assert normalize_guess_text("A Song [feat. Someone]") == "song"


def test_exact_artist_match():
    assert is_artist_guess_correct("The Beatles", "The Beatles") is True


def test_artist_match_tolerates_leading_article_and_case():
    assert is_artist_guess_correct("beatles", "The Beatles") is True


def test_artist_typo_within_threshold():
    assert is_artist_guess_correct("The Beetles", "The Beatles") is True


def test_artist_completely_wrong_is_rejected():
    assert is_artist_guess_correct("Queen", "The Beatles") is False


def test_title_match_ignores_word_order():
    assert is_title_guess_correct("Jude Hey", "Hey Jude") is True


def test_title_match_ignores_parenthetical_remaster_tag():
    assert is_title_guess_correct("Hey Jude", "Hey Jude (Remastered 2011)") is True


def test_title_completely_wrong_is_rejected():
    assert is_title_guess_correct("Yesterday", "Hey Jude") is False


def test_guess_bonus_requires_both_artist_and_title_correct():
    assert (
        is_guess_bonus_earned(
            guessed_artist="Beatles",
            guessed_title="Hey Jude",
            actual_artist="The Beatles",
            actual_title="Hey Jude (Remastered 2011)",
        )
        is True
    )


def test_guess_bonus_denied_if_only_artist_correct():
    assert (
        is_guess_bonus_earned(
            guessed_artist="The Beatles",
            guessed_title="Yesterday",
            actual_artist="The Beatles",
            actual_title="Hey Jude",
        )
        is False
    )


def test_guess_bonus_denied_if_only_title_correct():
    assert (
        is_guess_bonus_earned(
            guessed_artist="Queen",
            guessed_title="Hey Jude",
            actual_artist="The Beatles",
            actual_title="Hey Jude",
        )
        is False
    )
