"""Roundtrip and provenance audit using only approved demo-derived HTML."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]

class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = False
        self.discard = 0
        self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == 'body': self.body=True
        if tag in {'script','style','head','svg','iframe','object'}: self.discard+=1
        if self.body and not self.discard and tag in {'p','h1','h2','h3','div','section','br','li'}: self.text.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script','style','head','svg','iframe','object'} and self.discard: self.discard-=1
        if tag == 'body': self.body=False
        if self.body and not self.discard and tag in {'p','h1','h2','h3','div','section','li'}: self.text.append('\n')
    def handle_data(self, data):
        if self.body and not self.discard: self.text.append(data)

def normal(text):
    return re.sub(r'\s+', ' ', text).strip()

def main():
    source = ROOT/'tests/artifacts/approved_44pages_job/export/basic.html'
    parser=Visible()
    parser.feed(source.read_text(encoding='utf-8'))
    expected=normal(''.join(parser.text))
    book=source.parent/'epub/book.epub'
    actual=[]
    with zipfile.ZipFile(book) as package:
        for name in sorted(package.namelist()):
            if name.startswith('EPUB/text/') and name.endswith('.xhtml'):
                doc=ET.fromstring(package.read(name))
                actual.append(''.join(doc.find('{http://www.w3.org/1999/xhtml}body').itertext()))
    found=normal('\n'.join(actual))
    assert expected==found, 'Visible text differs from approved source'
    manifest=json.loads((ROOT/'phase7/font_style_manifest.json').read_text(encoding='utf-8'))
    documents=manifest['baseline_scope']['documents']
    for document in documents:
        assert hashlib.sha256((ROOT/document['file']).read_bytes()).hexdigest()==document['sha256']
    result={'scope':'Approved demo 44-page OCR output only', 'documents':documents,
            'source_path':str(source.relative_to(ROOT)), 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'epub_path':str(book.relative_to(ROOT)), 'epub_sha256':hashlib.sha256(book.read_bytes()).hexdigest(),
            'visible_characters':len(expected), 'visible_text_sha256':hashlib.sha256(expected.encode()).hexdigest(),
            'roundtrip_equal':True,'normalization':'collapse layout whitespace; no removal of Thai vowels/tones, no sorting, no Unicode NFC conversion',
            'review':'automated identity audit; Phase 7 baseline ground truth retained; no new human quality certification'}
    (ROOT/'phase8/fixture_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'PASS: approved 44 pages, {len(expected)} visible characters preserved; 6 demo hashes match')

if __name__=='__main__': main()
