from scripts.resume_claims import find_novel_words, find_unbacked_terms


def test_the_reported_case():
    assert find_unbacked_terms(
        "Handled member questions at the front desk.",
        "Coached members on fitness coaching and handled questions.",
        ["fitness coaching", "scheduling"],
    ) == ["fitness coaching"]


def test_a_term_already_in_the_original_is_not_flagged():
    assert find_unbacked_terms(
        "Led fitness coaching sessions.", "Ran fitness coaching for members.", ["fitness coaching"]
    ) == []


def test_matching_is_by_whole_word_and_ignores_case():
    assert find_unbacked_terms("Worked.", "We communicate at our location", ["cat"]) == []
    assert find_unbacked_terms("Worked.", "We rescue Cats", ["cat"]) == ["cat"]


def test_multi_word_terms_need_the_whole_phrase():
    assert find_unbacked_terms("Worked.", "Led coaching for members", ["fitness coaching"]) == []


def test_no_terms_returns_empty():
    assert find_unbacked_terms("a", "b", []) == []


def test_symbol_terms_match_literally():
    assert find_unbacked_terms("Wrote Python.", "Wrote C++ and Python.", ["C++"]) == ["C++"]
    assert find_unbacked_terms("Wrote Python.", "Wrote C and Python.", ["C++"]) == []
    assert find_unbacked_terms("Wrote Python.", "Wrote C# services.", ["C#"]) == ["C#"]
    assert find_unbacked_terms("Wrote Python.", "Wrote C services.", ["C#"]) == []
    assert find_unbacked_terms("Wrote C++.", "Wrote C++ code.", ["C++"]) == []
    assert find_unbacked_terms("x", "Built .NET apps", [".NET"]) == [".NET"]


def test_terms_are_returned_once_in_given_order():
    assert find_unbacked_terms("x", "dogs and cats and cat", ["cat", "dog", "cat"]) == ["cat", "dog"]


def test_novel_words_lists_words_in_neither_source():
    assert find_novel_words(
        "Answered phones and scheduled appointments.",
        "Answered phones, scheduled appointments and led wellness coaching.",
        ["Greeted visitors"],
    ) == ["wellness", "coaching"]


def test_novel_words_ignores_short_words_stopwords_plurals_and_punctuation():
    assert find_novel_words(
        "Managed phones and visitor desks.",
        "Managed phone, visitors; desk -- with a big team, results and 2024 C++!",
    ) == []


def test_novel_words_accepts_words_from_allowed_texts():
    assert find_novel_words(
        "Answered phones.", "Answered phones and greeted visitors.", ["Greeted visitors"]
    ) == []
