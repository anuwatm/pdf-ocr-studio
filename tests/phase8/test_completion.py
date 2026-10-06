"""Phase 8 completion regression fixtures; artifacts deliberately retained."""
import base64
import io
import json
import re
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
import zipfile
from xml.etree import ElementTree as ET
from PIL import Image
from src.epub_exporter import prepare_epub_preview, build_epub, get_epub_status, validate_epub_bytes
from src.job_artifact_guard import artifact_access

ROOT = Path('tests/artifacts/phase8_completion').resolve()
XHTML = '{http://www.w3.org/1999/xhtml}'
TEXT = 'น้ำ กำลัง ปี่ ไทย English\u200b\u200c\u200d עברית العربية & < > " \' 😀 [PAGE 2: CANCELLED]'

class CompletionTests(unittest.TestCase):
    def job(self, body=None):
        job = 'fixture_' + uuid.uuid4().hex[:12]
        export = ROOT / job / 'export'
        export.mkdir(parents=True)
        import html
        (export / 'basic.html').write_text('<html><body>' + (body or '<p>'+html.escape(TEXT)+'</p>') + '</body></html>', encoding='utf-8')
        return job

    def preview(self, job, **kwargs):
        return prepare_epub_preview(job, source_variant='basic', files_dir=str(ROOT), **kwargs)

    def build(self, job, meta):
        return build_epub(job, meta['preview_revision'], files_dir=str(ROOT))

    def content(self, job):
        return (ROOT / job / 'export/epub/book.epub').read_bytes()

    def test_unicode_roundtrip_and_page_markers(self):
        job = self.job()
        self.build(job, self.preview(job))
        with zipfile.ZipFile(io.BytesIO(self.content(job))) as package:
            chapter = ET.fromstring(package.read('EPUB/text/chapter-001.xhtml'))
            self.assertEqual(''.join(chapter.find('.//'+XHTML+'p').itertext()), TEXT)

    def test_cover_and_optional_metadata(self):
        image = io.BytesIO()
        Image.new('RGB', (120, 180), 'blue').save(image, format='PNG')
        cover = dict(data_base64=base64.b64encode(image.getvalue()).decode(), alt='ปก <หนังสือ>')
        job = self.job()
        meta = self.preview(job, cover=cover, metadata={'title':'ภาษาไทย', 'date':'2026-10-04', 'description':'คำอธิบาย'})
        self.assertEqual(meta['cover']['width'], 120)
        self.build(job, meta)
        with zipfile.ZipFile(io.BytesIO(self.content(job))) as package:
            self.assertIn('EPUB/assets/cover.png', package.namelist())
            self.assertIn(b'cover-image', package.read('EPUB/package.opf'))
            self.assertIn(b'2026-10-04', package.read('EPUB/package.opf'))
            cover_doc = ET.fromstring(package.read('EPUB/text/cover.xhtml'))
            self.assertEqual(cover_doc.find('.//'+XHTML+'img').get('alt'), 'ปก <หนังสือ>')
        (ROOT / 'cover_fixture.epub').write_bytes(self.content(job))

    def test_svg_and_invalid_cover_rejected(self):
        for data in (b'<svg><script>bad()</script></svg>', b'not image'):
            with self.assertRaisesRegex(ValueError, 'Invalid cover'):
                self.preview(self.job(), cover={'data_base64':base64.b64encode(data).decode()})

    def test_toc_hierarchy_and_references(self):
        job = self.job('<h1>บท</h1><h2>หัวข้อ</h2><h3>ย่อย</h3><p>เนื้อหา</p><h2>หัวข้อสอง</h2>')
        self.build(job, self.preview(job))
        with zipfile.ZipFile(io.BytesIO(self.content(job))) as package:
            nav = ET.fromstring(package.read('EPUB/nav.xhtml'))
            self.assertIsNotNone(nav.find('.//'+XHTML+'nav/'+XHTML+'ol/'+XHTML+'li/'+XHTML+'ol/'+XHTML+'li/'+XHTML+'ol/'+XHTML+'li'))
        self.assertTrue(validate_epub_bytes(self.content(job))['valid'])

    def test_no_heading_and_no_style_with_bare_text(self):
        job = self.job('ข้อความนอกย่อหน้า<section data-page="1"><p>หน้า 1</p></section><section data-page="2"><p>หน้า 2</p></section>')
        meta = self.preview(job)
        self.assertEqual(meta['chapters_count'], 3)
        self.build(job, meta)

    def test_exact_deterministic_regeneration(self):
        job = self.job()
        first = self.preview(job)
        self.build(job, first)
        content = self.content(job)
        second = self.preview(job)
        self.build(job, second)
        self.assertEqual(content, self.content(job))

    def test_failed_generation_preserves_previous_package(self):
        job = self.job()
        meta = self.preview(job)
        self.build(job, meta)
        previous = self.content(job)
        with patch('src.epub_exporter.validate_epub_bytes', return_value={'valid':False, 'errors':['fixture failure']}):
            with self.assertRaisesRegex(ValueError, 'validation failed'):
                self.build(job, meta)
        self.assertEqual(previous, self.content(job))
        self.assertTrue(get_epub_status(job, str(ROOT))['epub_ready'])
        self.assertEqual(get_epub_status(job, str(ROOT))['last_attempt_status'], 'failed')

    def test_concurrent_generation_and_delete_guard(self):
        job = self.job()
        with artifact_access(job, str(ROOT)):
            with self.assertRaisesRegex(ValueError, 'artifacts are busy'):
                self.preview(job)
            from src.cleanup_service import delete_single_job
            with self.assertRaisesRegex(ValueError, 'artifacts are busy'):
                delete_single_job(job, None, str(ROOT))

    def test_mid_generation_source_mutation_rejected(self):
        job = self.job()
        meta = self.preview(job)
        from src.epub_exporter import validate_epub_bytes as real_validate
        def mutate(content):
            (ROOT / job / 'export/basic.html').write_text('<html><body><p>ใหม่</p></body></html>', encoding='utf-8')
            return real_validate(content)
        with patch('src.epub_exporter.validate_epub_bytes', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during packaging'):
                self.build(job, meta)

    def test_dangerous_metadata_and_content(self):
        job = self.job('<h1>ชื่อ</h1><p onclick="bad()">ไทย <a href="https://evil.example/">ลิงก์</a></p><script>bad()</script><svg>bad()</svg>')
        self.build(job, self.preview(job, metadata={'title':'<script>bad()</script>', 'creator':'" onclick="bad()'}))
        with zipfile.ZipFile(io.BytesIO(self.content(job))) as package:
            for name in package.namelist():
                if name.endswith('.xhtml'):
                    root = ET.fromstring(package.read(name))
                    for element in root.iter():
                        self.assertNotIn(element.tag, {XHTML+'script', XHTML+'svg'})
                        self.assertFalse(any(k.startswith('on') for k in element.attrib))
                        self.assertFalse(any(v.startswith('https://evil') for v in element.attrib.values()))

    def test_validator_detects_missing_fragment_and_duplicate_ids(self):
        job = self.job('<h1>บท</h1><h2>หัวข้อ</h2><p>ไทย</p>')
        self.build(job, self.preview(job))
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.content(job))) as original, zipfile.ZipFile(buffer, 'w') as modified:
            for info in original.infolist():
                data = original.read(info.filename)
                if info.filename == 'EPUB/nav.xhtml':
                    data = re.sub(br'#heading-[A-Za-z0-9.-]+', b'#missing', data, count=1)
                modified.writestr(info, data)
        self.assertIn('Missing fragment', ';'.join(validate_epub_bytes(buffer.getvalue())['errors']))

if __name__ == '__main__':
    unittest.main()
