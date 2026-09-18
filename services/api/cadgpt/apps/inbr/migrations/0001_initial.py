import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='PdfDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_key', models.CharField(max_length=255, unique=True)),
                ('pdf_name', models.TextField()),
                ('file_path', models.TextField()),
                ('storage_uri', models.TextField(blank=True, null=True)),
                ('volume_number', models.PositiveIntegerField(blank=True, null=True)),
                ('edition_year', models.PositiveIntegerField(blank=True, null=True)),
                ('edition_code', models.CharField(max_length=255)),
                ('title_fa', models.TextField(blank=True, null=True)),
                ('source_sha256', models.CharField(max_length=64, unique=True)),
                ('file_size_bytes', models.BigIntegerField(blank=True, null=True)),
                ('page_count', models.PositiveIntegerField(blank=True, null=True)),
                ('metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'pdf_document',
            },
        ),
        migrations.CreateModel(
            name='PdfPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page_key', models.CharField(max_length=255, unique=True)),
                ('pdf_page_number', models.PositiveIntegerField()),
                ('printed_page_label', models.TextField(blank=True, null=True)),
                ('extraction_route', models.CharField(default='pending', max_length=32)),
                ('status', models.CharField(default='pending', max_length=32)),
                ('native_text', models.TextField(blank=True, null=True)),
                ('native_layout_json', models.JSONField(blank=True, null=True)),
                ('native_text_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('paddle_text', models.TextField(blank=True, null=True)),
                ('paddle_result_json', models.JSONField(blank=True, null=True)),
                ('paddle_text_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('luna_transcript_json', models.JSONField(blank=True, null=True)),
                ('luna_transcript_text', models.TextField(blank=True, null=True)),
                ('luna_transcript_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('luna_response_uri', models.TextField(blank=True, null=True)),
                ('luna_response_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('metadata', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document', models.ForeignKey(db_column='document_key', on_delete=django.db.models.deletion.CASCADE, related_name='pages', to='inbr.pdfdocument', to_field='document_key')),
            ],
            options={
                'db_table': 'pdf_page',
            },
        ),
        migrations.CreateModel(
            name='RuleCandidate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('candidate_key', models.CharField(max_length=255, unique=True)),
                ('source_record_key', models.TextField()),
                ('source_record_type', models.TextField(blank=True, null=True)),
                ('source_page_ids', models.JSONField(default=list)),
                ('source_text_fa', models.TextField(blank=True, null=True)),
                ('source_text_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('transcript_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('extraction_file_uri', models.TextField(blank=True, null=True)),
                ('extraction_file_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('extraction_json', models.JSONField(default=dict)),
                ('rule_key', models.TextField(blank=True, null=True)),
                ('implementation_type', models.CharField(blank=True, max_length=32, null=True)),
                ('semantic_fingerprint', models.CharField(blank=True, max_length=64, null=True)),
                ('ids_specification', models.JSONField(blank=True, null=True)),
                ('ids_xml_uri', models.TextField(blank=True, null=True)),
                ('ids_xml_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('sidecar_uri', models.TextField(blank=True, null=True)),
                ('sidecar_sha256', models.CharField(blank=True, max_length=64, null=True)),
                ('compiler_version', models.TextField(blank=True, null=True)),
                ('status', models.CharField(default='extracted', max_length=32)),
                ('reason_code', models.TextField(blank=True, null=True)),
                ('validation_json', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document', models.ForeignKey(db_column='document_key', on_delete=django.db.models.deletion.PROTECT, related_name='rule_candidates', to='inbr.pdfdocument', to_field='document_key')),
                ('primary_page', models.ForeignKey(db_column='primary_page_key', on_delete=django.db.models.deletion.PROTECT, related_name='rule_candidates', to='inbr.pdfpage', to_field='page_key')),
            ],
            options={
                'db_table': 'rule_candidate',
            },
        ),
        migrations.AddIndex(
            model_name='pdfpage',
            index=models.Index(fields=['document', 'pdf_page_number'], name='pdf_page_document_page_idx'),
        ),
        migrations.AddIndex(
            model_name='pdfpage',
            index=models.Index(fields=['luna_transcript_sha256'], name='pdf_page_luna_hash_idx'),
        ),
        migrations.AddConstraint(
            model_name='pdfpage',
            constraint=models.UniqueConstraint(fields=('document', 'pdf_page_number'), name='pdf_page_document_page_number_unique'),
        ),
        migrations.AddIndex(
            model_name='rulecandidate',
            index=models.Index(fields=['document', 'primary_page'], name='rule_candidate_document_idx'),
        ),
        migrations.AddIndex(
            model_name='rulecandidate',
            index=models.Index(fields=['status', 'implementation_type'], name='rule_candidate_status_idx'),
        ),
        migrations.AddIndex(
            model_name='rulecandidate',
            index=models.Index(fields=['semantic_fingerprint'], name='rule_candidate_fingerprint_idx'),
        ),
    ]
