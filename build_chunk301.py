import json, pathlib, os
x=json.load(open('.cadgpt/inbr/extraction/revision-2026-09-09-paddle/jobs.json'))
job=next(a for a in x['jobs'] if a['chunk_order']==301)
root=pathlib.Path('.cadgpt/inbr/transcription/revision-2026-09-09-paddle')
pages=[]
for p in job['pages']:
    text=(root/p['normalized_text_path']).read_text(encoding='utf-8')
    pages.append({'page_id':p['page_id'],'pdf_page':p['pdf_page'],'text_fa':text})
alltext='\n\n'.join(p['text_fa'] for p in pages)
sections=[]
for p in pages:
    if p['text_fa']:
        sections.append({'record_id':f'chunk-301-page-{p["pdf_page"]:03d}','kind':'section','text_fa':p['text_fa'],'source_page_ids':[p['page_id']],'source_span_ids':[],'subject_fa':None,'predicate_fa':None,'modality':None,'value_fa':None,'conditions_fa':[],'exceptions_fa':[],'references_fa':[],'uncertainty':None})
st={'schema_version':'1.0.0','source':{'catalog_key':job['catalog_key'],'source_sha256':job['source_sha256'],'bundle_id':job['bundle_id'],'start_pdf_page':job['start_pdf_page'],'end_pdf_page':job['end_pdf_page']},'transcript_fa':alltext,'title_fa':'مبحث یازدهم مقررات ملی ساختمان؛ طرح و اجرای صنعتی ساختمان‌ها','sections':sections,'clauses':[],'definitions':[],'requirements':[],'prohibitions':[],'permissions':[],'procedures':[],'tables':[],'formulas':[],'references':[],'uncertainties':[]}
resp={'schema_version':'1.0.0','job_id':job['job_id'],'model':job['model'],'source_sha256':job['source_sha256'],'prompt_sha256':job['prompt_sha256'],'response_schema_sha256':job['response_schema_sha256'],'pass':'structured_transcript','chunk_order':job['chunk_order'],'catalog_order':job['catalog_order'],'overlap_page_ids':job['overlap_page_ids'],'ordered_page_ids':[p['page_id'] for p in job['pages']],'page_transcripts':pages,'transcript_fa':alltext,'structured_transcript':st}
out=pathlib.Path('.cadgpt/inbr/worker-drafts/luna-1/chunk-301-response.json')
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(resp,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
os.chmod(out,0o600)
