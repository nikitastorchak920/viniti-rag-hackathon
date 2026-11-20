"""Validate the recommended RAG CSV format; this is not an official VINITI scorer.

Usage: python tools/check_submission.py submission test
Exit 0: checks completed without findings; 1: structural errors; 2: unresolved checks.
The checker cannot certify semantic correctness or annotation completeness.
"""
import argparse
import csv
import json
import math
import pathlib
import re
import sys
import subprocess
import tempfile
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DEFAULT_SCHEMA = pathlib.Path(__file__).resolve().parent.parent / 'submission_template' / 'schema.json'
NUMBERS = {
    'publications': {'year'},
    'configurations': {'chunk_size', 'chunk_overlap', 'top_k'},
    'experiments': {'latency_ms', 'tokens_per_query', 'sample_size'},
    'results': {'metric_k', 'metric_value', 'baseline_value', 'sample_size', 'normalized_value', 'source_page'},
    'issues': {'source_page'},
}
POSITIVE_INTS = {'year', 'source_page'}
NONNEGATIVE_INTS = {'top_k', 'metric_k'}
NONNEGATIVE = {'chunk_size', 'chunk_overlap', 'latency_ms', 'tokens_per_query', 'sample_size'}
SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*\Z')

def same_at_reported_precision(a, b):
    """Accept a coarser explicitly reported rounding; never rewrite either value."""
    try:
        x,y=Decimal(a),Decimal(b)
        if not x.is_finite() or not y.is_finite(): return False
        if x==y:return True
        ex,ey=x.as_tuple().exponent,y.as_tuple().exponent
        if ex==ey:return False
        coarse,fine=(x,y) if ex>ey else (y,x)
        return fine.quantize(Decimal(1).scaleb(coarse.as_tuple().exponent),rounding=ROUND_HALF_UP)==coarse
    except (InvalidOperation,ValueError):return False

