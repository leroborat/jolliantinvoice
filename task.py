
from math import degrees
import erppeek

from RPA.Database import Database


company_oid = '0da5cd6a-3719-48c0-a676-a7bc25ac7234'

# MYSQL Settings
mysql_database_name = "jolliantreopened"
mysql_username = "root"
mysql_password = ""
mysql_host = "localhost"

# odoo settings
odoo_server = 'https://ibassoftware-integreationtest-test-4508963.dev.odoo.com/'
odoo_database = 'ibassoftware-integreationtest-test-4508963'
odoo_username = "admin"
odoo_password = "123"
odoo_account_receivable_id = 6
odoo_account_payable_id = 14
odoo_company_id = 1
odoo_currency_id = 2
odoo_income_id = 21
odoo_tax_id = 16


# Global Variables
client = ''
db = ''


def main():
    # Initialize odoo
    global client
    client = erppeek.Client(
        server=odoo_server,
        db=odoo_database,
        user=odoo_username,
        password=odoo_password
    )
    # Get All Invoices From MYSQL Database for company
    invoices = get_all_invoices_from_mysql(company_oid)
    # For each Invoice
    for invoice in invoices:
        print('Creating odoo Invoice for ' + str(invoice['InvoiceNumber']))
        # Check if Customer is in Odoo / Get ID  If not in Odoo, create customer and return ID
        odoo_customer_id = get_odoo_customer_id(client, invoice)
        new_odoo_invoice_id = create_invoice_in_odoo(invoice, odoo_customer_id)
        create_invoice_lines_in_odoo(
            invoice, new_odoo_invoice_id, odoo_customer_id)

        # update ibas invoice record with odoo invoice
        sql = "UPDATE invoice SET OdooDatabaseID = " + \
            str(new_odoo_invoice_id) + " WHERE Oid = '" + invoice['Oid'] + "'"
        db.query(sql)

        print('Finished with odoo Invoice ID ' + str(new_odoo_invoice_id))


def get_odoo_analytic_id(analytic_oid):

    analytic_name = ""
    if analytic_oid is None:
        analytic_name = "NEEDS ATTENTION"
    else:
        analytic_res = db.query(
            "select * from suppliercode where Oid = '" + analytic_oid + "'")
        if analytic_res is None:
            analytic_name = "NEEDS ATTENTION"
        else:
            for x in analytic_res:
                analytic_name = x['SuppCode']

    res = client.count(
        'account.analytic.account', [('name', '=', analytic_name)])

    analytic_odoo_id = 0
    if res == 0:
        print(analytic_name + " not found. Creating Analytics in odoo...")
        analytic_odoo_id = create_analytic_in_odoo(analytic_name)
        print("Analytic odoo ID: " + str(analytic_odoo_id))

    analytic_odoo_id = client.search(
        'account.analytic.account', [('name', '=', analytic_name)])[0]

    return analytic_odoo_id


def create_analytic_in_odoo(analytic_name):
    params = {
        'name': analytic_name,
    }
    odoo_id = client.create('account.analytic.account', params)

    return odoo_id


def create_invoice_lines_in_odoo(ibas_invoice_record, odoo_invoice_id, odoo_customer_id):
    ibas_invoice_oid = ibas_invoice_record["Oid"]

    # Get Analytic Account
    analytic_id = get_odoo_analytic_id(ibas_invoice_record["SuppCode"])

    # Get Invoice Lines
    ibas_invoice_lines = db.query(
        "select * from invoiceline where Invoice = '" + ibas_invoice_oid + "'")

    for line in ibas_invoice_lines:
        # For each line,
        # Create line

        product_oid = line['Product']

        product_name = get_ibas_product_name(product_oid)
        odoo_product_id = get_odoo_product_id(product_name)
        paramsarray = []

        total_credit = float(line['UnitPrice']) * float(line['Quantity'])

        params = (0, 0, {
            "product_id": odoo_product_id,
            "name": product_name,
            "price_unit": float(line['UnitPrice']),
            "quantity": float(line['Quantity']),
            "currency_id": odoo_currency_id,
            "account_id": odoo_income_id,
            "credit": total_credit,
            "partner_id": odoo_customer_id,
            'analytic_account_id': analytic_id
        })

        paramsarray.append(params)

        updated_record = {
            'invoice_line_ids': paramsarray
        }

        # Update Invoice

        client.write('account.move', [odoo_invoice_id], updated_record)

    paramsarray = []
    # VAT
    params = (0, 0, {
        'account_id': odoo_tax_id,
        'credit': float(ibas_invoice_record['VAT']),
        'exclude_from_invoice_tab': True,
        "partner_id": odoo_customer_id,
    })

    paramsarray.append(params)

    params = (0, 0, {
        'account_id': odoo_income_id,
        'debit': float(ibas_invoice_record['VAT']),
        'exclude_from_invoice_tab': True,
        "partner_id": odoo_customer_id,
    })

    paramsarray.append(params)

    # DA

    params = (0, 0, {
        "name": "Distribution Allowance",
        "price_unit": float(ibas_invoice_record['DistributionAllowance']) * -1,
        "quantity": 1,
        "currency_id": odoo_currency_id,
        "account_id": odoo_income_id,
        "credit": float(ibas_invoice_record['DistributionAllowance']) * -1,
        "partner_id": odoo_customer_id,
    })

    paramsarray.append(params)

    updated_record = {
        'invoice_line_ids': paramsarray
    }

    client.write('account.move', [odoo_invoice_id], updated_record)

    return


