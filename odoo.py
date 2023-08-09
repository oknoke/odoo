import xmlrpc.client
from flask import Flask, request, jsonify, Response
from cachetools import TTLCache
import csv
import io
import pandas as pd
import requests
import json

URL = "https://xetechs-operadores-nacionales.odoo.com/"
db = "xetechs-operadoresnacionales-main-5656083"
username = 'elopez@operadoresn.com'
password = '972a5ea84fff27b49b2eeb7aea981398e7c0d50c'

app = Flask(__name__)

# Configurar un caché con una duración de 5 minutos (ajusta según tus necesidades)
cache = TTLCache(maxsize=100, ttl=300)

# Lista para almacenar los registros
registros = []

@app.route('/api/credit_notes', methods=['GET'])
def get_credit_notes():
    global registros
    
    try:
        # Verificar si los registros ya están en caché
        if not registros:
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL))
            uid = common.authenticate(db, username, password, {})
            
            if uid:
                models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL))

                campos_credit_notes = ["name",
                                       "partner_id",
                                       "invoice_user_id", 
                                       "invoice_date" ,
                                       "invoice_date_due",
                                       "amount_untaxed",
                                       "amount_total", 
                                       "amount_total_in_currency_signed"]

                # Obtener todos los pedidos de venta y sus campos requeridos
                order_domain = [('partner_id', '!=', False)]
                orders = models.execute_kw(db, uid, password, 'sale.order', 'search_read', [order_domain], {'fields': ['partner_id']})
                
                # Obtener los IDs de los contactos (res.partner) usando el partner_id de los pedidos
                partner_ids = [order['partner_id'][0] for order in orders if order.get('partner_id')]
                
                # Obtener la información del país de los contactos
                partner_country_info = models.execute_kw(db, uid, password, 'res.partner', 'read', [partner_ids], {'fields': ['country_id']})
                
                # Mapear el country_id a los IDs de los contactos
                contactos_country = {partner['id']: partner.get('country_id')[0] for partner in partner_country_info if partner.get('country_id')}
                
                # Obtener todas las notas de crédito relacionadas a los pedidos y sus campos requeridos
                domain = [('move_type', '=', 'out_refund'), ('partner_id', 'in', partner_ids)]
                registros = models.execute_kw(db, uid, password, 'account.move', 'search_read', [domain], {'fields': campos_credit_notes})
                
                # Agregar la información de país y country_id a los registros
                for registro in registros:
                    partner_id = registro.get('partner_id')
                    if partner_id:
                        country_id = contactos_country.get(partner_id[0])
                        if country_id:
                            country = models.execute_kw(db, uid, password, 'res.country', 'read', [country_id], {'fields': ['name']})
                            if country:
                                registro['pais'] = country[0].get('name')
                                registro['pais_id'] = country_id
                
                # Ordenar los registros por el campo 'pais'
                registros.sort(key=lambda x: x.get('pais'))
                
                cache['credit_notes'] = registros
            
            else:
                return jsonify({"error": "Autenticación fallida"}), 401
        
        # Convertir registros a formato pandas DataFrame
        df = pd.DataFrame(registros)
        
        # Si se solicita un archivo CSV, devolverlo
        if request.args.get('format') == 'csv':
            csv_output = io.StringIO()
            df.to_csv(csv_output, index=False)
            csv_content = csv_output.getvalue()
            return Response(csv_content, content_type='text/csv', headers={'Content-Disposition': 'attachment; filename=credit_notes.csv'})
        
        # Si se solicita un archivo JSON, devolverlo
        return df.to_json(orient='records')
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Ruta para llamar a la API y guardar los datos en la lista de registros
@app.route('/api/save_credit_notes', methods=['GET'])
def save_credit_notes():
    global registros
    
    try:
        # Realizar una solicitud GET a la API
        response = requests.get('http://localhost:8000/api/credit_notes')
        
        # Verificar si la solicitud fue exitosa
        if response.status_code == 200:
            try:
                # Convertir la respuesta en JSON
                data = response.json()
                
                # Agregar nuevos registros a la lista
                registros.extend(data)
                
                return 'Datos guardados exitosamente en registros'
            except json.JSONDecodeError as e:
                return 'Error al decodificar la respuesta JSON:', str(e)
        else:
            return 'Error al realizar la solicitud a la API. Código de estado:', response.status_code
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(port=8000, debug=True)
