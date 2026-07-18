from app.rag.lexical import character_ngrams, tokenize


def test_tokenize_casefolds_and_deduplicates_tokens() -> None:
    assert tokenize("Policy policy 123") == ("policy", "123")


def test_tokenize_adds_korean_character_ngrams() -> None:
    assert tokenize("암진단") == (
        "암진단",
        "암진",
        "진단",
    )


def test_character_ngrams_ignores_single_characters() -> None:
    assert character_ngrams("암") == ()
