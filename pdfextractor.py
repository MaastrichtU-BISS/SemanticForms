from pypdf import PdfReader

def extracttext(filename):
    fulltext_paper=PdfReader(filename) # download from doi

    text = ""

    for page in fulltext_paper.pages:
        text += page.extract_text() + "\n"

    return text