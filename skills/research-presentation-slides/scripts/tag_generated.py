#!/usr/bin/env python3
"""Bind author-assigned roles to images/charts whose public API lacks exportable names.
Only generated candidates are accepted; number and kind must match the sidecar.
No text, positions, data or media are changed.
"""
import argparse,json,zipfile,xml.etree.ElementTree as ET,os
from pathlib import Path
from normalise_generated import normalise
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
for k,v in NS.items():ET.register_namespace(k,v)
# xsi:type is a QName-valued string: ElementTree must retain its dcterms prefix.
for prefix,uri in {
 'cp':'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
 'dc':'http://purl.org/dc/elements/1.1/',
 'dcterms':'http://purl.org/dc/terms/',
 'xsi':'http://www.w3.org/2001/XMLSchema-instance',
}.items():ET.register_namespace(prefix,uri)
def tag(file,spec):
 with zipfile.ZipFile(file) as z:content={n:z.read(n) for n in z.namelist()}
 for page in spec['slides']:
  name=f'ppt/slides/slide{page["number"]}.xml';root=ET.fromstring(content[name]);tree=root.find('p:cSld/p:spTree',NS)
  for kind in ('image','chart'):
   expected=[e for e in page['expected_elements'] if e['kind']==kind]
   actual=[e for e in tree if (kind=='image' and e.tag==f'{{{NS["p"]}}}pic') or (kind=='chart' and e.find('.//c:chart',NS) is not None)]
   if len(expected)!=len(actual):raise ValueError(f'{name}: {kind} count mismatch')
   for e,n in zip(actual,expected):e.find('.//p:cNvPr',NS).set('name',f'role:{n["role"]}|id:{n["id"]}')
  content[name]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 if spec.get('metadata') and 'docProps/core.xml' in content:
  props=ET.fromstring(content['docProps/core.xml'])
  namespaces={'dc':'http://purl.org/dc/elements/1.1/','cp':'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'}
  for tag,value in [('dc:title',spec['metadata']['title']),('dc:creator',spec['metadata']['authors']),('cp:lastModifiedBy',spec['metadata']['authors'])]:
   prefix,local=tag.split(':');q=f'{{{namespaces[prefix]}}}{local}'
   e=props.find(q)
   if e is None:e=ET.SubElement(props,q)
   e.text='; '.join(value) if isinstance(value,list) else str(value)
  content['docProps/core.xml']=ET.tostring(props,encoding='utf-8',xml_declaration=True)
 temp=file.with_suffix('.tagged.pptx')
 with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in content.items():z.writestr(n,b)
 os.replace(temp,file)
 normalise(file)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate',type=Path);p.add_argument('layout',type=Path);a=p.parse_args();tag(a.candidate,json.loads(a.layout.read_text()))
if __name__=='__main__':main()