def norm(text):
    """Preserve words, numbers, minus signs, units and Cyrillic; normalize typography."""
    text = unicodedata.normalize('NFKC', text).replace('\u00ad', '')
    text = re.sub(r'(?<=\w)-\s*\r?\n\s*(?=\w)', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def read_pages(path):
    """Independent text extractions; never concatenate their text into a fake quote."""
    variants = []
    failures = []
    try:
        from pypdf import PdfReader
        variants.append([p.extract_text() or '' for p in PdfReader(path).pages])
    except Exception as exc:
        failures.append('pypdf: ' + str(exc))
    try:
        import pymupdf
        with pymupdf.open(path) as document:
            variants.append([p.get_text() or '' for p in document])
    except Exception as exc:
        failures.append('PyMuPDF: ' + str(exc))
    if not variants:
        raise ValueError('; '.join(failures))
    if len({len(pages) for pages in variants}) != 1:
        raise ValueError('PDF parsers disagree about page count; manual review required')
    return [[pages[i] for pages in variants] for i in range(len(variants[0]))]

def read_pages_with_ocr(path, executable='tesseract', language='eng', dpi=300):
    """OCR actual image-only PDF pages. Never trust supplied/transcribed sidecars.

    OCR is an additional same-page text variant, not fuzzy verification. A missed
    citation remains unresolved; numbers and minus signs are never auto-corrected.
    Requires the Tesseract executable and its selected language data separately.
    """
    import pymupdf
    pages=read_pages(path)
    with pymupdf.open(path) as document, tempfile.TemporaryDirectory(prefix='rag_ocr_') as temp:
        if len(document)!=len(pages):
            raise ValueError('OCR renderer and text parsers disagree about page count')
        for i,page in enumerate(document):
            if any(norm(text) for text in pages[i]):
                continue
            png=pathlib.Path(temp)/('page_'+str(i+1)+'.png')
            page.get_pixmap(dpi=dpi,colorspace=pymupdf.csRGB,alpha=False).save(png)
            try:
                process=subprocess.run(
                    [str(executable),str(png),'stdout','-l',language,'--psm','3'],
                    capture_output=True,encoding='utf-8',errors='replace',
                    check=True,timeout=120)
            except (OSError,subprocess.SubprocessError) as exc:
                raise ValueError('OCR failed on page '+str(i+1)+
                    '; install Tesseract/language data or set --tesseract: '+str(exc)) from exc
            pages[i].append(process.stdout or '')
    return pages

def validate(folder, pdfdir=None, schema_path=DEFAULT_SCHEMA, template=False, page_reader=read_pages):
    schema = json.loads(pathlib.Path(schema_path).read_text(encoding='utf-8'))
    folder = pathlib.Path(folder)
    errors, warnings, data, index = [], [], {}, {}
    quotes = {'requested': 0, 'matched': 0, 'unresolved': 0}
    def err(location, message): errors.append(f'{location}: {message}')
    def warn(location, message): warnings.append(f'{location}: {message}')
    for table, columns in schema['tables'].items():
        data[table] = []
        path = folder / (table + '.csv')
        try:
            with path.open(encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f, strict=True)
                if reader.fieldnames != columns:
                    err(table, 'columns/order differ from schema: expected ' + ','.join(columns))
                for n, row in enumerate(reader, 2):
                    if None in row or any(value is None for value in row.values()):
                        err(f'{table}:{n}', 'incorrect number of CSV cells')
                    clean = {c: (row.get(c) or '').strip() for c in columns}
                    clean['_line'] = n
                    data[table].append(clean)
        except (OSError, UnicodeError, csv.Error) as exc:
            err(table, str(exc))
        index[table] = {}
        for row in data[table]:
            loc = f'{table}:{row["_line"]}'
            pid = row['publication_id']
            rid = row[schema['keys'][table]]
            if not SAFE_ID.fullmatch(pid): err(loc, 'empty or unsafe publication_id')
            if not rid: err(loc, 'empty primary key')
            key = (pid, rid)
            if key in index[table]: err(loc, 'duplicate primary key ' + str(key))
            index[table][key] = row
            for field in NUMBERS.get(table, set()):
                value = row.get(field, '')
                if not value: continue
                try:
                    number = float(value)
                    if not math.isfinite(number): raise ValueError()
                    if field in POSITIVE_INTS and (not re.fullmatch(r'[0-9]+', value) or number < 1):
                        err(loc, field + ' must be a positive integer')
                    if field in NONNEGATIVE_INTS and not re.fullmatch(r'[0-9]+', value):
                        err(loc, field + ' must be a nonnegative integer (0 denotes no retrieved context)')
                    if field in NONNEGATIVE and number < 0: err(loc, field + ' must be nonnegative')
                    if field == 'sample_size' and not re.fullmatch(r'[0-9]+', value):
                        err(loc, 'sample_size must be an integer')
                except ValueError: err(loc, field + ' must be finite numeric data')
    for qualified, allowed in schema['enums'].items():
        table, field = qualified.split('.')
        for row in data[table]:
            if row[field] and row[field] not in allowed:
                err(f'{table}:{row["_line"]}', field + ' is not in ' + str(allowed))
    pubs = {r['publication_id']: r for r in data['publications']}
    if not template and not pubs: err('publications', 'no publications submitted')
    for pid, pub in pubs.items():
        if pub['in_scope'] not in {'true', 'false'}: err(pid, 'in_scope must be true or false')
        if pub['in_scope'] == 'false' and not pub['exclusion_reason']: err(pid, 'excluded without a reason')
        if pub['in_scope'] == 'true' and pub['exclusion_reason']: err(pid, 'included with an exclusion reason')
    for table, rows in data.items():
        if table == 'publications': continue
        for row in rows:
            loc = f'{table}:{row["_line"]}'
            pub = pubs.get(row['publication_id'])
            if not pub: err(loc, 'publication does not exist')
            elif pub['in_scope'] == 'false': err(loc, 'excluded publication has dependent rows')
    def reference(table, field, target, many=False):
        for row in data[table]:
            values = row[field].split(';') if many else [row[field]]
            for value in filter(None, map(str.strip, values)):
                if (row['publication_id'], value) not in index[target]:
                    err(f'{table}:{row["_line"]}', f'{field}={value} does not exist in {target} in this publication')
    for field, table in [('experiment_id', 'experiments'), ('config_id', 'configurations'), ('dataset_id', 'datasets'), ('task_id', 'tasks'), ('duplicate_of', 'results')]:
        reference('results', field, table)
    reference('issues', 'record_ids', 'results', many=True)
    for row in data['results']:
        loc = f'results:{row["_line"]}'
        if not row['metric_name']: err(loc, 'metric_name is empty')
        if not row['extraction_status']: err(loc, 'extraction_status is empty')
        if not row['result_origin']: err(loc, 'result_origin is empty')
        if row['result_origin'] == 'cited' and not row['cited_publication_id']: err(loc, 'cited result without citation identifier')
        if row['result_origin'] == 'primary' and row['cited_publication_id']: err(loc, 'primary result has cited_publication_id')
        if row['extraction_status'] == 'extracted':
            if not row['raw_value']: err(loc, 'extracted result without raw_value')
            if not row['metric_value']: warn(loc, 'extracted result without numeric metric_value')
            if not row['source_page']: err(loc, 'extracted result without source_page')
            if not any(row[k] for k in ['source_fragment','source_table','source_figure']): err(loc, 'extracted result without a source locator')
            if row['result_origin'] == 'primary':
                for field in ['experiment_id','config_id','dataset_id','task_id']:
                    if not row[field]: warn(loc, 'primary result without ' + field)
        elif row['metric_value'] or row['normalized_value']:
            warn(loc, 'non-extracted status with a numeric value: review status')
        if row['normalized_value'] and row['metric_value']:
            try:
                if float(row['normalized_value']) != float(row['metric_value']): err(loc, 'metric_value differs from normalized_value')
            except ValueError: pass
        if row['normalized_unit'] != row['metric_unit'] and row['normalized_value']:
            err(loc, 'metric_unit differs from normalized_unit')
        if row['metric_direction'] and row['metric_direction'] not in schema['recommended_enums']['results.metric_direction']:
            warn(loc, 'nonstandard metric_direction; document meaning in note')
        # A fractional threshold such as OC@0.8 is not a retrieval cutoff k.
        if re.search(r'@\d+(?![\d.])\b', row['metric_name']) and not row['metric_k']: warn(loc, '@k metric without metric_k')
        if row['metric_value'] and row['metric_unit'] in {'fraction','%'}:
            try:
                value=float(row['metric_value']); limit=1 if row['metric_unit']=='fraction' else 100
                # Only metrics intrinsically bounded by the explicitly supplied scale.
                if re.fullmatch(r'(?i)(accuracy|precision|recall|f1|exact match|em|hit(?:s)?(?:@\d+)?|mrr|ndcg)(?:@\d+)?',row['metric_name']) and not 0<=value<=limit:
                    warn(loc, 'value outside declared metric scale; preserve value and add an issue')
            except ValueError: pass
        seen=set(); current=row
        while current.get('duplicate_of'):
            key=(current['publication_id'],current['result_id'])
            if key in seen:
                err(loc,'duplicate_of cycle');break
            seen.add(key)
            target=index['results'].get((current['publication_id'],current['duplicate_of']))
            if target is None: break
            if current is row:
                fields=['experiment_id','config_id','dataset_id','task_id','metric_name','metric_variant','metric_k','metric_unit','metric_value','aggregation','sample_size','result_origin','cited_publication_id']
                for field in fields:
                    a,b=row[field],target[field]
                    equal=(a==b)
                    if field=='metric_value' and a and b:
                        equal=same_at_reported_precision(a,b)
                    if not equal: err(loc, 'duplicate_of differs in '+field)
            current=target
    for table in ['results','issues']:
        for row in data[table]:
            if row['source_fragment']:
                quotes['requested']+=1
                if not row['source_page']: err(f'{table}:{row["_line"]}','quote without page')
    if template:
        if any(data.values()): err('template', 'template mode expects header-only files')
    elif pdfdir is None:
        warn('PDF','PDF directory not provided: source checks not performed')
    else:
        pdfdir=pathlib.Path(pdfdir).resolve()
        actual={p.stem for p in pdfdir.glob('*.pdf')}
        for pid in sorted(actual-pubs.keys()): err('publications',pid+'.pdf has no publication row')
        for pid in sorted(pubs.keys()-actual): err('PDF',pid+'.pdf is missing')
        cache={}
        for table in ['results','issues']:
            for row in data[table]:
                pid=row['publication_id'];loc=f'{table}:{row["_line"]}'
                frag,page=row['source_fragment'],row['source_page']
                if not page: continue
                if not SAFE_ID.fullmatch(pid) or pid not in actual: continue
                if not re.fullmatch(r'[1-9][0-9]*',page): continue
                if pid not in cache:
                    try:
                        cache[pid]=[[norm(t) for t in (p if isinstance(p,list) else [p])] for p in page_reader(pdfdir/(pid+'.pdf'))]
                    except Exception as exc:
                        cache[pid]=None;warn(pid,'cannot read PDF/text: '+str(exc))
                pages=cache[pid]
                if pages is None:
                    if frag: quotes['unresolved']+=1
                    continue
                n=int(page)
                if not 1<=n<=len(pages):
                    err(loc,'source_page outside PDF');
                    if frag: quotes['unresolved']+=1
                    continue
                if not frag:
                    if table=='results' and row['extraction_status']=='extracted': warn(loc,'table/figure locator only: visual evidence requires manual review')
                    continue
                needle=norm(frag)
                if needle and any(needle in text for text in pages[n-1]): quotes['matched']+=1
                else:
                    quotes['unresolved']+=1
                    other=[str(i+1) for i,variants in enumerate(pages) if needle and any(needle in t for t in variants)]
                    hint='; found on pages '+','.join(other) if other else ''
                    missing_text='; no text layer/OCR text on this page: use --ocr or review the image' if not any(pages[n-1]) else ''
                    warn(loc,'quote not found on declared page'+hint+missing_text)
    if not template:
        for pid,pub in pubs.items():
            if pub['in_scope']=='true' and not any(r['publication_id']==pid for r in data['results']):
                warn(pid,'in-scope publication has no results; completeness has not been established')
    report={'errors':errors,'warnings':warnings,'rows':{t:len(r) for t,r in data.items()},'quotes':quotes,'semantic_completeness_certified':False}
    report['exit_code']=1 if errors else (2 if warnings or quotes['matched']<quotes['requested'] else 0)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('submission',type=pathlib.Path)
    parser.add_argument('pdfdir',nargs='?',type=pathlib.Path)
    parser.add_argument('--schema',type=pathlib.Path,default=DEFAULT_SCHEMA)
    parser.add_argument('--template',action='store_true')
    parser.add_argument('--json-report',type=pathlib.Path)
    parser.add_argument('--ocr',action='store_true',help='Run local Tesseract on image-only pages; unmatched OCR quotes remain unresolved.')
    parser.add_argument('--tesseract',default='tesseract',help='Tesseract executable path (requires a separate installation).')
    parser.add_argument('--ocr-language',default='eng',help='Installed Tesseract language(s), for example eng or eng+rus.')
    parser.add_argument('--ocr-dpi',type=int,default=300,choices=range(150,601),metavar='150..600')
    args=parser.parse_args()
    reader=(lambda path:read_pages_with_ocr(path,args.tesseract,args.ocr_language,args.ocr_dpi)) if args.ocr else read_pages
    try: report=validate(args.submission,args.pdfdir,args.schema,args.template,page_reader=reader)
    except (OSError,ValueError) as exc:
        print('ERROR:',exc);return 1
    report['source_text_mode']='native plus local OCR on image-only pages' if args.ocr else 'native PDF text only'
    for message in report['errors']:print('ERROR:',message)
    for message in report['warnings']:print('REVIEW:',message)
    print(json.dumps({k:v for k,v in report.items() if k not in ['errors','warnings']},ensure_ascii=False))
    print(f'Errors: {len(report["errors"])}; review items: {len(report["warnings"])}')
    if args.json_report:args.json_report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report['exit_code']

if __name__=='__main__':sys.exit(main())
