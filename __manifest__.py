# -*- encoding: utf-8 -*-

{
    'name': 'Honduras - Reportes y funcionalidad extra',
    'version': '1.0',
    'category': 'Localization',
    'description': """ Reportes requeridos para llevar una contabilidad en Honduras. """,
    'author': 'Aquih, S.A.',
    'website': 'http://aquih.com/',
    'depends': ['l10n_hn'],
    'data': [
        'views/account_move_views.xml',
        'views/account_journal_views.xml',
        'views/report.xml',
        'views/reporte_compras.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [],
    'installable': True,
}
