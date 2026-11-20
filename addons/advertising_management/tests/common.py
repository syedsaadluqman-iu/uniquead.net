from odoo.tools import file_open


class TemplateImportMixin:

    def _run_template_import(self, model, sheet, template_index=0, context=None):
        """Import the module's own template the way the Import screen does:
        headers are auto-matched to fields and every column must match.
        ``context`` stands for the context of the list view the import is started from."""
        template = self.env[model].get_import_templates()[template_index]['template']
        with file_open(template.replace('/advertising_management/', 'advertising_management/', 1), 'rb') as f:
            content = f.read()
        wizard = self.env['base_import.import'].with_context(**(context or {})).create({
            'res_model': model,
            'file': content,
            'file_name': 'template.xlsx',
            'file_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        options = {'has_headers': True, 'quoting': '"', 'separator': ',', 'sheet': sheet,
                   'float_thousand_separator': ',', 'float_decimal_separator': '.',
                   'date_format': '', 'datetime_format': ''}
        preview = wizard.parse_preview(options)
        self.assertFalse(preview.get('error'), preview)
        matches = preview['matches']
        fields_list = ['/'.join(matches[i]) if matches.get(i) else False
                       for i in range(len(preview['headers']))]
        self.assertTrue(all(fields_list), list(zip(preview['headers'], fields_list)))
        result = wizard.execute_import(fields_list, preview['headers'], options)
        self.assertFalse(result.get('messages'), result)
        return result
