from odoo import fields, models


class AdvertisingSitePhoto(models.Model):
    _name = 'advertising.site.photo'
    _description = 'Advertising Site Photograph'
    _order = 'sequence, id'

    site_id = fields.Many2one('advertising.site', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Caption')
    sequence = fields.Integer(default=10)
    image = fields.Image(required=True, max_width=1920, max_height=1920)
    image_thumb = fields.Image(string='Thumbnail', related='image', max_width=256, max_height=256, store=True)
    date = fields.Date(default=fields.Date.context_today)
