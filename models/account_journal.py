# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
import logging

class AccountJournal(models.Model):
    _inherit = "account.journal"

    tipo_documento = fields.Selection([("1", "Recibos de Servicios Públicos"), ("2", "Documentos del Sistema Financiero y Seguros"), ("3", "Boletos de Transportes Aéreos de Pasajeros"), ("4", "Otros autorizados por el SAR")], string="Tipo de documento")
