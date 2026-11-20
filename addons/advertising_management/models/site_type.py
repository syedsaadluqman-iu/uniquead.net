from odoo import fields, models


class AdvertisingSiteType(models.Model):
    _name = 'advertising.site.type'
    _description = 'Advertising Site Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    site_count = fields.Integer(compute='_compute_site_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'This site type already exists.'),
    ]

    def _compute_site_count(self):
        data = self.env['advertising.site']._read_group(
            [('site_type_id', 'in', self.ids)], ['site_type_id'], ['__count'])
        counts = {site_type.id: count for site_type, count in data}
        for site_type in self:
            site_type.site_count = counts.get(site_type.id, 0)