def get_odoo_product_id(product_name):
    # check if product is in odoo, create if not, return ID

    res = client.count(
        'product.product', [('name', '=', product_name)])
    product_odoo_id = 0
    if res == 0:
        print(product_name + " not found. Creating customer in odoo...")
        create_product_in_odoo(product_name)
        print("Product odoo ID: " + str(product_odoo_id))

    product_odoo_id = client.search(
        'product.product', [('name', '=', product_name)])[0]

    return product_odoo_id


def get_ibas_product_name(product_oid):
    products_res = db.query(
        "select * from product where Oid = '" + product_oid + "'")
    if products_res is None:
        return "PRODUCT IS NO LONGER IN IBAS"
    else:
        for x in products_res:
            return x['ProductName']


def create_invoice_in_odoo(invoice, customer_id):

    # Get Required Invoice parameters

    due_date = invoice["DueDate"]

    if due_date is None:
        due_date = invoice["InvoiceDate"].date()
    else:
        due_date = invoice["DueDate"].date()

    invobj = {
        "move_type": "out_invoice",
        "partner_id": customer_id,
        "invoice_date": str(invoice["InvoiceDate"].date()),
        "company_id": odoo_company_id,
        "move_name": invoice["InvoiceNumber"],
        "invoice_date_due": str(due_date)
    }

    new_odoo_invoice_id = client.create("account.move", invobj)
    return new_odoo_invoice_id


def get_odoo_customer_id(client, invoice):
    # Is Customer Record Valid, if not, Partner equals = "Needs Attention"
    customer_oid = invoice['Customer']
    odoo_partner_name = ''
    if customer_oid is None:
        odoo_partner_name = "ATTENTION - PLEASE FILL THIS IN"
    else:
        # Get Customer Name From My SQL
        odoo_partner_name = get_customer_name_from_mysql(customer_oid)

    customer_odoo_id = get_customer_odoo_id_from_odoo(odoo_partner_name)

    return customer_odoo_id


def get_customer_odoo_id_from_odoo(odoo_partner_name):
    # Is Customer in odoo? if not create customer in odoo
    res = client.count(
        'res.partner', [('name', '=', odoo_partner_name)])
    customer_odoo_id = 0
    if res == 0:
        print(odoo_partner_name + " not found. Creating customer in odoo...")
        customer_odoo_id = create_customer_in_odoo(odoo_partner_name)
        print("Customer odoo ID: " + str(customer_odoo_id))
    else:
        customer_odoo_id = client.search(
            'res.partner', [('name', '=', odoo_partner_name)])[0]
        print(odoo_partner_name + " found with odoo ID of " +
              str(customer_odoo_id) + ". Proceeding...")

    return customer_odoo_id


def create_product_in_odoo(product_name):
    params = {
        'name': product_name,
        'type': 'product',
        'categ_id': 1
    }
    odoo_id = client.create('product.product', params)

    return odoo_id


def create_customer_in_odoo(odoo_partner_name):
    params = {
        'company_type': 'company',
        'name': odoo_partner_name,
        'property_account_receivable_id': odoo_account_receivable_id,
        'property_account_payable_id': odoo_account_receivable_id,
    }

    odoo_id = client.create('res.partner', params)
    return odoo_id


def get_all_invoices_from_mysql(company_oid):
    global db
    db = Database()
    db.connect_to_database('pymysql', mysql_database_name,
                           mysql_username, mysql_password, mysql_host)
    invoices = db.query(
        "select * from invoice where OdooDatabaseID IS NULL AND InvoiceDate > '2021-01-01' AND Status = 1 AND Company = '" + company_oid + "'" +
        " OR OdooDatabaseID = 0 AND InvoiceDate > '2021-01-01' AND Status = 1 AND Company = '" + company_oid + "'")

    return invoices


def get_customer_name_from_mysql(customer_oid):
    customer_res = db.query(
        "select * from customer where Oid='" + customer_oid + "'")
    for x in customer_res:
        return x["CustomerName"]


def minimal_task():

    try:
        client = erppeek.Client(
            server='https://ibassoftware-integreationtest-demorpa-4522323.dev.odoo.com/',
            db='ibassoftware-integreationtest-demorpa-4522323',
            user='admin',
            password='123'
        )
    except Exception as e:
        print(str(e))
        exit()

    invobj = {
        "move_type": "out_invoice",
        "partner_id": 10,
        "invoice_date": '2022-03-24',
        "company_id": 1,
        # "journal_id": 1,
        # "line_ids": paramsarray,
        "invoice_date_due": '2022-03-24'
    }

    new_odoo_invoice_id = client.create("account.move", invobj)

    paramsarray = []

    params = (0, 0, {
        "product_id": 23,
        "name": 'Test Description',
        "price_unit": 50,
        "quantity": 10,
        "currency_id": 2,
        "account_id": 21,
        "credit": 50,
        "partner_id": 10,
    })

    paramsarray.append(params)

    updated_record = {
        'invoice_line_ids': paramsarray
    }

    client.write('account.move', [new_odoo_invoice_id], updated_record)

    print("Done.")


if __name__ == "__main__":
    main()
