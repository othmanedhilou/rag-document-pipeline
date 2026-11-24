from docpipe.chunking import chunk_pages
from docpipe.extract import Page, _clean


def test_short_page_single_chunk():
    chunks = chunk_pages([Page(1, "Un paragraphe court.")], "d1", "a.pdf", size=200, overlap=20)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "d1-0000"
    assert chunks[0].page == 1


def test_chunks_respect_size_and_keep_page():
    para = " ".join(f"Phrase numero {i} du document." for i in range(60))
    pages = [Page(1, para), Page(2, "Deuxieme page.")]
    chunks = chunk_pages(pages, "d1", "a.pdf", size=300, overlap=50)
    assert all(len(c.text) <= 300 + 50 for c in chunks)
    assert chunks[-1].page == 2
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_overlap_repeats_end_of_previous_chunk():
    text = " ".join(f"mot{i}" for i in range(200))
    chunks = chunk_pages([Page(1, text)], "d1", "a.txt", size=200, overlap=40)
    first, second = chunks[0].text.split(), chunks[1].text.split()
    shared = second[: second.index(first[-1]) + 1]
    assert 2 <= len(shared) <= 10
    assert first[-len(shared):] == shared


def test_clean_joins_hyphenated_words_and_blank_lines():
    assert _clean("infor-\nmatique\n\n\n\nsuite") == "informatique\n\nsuite"
