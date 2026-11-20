{
    'name': 'Advertising Site Rental Management',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Manage advertising sites, availability, quotations and bookings',
    'description': """
Manage the rental of advertising sites (billboards, wallscapes, rooftops,
digital screens...): site catalogue, availability schedule, quotations
(built on Sales) and confirmed bookings.
    """,
    'author': 'Unique Advertising',
    'depends': ['mail', 'sale_management', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/product_data.xml',
        'data/site_type_data.xml',
        'data/cron_data.xml',
        'views/site_type_views.xml',
        'views/site_views.xml',
        'views/booking_views.xml',
        'views/sale_order_views.xml',
        'views/menu_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}
