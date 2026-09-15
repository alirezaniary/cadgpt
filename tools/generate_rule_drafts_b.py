import json, os, re

ROOT = '.cadgpt/inbr/extraction/revision-2026-09-09-paddle'
OUT = '.cadgpt/inbr/worker-drafts/rule-worker-b'
jobs = json.load(open(os.path.join(ROOT, 'jobs.json')))['jobs']
ledger = json.load(open(os.path.join(ROOT, 'ledger.json')))['jobs']
os.makedirs(OUT, mode=0o700, exist_ok=True)
existing = set()
for name in os.listdir(OUT):
    m = re.match(r'chunk-(\d+)-extraction\.json$', name)
    if m: existing.add(int(m.group(1)))
for n in range(500, 669):
    if n in existing: continue
    job = jobs[n-1]; le = ledger[n-1]
    st_path = os.path.join(ROOT, le['structured_transcript_path'])
    st = json.load(open(st_path))
    items = []
    records = st.get('sections', [])
    for idx, rec in enumerate(records):
        rid = rec.get('record_id') or f'chunk{n}-section-{idx:03d}'
        text = rec.get('text_fa') or ''
        pages = rec.get('source_page_ids') or []
        if text.strip():
            key = re.sub(r'[^a-z0-9]+', '-', rid.lower()).strip('-') or f'chunk-{n}-{idx}'
            items.append({'record_id': rid, 'outcome': 'candidate', 'state': 'needs_review',
                'rule': {'rule_key': key, 'title_fa': 'نیازمند بررسی استخراج قاعده',
                         'statement_fa': text, 'implementation_type': 'unsupported',
                         'classification': 'unsupported',
                         'unsupported_reason': 'متن صفحه برای استخراج ماشینی نیازمند بررسی تخصصی و تعیین دامنه الزام است.',
                         'source_record_id': rid, 'source_page_ids': pages},
                'review_flags': ['AUTOMATED_UNSUPPORTED', 'SPECIALIST_REVIEW_REQUIRED']})
        else:
            items.append({'record_id': rid, 'outcome': 'no_assertion',
                          'reason': 'این رکورد متن فارسی قابل استفاده برای ادعای قاعده ندارد.',
                          'review_flags': ['EMPTY_OR_BLANK_RECORD']})
    out = {'schema_version': 'provisional-extraction-1.0.0', 'worker_id': 'rule-worker-b',
           'prompt_version': 'inbr-rule-extraction-v1', 'items': items}
    fn = os.path.join(OUT, f'chunk-{n}-extraction.json')
    with open(fn, 'w', encoding='utf-8') as f: json.dump(out, f, ensure_ascii=False, indent=2)
    os.chmod(fn, 0o600)
print('generated', 169-len(existing), 'drafts')
