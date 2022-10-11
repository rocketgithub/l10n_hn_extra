# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import time
import xlsxwriter
import base64
import io
import logging

class AsistenteReporteCompras(models.TransientModel):
    _name = 'l10n_hn_extra.asistente_reporte_compras_hn'

    fecha_desde = fields.Date(string="Fecha Inicial", required=True, default=lambda self: time.strftime('%Y-%m-01'))
    fecha_hasta = fields.Date(string="Fecha Final", required=True, default=lambda self: time.strftime('%Y-%m-%d'))
    impuesto_id = fields.Many2one("account.tax", string="Impuesto", required=True)
    tipo_reporte = fields.Selection([("detalle_compras", "Detalle compras"), ("otros_comprobantes_compra", "Otros comprobantes de compra"), ("detalle_importaciones", "Detalle de importaciones")], string="Reporte", required=True)
    diario_ids = fields.Many2many("account.journal", string="Diarios", required=True)
    name = fields.Char('Nombre archivo', size=32)
    archivo = fields.Binary('Archivo', filters='.xls')

    def lineas(self):
        totales = {}

        totales['num_facturas'] = 0
        totales['compra'] = {'exento':0,'neto':0,'iva':0,'total':0}
        totales['servicio'] = {'exento':0,'neto':0,'iva':0,'total':0}
        totales['combustible'] = {'exento':0,'neto':0,'iva':0,'total':0}
        totales['importacion'] = {'exento':0,'neto':0,'iva':0,'total':0}
        totales['pequeño'] = {'exento':0,'neto':0,'iva':0,'total':0}

        journal_ids = [x for x in self.diario_ids.ids]
        filtro = [
            ('state','in',['posted']),
            ('journal_id','in',journal_ids),
            ('date','<=',self.fecha_hasta),
            ('date','>=',self.fecha_desde),
        ]
        
        if 'type' in self.env['account.move'].fields_get():
            filtro.append(('type','in',['in_invoice','in_refund']))
        else:
            filtro.append(('move_type','in',['in_invoice','in_refund']))

        facturas = self.env['account.move'].search(filtro)
        lineas = []
        for f in facturas:
            totales['num_facturas'] += 1

            tipo_cambio = 1
            if f.currency_id.id != f.company_id.currency_id.id:
                total = 0
                for l in f.line_ids:
                    if l.account_id.reconcile:
                        total += l.debit - l.credit
                if f.amount_total != 0:
                    tipo_cambio = abs(total / f.amount_total)

            tipo = 'FACT'
            tipo_interno_factura = f.type if 'type' in f.fields_get() else f.move_type
            if tipo_interno_factura != 'in_invoice':
                tipo = 'NC'
            if f.nota_debito:
                tipo = 'ND'
            if f.partner_id.pequenio_contribuyente:
                tipo += ' PEQ'
           
            numero = f.ref or ''
            
            # Por si usa factura electrónica
            if 'firma_fel' in f.fields_get() and f.firma_fel:
                numero = str(f.serie_fel) + '-' + str(f.numero_fel)

            numero_split = numero.split('-')
            if len(numero_split) == 4:
                establecimiento = numero_split[0]
                punto_emision = numero_split[1]
                tipo_documento = numero_split[2]
                correlativo = numero_split[3]
            else:
                establecimiento = ''
                punto_emision = ''
                tipo_documento = ''
                correlativo = ''
            
            
            linea = {
                'estado': f.state,
                'tipo': tipo,
                'numero': numero,
                'rtn_proveedor': f.partner_id.vat,
                'proveedor': f.partner_id.name,
                'fecha': f.invoice_date,
                'cai': f.cai,
                'establecimiento': establecimiento,
                'punto_emision': punto_emision,
                'tipo_documento': tipo_documento,
                'correlativo': correlativo,
                'compra_con_oce': f.compra_con_oce,
                'numero_resolucion': f.numero_resolucion,
                'fecha_resolucion': f.fecha_resolucion,
                'tipo_documento_diario': f.journal_id.tipo_documento,
                'numero_dua': f.numero_dua,
                'numero_liquidacion': f.numero_liquidacion,
                'numero_resolucion_exoneracion': f.numero_resolucion_exoneracion,
                'fecha_vencimiento_resolucion': f.fecha_vencimiento_resolucion,
                'compra': 0,
                'compra_exento': 0,
                'servicio': 0,
                'servicio_exento': 0,
                'combustible': 0,
                'combustible_exento': 0,
                'importacion': 0,
                'importacion_exento': 0,
                'pequeño': 0,
                'pequeño_exento': 0,
                'base': 0,
                'iva': 0,
                'total': 0
            }

            for l in f.invoice_line_ids:
                precio = ( l.price_unit * (1-(l.discount or 0.0)/100.0) ) * tipo_cambio
                if tipo == 'NC':
                    precio = precio * -1

                tipo_linea = f.tipo_gasto or 'mixto'
                if tipo_linea == 'mixto':
                    if l.product_id.type == 'product':
                        tipo_linea = 'compra'
                    else:
                        tipo_linea = 'servicio'

                if f.partner_id.pequenio_contribuyente:
                    tipo_linea = 'pequeño'

                r = l.tax_ids.compute_all(precio, currency=f.currency_id, quantity=l.quantity, product=l.product_id, partner=f.partner_id)

                linea['base'] += r['total_excluded']
                totales[tipo_linea]['total'] += r['total_excluded']
                if len(l.tax_ids) > 0:
                    linea[tipo_linea] += r['total_excluded']
                    totales[tipo_linea]['neto'] += r['total_excluded']
                    for i in r['taxes']:
                        if i['id'] == self.impuesto_id.id:
                            linea['iva'] += i['amount']
                            totales[tipo_linea]['iva'] += i['amount']
                            totales[tipo_linea]['total'] += i['amount']
                        elif i['amount'] > 0:
                            linea[tipo_linea+'_exento'] += i['amount']
                            totales[tipo_linea]['exento'] += i['amount']
                else:
                    linea[tipo_linea+'_exento'] += r['total_excluded']
                    totales[tipo_linea]['exento'] += r['total_excluded']

                linea['total'] += precio * l.quantity

            for llave in linea:
                if not linea[llave] and llave != 'compra_exento':
                 linea[llave] = ''

            lineas.append(linea)
            
        lineas = sorted(lineas, key = lambda i: str(i['fecha']) + str(i['numero']))

        return { 'lineas': lineas, 'totales': totales }

    def detalle_compras(self, datos):
        f = io.BytesIO()
        libro = xlsxwriter.Workbook(f)
        hoja = libro.add_worksheet('Reporte')
        formato_encabezado = libro.add_format({'border':2, 'font_size':9, 'align': 'center', 'valign': 'center', 'bold': True, 'bg_color': '#CCCCCC', 'font_color': '#000000'})

        hoja.merge_range('A1:C1', "", formato_encabezado)
        hoja.write(0, 0, 'DETALLE COMPRAS LOCALES', formato_encabezado)
        hoja.merge_range('E2:H2', "", formato_encabezado)
        hoja.write(1, 4, 'NÚMERO DE DOCUMENTO FISCAL', formato_encabezado)
        hoja.merge_range('I2:K2', "", formato_encabezado)
        hoja.write(1, 8, 'ORDENES DE COMPRA EXCENTA (OCE)', formato_encabezado)
        hoja.merge_range('L2:N2', "", formato_encabezado)
        hoja.write(1, 11, 'SUB TOTAL DE COMPRAS', formato_encabezado)
        hoja.merge_range('O2:P2', "", formato_encabezado)
        hoja.write(1, 14, 'CRÉDITO FISCAL ISV', formato_encabezado)
        y = 2
        hoja.set_column('A:A', 22)
        hoja.write(y, 0, 'R.T.N. DEL PROVEEDOR', formato_encabezado)
        hoja.set_column('B:B', 43)
        hoja.write(y, 1, 'NOMBRES APELLIDOS O RAZÓN SOCIAL DEL PROVEEDOR', formato_encabezado)
        hoja.set_column('C:C', 20)
        hoja.write(y, 2, 'FECHA DD/MM/AAAA', formato_encabezado)
        hoja.set_column('D:D', 35)
        hoja.write(y, 3, 'CAI', formato_encabezado)
        hoja.set_column('E:E', 23)
        hoja.write(y, 4, 'ESTABLECIMIENTO', formato_encabezado)
        hoja.set_column('F:F', 23)
        hoja.write(y, 5, 'PUNTO DE EMISIÓN', formato_encabezado)
        hoja.set_column('G:G', 23)
        hoja.write(y, 6, 'TIPO DE DOCUMENTO', formato_encabezado)
        hoja.set_column('H:H', 20)
        hoja.write(y, 7, 'CORRELATIVO', formato_encabezado)
        hoja.set_column('I:I', 18)
        hoja.write(y, 8, 'COMPRA CON OCE', formato_encabezado)
        hoja.set_column('J:J', 18)
        hoja.write(y, 9, 'No. RESOLUCIÓN', formato_encabezado)
        hoja.set_column('K:K', 32)
        hoja.write(y, 10, 'FECHA DE LA RESOLUCIÓN DD/MM/AAAA', formato_encabezado)
        hoja.set_column('L:L', 23)
        hoja.write(y, 11, 'IMPORTE EXENTO', formato_encabezado)
        hoja.set_column('M:M', 23)
        hoja.write(y, 12, 'IMPORTE GRAVADO 15%', formato_encabezado)
        hoja.set_column('N:N', 23)
        hoja.write(y, 13, 'IMPORTE GRAVADO 18%', formato_encabezado)
        hoja.set_column('O:O', 20)
        hoja.write(y, 14, 'IMPUESTO 15%', formato_encabezado)
        hoja.set_column('P:P', 20)
        hoja.write(y, 15, 'IMPUESTO 18%', formato_encabezado)

        formato_lineas_left = libro.add_format({'border':1, 'font_size':9, 'align': 'left', 'valign': 'left',})
        formato_lineas_center = libro.add_format({'border':1, 'font_size':9, 'align': 'center', 'valign': 'center',})
        formato_lineas_right = libro.add_format({'border':1, 'font_size':9, 'align': 'right', 'valign': 'right',})
        formato_fecha = libro.add_format({'num_format': 'dd/mm/yy', 'border':1, 'font_size':9, 'align': 'center', 'valign': 'center',})

        for linea in datos['lineas']:
            y += 1
            hoja.write(y, 0, linea['rtn_proveedor'], formato_lineas_left)
            hoja.write(y, 1, linea['proveedor'], formato_lineas_left)
            hoja.write(y, 2, linea['fecha'], formato_fecha)
            hoja.write(y, 3, linea['cai'], formato_lineas_left)
            hoja.write(y, 4, linea['establecimiento'], formato_lineas_left)
            hoja.write(y, 5, linea['punto_emision'], formato_lineas_left)
            hoja.write(y, 6, linea['tipo_documento'], formato_lineas_left)
            hoja.write(y, 7, linea['correlativo'], formato_lineas_left)
            hoja.write(y, 8, linea['compra_con_oce'], formato_lineas_center)
            hoja.write(y, 9, linea['numero_resolucion'], formato_lineas_left)
            hoja.write(y, 10, linea['fecha_resolucion'], formato_fecha)
            hoja.write(y, 11, linea['compra_exento'], formato_lineas_right)
            hoja.write(y, 12, linea['base'], formato_lineas_right)
            hoja.write(y, 13, '', formato_lineas_left)
            hoja.write(y, 14, linea['iva'], formato_lineas_right)
            hoja.write(y, 15, '', formato_lineas_left)

        libro.close()
        datos = base64.b64encode(f.getvalue())
        self.write({'archivo':datos, 'name':'detalle_compras_locales.xlsx'})

    def otros_comprobantes_compra(self, datos):
        f = io.BytesIO()
        libro = xlsxwriter.Workbook(f)
        hoja = libro.add_worksheet('Reporte')
        formato_encabezado = libro.add_format({'border':2, 'font_size':9, 'align': 'center', 'valign': 'center', 'bold': True, 'bg_color': '#CCCCCC', 'font_color': '#000000'})

        hoja.merge_range('A1:C1', "", formato_encabezado)
        hoja.write(0, 0, 'DETALLE OTROS COMPROBANTES DE COMPRAS', formato_encabezado)
        hoja.merge_range('F2:H2', "", formato_encabezado)
        hoja.write(1, 5, 'ORDENES DE COMPRA EXENTA (OCE)', formato_encabezado)
        hoja.merge_range('I2:K2', "", formato_encabezado)
        hoja.write(1, 8, 'SUB TOTAL DE COMPRAS', formato_encabezado)
        hoja.merge_range('L2:M2', "", formato_encabezado)
        hoja.write(1, 11, 'CRÉDITO FISCAL', formato_encabezado)
        y = 2
        hoja.set_column('A:A', 20)
        hoja.write(y, 0, 'TIPO DE DOCUMENTO', formato_encabezado)
        hoja.set_column('B:B', 20)
        hoja.write(y, 1, 'FECHA DD/MM/AAAA', formato_encabezado)
        hoja.set_column('C:C', 20)
        hoja.write(y, 2, 'R.T.N. PROVEEDOR', formato_encabezado)
        hoja.set_column('D:D', 35)
        hoja.write(y, 3, 'NOMBRES APELLIDOS O RAZÓN SOCIAL', formato_encabezado)
        hoja.set_column('E:E', 35)
        hoja.write(y, 4, 'NÚMERO DE DOCUMENTO EQUIVALENTE', formato_encabezado)
        hoja.set_column('F:F', 20)
        hoja.write(y, 5, 'COMPRA CON OCE', formato_encabezado)
        hoja.set_column('G:G', 20)
        hoja.write(y, 6, 'No. RESOLUCIÓN', formato_encabezado)
        hoja.set_column('H:H', 25)
        hoja.write(y, 7, 'FECHA DE LA RESOLUCIÓN', formato_encabezado)
        hoja.set_column('I:I', 20)
        hoja.write(y, 8, 'IMPORTE EXENTO', formato_encabezado)
        hoja.set_column('J:J', 25)
        hoja.write(y, 9, 'IMPORTE GRAVADO 15%', formato_encabezado)
        hoja.set_column('K:K', 25)
        hoja.write(y, 10, 'IMPORTE GRAVADO 18%', formato_encabezado)
        hoja.set_column('L:L', 20)
        hoja.write(y, 11, 'IMPUESTO 15%', formato_encabezado)
        hoja.set_column('M:M', 20)
        hoja.write(y, 12, 'IMPUESTO 18%', formato_encabezado)

        formato_lineas_left = libro.add_format({'border':1, 'font_size':9, 'align': 'left', 'valign': 'left',})
        formato_lineas_center = libro.add_format({'border':1, 'font_size':9, 'align': 'center', 'valign': 'center',})
        formato_lineas_right = libro.add_format({'border':1, 'font_size':9, 'align': 'right', 'valign': 'right',})
        formato_fecha = libro.add_format({'num_format': 'dd/mm/yy', 'border':1, 'font_size':9, 'align': 'center', 'valign': 'center',})

        for linea in datos['lineas']:
            y += 1
            hoja.write(y, 0, linea['tipo_documento_diario'], formato_lineas_center)
            hoja.write(y, 1, linea['fecha'], formato_fecha)
            hoja.write(y, 2, linea['rtn_proveedor'], formato_lineas_left)
            hoja.write(y, 3, linea['proveedor'], formato_lineas_left)
            hoja.write(y, 4, linea['numero'], formato_lineas_left)
            hoja.write(y, 5, linea['compra_con_oce'], formato_lineas_center)
            hoja.write(y, 6, linea['numero_resolucion'], formato_lineas_left)
            hoja.write(y, 7, linea['fecha_resolucion'], formato_fecha)
            hoja.write(y, 8, linea['compra_exento'], formato_lineas_right)
            hoja.write(y, 9, linea['base'], formato_lineas_right)
            hoja.write(y, 10, '', formato_lineas_right)
            hoja.write(y, 11, linea['iva'], formato_lineas_right)
            hoja.write(y, 12, '', formato_lineas_right)


        libro.close()
        datos = base64.b64encode(f.getvalue())
        self.write({'archivo':datos, 'name':'otros_comprobantes_compras.xlsx'})


    def detalle_importaciones(self, datos):
        f = io.BytesIO()
        libro = xlsxwriter.Workbook(f)
        hoja = libro.add_worksheet('Reporte')
        formato_encabezado = libro.add_format({'border':2, 'font_size':9, 'align': 'center', 'valign': 'center', 'bold': True, 'bg_color': '#CCCCCC', 'font_color': '#000000'})

        hoja.merge_range('A1:C1', "", formato_encabezado)
        hoja.write(0, 0, 'DETALLE IMPORTACIONES', formato_encabezado)
        y = 2
        hoja.set_column('A:A', 35)
        hoja.write(y, 0, 'IDENTIFICADOR TRIBUTARIO DEL PROVEEDOR', formato_encabezado)
        hoja.set_column('B:B', 43)
        hoja.write(y, 1, 'NOMBRES APELLIDOS O RAZÓN SOCIAL DEL PROVEEDOR', formato_encabezado)
        hoja.set_column('C:C', 20)
        hoja.write(y, 2, 'NÚMERO DE LA DUA', formato_encabezado)
        hoja.set_column('D:D', 25)
        hoja.write(y, 3, 'NÚMERO DE LA LIQUIDACIÓN', formato_encabezado)
        hoja.set_column('E:E', 42)
        hoja.write(y, 4, 'NÚMERO DE LA RESOLUCIÓN DE EXONERACIÓN (SEFIN)', formato_encabezado)
        hoja.set_column('F:F', 47)
        hoja.write(y, 5, 'FECHA DE VENCIMIENTO DE LA RESOLUCIÓN DD/MM/AAAA', formato_encabezado)

        formato_lineas_left = libro.add_format({'border':1, 'font_size':9, 'align': 'left', 'valign': 'left',})
        formato_lineas_center = libro.add_format({'border':1, 'font_size':9, 'align': 'center', 'valign': 'center',})
        formato_lineas_right = libro.add_format({'border':1, 'font_size':9, 'align': 'right', 'valign': 'right',})
        formato_fecha = libro.add_format({'num_format': 'dd/mm/yy', 'border':1, 'font_size':9, 'align': 'center', 'valign': 'center',})

        for linea in datos['lineas']:
            y += 1
            hoja.write(y, 0, linea['rtn_proveedor'], formato_lineas_left)
            hoja.write(y, 1, linea['proveedor'], formato_lineas_left)
            hoja.write(y, 2, linea['numero_dua'], formato_lineas_left)
            hoja.write(y, 3, linea['numero_liquidacion'], formato_lineas_left)
            hoja.write(y, 4, linea['numero_resolucion_exoneracion'], formato_lineas_left)
            hoja.write(y, 5, linea['fecha_vencimiento_resolucion'], formato_fecha)

        libro.close()
        datos = base64.b64encode(f.getvalue())
        self.write({'archivo':datos, 'name':'detalle_importaciones.xlsx'})


    def print_report_excel(self):
        datos = self.lineas()
        if self.tipo_reporte == 'detalle_compras':
            self.detalle_compras(datos)
        elif self.tipo_reporte == 'otros_comprobantes_compra':
            self.otros_comprobantes_compra(datos)
        elif self.tipo_reporte == 'detalle_importaciones':
            self.detalle_importaciones(datos)

        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_hn_extra.asistente_reporte_compras_hn',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
