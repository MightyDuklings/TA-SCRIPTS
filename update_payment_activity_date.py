#! /usr/bin/env python
from __future__ import unicode_literals

import csv
from datetime import datetime

from django.db import transaction

from ecgps_core.models.payment_configs import Payment, Invoice, User
from ecgps_core.utils.xlsx_to_csv import xlsx_to_csv
from gpmodels.utils import AgencyContext


def mkdate(datestring):
    return datetime.strptime(datestring, '%Y-%b-%d').date()

def update_activity_date(payment, activity_date, ticket):
    un_status = ['released', 'credited']
    if payment.status in un_status:
        raise ValueError(
            'the payment is in the {0} state'.format(payment.status)
        )
    print(
        'payment updated {0}, activity completion date from {1} => {2}'.format(
            payment.gpid, payment.activity_completion_date, activity_date
        )
    )
    payment.activity_completion_date = activity_date
    payment.add_gp_note(ticket)
    payment.save()
    return payment.clinic_detail_study, payment.invoice_number

def update_invoice(cds, invoice_number, ticket, commit):
    from ecgps_core.services.invoice_services import resubmit_payments
    inv = Invoice.objects.get(
        invoice_number=invoice_number,
        clinic_detail_study=cds
    )
    inv_original = inv.invoice_status
    inv.invoice_status = 'unsubmitted'
    inv.save()
    invoice = resubmit_payments(inv, inv.payments)
    invoice.invoice_status = inv_original
    if commit:
        invoice.create_new_invoice_pdf(notify=False)
    print('invoice {0} updated'.format(invoice_number))
    invoice.add_gp_note(ticket)
    invoice.save()

def main(args):
    ticket = args.ticket
    commit = args.commit
    protocol = args.protocol
    if args.file_path:
        from selfserve.tasks.common import parse_csv_data
        file_path = args.file_path
        csv_files = xlsx_to_csv(file_path)
        my_sheet = dict(csv_files)
        data = parse_csv_data(my_sheet)
        list_of_rows = data['Sheet1']
        receipt_data = []
        for row in list_of_rows:
                gpid = row['gpid']
                activity_date = mkdate(row['payment_activity_date'])
                protocol = row['protocol']

                receipt_dict = {
                    'gpid': gpid,
                    'new_activity_date': activity_date,
                    'protocol': protocol,
                    'status':'success',
                    'message':' '
                }
                try:
                    payment = Payment.objects.get(
                        study__protocol=protocol,
                        id__istartswith=gpid
                    )
                    original_activity_date = payment.activity_completion_date
                    receipt_dict[
                        'original_activity_date'
                    ] = original_activity_date
                except Payment.DoesNotExist:
                    receipt_dict['message'] = 'Payment not found.'
                    receipt_dict['status'] = 'failed'
                    receipt_data.append(receipt_dict)
                    continue
                cds, invoice_number = update_activity_date(
                    payment, activity_date, ticket
                )

                if invoice_number and args.force_update:
                    update_invoice(cds, invoice_number, ticket, commit)
                    receipt_dict['message'] = 'Updated invoice {0}'.format(
                    invoice_number)
                elif invoice_number:
                    print(
                        'Payment is invoiced.'
                        ' The invoice number is {0}.'
                        'To update the payment and'
                        'invoice include --force_update'
                        .format(invoice_number)
                    )
                    assert False
                receipt_data.append(receipt_dict)
        path = '/tmp/activity_date_change_{0}.csv'.format(
            datetime.now()
        )
        with open(path, 'w') as file_object:
            list_of_keys = [
                'protocol',
                'gpid',
                'new_activity_date',
                'original_activity_date',
                'status',
                'message'
            ]
            receipt = csv.DictWriter(file_object,list_of_keys)
            receipt.writeheader()
            receipt.writerows(receipt_data)
            print('file located at {0}'.format(path))
    else:
        gpid = args.gpid
        activity_date = args.activity_date
        try:
            payment = Payment.objects.get(
                study__protocol=protocol,
                id__istartswith=gpid
            )
        except Payment.DoesNotExist:
            print('Payment {0} does not exist'.format(payment))
            return
        cds, invoice_number = update_activity_date(
            payment, activity_date, ticket
        )
        if invoice_number and args.force_update:
           update_invoice(cds, invoice_number, ticket, commit)
        elif invoice_number:
            print(
                'Payment is invoiced. The invoice number is {0}. To update '
                'both the payment and invoice include --force_update'.format(
                    invoice_number
                )
            )
            assert False

if __name__ == '__main__':
    import argparse
    from django import setup
    setup()
    parser = argparse.ArgumentParser(
        description=('Update the payment activity date as long as the payment'
                     'is not in released state')
    )
    group = parser.add_mutually_exclusive_group()
    parser.add_argument(
        '--commit',
        default=False,
        action='store_true',
        help='Commit script changes to DB'
    )
    group.add_argument(
        '--gpid',
        help='enter the gpid on the ticket',
    )
    parser.add_argument(
        '--activity_date',
        type=mkdate,
        help='enter the desired updated date for the activity completion'
               'date the input format expected is "YYYY-MM-DD"',
    )
    parser.add_argument(
        '--ticket', help='ticket number', required=True
    )
    parser.add_argument(
        '--force_update',
        help='By running this script you are updating a invoice',
        action='store_true',
     )
    parser.add_argument(
        '--user',
        help='Enter email of user so we know who made changes to the db',
        required=True
    )
    group.add_argument(
        '--file_path',
        help='enter the path to the template'
    )
    parser.add_argument(
        '--protocol',
        help='enter the protocol for the payment object',
    )
    args = parser.parse_args()
    owner = User.objects.get(email=args.user)
    with transaction.atomic(), AgencyContext.agent_context(owner):
        main(args)
        if not args.commit:
            raise ValueError('Dry Run. Changes not committed')

