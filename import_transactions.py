import csv, sys, argparse

from tinydb import TinyDB, Query
from fuzzywuzzy import process
from dateutil.parser import parse

def get_verified_response(prompt, valid_responses):
    while True:
        response = input(prompt)
        if response not in valid_responses:
            print("Invalid input. Try again.")
        else:
            return response

def import_transactions(csv_filename, db_filename, this_account, match_threshold=60):
    """
    Imports data from CSV file into database table.
    """
    with open(csv_filename, newline='') as csv_file:
        csv_has_header = csv.Sniffer().has_header(csv_file.read(1024))
        assert csv_has_header, "No header line found in CSV"
        csv_file.seek(0)

        csv_reader = csv.reader(csv_file)
        header = next(csv_reader, None)

        for i in range(len(header)):
            print(i, ":", header[i])

        columns = {}
        columns['date'] = int(input("Which entry contains the transaction date? "))
        columns['desc'] = int(input("Which entry contains the description? "))
        columns['debit'] = int(input("Which entry contains the debit amount? "))
        columns['credit'] = int(input("Which entry contains the credit amount? "))

        combined_debit_credit = columns['debit'] == columns['credit']

        source_db = TinyDB(db_filename, sort_keys=True, indent=4, separators=(',', ': '))

        imports = source_db.table('imports')

        payees = {}
        for row in source_db:
            description = row['description']
            if description not in payees:
                payees[description] = row['payee']

        for row in csv_reader:
            #print(row)

            if combined_debit_credit:
                print("\n" + " || ".join(row[i] for i in [columns['date'],
                                                             columns['desc'],
                                                             columns['debit']]))
            else:
                print("\n" + " || ".join(row[i] for i in [columns['date'],
                                                             columns['desc'],
                                                             columns['debit'],
                                                             columns['credit']]))

            # TODO: make this an assert?
            if not combined_debit_credit and row[columns['debit']] and row[columns['credit']]:
                raise RuntimeError("Entry has both debit and credit")

            transaction = dict()
            transaction['source_file'] = csv_filename
            transaction['reviewed'] = False
            transaction['date'] = parse(row[columns['date']]).strftime("%Y-%m-%d")

            description = row[columns['desc']]
            transaction['description'] = description

            this_account_amount = "$"
            if combined_debit_credit:
                if row[columns['debit']][0] == "-":
                    # "-" with combined debit/credit implies credit, i.e.
                    # positive amount for this_account
                    this_account_amount += row[columns['debit']][1:]
                else:
                    # lack of "-" for combined debit/credit implies debit,
                    # i.e.  negative amount from this_account
                    this_account_amount += "-" + row[columns['debit']]

            elif row[columns['debit']]:
                if row[columns['debit']][0] != "-":
                    this_account_amount += "-"
                this_account_amount += row[columns['debit']]

            else:
                this_account_amount += row[columns['credit']]

            account_info = {'account': this_account,
                            'amount': this_account_amount}

            transaction['accounts'] = [account_info]

            # check to see if this entry has already been imported
            Transaction = Query()
            already_imported = imports.contains((Transaction.source_file == transaction['source_file'])
                               & (Transaction.date == transaction['date'])
                               & (Transaction.description == transaction['description'])
                               & (Transaction.accounts.any(Query().amount == this_account_amount)))


            if already_imported:
                skip = get_verified_response("Duplicate import detected. Skip entry? (y/n) ",
                                             ['y', 'n'])
                if skip == 'y':
                    continue

            # Look for descriptions that match (or are close) to this one so
            # we can get some payee suggestions
            close_matches = [name for name, score in process.extract(description,
                                                                     payees.keys())
                             if score >= match_threshold]

            close_payees = []
            for desc in close_matches:
                p = payees[desc]
                if p not in close_payees:
                    close_payees.append(p)

            if len(close_payees) == 0:
                # no close matches
                print("No close matches found for:", description)
                payee = input("Enter Payee Name: ")

            else:
                # print out each close match and ask user to select
                print("\nClose Matches: (Select one)")
                for i, p in enumerate(close_payees):
                    print(i+1, ":", p)

                print("0 : Other...")

                # TODO: Validate input
                selection = int(get_verified_response("\nEnter your selection: ",
                                                       [str(i) for i in range(len(close_payees)+1)]))
                if selection == 0:
                    payee = input("Enter Payee Name: ")
                else:
                    payee = close_payees[selection - 1]

            transaction['payee'] = payee

            # associate this payee with the description to improve matching on
            # future imports from this file
            if description not in payees:
                payees[description] = payee

            imports.insert(transaction)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db_file", help="TinyDB database with transactions.")
    parser.add_argument("csv_file", help="CSV file with financial transactions.")
    parser.add_argument("--account", help="Account associated with transactions.")
    """
    parser.add_argument("--startdate", type=parse,
                        help="All entries BEFORE this datw will be ignored")
    parser.add_argument("--enddate", type=parse,
                        help="All entries AFTER this datw will be ignored")
    """
    args = parser.parse_args()

    if args.account:
        this_account = args.account
    else:
        this_account = input("Enter the CSV file's account name: ")

    import_transactions(args.csv_file, args.db_file, this_account)
