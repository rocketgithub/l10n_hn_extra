# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
import logging

class AccountMove(models.Model):
    _inherit = "account.move"

    cai = fields.Char(string="CAI")
    compra_con_oce = fields.Selection([("si", "Si"), ("no", "No")], string="Compra con OCE")
    numero_resolucion = fields.Char(string="No. resolución")
    fecha_resolucion = fields.Date("Fecha resolución")

    numero_dua = fields.Char(string="Número de la DUA")
    numero_liquidacion = fields.Char(string="Número de liquidación")
    numero_resolucion_exoneracion = fields.Char(string="Número resolución exoneración")
    fecha_vencimiento_resolucion = fields.Date("Fecha vencimiento resolución")
