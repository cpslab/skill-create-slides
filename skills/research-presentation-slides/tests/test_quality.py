"""架空のOOXML fixtureで既知の欠陥・正当な例外・未対応を回帰検証する。"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_layout import check
from extract_reference import extract, chart_data, NS
from quality_gate import evaluate
from check_memo import check as check_memo
from check_pptx import inspect, parse_xml
import xml.etree.ElementTree as ET

HEAD = '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:cSld><p:spTree>'
TAIL = '</p:spTree></p:cSld></p:sld>'


def textbody(text, font=16):
    size = f' sz="{int(font * 100)}"' if font else ''
    return f'<a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr{size}/><a:t>{escape(str(text))}</a:t></a:r></a:p>'


def transform(bounds, prefix='a'):
    x, y, w, h = [round(v * 914400) for v in bounds]
    return f'<{prefix}:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></{prefix}:xfrm>'


def shape(sid, eid, role, text='', font=16, bounds=(0.5, 1.4, 8, 0.5)):
    return f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="role:{role}|id:{eid}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>{transform(bounds)}</p:spPr><p:txBody>{textbody(text,font)}</p:txBody></p:sp>'


def table(sid=4, eid='comparison', font=14):
    return f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{sid}" name="role:table|id:{eid}"/></p:nvGraphicFramePr>{transform((0.5,2,8,1),"p")}<a:graphic><a:graphicData><a:tbl><a:tblGrid><a:gridCol w="3657600"/><a:gridCol w="3657600"/></a:tblGrid><a:tr h="914400"><a:tc><a:txBody>{textbody("Method",font)}</a:txBody></a:tc><a:tc><a:txBody>{textbody("Baseline",font)}</a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>'


def chart_frame():
    return f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="role:chart|id:results"/></p:nvGraphicFramePr>{transform((0.5,2,8,2),"p")}<a:graphic><a:graphicData><c:chart r:id="chart1"/></a:graphicData></a:graphic></p:graphicFrame>'

def connector(head='none', tail='triangle'):
    return f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="6" name="role:diagram-edge|id:edge"/><p:cNvCxnSpPr><a:stCxn id="4" idx="1"/><a:endCxn id="5" idx="1"/></p:cNvCxnSpPr></p:nvCxnSpPr><p:spPr>{transform((2,2,2,0))}<a:ln><a:headEnd type="{head}"/><a:tailEnd type="{tail}"/></a:ln></p:spPr></p:cxnSp>'


def chart_xml(value=4):
    return f'<c:chartSpace xmlns:c="{NS["c"]}" xmlns:a="{NS["a"]}"><c:chart><c:plotArea><c:barChart><c:ser><c:tx><c:strRef><c:strCache><c:pt idx="0"><c:v>Measured</c:v></c:pt></c:strCache></c:strRef></c:tx><c:cat><c:strLit><c:pt idx="0"><c:v>Item</c:v></c:pt></c:strLit></c:cat><c:val><c:numLit><c:pt idx="0"><c:v>{value}</c:v></c:pt></c:numLit></c:val></c:ser></c:barChart></c:plotArea></c:chart><c:txPr><a:p><a:pPr><a:defRPr sz="1400"/></a:pPr></a:p></c:txPr></c:chartSpace>'


def write_pptx(path, slides, chart_value=None):
    relationships_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    reltype = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('_rels/.rels', f'<Relationships xmlns="{relationships_ns}"><Relationship Id="root" Type="{reltype}officeDocument" Target="ppt/presentation.xml"/></Relationships>')
        ids = ''.join(f'<p:sldId id="{256+i}" r:id="s{i}"/>' for i in range(len(slides)))
        z.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{NS["p"]}" xmlns:r="{NS["r"]}"><p:sldIdLst>{ids}</p:sldIdLst><p:sldSz cx="9144000" cy="5143500"/></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels', f'<Relationships xmlns="{relationships_ns}">' + ''.join(f'<Relationship Id="s{i}" Type="{reltype}slide" Target="slides/slide{i+1}.xml"/>' for i in range(len(slides))) + '</Relationships>')
        for i, body in enumerate(slides, 1):
            z.writestr(f'ppt/slides/slide{i}.xml', HEAD + body + TAIL)
            if 'chart1' in body:
                z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels', f'<Relationships xmlns="{relationships_ns}"><Relationship Id="chart1" Type="{reltype}chart" Target="../charts/chart1.xml"/></Relationships>')
        if chart_value is not None:
            z.writestr('ppt/charts/chart1.xml', chart_xml(chart_value))


def base(number=1):
    return shape(2, 'title', 'title', 'Fictional example', 24, (0.5, 0.6, 8, 0.5)) + shape(3, 'page', 'page', number, 9, (9.1,5.3,0.4,0.2))


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fixture.pptx'
        self.spec = {'slides': [{'number': 1, 'title': 'Fictional example'}]}
        self.layout = {'slides': [{'number': 1, 'expected_elements': []}]}

    def tearDown(self):
        self.temp.cleanup()

    def report(self, body, **kwargs):
        write_pptx(self.path, [base() + body], kwargs.pop('chart_value', None))
        return check(self.path, deck_spec=self.spec, layout=self.layout, **kwargs)

    def codes(self, report, status=None):
        return {f['code'] for f in report['findings'] if status is None or f['status'] == status}

    def memo_evidence(self, visual):
        spec_path = Path(self.temp.name) / 'independent-input.json'
        spec_path.write_text(json.dumps(self.spec))
        visual['deck_spec_sha256'] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        return {'deck_spec': spec_path, 'memo_report': check_memo(self.path, spec_path)}

    def test_page_duplicate_and_missing(self):
        write_pptx(self.path, [base(1), base(1)])
        report = check(self.path, deck_spec={'slides':[{},{}]}, layout={'slides':[{},{}]})
        self.assertIn('page_duplicate', self.codes(report, 'error'))
        self.assertIn('page_number', self.codes(report, 'error'))
        write_pptx(self.path, [shape(2,'title','title','Title',24)])
        self.assertIn('page_count', self.codes(check(self.path, layout=self.layout), 'error'))

    def test_out_of_bounds_and_one_point_body(self):
        report = self.report(shape(4,'body','body','Small text',1,(20,2,2,1)))
        self.assertTrue({'out_of_bounds','font_too_small'} <= self.codes(report,'error'))

    def test_source_size_is_not_body_size(self):
        report = self.report(shape(4,'source','source','[1] Fictional source',8.5,(0.5,5,8,0.2)))
        self.assertNotIn('font_too_small',self.codes(report))

    def test_table_flattening(self):
        self.layout['slides'][0]['expected_elements'] = [{'id':'comparison','role':'table','kind':'table','table':{'rows':[['Method','Baseline']]}}]
        good = self.report(table())
        self.assertNotIn('native_kind', self.codes(good))
        bad = self.report(shape(4,'comparison','table','Method Baseline',14,(0.5,2,8,1)))
        self.assertIn('native_kind', self.codes(bad,'error'))

    def test_chart_cache_series_name_and_changed_value(self):
        self.layout['slides'][0]['expected_elements'] = [{'id':'results','role':'chart','kind':'chart','chart':{'categories':['Item'],'series':[{'name':'Measured','values':[4]}]}}]
        good = self.report(chart_frame(),chart_value=4)
        self.assertNotIn('chart_name',self.codes(good))
        self.assertNotIn('chart_values',self.codes(good))
        bad = self.report(chart_frame(),chart_value=5)
        self.assertIn('chart_values',self.codes(bad,'error'))

    def test_empty_native_axis_title_is_not_an_absent_title(self):
        for title, expected_error in [
            ('', False),
            ('<c:title><c:tx><c:rich><a:p><a:pPr><a:defRPr sz="1200"/></a:pPr></a:p></c:rich></c:tx></c:title>', True),
            ('<c:title><c:tx><c:rich><a:p><a:r><a:t>Time (s)</a:t></a:r></a:p></c:rich></c:tx></c:title>', False),
        ]:
            self.report(chart_frame(), chart_value=4)
            with zipfile.ZipFile(self.path) as archive:
                parts = {name: archive.read(name) for name in archive.namelist()}
            axis = f'<c:catAx><c:axId val="10"/>{title}</c:catAx>'
            parts['ppt/charts/chart1.xml'] = chart_xml().replace('</c:plotArea>', axis + '</c:plotArea>')
            with zipfile.ZipFile(self.path, 'w') as archive:
                for name, content in parts.items():
                    archive.writestr(name, content)
            report = check(self.path, deck_spec=self.spec, layout=self.layout)
            self.assertEqual('chart_empty_title' in self.codes(report, 'error'), expected_error)

    def test_declared_overlap(self):
        self.layout['slides'][0]['allowed_overlaps'] = [['photo','caption']]
        body = shape(4,'photo','image','',16,(1,2,4,2)) + shape(5,'caption','label','Label',14,(2,2.5,2,0.4))
        good=self.report(body)
        self.assertNotIn('overlap',self.codes(good))
        self.layout['slides'][0]['allowed_overlaps']=[]
        bad=self.report(body)
        self.assertIn('overlap',self.codes(bad,'review_required'))

    def test_nested_group_not_silently_passed(self):
        group = '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="6" name="role:diagram-node|id:group"/></p:nvGrpSpPr><p:grpSpPr>' + transform((1,1,2,2)) + '</p:grpSpPr>' + shape(7,'nested','label','Grouped',14,(20,20,1,1)) + '</p:grpSp>'
        report=self.report(group)
        self.assertIn('transform_unsupported',self.codes(report,'unverified'))

    def test_inherited_fonts_and_table_cells_not_silently_passed(self):
        report=self.report(shape(4,'body','body','Inherited',None) + table(font=None))
        self.assertIn('font_inheritance',self.codes(report,'unverified'))
        self.assertIn('table_font_inheritance',self.codes(report,'unverified'))

    def test_inserted_pages_require_updated_mapping(self):
        write_pptx(self.path,[base(1),base(2),base(2)])
        spec={'slides':[{'required_text':['Fictional example']},{'required_text':['Fictional example']},{'required_text':['Fictional example']}]}
        report=check(self.path,deck_spec=spec,layout={'slides':[{}, {}, {}]})
        self.assertIn('page_number',self.codes(report,'error'))
        write_pptx(self.path,[base(1),base(2),base(3)])
        self.assertNotIn('page_number',self.codes(check(self.path,deck_spec=spec,layout={'slides':[{}, {}, {}]})))

    def test_semantic_conditions_cannot_move_only_to_notes(self):
        self.spec['slides'][0]['semantic_claims']=[{'text':'Fictional example','source':'input paragraph 1','status':'illustrative','aggregation':'per trial'}]
        self.assertIn('claim_condition',self.codes(self.report(''),'error'))

    def test_quality_gate_binds_final_file_and_all_images(self):
        report=self.report('')
        image=Path(self.temp.name)/'page.png'
        image.write_bytes(b'fixture-image-not-a-render')
        visual={'pptx_sha256':report['pptx_sha256'],'pages':[{'number':1,'image':str(image),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'status':'pass','reviewer':'fixture','notes':'Synthetic verification fixture; not a real visual review.'}],
                'resolved_findings':[{'id':f['id'],'status':'pass','reason':'Fixture resolution','method':'test','evidence':'fixture'} for f in report['findings']]}
        memo = self.memo_evidence(visual)
        self.assertTrue(evaluate(self.path,report,visual,**memo)['verified_complete'])
        visual['pptx_sha256']='stale'
        self.assertFalse(evaluate(self.path,report,visual,**memo)['verified_complete'])
        visual['pptx_sha256']=report['pptx_sha256']
        visual['pages']=[]
        self.assertFalse(evaluate(self.path,report,visual,**memo)['verified_complete'])

    def test_independent_source_catches_generator_sidecar_error(self):
        self.layout['slides'][0]['expected_elements'] = [{'id':'results','role':'chart','kind':'chart','chart':{'categories':['Item'],'series':[{'name':'Measured','values':[5]}]}}]
        self.spec['slides'][0]['chart'] = {'categories':['Item'],'series':[{'name':'Measured','values':[4]}]}
        report = self.report(chart_frame(), chart_value=5)
        self.assertNotIn('chart_values', self.codes(report))
        self.assertIn('source_chart_values', self.codes(report, 'error'))
        self.spec['slides'][0].pop('chart')
        self.spec['slides'][0]['table'] = {'rows':[['Method','Changed input']]}
        report = self.report(table())
        self.assertIn('source_table_values', self.codes(report, 'error'))

    def test_quality_gate_rejects_sidecar_and_incomplete_layout_reports(self):
        report = self.report('')
        image = Path(self.temp.name) / 'page.png'
        image.write_bytes(b'fixture-image-not-a-render')
        visual = {'pptx_sha256': report['pptx_sha256'], 'pages': [
            {'number': 1, 'image': str(image),
             'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
             'status': 'pass', 'reviewer': 'fixture', 'notes': 'Synthetic gate fixture.'}],
            'resolved_findings': [
                {'id': f['id'], 'status': 'pass', 'reason': 'Fixture resolution',
                 'method': 'test', 'evidence': 'fixture'} for f in report['findings']]}
        memo = self.memo_evidence(visual)
        self.assertTrue(evaluate(self.path, report, visual, **memo)['verified_complete'])
        invalid = [
            {'schema_version': 1, 'pptx_sha256': report['pptx_sha256'], 'slides': []},
            {**report, 'checks': []},
            {**report, 'checks': report['checks'] * 2},
            {**report, 'slide_count': 2},
            {**report, 'findings': []},
            {**report, 'status': 'pass'},
            [],
        ]
        for candidate in invalid:
            result = evaluate(self.path, candidate, visual, **memo)
            self.assertFalse(result['verified_complete'])
            self.assertIn('layout_report_schema', {i['code'] for i in result['issues']})

    def test_independent_input_text_fields(self):
        self.spec['slides'][0].update(question='Required question', blocks=['Required block'], conditions=[{'title':'Condition A','text':'A required condition'}], takeaways=['Required conclusion'])
        report = self.report('')
        missing = [f for f in report['findings'] if f['code']=='required_text']
        self.assertEqual(len(missing),5)

    def test_independent_notes_object_is_not_ignored(self):
        self.spec['slides'][0]['notes']={'text':'Required source note'}
        self.assertIn('notes_required',self.codes(self.report(''),'error'))

    def test_source_diagram_edge_cannot_be_lost(self):
        self.spec['slides'][0]['diagram'] = {'edges':[{'id':'edge','from':'a','to':'b','meaning':'order'}]}
        report = self.report(shape(4,'a','label','A',14) + shape(5,'b','label','B',14,(4,2,1,1)))
        self.assertIn('source_diagram_connection', self.codes(report,'error'))

    def test_all_diagram_directions_and_independent_input(self):
        nodes = shape(4,'a','label','A',14) + shape(5,'b','label','B',14,(4,2,1,1))
        for direction, head, tail in [('forward','none','triangle'),('backward','triangle','none'),('both','triangle','triangle'),('none','none','none')]:
            edge={'id':'edge','from':'a','to':'b','direction':direction,'meaning':'Illustrative relation'}
            self.layout['slides'][0]['expected_elements']=[{'id':'edge','kind':'connector','edge':edge}]
            self.spec['slides'][0]['diagram']={'edges':[edge]}
            good=self.report(nodes+connector(head,tail))
            self.assertNotIn('diagram_direction',self.codes(good,'error'),direction)
            self.assertNotIn('source_diagram_direction',self.codes(good,'error'),direction)
            bad=self.report(nodes+connector('triangle' if head=='none' else 'none',tail))
            self.assertIn('diagram_direction',self.codes(bad,'error'),direction)
            self.assertIn('source_diagram_direction',self.codes(bad,'error'),direction)
        self.layout['slides'][0]['expected_elements'][0]['edge']={**edge,'direction':'forward'}
        wrong=self.report(nodes+connector('none','triangle'))
        self.assertNotIn('diagram_direction',self.codes(wrong,'error'))
        self.assertIn('source_diagram_direction',self.codes(wrong,'error'))

    def test_cli_exit_and_legacy_checker_compatibility(self):
        report=self.report(shape(4,'body','body','Small',1))
        layoutfile=Path(self.temp.name)/'spec.json'
        layoutfile.write_text(json.dumps(self.layout))
        scripts=Path(__file__).resolve().parents[1]/'scripts'
        check_run=subprocess.run([sys.executable,str(scripts/'check_layout.py'),str(self.path),'--layout',str(layoutfile)],capture_output=True,text=True)
        legacy_run=subprocess.run([sys.executable,str(scripts/'check_pptx.py'),str(self.path)],capture_output=True,text=True)
        self.assertEqual(check_run.returncode,1)
        self.assertEqual(legacy_run.returncode,0)
        self.assertIn('font_too_small',check_run.stdout)

    def test_cli_missing_explicit_input_does_not_fall_back(self):
        self.report('')
        scripts=Path(__file__).resolve().parents[1]/'scripts'
        for flag in ('--profile', '--deck-spec', '--layout'):
            result=subprocess.run([sys.executable,str(scripts/'check_layout.py'),str(self.path),flag,str(Path(self.temp.name)/'missing.json')],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertIn('does not exist',result.stderr)

    def test_qname_value_prefix_requires_in_scope_declaration(self):
        xsi='http://www.w3.org/2001/XMLSchema-instance'
        dcterms='http://purl.org/dc/terms/'
        bad=f'<root xmlns:xsi="{xsi}" xmlns:ns2="{dcterms}"><ns2:created xsi:type="dcterms:W3CDTF">2026-01-01</ns2:created></root>'
        write_pptx(self.path,[base()])
        with zipfile.ZipFile(self.path,'a') as archive:
            archive.writestr('docProps/core.xml',bad)
        self.assertTrue(any('Undeclared xsi:type QName prefix' in item for item in inspect(self.path)['errors']))
        good=bad.replace('xmlns:ns2=',f'xmlns:dcterms="{dcterms}" xmlns:ns2=')
        self.assertEqual(parse_xml(good.encode())[1],[])
        nested=f'<root xmlns:xsi="{xsi}"><one xmlns:t="{dcterms}" xsi:type="t:W3CDTF"/><two xsi:type="t:W3CDTF"/></root>'
        self.assertEqual(len(parse_xml(nested.encode())[1]),1)
        self.assertEqual(parse_xml(f'<root xmlns:xsi="{xsi}" xsi:type="LocalType"/>'.encode())[1],[])


if __name__=='__main__':
    unittest.main()
